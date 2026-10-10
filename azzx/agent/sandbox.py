"""Sandboxed command execution for AZZX (v10.5).

Two backends:
- ``local``  — subprocess confined to a working directory, with timeout,
  output caps, secret-scrubbed environment and (on POSIX) RLIMIT_CPU /
  RLIMIT_AS guards. No network isolation on this backend: use ``docker``
  when you need it.
- ``docker`` — ``docker run --rm`` with an isolated network namespace
  (``--network none`` unless ``allow_network``), the working directory
  mounted at ``/work``. Requires the docker CLI on PATH.

Honest limits: ``local`` cannot block network access or syscalls; it is a
*containment* helper (cwd jail + timeout + resource caps + secret scrubbing),
not a security boundary. Treat ``docker`` as the real isolation backend.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_SECRET_ENV_RE = re.compile(r"(API_KEY|APIKEY|TOKEN|SECRET|PASSWORD|PASSWD|PRIVATE_KEY|CREDENTIAL)", re.IGNORECASE)

DEFAULT_TIMEOUT = 60
MAX_OUTPUT_CHARS = 200_000


@dataclass
class SandboxResult:
    ok: bool
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool
    backend: str
    duration_ms: int
    workdir: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "timed_out": self.timed_out,
            "backend": self.backend,
            "duration_ms": self.duration_ms,
            "workdir": self.workdir,
        }


def _scrub_env() -> dict[str, str]:
    """Copy the environment minus secret-looking variables."""
    return {k: v for k, v in os.environ.items() if not _SECRET_ENV_RE.search(k)}


def _posix_limits(timeout: int):
    try:
        import resource

        def _apply():
            try:
                resource.setrlimit(resource.RLIMIT_CPU, (timeout + 10, timeout + 10))
            except Exception:
                pass
            try:
                # 512 MiB address-space cap
                mem = 512 * 1024 * 1024
                resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
            except Exception:
                pass

        return _apply
    except Exception:
        return None


class SandboxExecutor:
    """Run shell commands inside a confined working directory."""

    def backends(self) -> list[str]:
        found = ["local"]
        if shutil.which("docker"):
            found.append("docker")
        return found

    def run(
        self,
        command: str,
        workdir: str | None = None,
        timeout: int = DEFAULT_TIMEOUT,
        backend: str = "auto",
        allow_network: bool = False,
        image: str = "alpine:latest",
    ) -> SandboxResult:
        command = (command or "").strip()
        if not command:
            raise ValueError("command must not be empty")
        timeout = max(1, min(int(timeout or DEFAULT_TIMEOUT), 600))

        owned_tmp = False
        if workdir:
            wd = Path(workdir).expanduser().resolve()
            wd.mkdir(parents=True, exist_ok=True)
        else:
            wd = Path(tempfile.mkdtemp(prefix="azzx-sandbox-"))
            owned_tmp = True

        if backend == "auto":
            backend = "docker" if shutil.which("docker") else "local"
        if backend not in ("local", "docker"):
            raise ValueError(f"unknown backend: {backend}")
        if backend == "docker" and not shutil.which("docker"):
            raise ValueError("docker backend requested but docker CLI not found")

        start = time.monotonic()
        try:
            if backend == "docker":
                result = self._run_docker(command, wd, timeout, allow_network, image)
            else:
                result = self._run_local(command, wd, timeout)
        finally:
            if owned_tmp:
                shutil.rmtree(wd, ignore_errors=True)
        duration_ms = int((time.monotonic() - start) * 1000)
        result.duration_ms = duration_ms
        result.backend = backend
        result.workdir = str(wd) if not owned_tmp else "<temp>"
        return result

    # -- backends ------------------------------------------------------
    def _run_local(self, command: str, wd: Path, timeout: int) -> SandboxResult:
        shell = shutil.which("bash") or shutil.which("sh") or "/bin/sh"
        proc = subprocess.Popen(
            [shell, "-c", command],
            cwd=str(wd),
            env=_scrub_env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
            preexec_fn=_posix_limits(timeout),
        )
        timed_out = False
        try:
            out, err = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                import signal
                os.killpg(proc.pid, signal.SIGKILL)
            except Exception:
                proc.kill()
            out, err = proc.communicate()
        return SandboxResult(
            ok=(proc.returncode == 0 and not timed_out),
            exit_code=proc.returncode if proc.returncode is not None else -1,
            stdout=_cap(out or ""),
            stderr=_cap(err or ""),
            timed_out=timed_out,
            backend="local",
            duration_ms=0,
        )

    def _run_docker(
        self, command: str, wd: Path, timeout: int, allow_network: bool, image: str
    ) -> SandboxResult:
        net = [] if allow_network else ["--network", "none"]
        cmd = [
            "docker", "run", "--rm", "-i",
            *net,
            "--memory", "512m",
            "--cpus", "1.0",
            "-v", f"{wd}:/work",
            "-w", "/work",
            image, "sh", "-c", command,
        ]
        timed_out = False
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout,
                env=_scrub_env(),
            )
            out, err, code = proc.stdout, proc.stderr, proc.returncode
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            out = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
            err = (exc.stderr or "") if isinstance(exc.stderr, str) else ""
            code = -1
        except FileNotFoundError as exc:
            raise ValueError(f"docker backend failed: {exc}")
        return SandboxResult(
            ok=(code == 0 and not timed_out),
            exit_code=code,
            stdout=_cap(out or ""),
            stderr=_cap(err or ""),
            timed_out=timed_out,
            backend="docker",
            duration_ms=0,
        )


def _cap(text: str) -> str:
    if len(text) > MAX_OUTPUT_CHARS:
        return text[:MAX_OUTPUT_CHARS] + f"\n…[truncated {len(text) - MAX_OUTPUT_CHARS} chars]"
    return text


_EXECUTOR = SandboxExecutor()


def get_sandbox_executor() -> SandboxExecutor:
    return _EXECUTOR


# -- tool registration -------------------------------------------------
def _tool_sandbox_exec(
    command: str,
    workdir: str = "",
    timeout: int = DEFAULT_TIMEOUT,
    backend: str = "auto",
    allow_network: bool = False,
) -> dict[str, Any]:
    """Tool handler: run a shell command inside the sandbox."""
    result = _EXECUTOR.run(
        command=command,
        workdir=workdir or None,
        timeout=timeout,
        backend=backend,
        allow_network=bool(allow_network),
    )
    return result.to_dict()


def register_sandbox_tools() -> None:
    from azzx.core import REGISTRY, ToolSpec

    REGISTRY.register(ToolSpec(
        name="sandbox.exec",
        description=(
            "Run a shell command inside a sandbox (cwd jail, timeout, output cap, "
            "secret-scrubbed env; 'local' backend or 'docker' for network isolation). "
            "Use for untrusted or generated code instead of the raw shell."
        ),
        permissions=["sandbox.execute"],
        handler=_tool_sandbox_exec,
        schema={
            "command": "str (required)",
            "workdir": "str (optional; temp dir if empty)",
            "timeout": "int seconds (optional, default 60, max 600)",
            "backend": "str 'auto'|'local'|'docker' (optional)",
            "allow_network": "bool (optional; docker backend only)",
        },
    ))
