#!/usr/bin/env python3
from __future__ import annotations

# Ensure package root is on sys.path when executed as a script
import sys as _sys
from pathlib import Path as _Path
_ROOT = _Path(__file__).resolve().parent
if str(_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_ROOT))

import argparse
import ast
import base64
import datetime as dt
import difflib
import getpass
import hashlib
import json
import os
import platform
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import textwrap
import time
import tarfile
import urllib.parse
import uuid
import threading
import queue
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

import httpx
try:
    from cryptography.fernet import Fernet, InvalidToken
except ImportError:  # Optional: keeps Termux install lightweight.
    Fernet = None  # type: ignore[assignment]
    InvalidToken = Exception  # type: ignore[assignment,misc]
from rich import box
from rich.align import Align
from rich.console import Console, Group
from rich.live import Live
from rich.columns import Columns
from rich.rule import Rule
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeElapsedColumn
from rich.table import Table
from rich.text import Text

APP_NAME = "AZZATSSINS LITE AGENT"
APP_SLUG = "azzatssins-lite-agent"
VERSION = "10.0.0"

console = Console(highlight=False)

CONFIG_HOME = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / APP_SLUG
DATA_HOME = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / APP_SLUG
CONFIG_FILE = CONFIG_HOME / "config.json"
PROVIDERS_FILE = CONFIG_HOME / "providers.json"
SECRETS_FILE = CONFIG_HOME / "secrets.enc"
PLAIN_SECRETS_FILE = CONFIG_HOME / "secrets.json"
MASTER_KEY_FILE = CONFIG_HOME / "master.key"

DEFAULT_CONFIG: dict[str, Any] = {
    "version": 1,
    "default_provider": "",
    "provider_priority": [],
    "fallback_enabled": True,
    "mode": "safe",
    "theme": "azzatssins",
    "max_context_chars": 24000,
    "max_files": 8,
    "timeout_seconds": 120,
    "max_debug_iterations": 4,
    "auto_test_after_edit": False,
    "smart_routing": True,
    "role_providers": {"planner": "", "architect": "", "coder": "", "backend": "", "frontend": "", "database": "", "security": "", "qa": "", "reviewer": "", "tester": ""},
    "checkpoint_before_edit": True,
    "research_max_results": 5,
    "research_fetch_sources": 3,
    "context_symbol_boost": True,
    "task_auto_review": True,
    "mcp_protocol": "auto",
    "impact_depth": 2,
    "security_external_tools": False,
    "benchmark_runs": 3,
    "active_skill": "",
    "permissions": {
        "filesystem.write": "allow",
        "shell.run": "ask",
        "package.install": "ask",
        "git.commit": "ask",
        "git.push": "deny",
        "ssh": "ask",
        "database.write": "ask",
        "network.http": "allow",
        "release.publish": "deny",
        "device.adb": "ask",
        "device.mirror": "ask",
        "workflow.run": "ask",
        "plugin.install": "ask",
        "process.inspect": "allow",
        "archive.write": "ask",
        "filesystem.read": "allow"
    },
    "sandbox_keep_failed": True,
    "factory_security_gate": True,
    "factory_regression_gate": True,
    "app_prefer_native": True,
    "app_trusted_recipes_only": True,
    "app_install_output_lines": 10,
}

# Most providers below expose OpenAI-style /chat/completions. Claude and Cohere
# use dedicated adapters. Qwen's shared Singapore endpoint remains useful for
# quick setup, while users can replace it with a workspace-specific endpoint.
PROVIDER_TEMPLATES: dict[str, dict[str, Any]] = {
    "openai": {
        "name": "OpenAI",
        "kind": "openai",
        "base_url": "https://api.openai.com/v1",
        "model": "",
        "requires_key": True,
    },
    "gemini": {
        "name": "Google Gemini",
        "kind": "openai",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "model": "",
        "requires_key": True,
    },
    "claude": {
        "name": "Claude / Anthropic",
        "kind": "anthropic",
        "base_url": "https://api.anthropic.com",
        "model": "",
        "requires_key": True,
    },
    "groq": {
        "name": "Groq",
        "kind": "openai",
        "base_url": "https://api.groq.com/openai/v1",
        "model": "",
        "requires_key": True,
    },
    "qwen": {
        "name": "Qwen / Alibaba Model Studio",
        "kind": "openai",
        "base_url": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        "model": "",
        "requires_key": True,
        "ask_base_url": True,
    },
    "mistral": {
        "name": "Mistral AI",
        "kind": "openai",
        "base_url": "https://api.mistral.ai/v1",
        "model": "",
        "requires_key": True,
    },
    "cohere": {
        "name": "Cohere",
        "kind": "cohere",
        "base_url": "https://api.cohere.com",
        "model": "",
        "requires_key": True,
    },
    "openrouter": {
        "name": "OpenRouter",
        "kind": "openai",
        "base_url": "https://openrouter.ai/api/v1",
        "model": "",
        "requires_key": True,
        "headers": {"HTTP-Referer": "https://local.azzx", "X-Title": APP_NAME},
    },
    "modelscope": {
        "name": "ModelScope",
        "kind": "openai",
        "base_url": "https://api-inference.modelscope.cn/v1",
        "model": "",
        "requires_key": True,
    },
    "aionlabs": {
        "name": "Aion Labs",
        "kind": "openai",
        "base_url": "https://api.aionlabs.ai/v1",
        "model": "",
        "requires_key": True,
    },
    "agnes": {
        "name": "Agnes AI",
        "kind": "openai",
        "base_url": "https://apihub.agnes-ai.com/v1",
        "model": "agnes-3.0-flash",
        "requires_key": True,
    },
    "meta": {
        "name": "Meta / Llama (custom endpoint)",
        "kind": "openai",
        "base_url": "",
        "model": "",
        "requires_key": True,
        "ask_base_url": True,
    },
    "ollama": {
        "name": "Ollama (local)",
        "kind": "openai",
        "base_url": "http://127.0.0.1:11434/v1",
        "model": "",
        "requires_key": False,
    },
    "custom": {
        "name": "Custom OpenAI-compatible API",
        "kind": "openai",
        "base_url": "",
        "model": "",
        "requires_key": True,
        "ask_base_url": True,
        "ask_name": True,
    },
}

IGNORE_DIRS = {
    ".git", ".hg", ".svn", ".azzx", "node_modules", "vendor", "dist", "build",
    ".venv", "venv", "env", ".env", "__pycache__", ".pytest_cache", ".mypy_cache",
    ".next", ".nuxt", "coverage", ".idea", ".vscode", "target", "Pods",
}

TEXT_EXTS = {
    ".py", ".pyi", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".json",
    ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".sh", ".bash", ".zsh",
    ".html", ".htm", ".css", ".scss", ".md", ".txt", ".gs", ".java", ".kt",
    ".go", ".rs", ".php", ".sql", ".xml", ".properties", ".gradle", ".dart",
    ".vue", ".svelte", ".rb", ".pl", ".lua", ".c", ".h", ".cpp", ".hpp",
}

SPECIAL_TEXT_FILES = {
    "Dockerfile", "Makefile", "Procfile", "Gemfile", "Rakefile", "requirements.txt",
    "package.json", "pyproject.toml", "Cargo.toml", "go.mod", ".gitignore", ".env.example",
}

SENSITIVE_EXACT_NAMES = {
    ".env", "credentials.json", "credential.json", "secrets.json", "secret.json",
    "service-account.json", "service_account.json", "id_rsa", "id_ed25519",
}

MAX_FILE_BYTES = 350_000


class AzzxError(Exception):
    pass


class ProviderError(AzzxError):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def now_stamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d_%H%M%S")


def ensure_private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    try:
        path.chmod(0o700)
    except OSError:
        pass


def atomic_write(path: Path, content: str, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)
    if mode is not None:
        try:
            path.chmod(mode)
        except OSError:
            pass


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return json.loads(json.dumps(default))


def save_json(path: Path, data: Any, private: bool = False) -> None:
    atomic_write(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n", 0o600 if private else None)


def setup_homes() -> None:
    ensure_private_dir(CONFIG_HOME)
    ensure_private_dir(DATA_HOME)
    if not CONFIG_FILE.exists():
        save_json(CONFIG_FILE, DEFAULT_CONFIG, private=True)
    if not PROVIDERS_FILE.exists():
        save_json(PROVIDERS_FILE, {}, private=True)


def load_config() -> dict[str, Any]:
    setup_homes()
    cfg = DEFAULT_CONFIG.copy()
    cfg.update(load_json(CONFIG_FILE, {}))
    return cfg


def save_config(cfg: dict[str, Any]) -> None:
    save_json(CONFIG_FILE, cfg, private=True)


def load_providers() -> dict[str, dict[str, Any]]:
    setup_homes()
    data = load_json(PROVIDERS_FILE, {})
    return data if isinstance(data, dict) else {}


def save_providers(providers: dict[str, dict[str, Any]]) -> None:
    save_json(PROVIDERS_FILE, providers, private=True)


class SecretVault:
    """Local API-key store.

    If the optional ``cryptography`` package is available, values are encrypted with
    Fernet and the local key is protected with mode 0600. On lightweight Termux
    installs, AZZX falls back to a mode-0600 JSON secret file so setup does not
    require compiling native crypto packages. Either mode protects against accidental
    project/Git exposure; neither protects against an attacker controlling the same OS
    account.
    """

    def __init__(self) -> None:
        setup_homes()
        self.encrypted = Fernet is not None
        self._fernet = Fernet(self._load_or_create_master_key()) if self.encrypted else None
        # Seamless upgrade path: Termux/light installs may have used the 0600
        # plaintext fallback before cryptography became available.
        if self.encrypted and PLAIN_SECRETS_FILE.exists() and not SECRETS_FILE.exists():
            legacy = load_json(PLAIN_SECRETS_FILE, {})
            if isinstance(legacy, dict) and legacy:
                self._save({str(k): str(v) for k, v in legacy.items()})
            try:
                PLAIN_SECRETS_FILE.unlink()
            except OSError:
                pass

    @property
    def mode(self) -> str:
        return "encrypted (Fernet)" if self.encrypted else "protected file (0600)"

    def _load_or_create_master_key(self) -> bytes:
        if MASTER_KEY_FILE.exists():
            return MASTER_KEY_FILE.read_bytes().strip()
        assert Fernet is not None
        key = Fernet.generate_key()
        MASTER_KEY_FILE.write_bytes(key + b"\n")
        try:
            MASTER_KEY_FILE.chmod(0o600)
        except OSError:
            pass
        return key

    def _load(self) -> dict[str, str]:
        if not self.encrypted:
            if SECRETS_FILE.exists():
                raise AzzxError("Encrypted API-key vault exists but cryptography is unavailable. Install cryptography or rerun the AZZX installer without --no-crypto.")
            data = load_json(PLAIN_SECRETS_FILE, {})
            return data if isinstance(data, dict) else {}
        if not SECRETS_FILE.exists():
            return {}
        raw = SECRETS_FILE.read_bytes()
        if not raw.strip():
            return {}
        try:
            assert self._fernet is not None
            plain = self._fernet.decrypt(raw)
            obj = json.loads(plain.decode("utf-8"))
            return obj if isinstance(obj, dict) else {}
        except (InvalidToken, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise AzzxError("Vault API key tidak dapat dibaca. Jangan hapus master.key secara terpisah.") from exc

    def _save(self, data: dict[str, str]) -> None:
        if not self.encrypted:
            save_json(PLAIN_SECRETS_FILE, data, private=True)
            return
        assert self._fernet is not None
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        encrypted = self._fernet.encrypt(payload)
        SECRETS_FILE.write_bytes(encrypted)
        try:
            SECRETS_FILE.chmod(0o600)
        except OSError:
            pass

    def set(self, secret_id: str, value: str) -> None:
        data = self._load()
        data[secret_id] = value
        self._save(data)

    def get(self, secret_id: str) -> str:
        return self._load().get(secret_id, "")

    def delete(self, secret_id: str) -> None:
        data = self._load()
        if secret_id in data:
            del data[secret_id]
            self._save(data)

    def mask(self, secret_id: str) -> str:
        value = self.get(secret_id)
        if not value:
            return "-"
        if len(value) <= 8:
            return "•" * len(value)
        return value[:4] + "•" * 10 + value[-4:]


def banner(workspace: Path | None = None, compact: bool = False) -> None:
    width = min(console.width, 104)
    if console.width < 64:
        title = Text.assemble(("◈ AZZX", "bold bright_cyan"), (f"  v{VERSION}", "dim"))
        subtitle = Text("AI Agent • App Installer • Dev Factory", style="cyan")
        body = Group(Align.center(title), Align.center(subtitle))
    else:
        mark = Text("AZZX", style="bold bright_cyan")
        mark.append("  //  ", style="dim")
        mark.append(APP_NAME, style="bold white")
        mark.append(f"  v{VERSION}", style="dim")
        line = Text("◆ AGENT ONLINE  •  UNIVERSAL INSTALLER  •  SOFTWARE FACTORY", style="cyan")
        body = Group(Align.center(mark), Align.center(line))
    console.print(Panel(body, width=width, box=box.HEAVY, border_style="bright_cyan", padding=(0, 2)))
    if workspace and not compact:
        console.print(f"[dim]Workspace[/] [bold]{workspace}[/]")


def status_badge(ok: bool, yes: str = "READY", no: str = "NOT SET") -> str:
    return f"[green]● {yes}[/]" if ok else f"[dim]○ {no}[/]"


def normalize_base_url(url: str) -> str:
    return url.strip().rstrip("/")


def headers_for_provider(provider: dict[str, Any], api_key: str) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    headers.update(provider.get("headers") or {})
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def extract_text_content(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts)
    if value is None:
        return ""
    return str(value)


class BaseAdapter:
    def __init__(self, provider: dict[str, Any], api_key: str, timeout: float):
        self.provider = provider
        self.api_key = api_key
        self.base_url = normalize_base_url(provider.get("base_url", ""))
        self.timeout = timeout

    def list_models(self) -> list[str]:
        raise NotImplementedError

    def chat(self, messages: list[dict[str, str]], model: str) -> str:
        raise NotImplementedError

    def _raise_http(self, response: httpx.Response) -> None:
        if response.is_success:
            return
        try:
            body = response.json()
            if isinstance(body, dict):
                err = body.get("error")
                if isinstance(err, dict):
                    msg = err.get("message") or str(err)
                else:
                    msg = body.get("message") or str(body)
            else:
                msg = str(body)
        except Exception:
            msg = response.text[:800]
        raise ProviderError(f"HTTP {response.status_code}: {msg}", response.status_code)


class OpenAICompatibleAdapter(BaseAdapter):
    def list_models(self) -> list[str]:
        if not self.base_url:
            return []
        url = f"{self.base_url}/models"
        headers = headers_for_provider(self.provider, self.api_key)
        try:
            with httpx.Client(timeout=min(self.timeout, 30)) as client:
                response = client.get(url, headers=headers)
            self._raise_http(response)
            body = response.json()
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(str(exc)) from exc

        rows = body.get("data") if isinstance(body, dict) else None
        if not isinstance(rows, list) and isinstance(body, dict):
            rows = body.get("models")
        result: list[str] = []
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict):
                    mid = row.get("id") or row.get("name")
                    if mid:
                        result.append(str(mid))
                elif isinstance(row, str):
                    result.append(row)
        return sorted(set(result), key=str.lower)

    def chat(self, messages: list[dict[str, str]], model: str) -> str:
        if not self.base_url:
            raise ProviderError("Base URL belum dikonfigurasi.")
        if not model:
            raise ProviderError("Model belum dipilih.")
        url = f"{self.base_url}/chat/completions"
        payload: dict[str, Any] = {"model": model, "messages": messages}
        headers = headers_for_provider(self.provider, self.api_key)
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(url, headers=headers, json=payload)
            self._raise_http(response)
            body = response.json()
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(str(exc)) from exc

        try:
            choice = body["choices"][0]
            message = choice.get("message") or {}
            content = message.get("content")
            text = extract_text_content(content)
            if not text and "text" in choice:
                text = extract_text_content(choice.get("text"))
            if not text:
                raise KeyError("empty content")
            return text
        except Exception as exc:
            raise ProviderError(f"Format respons tidak dikenali: {str(body)[:900]}") from exc


class AnthropicAdapter(BaseAdapter):
    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }

    def list_models(self) -> list[str]:
        try:
            with httpx.Client(timeout=min(self.timeout, 30)) as client:
                response = client.get(f"{self.base_url}/v1/models", headers=self._headers())
            self._raise_http(response)
            rows = response.json().get("data", [])
            return sorted({str(x.get("id")) for x in rows if isinstance(x, dict) and x.get("id")})
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(str(exc)) from exc

    def chat(self, messages: list[dict[str, str]], model: str) -> str:
        system_parts = [m["content"] for m in messages if m.get("role") == "system"]
        convo = [m for m in messages if m.get("role") in {"user", "assistant"}]
        payload: dict[str, Any] = {
            "model": model,
            "max_tokens": 4096,
            "messages": convo,
        }
        if system_parts:
            payload["system"] = "\n\n".join(system_parts)
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(f"{self.base_url}/v1/messages", headers=self._headers(), json=payload)
            self._raise_http(response)
            body = response.json()
            content = body.get("content", [])
            text = extract_text_content(content)
            if not text:
                raise KeyError("empty content")
            return text
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(str(exc)) from exc


class CohereAdapter(BaseAdapter):
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def list_models(self) -> list[str]:
        urls = [f"{self.base_url}/v1/models", f"{self.base_url}/v2/models"]
        last_error: Exception | None = None
        for url in urls:
            try:
                with httpx.Client(timeout=min(self.timeout, 30)) as client:
                    response = client.get(url, headers=self._headers())
                if not response.is_success:
                    last_error = ProviderError(f"HTTP {response.status_code}", response.status_code)
                    continue
                body = response.json()
                rows = body.get("models") or body.get("data") or []
                models = []
                for row in rows:
                    if isinstance(row, dict):
                        mid = row.get("name") or row.get("id")
                        if mid:
                            models.append(str(mid))
                if models:
                    return sorted(set(models), key=str.lower)
            except Exception as exc:
                last_error = exc
        if last_error:
            raise ProviderError(str(last_error))
        return []

    def chat(self, messages: list[dict[str, str]], model: str) -> str:
        payload = {"model": model, "messages": messages, "stream": False}
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(f"{self.base_url}/v2/chat", headers=self._headers(), json=payload)
            self._raise_http(response)
            body = response.json()
            message = body.get("message") or {}
            text = extract_text_content(message.get("content"))
            if not text:
                raise KeyError("empty content")
            return text
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(str(exc)) from exc


def adapter_for(provider: dict[str, Any], api_key: str, timeout: float) -> BaseAdapter:
    kind = provider.get("kind", "openai")
    if kind == "anthropic":
        return AnthropicAdapter(provider, api_key, timeout)
    if kind == "cohere":
        return CohereAdapter(provider, api_key, timeout)
    return OpenAICompatibleAdapter(provider, api_key, timeout)


@dataclass
class RouteResult:
    text: str
    provider_id: str
    provider_name: str
    model: str
    key_index: int
    errors: list[str] = field(default_factory=list)


class AIRouter:
    def __init__(self, cfg: dict[str, Any], providers: dict[str, dict[str, Any]], vault: SecretVault):
        self.cfg = cfg
        self.providers = providers
        self.vault = vault

    def route_order(self, forced_provider: str | None = None) -> list[str]:
        if forced_provider:
            return [forced_provider]
        default = self.cfg.get("default_provider", "")
        priority = [x for x in self.cfg.get("provider_priority", []) if x in self.providers]
        order: list[str] = []
        if default and default in self.providers:
            order.append(default)
        for pid in priority:
            if pid not in order:
                order.append(pid)
        if self.cfg.get("fallback_enabled", True):
            for pid, provider in self.providers.items():
                if provider.get("enabled", True) and pid not in order:
                    order.append(pid)
        return order

    def provider_for_role(self, role: str) -> str | None:
        if not self.cfg.get("smart_routing", True):
            return None
        roles = self.cfg.get("role_providers") or {}
        pid = str(roles.get(role) or "").strip()
        return pid if pid in self.providers else None

    def chat_role(self, messages: list[dict[str, str]], role: str, forced_provider: str | None = None) -> RouteResult:
        return self.chat(messages, forced_provider or self.provider_for_role(role))

    def chat(self, messages: list[dict[str, str]], forced_provider: str | None = None) -> RouteResult:
        errors: list[str] = []
        timeout = float(self.cfg.get("timeout_seconds", 120))
        order = self.route_order(forced_provider)
        if not order:
            raise AzzxError("Belum ada AI provider yang dikonfigurasi. Jalankan: azzx ai")

        for pid in order:
            provider = self.providers.get(pid)
            if not provider or not provider.get("enabled", True):
                continue
            model = str(provider.get("model") or "")
            key_ids = list(provider.get("key_ids") or [])
            if not key_ids and not provider.get("requires_key", True):
                key_ids = [""]
            if not key_ids:
                errors.append(f"{pid}: API key belum ada")
                continue

            for idx, key_id in enumerate(key_ids, 1):
                api_key = self.vault.get(key_id) if key_id else "ollama"
                if provider.get("requires_key", True) and not api_key:
                    errors.append(f"{pid} key#{idx}: key kosong")
                    continue
                try:
                    adapter = adapter_for(provider, api_key, timeout)
                    text = adapter.chat(messages, model)
                    return RouteResult(
                        text=text,
                        provider_id=pid,
                        provider_name=provider.get("name", pid),
                        model=model,
                        key_index=idx,
                        errors=errors,
                    )
                except ProviderError as exc:
                    errors.append(f"{provider.get('name', pid)} key#{idx}: {exc}")
                    continue
        joined = "\n".join(f"- {e}" for e in errors[-12:])
        raise AzzxError(f"Semua AI provider gagal.\n{joined}")


def choose_from_list(title: str, items: list[tuple[str, str]], allow_cancel: bool = True) -> str | None:
    console.print(f"\n[bold cyan]{title}[/]")
    for i, (_, label) in enumerate(items, 1):
        console.print(f"  [cyan]{i:>2}[/]. {label}")
    if allow_cancel:
        console.print("   [dim]0. Batal[/]")
    while True:
        val = IntPrompt.ask("Pilih", default=0 if allow_cancel else 1)
        if allow_cancel and val == 0:
            return None
        if 1 <= val <= len(items):
            return items[val - 1][0]
        console.print("[yellow]Pilihan tidak valid.[/]")


def provider_display_rows(providers: dict[str, dict[str, Any]], vault: SecretVault, cfg: dict[str, Any]) -> Table:
    table = Table(box=box.ROUNDED, border_style="cyan", header_style="bold cyan", expand=True)
    table.add_column("Provider", no_wrap=True)
    table.add_column("Status", no_wrap=True)
    table.add_column("Keys", justify="center", no_wrap=True)
    table.add_column("Model")
    table.add_column("Default", justify="center", no_wrap=True)
    for pid, provider in providers.items():
        key_ids = provider.get("key_ids") or []
        requires_key = provider.get("requires_key", True)
        ready = bool(provider.get("base_url") and provider.get("model") and (key_ids or not requires_key))
        key_count = len(key_ids) if requires_key else "local"
        table.add_row(
            provider.get("name", pid),
            status_badge(ready),
            str(key_count),
            provider.get("model") or "[dim]-[/]",
            "[green]★[/]" if cfg.get("default_provider") == pid else "",
        )
    return table


def unique_provider_id(base: str, providers: dict[str, dict[str, Any]]) -> str:
    cleaned = re.sub(r"[^a-z0-9_-]+", "-", base.lower()).strip("-") or "custom"
    if cleaned not in providers:
        return cleaned
    i = 2
    while f"{cleaned}-{i}" in providers:
        i += 1
    return f"{cleaned}-{i}"


def fetch_models_for(provider: dict[str, Any], api_key: str, cfg: dict[str, Any]) -> tuple[list[str], str | None]:
    try:
        adapter = adapter_for(provider, api_key or "ollama", float(cfg.get("timeout_seconds", 120)))
        return adapter.list_models(), None
    except Exception as exc:
        return [], str(exc)


def pick_model(provider: dict[str, Any], api_key: str, cfg: dict[str, Any]) -> str:
    with console.status("[cyan]Mengambil daftar model...[/]", spinner="dots"):
        models, error = fetch_models_for(provider, api_key, cfg)
    if models:
        # Keep the menu usable even when a provider exposes hundreds of models.
        shown = models[:40]
        console.print(f"[green]✓[/] {len(models)} model ditemukan.")
        for i, model in enumerate(shown, 1):
            console.print(f"  [cyan]{i:>2}[/]. {model}")
        if len(models) > len(shown):
            console.print(f"  [dim]... {len(models) - len(shown)} model lain tidak ditampilkan[/]")
        console.print("   [cyan]0[/]. Masukkan model ID manual")
        while True:
            choice = IntPrompt.ask("Model", default=1)
            if choice == 0:
                return Prompt.ask("Model ID").strip()
            if 1 <= choice <= len(shown):
                return shown[choice - 1]
            console.print("[yellow]Pilihan tidak valid.[/]")
    if error:
        console.print(f"[yellow]Daftar model tidak bisa diambil:[/] {error}")
    default_model = str(provider.get("model") or "")
    return Prompt.ask("Masukkan model ID", default=default_model or None).strip()


def test_provider(provider: dict[str, Any], api_key: str, cfg: dict[str, Any]) -> tuple[bool, str]:
    model = provider.get("model") or ""
    if not model:
        return False, "Model belum dipilih"
    try:
        adapter = adapter_for(provider, api_key or "ollama", float(cfg.get("timeout_seconds", 120)))
        reply = adapter.chat([{"role": "user", "content": "Reply with exactly: OK"}], model)
        return True, reply.strip()[:120]
    except Exception as exc:
        return False, str(exc)


def configure_provider(
    template_id: str,
    providers: dict[str, dict[str, Any]],
    cfg: dict[str, Any],
    vault: SecretVault,
    existing_id: str | None = None,
) -> str | None:
    if existing_id:
        pid = existing_id
        provider = dict(providers[pid])
    else:
        template = dict(PROVIDER_TEMPLATES[template_id])
        if template.get("ask_name"):
            display_name = Prompt.ask("Nama provider", default="Custom AI").strip()
            template["name"] = display_name
            pid = unique_provider_id(display_name, providers)
        else:
            pid = unique_provider_id(template_id, providers)
        provider = template

    console.print(Panel(f"[bold]{provider.get('name', pid)}[/]", title="AI CONFIGURE", border_style="cyan"))

    if provider.get("ask_base_url") or not provider.get("base_url"):
        current = provider.get("base_url") or ""
        provider["base_url"] = normalize_base_url(Prompt.ask("Base URL", default=current or None))
    else:
        console.print(f"Base URL: [dim]{provider.get('base_url')}[/]")

    requires_key = bool(provider.get("requires_key", True))
    api_key = ""
    key_ids = list(provider.get("key_ids") or [])
    if requires_key:
        if key_ids and existing_id:
            console.print(f"API key tersimpan: [dim]{vault.mask(key_ids[0])}[/]")
            change = Confirm.ask("Ganti/tambah API key sekarang?", default=False)
        else:
            change = True
        if change:
            api_key = Prompt.ask("API Key", password=True).strip()
            if not api_key:
                console.print("[red]API key kosong. Konfigurasi dibatalkan.[/]")
                return None
            secret_id = f"{pid}:{int(time.time())}:{len(key_ids)+1}"
            vault.set(secret_id, api_key)
            key_ids.append(secret_id)
            provider["key_ids"] = key_ids
        elif key_ids:
            api_key = vault.get(key_ids[0])
    else:
        provider["key_ids"] = []
        api_key = "ollama"

    model = pick_model(provider, api_key, cfg)
    if not model:
        console.print("[red]Model tidak boleh kosong.[/]")
        return None
    provider["model"] = model
    provider["enabled"] = True

    with console.status("[cyan]Menguji koneksi AI...[/]", spinner="dots"):
        ok, detail = test_provider(provider, api_key, cfg)
    if ok:
        console.print(f"[green]✓ Connected[/] — {detail}")
    else:
        console.print(f"[yellow]⚠ Test gagal:[/] {detail}")
        if not Confirm.ask("Simpan konfigurasi ini tetap?", default=False):
            # New secret should not be left behind if the entire setup is rejected.
            if requires_key and provider.get("key_ids") and not existing_id:
                for sid in provider.get("key_ids", []):
                    vault.delete(sid)
            return None

    providers[pid] = provider
    save_providers(providers)

    priority = list(cfg.get("provider_priority") or [])
    if pid not in priority:
        priority.append(pid)
    cfg["provider_priority"] = priority
    if not cfg.get("default_provider"):
        cfg["default_provider"] = pid
    save_config(cfg)
    console.print(f"[green]✓[/] {provider.get('name', pid)} tersimpan.")
    return pid


def add_key_to_provider(pid: str, providers: dict[str, dict[str, Any]], vault: SecretVault) -> None:
    provider = providers[pid]
    if not provider.get("requires_key", True):
        console.print("[yellow]Provider lokal ini tidak membutuhkan API key.[/]")
        return
    key = Prompt.ask("API Key baru", password=True).strip()
    if not key:
        return
    key_ids = list(provider.get("key_ids") or [])
    sid = f"{pid}:{int(time.time())}:{len(key_ids)+1}"
    vault.set(sid, key)
    key_ids.append(sid)
    provider["key_ids"] = key_ids
    save_providers(providers)
    console.print(f"[green]✓[/] Key #{len(key_ids)} ditambahkan.")


def replace_primary_key(pid: str, providers: dict[str, dict[str, Any]], vault: SecretVault) -> None:
    provider = providers[pid]
    if not provider.get("requires_key", True):
        console.print("[yellow]Provider lokal ini tidak membutuhkan API key.[/]")
        return
    key = Prompt.ask("API Key baru", password=True).strip()
    if not key:
        return
    key_ids = list(provider.get("key_ids") or [])
    if key_ids:
        sid = key_ids[0]
    else:
        sid = f"{pid}:{int(time.time())}:1"
        key_ids.append(sid)
    vault.set(sid, key)
    provider["key_ids"] = key_ids
    save_providers(providers)
    console.print("[green]✓[/] Primary API key diperbarui.")


def choose_configured_provider(providers: dict[str, dict[str, Any]], title: str = "Pilih provider") -> str | None:
    if not providers:
        return None
    return choose_from_list(title, [(pid, p.get("name", pid)) for pid, p in providers.items()])


def configure_priority(cfg: dict[str, Any], providers: dict[str, dict[str, Any]]) -> None:
    if not providers:
        return
    console.print("\n[bold cyan]Fallback Priority[/]")
    console.print("Masukkan nomor provider berurutan, contoh: [bold]2,1,3[/]")
    entries = list(providers.items())
    for i, (pid, provider) in enumerate(entries, 1):
        console.print(f"  {i}. {provider.get('name', pid)}")
    raw = Prompt.ask("Urutan").strip()
    order: list[str] = []
    for token in re.split(r"[,\s]+", raw):
        if token.isdigit() and 1 <= int(token) <= len(entries):
            pid = entries[int(token) - 1][0]
            if pid not in order:
                order.append(pid)
    if order:
        cfg["provider_priority"] = order
        save_config(cfg)
        console.print("[green]✓[/] Fallback priority diperbarui.")


def ai_config_menu() -> None:
    setup_homes()
    vault = SecretVault()
    while True:
        cfg = load_config()
        providers = load_providers()
        console.clear()
        banner(compact=True)
        console.print(provider_display_rows(providers, vault, cfg))
        console.print("\n[bold]AI Configure[/]")
        console.print("  [cyan]1[/] Add / configure provider")
        console.print("  [cyan]2[/] Add API key")
        console.print("  [cyan]3[/] Change primary API key")
        console.print("  [cyan]4[/] Change model / endpoint")
        console.print("  [cyan]5[/] Set default provider")
        console.print("  [cyan]6[/] Set fallback priority")
        console.print("  [cyan]7[/] Test provider")
        console.print("  [cyan]8[/] Enable/disable fallback")
        console.print("  [cyan]9[/] Remove provider")
        console.print("  [cyan]0[/] Back")
        choice = IntPrompt.ask("Pilih", default=0)
        if choice == 0:
            return
        if choice == 1:
            templates = [(k, v["name"]) for k, v in PROVIDER_TEMPLATES.items()]
            tid = choose_from_list("Tambah provider", templates)
            if tid:
                configure_provider(tid, providers, cfg, vault)
                Prompt.ask("Enter untuk lanjut", default="")
        elif choice in {2, 3, 4, 5, 7, 9}:
            pid = choose_configured_provider(providers)
            if not pid:
                console.print("[yellow]Belum ada provider.[/]")
                Prompt.ask("Enter untuk lanjut", default="")
                continue
            if choice == 2:
                add_key_to_provider(pid, providers, vault)
            elif choice == 3:
                replace_primary_key(pid, providers, vault)
            elif choice == 4:
                configure_provider(pid if pid in PROVIDER_TEMPLATES else "custom", providers, cfg, vault, existing_id=pid)
            elif choice == 5:
                cfg["default_provider"] = pid
                save_config(cfg)
                console.print(f"[green]✓[/] Default = {providers[pid].get('name', pid)}")
            elif choice == 7:
                provider = providers[pid]
                key_ids = provider.get("key_ids") or []
                key = vault.get(key_ids[0]) if key_ids else "ollama"
                with console.status("[cyan]Testing...[/]"):
                    ok, detail = test_provider(provider, key, cfg)
                console.print(f"[green]✓ PASS[/] {detail}" if ok else f"[red]✗ FAIL[/] {detail}")
            elif choice == 9:
                if Confirm.ask(f"Hapus {providers[pid].get('name', pid)}?", default=False):
                    for sid in providers[pid].get("key_ids") or []:
                        vault.delete(sid)
                    del providers[pid]
                    save_providers(providers)
                    cfg["provider_priority"] = [x for x in cfg.get("provider_priority", []) if x != pid]
                    if cfg.get("default_provider") == pid:
                        cfg["default_provider"] = cfg["provider_priority"][0] if cfg["provider_priority"] else ""
                    save_config(cfg)
                    console.print("[green]✓ Provider dihapus.[/]")
            Prompt.ask("Enter untuk lanjut", default="")
        elif choice == 6:
            configure_priority(cfg, providers)
            Prompt.ask("Enter untuk lanjut", default="")
        elif choice == 8:
            cfg["fallback_enabled"] = not bool(cfg.get("fallback_enabled", True))
            save_config(cfg)
            state = "ON" if cfg["fallback_enabled"] else "OFF"
            console.print(f"[green]✓[/] Fallback {state}")
            Prompt.ask("Enter untuk lanjut", default="")


def first_run_wizard() -> None:
    setup_homes()
    providers = load_providers()
    if providers:
        return
    cfg = load_config()
    vault = SecretVault()
    console.clear()
    banner(compact=True)
    console.print(Panel(
        "Belum ada AI provider. Pilih provider pertama, masukkan API key sekali, "
        "lalu key akan disimpan di secret vault lokal (terenkripsi jika modul crypto tersedia).",
        title="FIRST RUN",
        border_style="cyan",
    ))
    while not providers:
        templates = [(k, v["name"]) for k, v in PROVIDER_TEMPLATES.items()]
        tid = choose_from_list("Pilih AI provider", templates, allow_cancel=False)
        if tid is None:
            raise AzzxError("Setup dibatalkan.")
        pid = configure_provider(tid, providers, cfg, vault)
        providers = load_providers()
        if pid:
            break
    while Confirm.ask("Tambahkan provider AI lain sekarang?", default=False):
        templates = [(k, v["name"]) for k, v in PROVIDER_TEMPLATES.items()]
        tid = choose_from_list("Pilih AI provider", templates)
        if not tid:
            break
        configure_provider(tid, providers, cfg, vault)
        providers = load_providers()
    console.print("\n[green bold]✓ First setup selesai.[/]")
    time.sleep(0.4)


def is_text_file(path: Path) -> bool:
    return path.suffix.lower() in TEXT_EXTS or path.name in SPECIAL_TEXT_FILES


def safe_read_text(path: Path, max_bytes: int = MAX_FILE_BYTES) -> str | None:
    try:
        if path.stat().st_size > max_bytes:
            return None
        raw = path.read_bytes()
        if b"\x00" in raw[:4096]:
            return None
        return raw.decode("utf-8", errors="replace")
    except (OSError, UnicodeError):
        return None


def looks_sensitive_file(path: Path) -> bool:
    name = path.name.lower()
    if name in SENSITIVE_EXACT_NAMES:
        return True
    if name.startswith(".env.") and name not in {".env.example", ".env.sample", ".env.template"}:
        return True
    if re.search(r"(?:^|[_-])(credential|credentials|secret|secrets|private[_-]?key)(?:[_.-]|$)", name):
        return True
    return False


def list_project_files(root: Path) -> list[Path]:
    result: list[Path] = []
    for current, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS and not d.startswith(".tox")]
        current_path = Path(current)
        for name in files:
            path = current_path / name
            try:
                rel = path.relative_to(root)
            except ValueError:
                continue
            if any(part in IGNORE_DIRS for part in rel.parts):
                continue
            if looks_sensitive_file(path):
                continue
            if is_text_file(path) and path.is_file():
                try:
                    if path.stat().st_size <= MAX_FILE_BYTES:
                        result.append(path)
                except OSError:
                    pass
    return result


def project_tree(root: Path, files: list[Path], limit: int = 300) -> str:
    rels = sorted(str(p.relative_to(root)) for p in files)
    if len(rels) > limit:
        rels = rels[:limit] + [f"... ({len(files)-limit} more files)"]
    return "\n".join(rels)


def tokenize_query(query: str) -> set[str]:
    words = re.findall(r"[A-Za-z0-9_./-]{2,}", query.lower())
    stop = {
        "yang", "dan", "atau", "untuk", "dengan", "dari", "ini", "itu", "saya", "aku",
        "the", "and", "or", "with", "from", "this", "that", "please", "tolong", "buat",
        "perbaiki", "fix", "add", "implement", "error", "script", "file",
    }
    return {w for w in words if w not in stop}


def score_file(path: Path, root: Path, query: str, content: str | None = None) -> float:
    rel = str(path.relative_to(root)).lower()
    tokens = tokenize_query(query)
    score = 0.0
    for tok in tokens:
        if tok in rel:
            score += 12.0
        if path.name.lower() == tok:
            score += 20.0
    common = {"main.py", "app.py", "index.js", "index.ts", "package.json", "pyproject.toml", "code.gs", "main.go"}
    if path.name.lower() in common:
        score += 2.0
    if content:
        lower = content.lower()
        for tok in tokens:
            count = lower.count(tok)
            score += min(count, 8) * 1.2
    # Slight preference for smaller files; huge files often waste context.
    try:
        score += max(0, 2.0 - path.stat().st_size / 100_000)
    except OSError:
        pass
    return score


def format_file_context(root: Path, selected: list[Path], max_chars: int) -> str:
    chunks: list[str] = []
    used = 0
    for path in selected:
        content = safe_read_text(path)
        if content is None:
            continue
        rel = str(path.relative_to(root))
        chunk = f"\n===== FILE: {rel} =====\n{content}\n===== END FILE: {rel} =====\n"
        if used + len(chunk) > max_chars:
            remaining = max_chars - used
            if remaining > 1000:
                chunks.append(chunk[:remaining] + "\n...[truncated by AZZX]...\n")
            break
        chunks.append(chunk)
        used += len(chunk)
    return "".join(chunks)


def ensure_workspace_state(root: Path) -> Path:
    state = root / ".azzx"
    (state / "backups").mkdir(parents=True, exist_ok=True)
    try:
        (state / "backups").chmod(0o700)
    except OSError:
        pass
    internal_gitignore = state / ".gitignore"
    if not internal_gitignore.exists():
        atomic_write(internal_gitignore, "*\n!.gitignore\n")
    project_file = state / "project.json"
    if not project_file.exists():
        save_json(project_file, {
            "created_at": dt.datetime.now().isoformat(timespec="seconds"),
            "workspace": str(root),
            "version": VERSION,
        })
    for dirname in ("checkpoints", "plugins", "tasks", "mcp"):
        (state / dirname).mkdir(parents=True, exist_ok=True)
    memory_file = state / "memory.md"
    if not memory_file.exists():
        atomic_write(memory_file, "# AZZX Project Memory\n\n")
    architecture_file = state / "architecture.md"
    if not architecture_file.exists():
        atomic_write(architecture_file, "# Project Architecture\n\nNot generated yet. Run `azzx architect`.\n")
    return state


def latest_backup_dir(root: Path) -> Path | None:
    backup_root = root / ".azzx" / "backups"
    if not backup_root.exists():
        return None
    dirs = sorted([p for p in backup_root.iterdir() if p.is_dir() and not (p / ".restored").exists()], reverse=True)
    return dirs[0] if dirs else None


def safe_workspace_path(root: Path, relative: str) -> Path:
    rel = Path(relative)
    if rel.is_absolute():
        raise AzzxError(f"Path absolut ditolak: {relative}")
    target = (root / rel).resolve()
    root_resolved = root.resolve()
    try:
        target.relative_to(root_resolved)
    except ValueError as exc:
        raise AzzxError(f"Path keluar workspace ditolak: {relative}") from exc
    # Only reject attempts to address AZZX/Git internals *inside this workspace*.
    # The workspace itself may intentionally live under a parent .azzx/sandboxes directory.
    if ".git" in rel.parts or ".azzx" in rel.parts:
        raise AzzxError(f"Agent tidak boleh mengedit area internal: {relative}")
    return target


def validate_content(path: Path, content: str) -> str | None:
    suffix = path.suffix.lower()
    try:
        if suffix in {".py", ".pyi"}:
            ast.parse(content, filename=str(path))
        elif suffix == ".json" or path.name == "package.json":
            json.loads(content)
        elif suffix == ".toml" or path.name == "pyproject.toml":
            try:
                import tomllib
                tomllib.loads(content)
            except ImportError:
                pass
        elif suffix in {".sh", ".bash"}:
            bash = shutil.which("bash")
            if bash:
                with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False, encoding="utf-8") as tmp:
                    tmp.write(content)
                    tmp_path = tmp.name
                try:
                    proc = subprocess.run([bash, "-n", tmp_path], capture_output=True, text=True, timeout=10)
                    if proc.returncode != 0:
                        return proc.stderr.strip()[:1000]
                finally:
                    Path(tmp_path).unlink(missing_ok=True)
    except Exception as exc:
        return str(exc)
    return None


def create_backup(root: Path, changes: list[dict[str, str]], summary: str) -> Path:
    state = ensure_workspace_state(root)
    backup = state / "backups" / now_stamp()
    suffix = 2
    while backup.exists():
        backup = state / "backups" / f"{now_stamp()}_{suffix}"
        suffix += 1
    backup.mkdir(parents=True)
    manifest: dict[str, Any] = {
        "created_at": dt.datetime.now().isoformat(timespec="seconds"),
        "summary": summary,
        "files": [],
    }
    for change in changes:
        rel = change["path"]
        target = safe_workspace_path(root, rel)
        existed = target.exists()
        record = {"path": rel, "existed": existed}
        if existed:
            source = target.read_bytes()
            backup_file = backup / "files" / rel
            backup_file.parent.mkdir(parents=True, exist_ok=True)
            backup_file.write_bytes(source)
        manifest["files"].append(record)
    save_json(backup / "manifest.json", manifest)
    return backup


def apply_changes(root: Path, changes: list[dict[str, str]], summary: str) -> Path:
    if not changes:
        raise AzzxError("AI tidak menghasilkan perubahan file.")
    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    errors: list[str] = []
    for change in changes:
        rel = str(change.get("path") or "").strip()
        content = change.get("content")
        if not rel or not isinstance(content, str):
            errors.append("Change memiliki path/content yang tidak valid")
            continue
        if rel in seen:
            errors.append(f"Duplicate change: {rel}")
            continue
        seen.add(rel)
        target = safe_workspace_path(root, rel)
        issue = validate_content(target, content)
        if issue:
            errors.append(f"{rel}: {issue}")
        normalized.append({"path": rel, "content": content})
    if errors:
        raise AzzxError("Validasi patch gagal:\n" + "\n".join(f"- {e}" for e in errors))

    backup = create_backup(root, normalized, summary)
    for change in normalized:
        target = safe_workspace_path(root, change["path"])
        target.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(target, change["content"])
    return backup


def restore_backup(root: Path, backup: Path) -> list[str]:
    manifest = load_json(backup / "manifest.json", {})
    restored: list[str] = []
    for record in manifest.get("files", []):
        rel = record.get("path")
        if not rel:
            continue
        target = safe_workspace_path(root, rel)
        if record.get("existed"):
            source = backup / "files" / rel
            if source.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source.read_bytes())
        else:
            target.unlink(missing_ok=True)
        restored.append(rel)
    return restored


def diff_backup(root: Path, backup: Path) -> str:
    manifest = load_json(backup / "manifest.json", {})
    chunks: list[str] = []
    for record in manifest.get("files", []):
        rel = record.get("path")
        if not rel:
            continue
        target = safe_workspace_path(root, rel)
        before = ""
        if record.get("existed"):
            source = backup / "files" / rel
            if source.exists():
                before = source.read_text(encoding="utf-8", errors="replace")
        after = target.read_text(encoding="utf-8", errors="replace") if target.exists() else ""
        lines = difflib.unified_diff(
            before.splitlines(True),
            after.splitlines(True),
            fromfile=f"a/{rel}",
            tofile=f"b/{rel}",
        )
        chunks.append("".join(lines))
    return "\n".join(c for c in chunks if c)

EDIT_SYSTEM = r"""
You are AZZATSSINS LITE AGENT, a careful coding agent operating on a local workspace.
Your job is to implement the user's requested code change using ONLY the workspace context provided.

Return STRICT JSON only. No markdown fences. Schema:
{
  "summary": "short summary",
  "needs_files": ["optional/relative/path"],
  "changes": [
    {
      "path": "existing/file.py",
      "replacements": [
        {"search": "EXACT old text", "replace": "new text"}
      ]
    },
    {"path": "new/file.py", "content": "FULL content for a new file"}
  ],
  "notes": ["optional note"]
}

Rules:
- For EXISTING files, strongly prefer exact replacements to reduce output size. Every search string must match exactly once.
- Use full content when creating a NEW file, or only when an exact replacement is impractical.
- If using changes.content for an existing file, it must be the complete final file content, never a partial snippet.
- Preserve unrelated behavior and public interfaces unless the user explicitly asks otherwise.
- Never expose, invent, or write API keys, passwords, cookies, tokens, or secrets.
- Do not edit .git, .azzx, virtual environments, generated dependency folders, or files outside the workspace.
- Do not delete files. If deletion is needed, explain it in notes and leave changes empty for that file.
- Prefer the smallest coherent patch that solves the request.
- If critical source is missing from context, use needs_files and do not guess its contents.
- Keep existing language/style conventions.
- For bug fixes, address root cause rather than hiding errors.
- New files are allowed when necessary.
""".strip()

ASK_SYSTEM = r"""
You are AZZATSSINS LITE AGENT. Answer questions about the supplied local codebase.
Be concrete and reference relative file paths/functions when possible. Do not invent unseen code.
Do not output or request secrets. Answer in the user's language when obvious from the request.
""".strip()

REVIEW_SYSTEM = r"""
You are AZZATSSINS LITE AGENT performing a code review.
Review only the supplied workspace context. Prioritize real bugs, broken logic, security problems,
data-loss risks, portability issues, performance bottlenecks, and maintainability issues.
Separate confirmed findings from possibilities. Mention relative file paths and relevant symbols.
Do not fabricate line numbers. Do not output secrets. Give practical fixes but do not rewrite files.
""".strip()


def parse_json_object(text: str) -> dict[str, Any]:
    raw = text.strip()
    # Remove a single markdown fence if a provider ignored the strict-JSON request.
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", raw, re.S | re.I)
    if fence:
        raw = fence.group(1).strip()
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass

    # Find the first balanced JSON object while respecting strings/escapes.
    start = raw.find("{")
    if start >= 0:
        depth = 0
        in_string = False
        escaped = False
        for i in range(start, len(raw)):
            ch = raw[i]
            if in_string:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidate = raw[start : i + 1]
                    try:
                        obj = json.loads(candidate)
                        if isinstance(obj, dict):
                            return obj
                    except json.JSONDecodeError:
                        break
    raise AzzxError("AI tidak mengembalikan JSON patch yang valid. Coba ulang atau ganti model/provider.")


def sanitize_changes(obj: dict[str, Any]) -> list[dict[str, Any]]:
    rows = obj.get("changes") or []
    result: list[dict[str, Any]] = []
    if not isinstance(rows, list):
        return result
    for row in rows:
        if not isinstance(row, dict):
            continue
        path = row.get("path")
        if not isinstance(path, str) or not path.strip():
            continue
        item: dict[str, Any] = {"path": path.strip()}
        if isinstance(row.get("content"), str):
            item["content"] = row["content"]
        reps = row.get("replacements")
        if isinstance(reps, list):
            clean_reps: list[dict[str, str]] = []
            for rep in reps:
                if not isinstance(rep, dict):
                    continue
                search = rep.get("search")
                replace = rep.get("replace")
                if isinstance(search, str) and search and isinstance(replace, str):
                    clean_reps.append({"search": search, "replace": replace})
            if clean_reps:
                item["replacements"] = clean_reps
        if "content" in item or "replacements" in item:
            result.append(item)
    return result


def materialize_changes(root: Path, changes: list[dict[str, Any]]) -> list[dict[str, str]]:
    final: list[dict[str, str]] = []
    for change in changes:
        rel = change["path"]
        target = safe_workspace_path(root, rel)
        if "replacements" in change:
            if not target.exists():
                raise AzzxError(f"Patch replacements membutuhkan file yang sudah ada: {rel}")
            original = safe_read_text(target)
            if original is None:
                raise AzzxError(f"File tidak dapat dibaca sebagai teks: {rel}")
            content = original
            for rep in change["replacements"]:
                search = rep["search"]
                count = content.count(search)
                if count != 1:
                    raise AzzxError(
                        f"Exact replacement gagal untuk {rel}: search harus cocok tepat 1 kali, ditemukan {count}."
                    )
                content = content.replace(search, rep["replace"], 1)
            final.append({"path": rel, "content": content})
        else:
            final.append({"path": rel, "content": change["content"]})
    return final


def write_history(root: Path, record: dict[str, Any]) -> None:
    state = ensure_workspace_state(root)
    history = state / "history.jsonl"
    record = {"time": dt.datetime.now().isoformat(timespec="seconds"), **record}
    with history.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def show_route(result: RouteResult) -> None:
    console.print(
        f"[dim]AI:[/] [cyan]{result.provider_name}[/]  "
        f"[dim]Model:[/] [cyan]{result.model}[/]  "
        f"[dim]Key:[/] #{result.key_index}"
    )
    if result.errors:
        console.print(f"[dim]Fallback melewati {len(result.errors)} percobaan yang gagal.[/]")


def get_router() -> AIRouter:
    return AIRouter(load_config(), load_providers(), SecretVault())


def render_change_summary(changes: list[dict[str, str]], root: Path) -> None:
    table = Table(title="Planned Changes", box=box.SIMPLE, header_style="bold cyan")
    table.add_column("File")
    table.add_column("Action")
    table.add_column("Size", justify="right")
    for c in changes:
        path = safe_workspace_path(root, c["path"])
        action = "MODIFY" if path.exists() else "CREATE"
        table.add_row(c["path"], action, f"{len(c['content']):,} chars")
    console.print(table)


def run_edit_task(root: Path, instruction: str, mode: str = "fix", forced_provider: str | None = None, extra_context: str = "") -> bool:
    cfg = load_config()
    router = get_router()
    ensure_workspace_state(root)

    verb = {"fix": "Fix the problem", "add": "Add the requested feature", "implement": "Implement the request", "create": "Create the requested project/files"}.get(mode, "Implement the request")
    query = instruction
    context, selected, files = build_workspace_context(root, query, cfg)

    console.print(Panel(
        f"[bold]{instruction}[/]\n\n[dim]{len(files)} project files • {len(selected)} files selected for context[/]",
        title=mode.upper(),
        border_style="cyan",
    ))
    if selected:
        console.print("[dim]Context:[/] " + ", ".join(str(p.relative_to(root)) for p in selected))

    user_payload = f"""
TASK TYPE: {mode}
TASK: {instruction}

{("PLANNER CONTEXT:\n" + extra_context + "\n\n") if extra_context else ""}{context}

{verb}. Return strict JSON using the required schema.
""".strip()
    messages = [
        {"role": "system", "content": EDIT_SYSTEM},
        {"role": "user", "content": user_payload},
    ]

    last_obj: dict[str, Any] | None = None
    route: RouteResult | None = None
    for round_no in range(1, 4):
        label = "Menganalisis project..." if round_no == 1 else "Menyempurnakan patch..."
        with console.status(f"[cyan]{label}[/]", spinner="dots"):
            route = router.chat_role(messages, "coder", forced_provider)
        obj = parse_json_object(route.text)
        last_obj = obj

        needs = obj.get("needs_files") or []
        if isinstance(needs, list) and needs:
            valid_needs = [x for x in needs if isinstance(x, str)][:8]
            if valid_needs and round_no < 3:
                extra_chunks: list[str] = []
                for rel in valid_needs:
                    try:
                        path = safe_workspace_path(root, rel)
                    except AzzxError:
                        continue
                    if path.exists() and path.is_file():
                        content = safe_read_text(path)
                        if content is not None:
                            extra_chunks.append(f"===== FILE: {rel} =====\n{content}\n===== END FILE =====")
                if extra_chunks:
                    messages.append({"role": "assistant", "content": route.text})
                    messages.append({
                        "role": "user",
                        "content": "Requested files:\n\n" + "\n\n".join(extra_chunks) + "\n\nNow return the final JSON patch.",
                    })
                    continue

        raw_changes = sanitize_changes(obj)
        if not raw_changes:
            notes = obj.get("notes") or []
            summary = obj.get("summary") or "AI tidak menghasilkan perubahan."
            console.print(Panel(str(summary), title="NO PATCH", border_style="yellow"))
            if notes:
                console.print(Markdown("\n".join(f"- {n}" for n in notes)))
            if route:
                show_route(route)
            write_history(root, {"action": mode, "instruction": instruction, "result": "no_changes"})
            return False

        # Convert compact exact replacements into complete in-memory files, then
        # validate before touching disk. This saves output tokens on large files.
        validation_errors: list[str] = []
        changes: list[dict[str, str]] = []
        try:
            changes = materialize_changes(root, raw_changes)
        except AzzxError as exc:
            validation_errors.append(str(exc))
        for change in changes:
            try:
                target = safe_workspace_path(root, change["path"])
                issue = validate_content(target, change["content"])
                if issue:
                    validation_errors.append(f"{change['path']}: {issue}")
            except AzzxError as exc:
                validation_errors.append(str(exc))
        if validation_errors and round_no < 3:
            messages.append({"role": "assistant", "content": route.text})
            messages.append({
                "role": "user",
                "content": "Your patch failed local syntax/safety validation:\n- "
                           + "\n- ".join(validation_errors)
                           + "\nReturn a corrected strict JSON patch. Prefer exact replacements for existing files.",
            })
            continue
        if validation_errors:
            raise AzzxError("Patch tetap gagal setelah retry:\n- " + "\n- ".join(validation_errors))

        summary = str(obj.get("summary") or instruction)
        render_change_summary(changes, root)
        if cfg.get("checkpoint_before_edit", True):
            try:
                create_git_checkpoint(root, f"before-{mode}", quiet=True)
            except Exception:
                pass
        backup = apply_changes(root, changes, summary)
        console.print(Panel(f"[green bold]✓ TASK COMPLETED[/]\n{summary}", border_style="green"))
        console.print(f"[dim]Backup:[/] {backup.relative_to(root)}")
        if route:
            show_route(route)
        notes = obj.get("notes") or []
        if notes:
            console.print(Markdown("\n".join(f"- {n}" for n in notes)))
        write_history(root, {
            "action": mode,
            "instruction": instruction,
            "result": "changed",
            "summary": summary,
            "files": [c["path"] for c in changes],
            "backup": str(backup.relative_to(root)),
            "provider": route.provider_id if route else "",
            "model": route.model if route else "",
        })
        if cfg.get("auto_test_after_edit", False):
            run_tests(root, quiet=False)
        return True

    if last_obj:
        raise AzzxError(str(last_obj))
    return False


def run_ask(root: Path, question: str, forced_provider: str | None = None) -> None:
    cfg = load_config()
    context, selected, files = build_workspace_context(root, question, cfg)
    messages = [
        {"role": "system", "content": ASK_SYSTEM},
        {"role": "user", "content": f"QUESTION: {question}\n\n{context}"},
    ]
    with console.status("[cyan]Membaca project dan bertanya ke AI...[/]", spinner="dots"):
        result = get_router().chat_role(messages, "planner", forced_provider)
    console.print(Panel(Markdown(result.text), title="ANSWER", border_style="cyan"))
    show_route(result)
    write_history(root, {"action": "ask", "instruction": question, "result": "answered", "provider": result.provider_id, "model": result.model})


def run_review(root: Path, focus: str = "", forced_provider: str | None = None) -> None:
    cfg = load_config()
    query = focus or "review bugs security logic performance maintainability entrypoints configuration"
    context, selected, files = build_workspace_context(root, query, cfg)
    user = "Review this project."
    if focus:
        user += f" Focus especially on: {focus}."
    messages = [
        {"role": "system", "content": REVIEW_SYSTEM},
        {"role": "user", "content": f"{user}\n\n{context}"},
    ]
    console.print(f"[dim]Review context: {len(selected)}/{len(files)} files[/]")
    with console.status("[cyan]Reviewing...[/]", spinner="dots"):
        result = get_router().chat_role(messages, "reviewer", forced_provider)
    console.print(Panel(Markdown(result.text), title="CODE REVIEW", border_style="cyan"))
    show_route(result)
    write_history(root, {"action": "review", "instruction": focus, "result": "reviewed", "provider": result.provider_id, "model": result.model})


def run_debug(root: Path, command: str, forced_provider: str | None = None) -> None:
    console.print(Panel(f"[bold]{command}[/]", title="DEBUG COMMAND", border_style="yellow"))
    try:
        proc = subprocess.run(
            command,
            cwd=root,
            shell=True,
            text=True,
            capture_output=True,
            timeout=90,
        )
        output = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
        output = output[-30000:]
        console.print(f"Exit code: [bold]{proc.returncode}[/]")
        if output.strip():
            console.print(Panel(output.strip()[:12000], title="OUTPUT", border_style="dim"))
        if proc.returncode == 0:
            console.print("[green]✓ Command selesai tanpa error.[/]")
            return
        instruction = (
            f"Debug and fix the project so this user-supplied command succeeds: {command}\n\n"
            f"Exit code: {proc.returncode}\nOUTPUT:\n{output}"
        )
        run_edit_task(root, instruction, "fix", forced_provider)
    except subprocess.TimeoutExpired as exc:
        output = ((exc.stdout or "") if isinstance(exc.stdout, str) else "") + "\n" + ((exc.stderr or "") if isinstance(exc.stderr, str) else "")
        instruction = f"Debug why this command timed out after 90 seconds: {command}\n\nPartial output:\n{output[-20000:]}"
        run_edit_task(root, instruction, "fix", forced_provider)


def show_diff(root: Path) -> None:
    backup = latest_backup_dir(root)
    if not backup:
        console.print("[yellow]Belum ada backup/perubahan AZZX di workspace ini.[/]")
        return
    diff = diff_backup(root, backup)
    if not diff.strip():
        console.print("[green]Tidak ada perbedaan terhadap backup terakhir.[/]")
        return
    console.print(Panel(Text(diff), title=f"DIFF • {backup.name}", border_style="cyan"))


def undo_last(root: Path, assume_yes: bool = False) -> None:
    backup = latest_backup_dir(root)
    if not backup:
        console.print("[yellow]Belum ada backup untuk di-undo.[/]")
        return
    manifest = load_json(backup / "manifest.json", {})
    summary = manifest.get("summary") or backup.name
    console.print(f"Backup terakhir: [cyan]{backup.name}[/] — {summary}")
    if not assume_yes and not Confirm.ask("Restore backup ini?", default=True):
        return
    restored = restore_backup(root, backup)
    # Mark it restored rather than deleting evidence/history.
    atomic_write(backup / ".restored", dt.datetime.now().isoformat(timespec="seconds") + "\n")
    console.print(f"[green]✓[/] Restore selesai: {', '.join(restored)}")
    write_history(root, {"action": "undo", "result": "restored", "backup": backup.name, "files": restored})


def scan_workspace(root: Path) -> None:
    files = list_project_files(root)
    counts: dict[str, int] = {}
    for path in files:
        ext = path.suffix.lower() or path.name
        counts[ext] = counts.get(ext, 0) + 1
    table = Table(title=f"Workspace Scan • {root}", box=box.ROUNDED, border_style="cyan")
    table.add_column("Type")
    table.add_column("Files", justify="right")
    for ext, count in sorted(counts.items(), key=lambda x: (-x[1], x[0]))[:30]:
        table.add_row(ext, str(count))
    console.print(table)
    console.print(f"Total text/code files: [bold]{len(files)}[/]")
    if files:
        console.print("\n[dim]Sample:[/]")
        for path in files[:40]:
            console.print(f"  {path.relative_to(root)}")


def show_history(root: Path, limit: int = 20) -> None:
    history = root / ".azzx" / "history.jsonl"
    if not history.exists():
        console.print("[yellow]Belum ada history AZZX.[/]")
        return
    rows: list[dict[str, Any]] = []
    for line in history.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            row = json.loads(line)
            if isinstance(row, dict):
                rows.append(row)
        except json.JSONDecodeError:
            continue
    table = Table(title="AZZX History", box=box.ROUNDED, border_style="cyan")
    table.add_column("Time", no_wrap=True)
    table.add_column("Action", no_wrap=True)
    table.add_column("Result", no_wrap=True)
    table.add_column("Instruction / Summary")
    for row in rows[-limit:][::-1]:
        desc = row.get("summary") or row.get("instruction") or ""
        table.add_row(str(row.get("time", "")), str(row.get("action", "")), str(row.get("result", "")), str(desc)[:100])
    console.print(table)


def doctor(online: bool = False) -> None:
    cfg = load_config()
    providers = load_providers()
    vault = SecretVault()
    table = Table(title="AZZATSSINS LITE AGENT • Doctor", box=box.ROUNDED, border_style="cyan")
    table.add_column("Check")
    table.add_column("Status")
    table.add_column("Detail")
    py_ok = sys.version_info >= (3, 10)
    table.add_row("Python", "[green]✓[/]" if py_ok else "[red]✗[/]", platform.python_version())
    table.add_row("Git", "[green]✓[/]" if shutil.which("git") else "[yellow]○[/]", shutil.which("git") or "not found")
    table.add_row("Bash", "[green]✓[/]" if shutil.which("bash") else "[yellow]○[/]", shutil.which("bash") or "not found")
    table.add_row("Ripgrep", "[green]✓[/]" if shutil.which("rg") else "[yellow]○[/]", shutil.which("rg") or "optional")
    table.add_row("SSH", "[green]✓[/]" if shutil.which("ssh") else "[yellow]○[/]", shutil.which("ssh") or "optional")
    table.add_row("Config", "[green]✓[/]", str(CONFIG_HOME))
    table.add_row("Vault", "[green]✓[/]", vault.mode)
    table.add_row("Fallback", "[green]ON[/]" if cfg.get("fallback_enabled") else "[yellow]OFF[/]", " → ".join(cfg.get("provider_priority", [])) or "-")
    console.print(table)

    ptable = Table(title="AI Providers", box=box.ROUNDED, border_style="cyan")
    ptable.add_column("Provider")
    ptable.add_column("Config")
    ptable.add_column("Online" if online else "Model")
    for pid, provider in providers.items():
        key_ids = provider.get("key_ids") or []
        ready = bool(provider.get("base_url") and provider.get("model") and (key_ids or not provider.get("requires_key", True)))
        if online and ready:
            key = vault.get(key_ids[0]) if key_ids else "ollama"
            with console.status(f"Testing {provider.get('name', pid)}..."):
                models, error = fetch_models_for(provider, key, cfg)
            online_state = f"[green]✓ {len(models)} models[/]" if models else f"[yellow]⚠ {error or 'reachable, list empty'}[/]"
        else:
            online_state = provider.get("model") or "-"
        ptable.add_row(provider.get("name", pid), status_badge(ready), online_state)
    if providers:
        console.print(ptable)
    else:
        console.print("[yellow]Belum ada provider. Jalankan: azzx ai[/]")



# ---------------------------- V2 FEATURES ----------------------------

def read_project_memory(root: Path) -> str:
    state = ensure_workspace_state(root)
    return safe_read_text(state / "memory.md", 64_000) or ""


def remember_project(root: Path, note: str) -> None:
    state = ensure_workspace_state(root)
    path = state / "memory.md"
    existing = safe_read_text(path, 128_000) or "# AZZX Project Memory\n\n"
    stamp = dt.datetime.now().isoformat(timespec="seconds")
    atomic_write(path, existing.rstrip() + f"\n\n- [{stamp}] {note.strip()}\n")
    console.print("[green]✓ Project memory updated.[/]")


def show_project_memory(root: Path) -> None:
    console.print(Panel(Markdown(read_project_memory(root) or "No project memory."), title="PROJECT MEMORY", border_style="cyan"))


def refresh_project_index(root: Path, quiet: bool = False) -> dict[str, Any]:
    state = ensure_workspace_state(root)
    files = list_project_files(root)
    rows: list[dict[str, Any]] = []
    languages: dict[str, int] = {}
    for p in files:
        try:
            data = p.read_bytes()
            rel = str(p.relative_to(root))
            ext = p.suffix.lower() or p.name
            languages[ext] = languages.get(ext, 0) + 1
            rows.append({
                "path": rel,
                "size": len(data),
                "mtime": int(p.stat().st_mtime),
                "sha1": hashlib.sha1(data).hexdigest(),
            })
        except OSError:
            continue
    payload = {
        "version": VERSION,
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "workspace": str(root),
        "file_count": len(rows),
        "languages": dict(sorted(languages.items(), key=lambda x: (-x[1], x[0]))),
        "files": rows,
    }
    save_json(state / "index.json", payload)
    if not quiet:
        console.print(f"[green]✓[/] Indexed [bold]{len(rows)}[/] files → .azzx/index.json")
    return payload


ARCHITECT_SYSTEM = """
You are a software architect. Analyze only the supplied project context and produce a concise,
practical architecture document in Markdown. Include: purpose, entry points, important modules,
data flow, configuration, external services, tests/build commands if visible, risks, and safe
rules a future coding agent should preserve. Never invent secrets or unseen components.
""".strip()


def generate_architecture(root: Path, forced_provider: str | None = None) -> None:
    cfg = load_config()
    context, selected, files = build_workspace_context(root, "architecture entrypoints modules configuration data flow tests", cfg)
    with console.status("[cyan]Building project architecture...[/]", spinner="dots"):
        result = get_router().chat_role([
            {"role": "system", "content": ARCHITECT_SYSTEM},
            {"role": "user", "content": context},
        ], "planner", forced_provider)
    state = ensure_workspace_state(root)
    atomic_write(state / "architecture.md", result.text.strip() + "\n")
    refresh_project_index(root, quiet=True)
    console.print(Panel(Markdown(result.text), title="PROJECT ARCHITECTURE", border_style="green"))
    show_route(result)


def create_project(root: Path, instruction: str, name: str | None, forced_provider: str | None = None) -> Path:
    target = root
    if name:
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "-", name.strip()).strip("-.")
        if not safe_name:
            raise AzzxError("Invalid project name.")
        target = (root / safe_name).resolve()
        try:
            target.relative_to(root.resolve())
        except ValueError as exc:
            raise AzzxError("Project target escaped current workspace.") from exc
        target.mkdir(parents=True, exist_ok=True)
    ensure_workspace_state(target)
    refresh_project_index(target, quiet=True)
    prompt = (
        instruction
        + "\nCreate a clean, runnable project. Include README.md, a suitable dependency manifest, "
          "and .gitignore when appropriate. Do not place credentials in source files; use examples/placeholders."
    )
    changed = run_edit_task(target, prompt, "create", forced_provider)
    if changed:
        refresh_project_index(target, quiet=True)
        console.print(f"[green bold]PROJECT READY[/]  {target}")
    return target


def run_shell_capture(root: Path, command: str, timeout: int = 120) -> tuple[int, str]:
    try:
        proc = subprocess.run(command, cwd=root, shell=True, text=True, capture_output=True, timeout=timeout)
        out = (proc.stdout or "") + (("\n" + proc.stderr) if proc.stderr else "")
        return proc.returncode, out[-40_000:]
    except subprocess.TimeoutExpired as exc:
        out = ((exc.stdout or "") if isinstance(exc.stdout, str) else "")
        out += "\n" + ((exc.stderr or "") if isinstance(exc.stderr, str) else "")
        return 124, (out + f"\nAZZX: timed out after {timeout}s")[-40_000:]


def run_debug_loop(root: Path, command: str, forced_provider: str | None = None, max_iterations: int | None = None) -> bool:
    cfg = load_config()
    limit = max_iterations or int(cfg.get("max_debug_iterations", 4))
    timeout = int(cfg.get("timeout_seconds", 120))
    for attempt in range(1, max(1, limit) + 1):
        console.print(Panel(f"[bold]{command}[/]\nIteration {attempt}/{limit}", title="AUTO DEBUG", border_style="yellow"))
        code, output = run_shell_capture(root, command, timeout)
        if output.strip():
            console.print(Panel(output[-12_000:], title=f"OUTPUT • exit {code}", border_style="dim"))
        if code == 0:
            console.print("[green bold]✓ Debug loop succeeded.[/]")
            write_history(root, {"action": "autodebug", "instruction": command, "result": "success", "iterations": attempt})
            return True
        problem = (
            f"The following command still fails. Fix the root cause, then preserve existing behavior.\n"
            f"COMMAND: {command}\nEXIT CODE: {code}\nOUTPUT:\n{output}"
        )
        changed = run_edit_task(root, problem, "fix", forced_provider)
        if not changed:
            break
    console.print("[red]✗ Auto debug stopped before the command succeeded.[/]")
    return False


def detect_test_command(root: Path) -> str | None:
    if (root / "pytest.ini").exists() or (root / "tests").exists() or "pytest" in (safe_read_text(root / "pyproject.toml") or "").lower():
        return f"{shlex.quote(sys.executable)} -m pytest -q"
    package = load_json(root / "package.json", {}) if (root / "package.json").exists() else {}
    test_script = ((package.get("scripts") or {}).get("test") if isinstance(package, dict) else None)
    if test_script and "no test specified" not in str(test_script).lower() and shutil.which("npm"):
        return "npm test"
    if (root / "go.mod").exists() and shutil.which("go"):
        return "go test ./..."
    if (root / "Cargo.toml").exists() and shutil.which("cargo"):
        return "cargo test -q"
    return None


def syntax_check_workspace(root: Path) -> list[str]:
    errors: list[str] = []
    for path in list_project_files(root):
        content = safe_read_text(path)
        if content is None:
            continue
        issue = validate_content(path, content)
        if issue:
            errors.append(f"{path.relative_to(root)}: {issue}")
            if len(errors) >= 40:
                break
    return errors


def run_tests(root: Path, command: str | None = None, quiet: bool = False) -> bool:
    errors = syntax_check_workspace(root)
    if errors:
        if not quiet:
            console.print(Panel("\n".join(errors[:20]), title="SYNTAX CHECK FAILED", border_style="red"))
        return False
    command = command or detect_test_command(root)
    if not command:
        if not quiet:
            console.print("[green]✓ Syntax validation passed.[/] [dim]No test command was auto-detected.[/]")
        return True
    if not quiet:
        console.print(f"[cyan]Running tests:[/] {command}")
    code, output = run_shell_capture(root, command, int(load_config().get("timeout_seconds", 120)))
    if output.strip() and not quiet:
        console.print(Panel(output[-12_000:], title=f"TEST OUTPUT • exit {code}", border_style="green" if code == 0 else "red"))
    return code == 0


def dependency_report(root: Path) -> dict[str, Any]:
    manifests = [name for name in ("requirements.txt", "pyproject.toml", "package.json", "go.mod", "Cargo.toml", "composer.json", "Gemfile") if (root / name).exists()]
    imports: set[str] = set()
    local_names = {p.stem for p in root.glob("*.py")} | {p.name for p in root.iterdir() if p.is_dir()}
    for p in list_project_files(root):
        if p.suffix != ".py":
            continue
        content = safe_read_text(p)
        if not content:
            continue
        try:
            tree = ast.parse(content)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                imports.add(node.module.split(".")[0])
    missing: list[str] = []
    stdlib = getattr(sys, "stdlib_module_names", set())
    import importlib.util
    for name in sorted(imports):
        if name in stdlib or name in local_names:
            continue
        try:
            found = importlib.util.find_spec(name) is not None
        except Exception:
            found = True
        if not found:
            missing.append(name)
    return {"manifests": manifests, "python_imports": sorted(imports), "missing_python_imports": missing}


def show_dependencies(root: Path, install: bool = False) -> None:
    report = dependency_report(root)
    table = Table(title="Dependency Agent", box=box.ROUNDED, border_style="cyan")
    table.add_column("Item")
    table.add_column("Value")
    table.add_row("Manifests", ", ".join(report["manifests"]) or "none")
    table.add_row("Python imports", str(len(report["python_imports"])))
    table.add_row("Missing imports", ", ".join(report["missing_python_imports"]) or "none detected")
    console.print(table)
    if install:
        req = root / "requirements.txt"
        if not req.exists():
            console.print("[yellow]Automatic install is limited to requirements.txt for safety.[/]")
            return
        require_permission("package.install", "Install Python dependencies from requirements.txt")
        if not Confirm.ask(f"Run {sys.executable} -m pip install -r requirements.txt ?", default=False):
            return
        proc = subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(req)], cwd=root)
        if proc.returncode != 0:
            raise AzzxError("Dependency installation failed.")


def git_root(root: Path) -> Path | None:
    if not shutil.which("git"):
        return None
    try:
        proc = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=root, capture_output=True, text=True, timeout=5)
        if proc.returncode == 0 and proc.stdout.strip():
            return Path(proc.stdout.strip()).resolve()
    except Exception:
        pass
    return None


def create_git_checkpoint(root: Path, label: str = "checkpoint", quiet: bool = False) -> Path | None:
    gr = git_root(root)
    if not gr:
        return None
    state = ensure_workspace_state(root)
    target = state / "checkpoints" / f"{now_stamp()}_{re.sub(r'[^A-Za-z0-9._-]+', '-', label)[:40]}"
    target.mkdir(parents=True, exist_ok=True)
    status = subprocess.run(["git", "status", "--short"], cwd=gr, capture_output=True, text=True, timeout=10)
    diff = subprocess.run(["git", "diff", "--binary"], cwd=gr, capture_output=True, text=True, timeout=20)
    staged = subprocess.run(["git", "diff", "--cached", "--binary"], cwd=gr, capture_output=True, text=True, timeout=20)
    atomic_write(target / "status.txt", status.stdout)
    atomic_write(target / "working.patch", diff.stdout)
    atomic_write(target / "staged.patch", staged.stdout)
    save_json(target / "meta.json", {"git_root": str(gr), "label": label, "time": dt.datetime.now().isoformat(timespec="seconds")})
    if not quiet:
        console.print(f"[green]✓ Git checkpoint:[/] {target.relative_to(root)}")
    return target


def git_command(root: Path, action: str, value: str = "") -> None:
    gr = git_root(root)
    if not gr:
        raise AzzxError("This workspace is not inside a Git repository, or git is unavailable.")
    if action == "status":
        args = ["git", "status", "--short", "--branch"]
    elif action == "diff":
        args = ["git", "diff"]
    elif action == "checkpoint":
        create_git_checkpoint(root, value or "manual")
        return
    elif action == "branch":
        if not value:
            raise AzzxError("Branch name required.")
        args = ["git", "switch", "-c", value]
    elif action == "commit":
        if not value:
            raise AzzxError("Commit message required.")
        require_permission("git.commit", f"Commit staged Git changes: {value}")
        if not Confirm.ask("Commit currently staged changes? AZZX will not stage files automatically.", default=False):
            return
        args = ["git", "commit", "-m", value]
    else:
        raise AzzxError(f"Unknown git action: {action}")
    proc = subprocess.run(args, cwd=gr, text=True, capture_output=True)
    text_out = (proc.stdout or "") + (("\n" + proc.stderr) if proc.stderr else "")
    console.print(Panel(text_out.strip() or f"exit {proc.returncode}", title=f"GIT {action.upper()}", border_style="cyan" if proc.returncode == 0 else "red"))
    if proc.returncode != 0:
        raise AzzxError(f"Git command failed: {action}")


def configure_roles() -> None:
    cfg = load_config()
    providers = load_providers()
    if not providers:
        raise AzzxError("Configure at least one provider first: azzx ai")
    roles = dict(cfg.get("role_providers") or {})
    for role in ("planner", "architect", "coder", "backend", "frontend", "database", "security", "qa", "reviewer", "tester"):
        items = [("", "AUTO / fallback router")] + [(pid, f"{p.get('name', pid)} • {p.get('model') or '-'}") for pid, p in providers.items()]
        current = roles.get(role, "")
        console.print(f"\n[bold]{role.upper()}[/] current: [cyan]{current or 'AUTO'}[/]")
        choice = choose_from_list(f"Provider for {role}", items, allow_cancel=True)
        if choice is not None:
            roles[role] = choice
    cfg["role_providers"] = roles
    cfg["smart_routing"] = True
    save_config(cfg)
    console.print("[green]✓ Smart routing roles saved.[/]")


PLAN_SYSTEM = """
You are the Planner agent in a local coding-agent pipeline. Analyze the project context and user goal.
Return a compact implementation plan in Markdown: files/symbols likely involved, ordered steps, tests/checks,
and risks. Do not write code and do not invent files that are not required.
""".strip()


def get_review_text(root: Path, focus: str, forced_provider: str | None = None) -> RouteResult:
    cfg = load_config()
    context, _, _ = build_workspace_context(root, focus or "review recent implementation", cfg)
    return get_router().chat_role([
        {"role": "system", "content": REVIEW_SYSTEM},
        {"role": "user", "content": f"Review the current implementation for this goal: {focus}\n\n{context}"},
    ], "reviewer", forced_provider)


def run_multi_agent(root: Path, goal: str, forced_provider: str | None = None) -> bool:
    cfg = load_config()
    context, _, _ = build_workspace_context(root, goal, cfg)
    with console.status("[cyan]Planner agent...[/]", spinner="dots"):
        plan = get_router().chat_role([
            {"role": "system", "content": PLAN_SYSTEM},
            {"role": "user", "content": f"GOAL: {goal}\n\n{context}"},
        ], "planner", forced_provider)
    console.print(Panel(Markdown(plan.text), title="PLANNER", border_style="cyan"))
    changed = run_edit_task(root, goal, "implement", forced_provider, extra_context=plan.text)
    if not changed:
        return False
    with console.status("[cyan]Reviewer agent...[/]", spinner="dots"):
        review = get_review_text(root, goal, forced_provider)
    console.print(Panel(Markdown(review.text), title="REVIEWER", border_style="magenta"))
    test_ok = run_tests(root)
    if not test_ok:
        console.print("[yellow]Tester found a failure. Running one repair pass...[/]")
        run_edit_task(root, f"Tests/checks failed after implementing: {goal}. Inspect the project and repair the regression.", "fix", forced_provider, extra_context=review.text)
        test_ok = run_tests(root)
    write_history(root, {"action": "agent", "instruction": goal, "result": "success" if test_ok else "needs_attention", "planner": plan.provider_id, "reviewer": review.provider_id})
    return test_ok


def plugin_dirs(root: Path) -> list[Path]:
    global_dir = CONFIG_HOME / "plugins"
    ensure_private_dir(global_dir)
    local_dir = ensure_workspace_state(root) / "plugins"
    return [local_dir, global_dir]


def load_plugins(root: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for d in reversed(plugin_dirs(root)):
        for p in d.glob("*.json"):
            obj = load_json(p, {})
            if isinstance(obj, dict) and obj.get("name") and obj.get("command"):
                result[str(obj["name"])] = obj
    return result


def plugin_command(root: Path, action: str, name: str = "", command: str = "", args: str = "", global_scope: bool = False) -> None:
    plugins = load_plugins(root)
    if action == "list":
        table = Table(title="AZZX Tool Plugins", box=box.ROUNDED, border_style="cyan")
        table.add_column("Name"); table.add_column("Description"); table.add_column("Command")
        for n, p in sorted(plugins.items()):
            table.add_row(n, str(p.get("description") or ""), str(p.get("command") or ""))
        console.print(table if plugins else "[yellow]No plugins configured.[/]")
        return
    if action == "add":
        if not name or not command:
            raise AzzxError("Plugin add requires NAME and COMMAND.")
        if not re.fullmatch(r"[A-Za-z0-9._-]+", name):
            raise AzzxError("Plugin name may only contain letters, numbers, dot, underscore, dash.")
        d = (CONFIG_HOME / "plugins") if global_scope else (ensure_workspace_state(root) / "plugins")
        d.mkdir(parents=True, exist_ok=True)
        save_json(d / f"{name}.json", {"name": name, "description": f"Custom command plugin: {name}", "command": command})
        console.print(f"[green]✓ Plugin saved:[/] {name}")
        return
    if action == "remove":
        removed = False
        for d in plugin_dirs(root):
            p = d / f"{name}.json"
            if p.exists(): p.unlink(); removed = True
        console.print("[green]✓ Removed.[/]" if removed else "[yellow]Plugin not found.[/]")
        return
    if action == "run":
        p = plugins.get(name)
        if not p:
            raise AzzxError(f"Plugin not found: {name}")
        template = str(p["command"])
        final = template.replace("{workspace}", shlex.quote(str(root))).replace("{args}", args)
        console.print(Panel(final, title=f"PLUGIN • {name}", border_style="yellow"))
        require_permission("shell.run", f"Run plugin command: {name}")
        if not Confirm.ask("Run this user-defined command?", default=False):
            return
        code, out = run_shell_capture(root, final, int(load_config().get("timeout_seconds", 120)))
        console.print(Panel(out.strip() or f"exit {code}", title="PLUGIN OUTPUT", border_style="green" if code == 0 else "red"))
        return
    raise AzzxError(f"Unknown plugin action: {action}")


def fetch_docs(root: Path, url: str, question: str, forced_provider: str | None = None) -> None:
    require_permission("network.http", f"Fetch documentation URL: {url}")
    if not re.match(r"^https?://", url, re.I):
        raise AzzxError("Docs URL must start with http:// or https://")
    try:
        response = httpx.get(url, timeout=30, follow_redirects=True, headers={"User-Agent": "AZZX/2.0"})
        response.raise_for_status()
    except Exception as exc:
        raise AzzxError(f"Failed to fetch documentation: {exc}") from exc
    text = response.text
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()[:50_000]
    prompt = f"Documentation URL: {url}\nQuestion: {question}\n\nDOCUMENT TEXT:\n{text}"
    result = get_router().chat_role([
        {"role": "system", "content": "Answer the user's coding/documentation question using the supplied document text. Distinguish what the document says from your inference."},
        {"role": "user", "content": prompt},
    ], "planner", forced_provider)
    console.print(Panel(Markdown(result.text), title="DOCS RESEARCH", border_style="cyan"))
    show_route(result)


def remote_command(host: str, remote_path: str, azzx_args: list[str]) -> None:
    require_permission("ssh", f"Connect to {host}")
    if not shutil.which("ssh"):
        raise AzzxError("ssh command is not installed.")
    if not re.fullmatch(r"[A-Za-z0-9._@:-]+", host):
        raise AzzxError("Invalid SSH host string.")
    quoted = " ".join(shlex.quote(x) for x in azzx_args)
    remote = f"cd {shlex.quote(remote_path)} && azzx {quoted}".strip()
    console.print(Panel(f"ssh {host} {remote}", title="REMOTE AZZX", border_style="yellow"))
    os.execvp("ssh", ["ssh", "-t", host, remote])



# ---------------------------- V3 FEATURES ----------------------------

SYMBOL_EXTS = {".py", ".pyi", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".gs", ".go", ".rs", ".java", ".kt", ".php", ".c", ".h", ".cpp", ".hpp"}


def _line_of_offset(text: str, offset: int) -> int:
    return text.count("\n", 0, max(0, offset)) + 1


def extract_symbols(path: Path, content: str) -> tuple[list[dict[str, Any]], set[str]]:
    """Best-effort symbol extractor. It is intentionally dependency-free."""
    symbols: list[dict[str, Any]] = []
    refs: set[str] = set()
    suffix = path.suffix.lower()
    if suffix in {".py", ".pyi"}:
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    symbols.append({"name": node.name, "kind": "function", "line": int(getattr(node, "lineno", 1))})
                elif isinstance(node, ast.ClassDef):
                    symbols.append({"name": node.name, "kind": "class", "line": int(getattr(node, "lineno", 1))})
                elif isinstance(node, ast.Name):
                    refs.add(node.id)
                elif isinstance(node, ast.Attribute):
                    refs.add(node.attr)
                elif isinstance(node, ast.Import):
                    refs.update(a.name.split(".")[0] for a in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    refs.add(node.module.split(".")[0])
            return symbols, refs
        except SyntaxError:
            pass

    patterns: list[tuple[str, str]] = [
        (r"(?m)^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(", "function"),
        (r"(?m)^\s*(?:export\s+)?class\s+([A-Za-z_$][\w$]*)\b", "class"),
        (r"(?m)^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=", "variable"),
        (r"(?m)^\s*func\s+(?:\([^)]*\)\s*)?([A-Za-z_]\w*)\s*\(", "function"),
        (r"(?m)^\s*(?:pub\s+)?(?:fn|struct|enum|trait)\s+([A-Za-z_]\w*)\b", "symbol"),
        (r"(?m)^\s*(?:public\s+|private\s+|protected\s+)?(?:class|interface|enum)\s+([A-Za-z_]\w*)\b", "class"),
        (r"(?m)^\s*function\s+([A-Za-z_]\w*)\s*\(", "function"),
    ]
    for pattern, kind in patterns:
        for m in re.finditer(pattern, content):
            symbols.append({"name": m.group(1), "kind": kind, "line": _line_of_offset(content, m.start())})
    for ident in re.findall(r"\b[A-Za-z_$][A-Za-z0-9_$]{2,}\b", content):
        refs.add(ident)
    # Stable de-duplication.
    seen: set[tuple[str, int]] = set()
    unique: list[dict[str, Any]] = []
    for row in symbols:
        key=(str(row["name"]), int(row["line"]))
        if key not in seen:
            seen.add(key); unique.append(row)
    return unique, refs


def refresh_repository_map(root: Path, quiet: bool = False) -> dict[str, Any]:
    state = ensure_workspace_state(root)
    files = list_project_files(root)
    file_rows: list[dict[str, Any]] = []
    definitions: dict[str, list[dict[str, Any]]] = {}
    references: dict[str, list[str]] = {}
    for path in files:
        if path.suffix.lower() not in SYMBOL_EXTS:
            continue
        content = safe_read_text(path)
        if content is None:
            continue
        rel = str(path.relative_to(root))
        syms, refs = extract_symbols(path, content)
        file_rows.append({"path": rel, "symbols": syms, "reference_count": len(refs)})
        for sym in syms:
            definitions.setdefault(sym["name"], []).append({"path": rel, "line": sym["line"], "kind": sym["kind"]})
        for name in refs:
            references.setdefault(name, []).append(rel)
    for name, paths in list(references.items()):
        references[name] = sorted(set(paths))[:200]
    payload = {
        "version": VERSION,
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "file_count": len(file_rows),
        "symbol_count": sum(len(x["symbols"]) for x in file_rows),
        "files": file_rows,
        "definitions": definitions,
        "references": references,
    }
    save_json(state / "repo_map.json", payload)
    if not quiet:
        console.print(f"[green]✓[/] Repository map: [bold]{payload['symbol_count']}[/] symbols across {len(file_rows)} files → .azzx/repo_map.json")
    return payload


def load_repository_map(root: Path, refresh_if_missing: bool = True) -> dict[str, Any]:
    path = ensure_workspace_state(root) / "repo_map.json"
    data = load_json(path, {})
    if refresh_if_missing and not data:
        return refresh_repository_map(root, quiet=True)
    return data if isinstance(data, dict) else {}


def show_repository_map(root: Path) -> None:
    repo = refresh_repository_map(root, quiet=True)
    defs = repo.get("definitions") or {}
    table = Table(title="Repository Intelligence", box=box.ROUNDED, border_style="cyan")
    table.add_column("Metric"); table.add_column("Value", justify="right")
    table.add_row("Indexed files", str(repo.get("file_count", 0)))
    table.add_row("Symbols", str(repo.get("symbol_count", 0)))
    table.add_row("Unique names", str(len(defs)))
    console.print(table)
    top = sorted(defs.items(), key=lambda x: (-len(x[1]), x[0].lower()))[:30]
    if top:
        t = Table(title="Symbols", box=box.SIMPLE)
        t.add_column("Name"); t.add_column("Definitions", justify="right"); t.add_column("Location")
        for name, rows in top:
            first = rows[0]
            t.add_row(name, str(len(rows)), f"{first['path']}:{first['line']}")
        console.print(t)


def show_symbol(root: Path, name: str, refs_only: bool = False) -> None:
    repo = load_repository_map(root)
    definitions = (repo.get("definitions") or {}).get(name, [])
    references = (repo.get("references") or {}).get(name, [])
    if not definitions and not references:
        # case-insensitive fallback
        lookup = {str(k).lower(): k for k in (repo.get("definitions") or {})}
        actual = lookup.get(name.lower())
        if actual:
            name = actual
            definitions = (repo.get("definitions") or {}).get(name, [])
            references = (repo.get("references") or {}).get(name, [])
    if not definitions and not references:
        raise AzzxError(f"Symbol not found: {name}. Run `azzx map` to refresh the repository map.")
    table = Table(title=f"References • {name}" if refs_only else f"Symbol • {name}", box=box.ROUNDED, border_style="cyan")
    table.add_column("Type"); table.add_column("Location")
    if not refs_only:
        for row in definitions:
            table.add_row(str(row.get("kind", "definition")), f"{row.get('path')}:{row.get('line')}")
    for rel in references[:100]:
        table.add_row("reference", str(rel))
    console.print(table)


def select_relevant_files(root: Path, files: list[Path], query: str, max_files: int) -> list[Path]:
    """V3 context selector: path/content ranking + repository-symbol boost."""
    explicit: list[Path] = []
    query_lower = query.lower()
    by_rel = {str(p.relative_to(root)): p for p in files}
    for p in files:
        rel = str(p.relative_to(root))
        if rel.lower() in query_lower or p.name.lower() in query_lower:
            explicit.append(p)
    scores: dict[Path, float] = {p: score_file(p, root, query) for p in files}
    candidates = sorted(files, key=lambda p: scores[p], reverse=True)[:max(max_files * 5, 30)]
    for p in candidates:
        scores[p] = score_file(p, root, query, safe_read_text(p) or "")
    if load_config().get("context_symbol_boost", True):
        try:
            repo = load_repository_map(root)
            tokens = tokenize_query(query)
            definitions = repo.get("definitions") or {}
            references = repo.get("references") or {}
            for token in tokens:
                matched_names = [n for n in definitions if token in str(n).lower()][:30]
                for name in matched_names:
                    for d in definitions.get(name, []):
                        p = by_rel.get(str(d.get("path")))
                        if p: scores[p] = scores.get(p, 0) + 25.0
                    for rel in references.get(name, [])[:25]:
                        p = by_rel.get(rel)
                        if p: scores[p] = scores.get(p, 0) + 8.0
        except Exception:
            pass
    ranked = sorted(files, key=lambda p: scores.get(p, 0), reverse=True)
    return list(dict.fromkeys(explicit + ranked))[:max_files]


def build_workspace_context(root: Path, query: str, cfg: dict[str, Any], extra_files: list[str] | None = None) -> tuple[str, list[Path], list[Path]]:
    files = list_project_files(root)
    max_files = int(cfg.get("max_files", 8))
    selected = select_relevant_files(root, files, query, max_files)
    if extra_files:
        for rel in extra_files:
            try: p = safe_workspace_path(root, rel)
            except AzzxError: continue
            if p.exists() and p.is_file() and is_text_file(p) and p not in selected:
                selected.append(p)
    selected = selected[: max_files + 6]
    state = ensure_workspace_state(root)
    memory = safe_read_text(state / "memory.md", 16_000) or ""
    architecture = safe_read_text(state / "architecture.md", 20_000) or ""
    project_notes = ""
    skill_context = active_skill_context(root)
    if skill_context.strip(): project_notes += skill_context + "\n"
    if memory.strip(): project_notes += f"PROJECT MEMORY:\n{memory}\n\n"
    if architecture.strip() and "Not generated yet" not in architecture:
        project_notes += f"PROJECT ARCHITECTURE:\n{architecture}\n\n"
    symbol_hint = ""
    try:
        repo = load_repository_map(root)
        defs = repo.get("definitions") or {}
        tokens = tokenize_query(query)
        found=[]
        for token in tokens:
            for name, rows in defs.items():
                if token in str(name).lower():
                    found.append(f"{name}: " + ", ".join(f"{r['path']}:{r['line']}" for r in rows[:3]))
                    if len(found) >= 20: break
            if len(found) >= 20: break
        if found: symbol_hint = "RELEVANT SYMBOL MAP:\n" + "\n".join(found) + "\n\n"
    except Exception:
        pass
    context = (
        f"WORKSPACE: {root}\n\n{project_notes}{symbol_hint}"
        f"PROJECT TREE:\n{project_tree(root, files)}\n\n"
        f"SELECTED FILE CONTENTS:\n{format_file_context(root, selected, int(cfg.get('max_context_chars', 24000)))}"
    )
    return context, selected, files


# ---- Persistent tasks -------------------------------------------------------

def task_dir(root: Path) -> Path:
    d = ensure_workspace_state(root) / "tasks"; d.mkdir(parents=True, exist_ok=True); return d


def _task_path(root: Path, task_id: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", task_id): raise AzzxError("Invalid task id.")
    return task_dir(root) / f"{task_id}.json"


def _next_task_id(root: Path) -> str:
    nums=[]
    for p in task_dir(root).glob("*.json"):
        if p.stem.isdigit(): nums.append(int(p.stem))
    return f"{(max(nums, default=0)+1):04d}"


def _plan_steps_from_text(text: str) -> list[dict[str, Any]]:
    steps=[]
    for line in text.splitlines():
        cleaned=re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", line).strip()
        if cleaned and len(cleaned) > 4 and not cleaned.startswith("#"):
            steps.append({"text": cleaned[:300], "done": False})
        if len(steps) >= 12: break
    return steps


def task_create(root: Path, goal: str, forced_provider: str | None = None) -> str:
    tid=_next_task_id(root)
    plan=""
    try:
        cfg=load_config(); context,_,_=build_workspace_context(root, goal, cfg)
        result=get_router().chat_role([
            {"role":"system","content":PLAN_SYSTEM},
            {"role":"user","content":f"Create an implementation plan for a persistent task. GOAL: {goal}\n\n{context}"},
        ], "planner", forced_provider)
        plan=result.text
    except Exception as exc:
        plan=f"Manual task created. Planner unavailable: {exc}"
    obj={"id":tid,"goal":goal,"status":"active","created_at":dt.datetime.now().isoformat(timespec="seconds"),"updated_at":dt.datetime.now().isoformat(timespec="seconds"),"plan":plan,"steps":_plan_steps_from_text(plan),"runs":[]}
    save_json(_task_path(root,tid),obj)
    console.print(Panel(Markdown(plan), title=f"TASK #{tid} • ACTIVE", border_style="cyan"))
    return tid


def task_list(root: Path) -> None:
    rows=[]
    for p in sorted(task_dir(root).glob("*.json")):
        obj=load_json(p,{})
        if isinstance(obj,dict): rows.append(obj)
    table=Table(title="AZZX Tasks",box=box.ROUNDED,border_style="cyan")
    table.add_column("ID"); table.add_column("Status"); table.add_column("Goal"); table.add_column("Updated")
    for obj in rows:
        table.add_row(str(obj.get("id")),str(obj.get("status")),str(obj.get("goal",""))[:90],str(obj.get("updated_at","")))
    console.print(table if rows else "[yellow]No tasks yet.[/]")


def task_show(root: Path, task_id: str) -> dict[str, Any]:
    obj=load_json(_task_path(root,task_id),{})
    if not obj: raise AzzxError(f"Task not found: {task_id}")
    body=f"**Goal:** {obj.get('goal')}\n\n**Status:** {obj.get('status')}\n\n## Plan\n{obj.get('plan') or '-'}"
    console.print(Panel(Markdown(body),title=f"TASK #{task_id}",border_style="cyan")); return obj


def task_set_status(root: Path, task_id: str, status: str) -> None:
    path=_task_path(root,task_id); obj=load_json(path,{})
    if not obj: raise AzzxError(f"Task not found: {task_id}")
    obj["status"]=status; obj["updated_at"]=dt.datetime.now().isoformat(timespec="seconds"); save_json(path,obj)
    console.print(f"[green]✓[/] Task {task_id} → {status}")


def task_resume(root: Path, task_id: str, forced_provider: str | None = None) -> bool:
    path=_task_path(root,task_id); obj=load_json(path,{})
    if not obj: raise AzzxError(f"Task not found: {task_id}")
    if obj.get("status") == "done": console.print("[yellow]Task is already done.[/]"); return True
    obj["status"]="active"; save_json(path,obj)
    goal=str(obj.get("goal") or "")
    plan=str(obj.get("plan") or "")
    ok=run_multi_agent(root, goal + "\n\nPersistent task plan:\n" + plan, forced_provider)
    obj=load_json(path,obj); obj.setdefault("runs",[]).append({"time":dt.datetime.now().isoformat(timespec="seconds"),"success":bool(ok)})
    obj["status"]="done" if ok else "active"; obj["updated_at"]=dt.datetime.now().isoformat(timespec="seconds"); save_json(path,obj)
    return ok


def task_command(root: Path, action: str, task_id: str = "", text: str = "", forced_provider: str | None = None) -> None:
    if action=="list": task_list(root)
    elif action=="create": task_create(root,text,forced_provider)
    elif action=="show": task_show(root,task_id)
    elif action=="resume": task_resume(root,task_id,forced_provider)
    elif action in {"pause","done"}: task_set_status(root,task_id,"paused" if action=="pause" else "done")
    else: raise AzzxError(f"Unknown task action: {action}")


# ---- Diagnostics ------------------------------------------------------------

def collect_diagnostics(root: Path, command: str = "") -> str:
    chunks=[f"WORKSPACE: {root}",f"PLATFORM: {platform.platform()}",f"PYTHON: {platform.python_version()}"]
    gr=git_root(root)
    if gr:
        for label,args in (("GIT STATUS",["git","status","--short","--branch"]),("RECENT COMMITS",["git","log","-5","--oneline"])):
            try:
                pr=subprocess.run(args,cwd=gr,capture_output=True,text=True,timeout=10); chunks.append(label+":\n"+(pr.stdout+pr.stderr)[-8000:])
            except Exception: pass
    dep=dependency_report(root); chunks.append("DEPENDENCIES:\n"+json.dumps(dep,indent=2)[:10000])
    syntax=syntax_check_workspace(root); chunks.append("SYNTAX:\n"+("OK" if not syntax else "\n".join(syntax[:30])))
    if command:
        code,out=run_shell_capture(root,command,int(load_config().get("timeout_seconds",120)))
        chunks.append(f"COMMAND: {command}\nEXIT: {code}\nOUTPUT:\n{out[-16000:]}")
    logs=[]
    for p in root.rglob("*.log"):
        try:
            if any(part in IGNORE_DIRS for part in p.relative_to(root).parts): continue
            txt=safe_read_text(p,100_000)
            if txt: logs.append(f"{p.relative_to(root)}:\n{txt[-5000:]}")
        except Exception: continue
        if len(logs)>=3: break
    if logs: chunks.append("RECENT LOGS:\n"+"\n\n".join(logs))
    return "\n\n".join(chunks)[-50000:]


def run_diagnose(root: Path, command: str = "", forced_provider: str | None = None) -> None:
    diagnostics=collect_diagnostics(root,command)
    cfg=load_config(); context,_,_=build_workspace_context(root, command or "diagnose runtime regression", cfg)
    result=get_router().chat_role([
        {"role":"system","content":"You are a senior debugging engineer. Diagnose root causes from supplied facts. Separate confirmed evidence from hypotheses. Recommend the smallest safe next fix; do not invent logs or code."},
        {"role":"user","content":diagnostics+"\n\nCODE CONTEXT:\n"+context},
    ],"reviewer",forced_provider)
    console.print(Panel(Markdown(result.text),title="DIAGNOSIS",border_style="magenta")); show_route(result)
    write_history(root,{"action":"diagnose","instruction":command,"result":"diagnosed","provider":result.provider_id})


def watch_command(root: Path, command: str, cycles: int, interval: int, forced_provider: str | None = None) -> bool:
    cycles=max(1,min(cycles,50)); interval=max(1,min(interval,3600))
    for i in range(1,cycles+1):
        console.print(f"[cyan]Watch cycle {i}/{cycles}[/]  {command}")
        code,out=run_shell_capture(root,command,int(load_config().get("timeout_seconds",120)))
        if code!=0:
            console.print(Panel(out[-12000:] or f"exit {code}",title="WATCH FAILURE",border_style="red"))
            return run_debug_loop(root,command,forced_provider)
        if i<cycles: time.sleep(interval)
    console.print("[green]✓ Watch cycles completed without failures.[/]"); return True


# ---- Build / package --------------------------------------------------------

def detect_build(root: Path) -> tuple[str,str] | None:
    if (root / "gradlew").exists():
        return ("android", "./gradlew assembleDebug")
    if (root / "package.json").exists():
        pkg = load_json(root / "package.json", {})
        scripts = (pkg.get("scripts") or {}) if isinstance(pkg, dict) else {}
        if "build" in scripts and shutil.which("npm"):
            return ("node", "npm run build")
    if (root / "Cargo.toml").exists() and shutil.which("cargo"):
        return ("rust", "cargo build --release")
    if (root / "go.mod").exists() and shutil.which("go"):
        return ("go", "go build ./...")
    if (root / "pyproject.toml").exists():
        return ("python", "python -m build")
    if (root / "Makefile").exists() and shutil.which("make"):
        return ("make", "make")
    return None


def package_tar(root: Path, output_name: str = "") -> Path:
    dist = root / "dist"
    dist.mkdir(exist_ok=True)
    base = re.sub(r"[^A-Za-z0-9._-]+", "-", root.name).strip("-") or "project"
    filename = output_name or f"{base}-{VERSION}.tar.gz"
    if Path(filename).name != filename or filename in {".", ".."}:
        raise AzzxError("Invalid package output filename.")
    target = dist / filename
    with tarfile.open(target, "w:gz") as tf:
        for path in root.rglob("*"):
            try:
                rel = path.relative_to(root)
            except ValueError:
                continue
            if not rel.parts or any(part in IGNORE_DIRS or part == ".azzx" for part in rel.parts):
                continue
            if rel.parts[0] == "dist":
                continue
            tf.add(path, arcname=str(Path(base) / rel), recursive=False)
    return target


def project_package_meta(root: Path) -> dict[str, Any]:
    explicit_path = root / ".azzx-package.json"
    explicit = load_json(explicit_path, {}) if explicit_path.exists() else {}
    if isinstance(explicit, dict) and explicit:
        return explicit
    name = re.sub(r"[^a-z0-9+.-]+", "-", root.name.lower()).strip("-") or "azzx-app"
    version = "0.1.0"
    description = f"Package generated by AZZX for {root.name}"
    entry = ""
    pyproject = safe_read_text(root / "pyproject.toml") or ""
    m = re.search(r'(?m)^name\s*=\s*["\']([^"\']+)', pyproject)
    if m:
        name = re.sub(r"[^a-z0-9+.-]+", "-", m.group(1).lower()).strip("-")
    m = re.search(r'(?m)^version\s*=\s*["\']([^"\']+)', pyproject)
    if m:
        version = m.group(1)
    for candidate in ("main.py", "app.py", "cli.py"):
        if (root / candidate).exists():
            entry = candidate
            break
    return {
        "name": name,
        "version": version,
        "description": description,
        "entrypoint": entry,
        "runtime": "python3",
    }


def _copy_project_for_package(root: Path, destination: Path) -> None:
    for path in root.rglob("*"):
        rel = path.relative_to(root)
        if any(part in IGNORE_DIRS or part in {".azzx", "dist"} for part in rel.parts):
            continue
        dst = destination / rel
        if path.is_dir():
            dst.mkdir(parents=True, exist_ok=True)
        elif path.is_file():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dst)


def build_deb(root: Path) -> Path:
    if not shutil.which("dpkg-deb"):
        raise AzzxError("dpkg-deb is not installed. On Debian/Ubuntu: sudo apt install dpkg-dev")
    meta = project_package_meta(root)
    entry = str(meta.get("entrypoint") or "")
    if not entry or not (root / entry).is_file():
        raise AzzxError("Debian packaging needs an entrypoint. Add .azzx-package.json with an existing 'entrypoint', e.g. main.py.")
    name = re.sub(r"[^a-z0-9+.-]+", "-", str(meta.get("name") or "azzx-app").lower()).strip("-")
    version = re.sub(r"[^A-Za-z0-9.+:~_-]+", "-", str(meta.get("version") or "0.1.0")).strip("-") or "0.1.0"
    runtime = str(meta.get("runtime") or "python3")
    with tempfile.TemporaryDirectory() as td:
        stage = Path(td) / f"{name}_{version}"
        appdir = stage / "opt" / name
        bindir = stage / "usr" / "bin"
        debian = stage / "DEBIAN"
        appdir.mkdir(parents=True)
        bindir.mkdir(parents=True)
        debian.mkdir(parents=True)
        _copy_project_for_package(root, appdir)
        control = (
            f"Package: {name}\n"
            f"Version: {version}\n"
            "Section: utils\n"
            "Priority: optional\n"
            "Architecture: all\n"
            "Maintainer: Local User\n"
            f"Depends: {runtime}\n"
            f"Description: {meta.get('description') or name}\n"
        )
        atomic_write(debian / "control", control)
        launcher = bindir / name
        launcher_text = "#!/usr/bin/env bash\n" + f"exec {shlex.quote(runtime)} /opt/{name}/{entry} \"$@\"\n"
        atomic_write(launcher, launcher_text, 0o755)
        dist = root / "dist"
        dist.mkdir(exist_ok=True)
        target = dist / f"{name}_{version}_all.deb"
        pr = subprocess.run(["dpkg-deb", "--build", str(stage), str(target)], capture_output=True, text=True)
        if pr.returncode != 0:
            raise AzzxError("dpkg-deb failed: " + (pr.stderr or pr.stdout)[-2000:])
    return target


def build_arch_package(root: Path) -> Path:
    meta = project_package_meta(root)
    entry = str(meta.get("entrypoint") or "")
    if not entry or not (root / entry).is_file():
        raise AzzxError("Arch packaging needs an existing entrypoint. Add .azzx-package.json if auto-detection is wrong.")
    name = re.sub(r"[^a-z0-9@._+\-]+", "-", str(meta.get("name") or "azzx-app").lower()).strip("-")
    version = re.sub(r"[^A-Za-z0-9.+_-]+", "-", str(meta.get("version") or "0.1.0")).strip("-") or "0.1.0"
    out = root / "dist" / "arch"
    out.mkdir(parents=True, exist_ok=True)
    archive = package_tar(root, f"{name}-{version}.tar.gz")
    archive_root = re.sub(r"[^A-Za-z0-9._-]+", "-", root.name).strip("-") or "project"
    # This is a PKGBUILD scaffold. makepkg remains an explicit user action because PKGBUILD executes shell code.
    pkgbuild = (
        f"pkgname={name}\n"
        f"pkgver={version}\n"
        "pkgrel=1\n"
        f"pkgdesc={json.dumps(str(meta.get('description') or name))}\n"
        "arch=('any')\n"
        "depends=('python')\n"
        f"source=('{archive.name}')\n"
        "sha256sums=('SKIP')\n"
        "package() {\n"
        "  install -dm755 \"$pkgdir/opt/$pkgname\" \"$pkgdir/usr/bin\"\n"
        f"  cp -a \"$srcdir/{archive_root}/.\" \"$pkgdir/opt/$pkgname/\"\n"
        f"  printf '%s\\n' '#!/usr/bin/env bash' 'exec python3 /opt/{name}/{entry} \"$@\"' > \"$pkgdir/usr/bin/{name}\"\n"
        f"  chmod +x \"$pkgdir/usr/bin/{name}\"\n"
        "}\n"
    )
    atomic_write(out / "PKGBUILD", pkgbuild)
    shutil.copy2(archive, out / archive.name)
    return out / "PKGBUILD"


def run_build(root: Path, target: str = "auto") -> bool:
    if target in {"tar", "archive", "portable"}:
        p = package_tar(root)
        console.print(f"[green]✓ Package:[/] {p.relative_to(root)}")
        return True
    if target == "deb":
        p = build_deb(root)
        console.print(f"[green]✓ Debian package:[/] {p.relative_to(root)}")
        return True
    if target == "arch":
        p = build_arch_package(root)
        console.print(f"[green]✓ PKGBUILD generated:[/] {p.relative_to(root)}")
        return True
    if target == "apk":
        if not (root / "gradlew").exists():
            raise AzzxError("gradlew not found; APK build requires an Android/Gradle project.")
        cmd = "./gradlew assembleDebug"
    elif target == "web":
        if not (root / "package.json").exists():
            raise AzzxError("package.json not found; web build expects a Node project.")
        cmd = "npm run build"
    elif target == "executable":
        meta = project_package_meta(root)
        entry = str(meta.get("entrypoint") or "")
        if not entry:
            raise AzzxError("No Python entrypoint detected. Add .azzx-package.json.")
        if not shutil.which("pyinstaller"):
            raise AzzxError("PyInstaller is not installed in this environment.")
        cmd = f"pyinstaller --onefile {shlex.quote(entry)}"
    else:
        detected = detect_build(root)
        if target not in {"auto", "native"}:
            commands = {
                "node": "npm run build",
                "go": "go build ./...",
                "rust": "cargo build --release",
                "python": "python -m build",
                "make": "make",
            }
            cmd = commands.get(target)
            if not cmd:
                raise AzzxError("Unknown build target.")
        else:
            if not detected:
                p = package_tar(root)
                console.print(f"[yellow]No native build detected; created portable archive:[/] {p.relative_to(root)}")
                return True
            _, cmd = detected
    console.print(Panel(cmd, title="BUILD", border_style="yellow"))
    code, out = run_shell_capture(root, cmd, max(300, int(load_config().get("timeout_seconds", 120))))
    console.print(Panel(out[-16000:] or f"exit {code}", title="BUILD OUTPUT", border_style="green" if code == 0 else "red"))
    return code == 0


def release_project(root: Path, version: str = "") -> Path:
    if not run_tests(root, quiet=False):
        raise AzzxError("Release aborted because tests/checks failed.")
    meta = project_package_meta(root)
    if version:
        meta["version"] = version
    safe_name = re.sub(r"[^A-Za-z0-9._+-]+", "-", str(meta.get("name") or root.name)).strip("-") or "project"
    safe_version = re.sub(r"[^A-Za-z0-9._+~-]+", "-", str(meta.get("version") or "0.1.0")).strip("-") or "0.1.0"
    meta["name"] = safe_name
    meta["version"] = safe_version
    archive = package_tar(root, f"{safe_name}-{safe_version}.tar.gz")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    manifest = {
        "name": meta.get("name"),
        "version": meta.get("version"),
        "created_at": dt.datetime.now().isoformat(timespec="seconds"),
        "artifact": str(archive.relative_to(root)),
        "sha256": digest,
        "git_head": "",
    }
    gr = git_root(root)
    if gr:
        pr = subprocess.run(["git", "rev-parse", "HEAD"], cwd=gr, capture_output=True, text=True)
        manifest["git_head"] = pr.stdout.strip() if pr.returncode == 0 else ""
    target = root / "dist" / "release.json"
    save_json(target, manifest)
    console.print(Panel(json.dumps(manifest, indent=2), title="RELEASE MANIFEST", border_style="green"))
    return target


# ---- Web research -----------------------------------------------------------

def _strip_html(text: str) -> str:
    text=re.sub(r"(?is)<(script|style|noscript).*?>.*?</\1>"," ",text)
    text=re.sub(r"(?s)<[^>]+>"," ",text)
    text=(text.replace("&amp;","&").replace("&lt;","<").replace("&gt;",">").replace("&quot;",'"').replace("&#x27;","'"))
    return re.sub(r"\s+"," ",text).strip()


def web_search_basic(query: str, limit: int = 5, domain: str = "") -> list[dict[str,str]]:
    q=query + (f" site:{domain}" if domain else "")
    url="https://html.duckduckgo.com/html/?q="+urllib.parse.quote_plus(q)
    try:
        r=httpx.get(url,timeout=20,follow_redirects=True,headers={"User-Agent":"Mozilla/5.0 AZZX/3.0"}); r.raise_for_status()
    except Exception as exc: raise AzzxError(f"Web search failed: {exc}") from exc
    results=[]
    pattern=re.compile(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',re.I|re.S)
    for href,title in pattern.findall(r.text):
        href=href.replace("&amp;","&")
        parsed=urllib.parse.urlparse(href)
        if "duckduckgo.com" in parsed.netloc:
            qs=urllib.parse.parse_qs(parsed.query); href=(qs.get("uddg") or [href])[0]
        if href.startswith("http"):
            results.append({"title":_strip_html(title),"url":href})
        if len(results)>=limit: break
    return results


def run_research(root: Path, query: str, domain: str = "", forced_provider: str | None = None) -> None:
    cfg=load_config(); max_results=int(cfg.get("research_max_results",5)); fetch_n=int(cfg.get("research_fetch_sources",3))
    results=web_search_basic(query,max_results,domain)
    if not results: raise AzzxError("Search returned no usable results.")
    sources=[]
    for i,row in enumerate(results[:fetch_n],1):
        try:
            r=httpx.get(row["url"],timeout=20,follow_redirects=True,headers={"User-Agent":"Mozilla/5.0 AZZX/3.0"}); r.raise_for_status(); body=_strip_html(r.text)[:18000]
        except Exception as exc: body=f"FETCH ERROR: {exc}"
        sources.append(f"SOURCE {i}: {row['title']}\nURL: {row['url']}\nTEXT:\n{body}")
    result=get_router().chat_role([
        {"role":"system","content":"You are a technical research agent. Answer from the supplied current web sources. Prefer official documentation. Explicitly distinguish sourced facts from inference and include the source URLs you used."},
        {"role":"user","content":f"QUERY: {query}\n\n"+"\n\n".join(sources)},
    ],"planner",forced_provider)
    console.print(Panel(Markdown(result.text),title="TECHNICAL RESEARCH",border_style="cyan")); show_route(result)
    console.print("\n[bold]Sources[/]")
    for i,row in enumerate(results,1): console.print(f" {i}. {row['title']}\n    {row['url']}")


# ---- MCP/tool protocol ------------------------------------------------------
MCP_MODERN_VERSION="2026-07-28"
MCP_LEGACY_VERSION="2025-11-25"


def mcp_dirs(root: Path) -> list[Path]:
    g=CONFIG_HOME/"mcp"; ensure_private_dir(g); l=ensure_workspace_state(root)/"mcp"; l.mkdir(parents=True,exist_ok=True); return [l,g]


def load_mcp_servers(root: Path) -> dict[str,dict[str,Any]]:
    out={}
    for d in reversed(mcp_dirs(root)):
        for p in d.glob("*.json"):
            obj=load_json(p,{})
            if isinstance(obj,dict) and obj.get("name") and obj.get("command"): out[str(obj["name"])]=obj
    return out


def _readline_timeout(stream: Any, timeout: float) -> str:
    q: queue.Queue[Any]=queue.Queue(maxsize=1)
    def worker():
        try: q.put(stream.readline())
        except Exception as exc: q.put(exc)
    threading.Thread(target=worker,daemon=True).start()
    try: item=q.get(timeout=timeout)
    except queue.Empty as exc: raise TimeoutError("MCP server response timed out") from exc
    if isinstance(item,Exception): raise item
    if item=="": raise AzzxError("MCP server closed stdout.")
    return str(item)


def _mcp_send(proc: subprocess.Popen[str], payload: dict[str,Any]) -> None:
    assert proc.stdin is not None; proc.stdin.write(json.dumps(payload,separators=(",",":"))+"\n"); proc.stdin.flush()


def _mcp_recv_for_id(proc: subprocess.Popen[str], req_id: int, timeout: float = 8.0) -> dict[str,Any]:
    assert proc.stdout is not None
    deadline=time.time()+timeout
    while time.time()<deadline:
        line=_readline_timeout(proc.stdout,max(0.1,deadline-time.time())).strip()
        if not line: continue
        try: obj=json.loads(line)
        except json.JSONDecodeError: continue
        if isinstance(obj,dict) and obj.get("id")==req_id: return obj
    raise TimeoutError("MCP response timed out")


def _spawn_mcp(root: Path, server: dict[str,Any]) -> subprocess.Popen[str]:
    cmd=[str(server["command"])] + [str(x) for x in (server.get("args") or [])]
    env=os.environ.copy(); env.update({str(k):str(v) for k,v in (server.get("env") or {}).items()})
    try: return subprocess.Popen(cmd,cwd=root,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1,env=env)
    except FileNotFoundError as exc: raise AzzxError(f"MCP command not found: {cmd[0]}") from exc




def _close_mcp_process(proc: subprocess.Popen[str]) -> None:
    try:
        if proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=1)
    except Exception:
        try:
            proc.kill(); proc.wait(timeout=1)
        except Exception:
            pass
    for stream in (proc.stdin, proc.stdout, proc.stderr):
        try:
            if stream is not None:
                stream.close()
        except Exception:
            pass

def _modern_meta() -> dict[str,Any]:
    return {"io.modelcontextprotocol/protocolVersion":MCP_MODERN_VERSION,"io.modelcontextprotocol/clientCapabilities":{},"io.modelcontextprotocol/clientInfo":{"name":"azzx","version":VERSION}}


def _mcp_open(root: Path, server: dict[str,Any]) -> tuple[subprocess.Popen[str],str]:
    mode=str(server.get("protocol") or load_config().get("mcp_protocol","auto"))
    if mode in {"auto","modern"}:
        proc=_spawn_mcp(root,server)
        try:
            _mcp_send(proc,{"jsonrpc":"2.0","id":1,"method":"server/discover","params":{"_meta":_modern_meta()}})
            res=_mcp_recv_for_id(proc,1,2.5 if mode=="auto" else 8)
            if "result" in res:
                return proc,"modern"
            _close_mcp_process(proc)
            if mode=="modern":
                raise AzzxError(f"MCP modern discovery failed: {res.get('error') or 'no result'}")
        except Exception:
            if proc.poll() is None or any(x is not None and not x.closed for x in (proc.stdin, proc.stdout, proc.stderr)):
                _close_mcp_process(proc)
            if mode=="modern": raise AzzxError("MCP modern discovery failed.")
    proc=_spawn_mcp(root,server)
    _mcp_send(proc,{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":MCP_LEGACY_VERSION,"capabilities":{},"clientInfo":{"name":"azzx","version":VERSION}}})
    try:
        res=_mcp_recv_for_id(proc,1,8)
    except Exception:
        _close_mcp_process(proc)
        raise
    if "error" in res:
        _close_mcp_process(proc)
        raise AzzxError(f"MCP initialize failed: {res['error']}")
    _mcp_send(proc,{"jsonrpc":"2.0","method":"notifications/initialized","params":{}})
    return proc,"legacy"


def _mcp_request(proc: subprocess.Popen[str], era: str, req_id: int, method: str, params: dict[str,Any]) -> dict[str,Any]:
    params=dict(params)
    if era=="modern": params["_meta"]=_modern_meta()
    _mcp_send(proc,{"jsonrpc":"2.0","id":req_id,"method":method,"params":params})
    res=_mcp_recv_for_id(proc,req_id,20)
    if "error" in res: raise AzzxError(f"MCP {method} error: {res['error']}")
    result=res.get("result") or {}
    if isinstance(result,dict) and result.get("resultType")=="input_required": raise AzzxError("This MCP tool requested multi-round-trip user input, which AZZX Lite does not automate yet.")
    return result if isinstance(result,dict) else {"value":result}


def mcp_command(root: Path, action: str, name: str = "", command: str = "", args: list[str] | None = None, tool: str = "", json_args: str = "{}", global_scope: bool = False) -> None:
    servers=load_mcp_servers(root)
    if action=="list":
        t=Table(title="MCP Servers",box=box.ROUNDED,border_style="cyan"); t.add_column("Name"); t.add_column("Command"); t.add_column("Protocol")
        for n,srv in sorted(servers.items()): t.add_row(n," ".join([str(srv.get('command'))]+[str(x) for x in srv.get('args',[])]),str(srv.get("protocol","auto")))
        console.print(t if servers else "[yellow]No MCP servers configured.[/]"); return
    if action=="add":
        if not name or not command: raise AzzxError("mcp add requires NAME and COMMAND")
        if not re.fullmatch(r"[A-Za-z0-9._-]+",name): raise AzzxError("Invalid MCP server name.")
        d=(CONFIG_HOME/"mcp") if global_scope else (ensure_workspace_state(root)/"mcp"); d.mkdir(parents=True,exist_ok=True)
        save_json(d/f"{name}.json",{"name":name,"command":command,"args":args or [],"protocol":"auto"}); console.print(f"[green]✓ MCP server saved:[/] {name}"); return
    if action=="remove":
        removed=False
        for d in mcp_dirs(root):
            q=d/f"{name}.json"
            if q.exists(): q.unlink(); removed=True
        console.print("[green]✓ Removed.[/]" if removed else "[yellow]Server not found.[/]"); return
    srv=servers.get(name)
    if not srv: raise AzzxError(f"MCP server not found: {name}")
    proc=None
    try:
        proc,era=_mcp_open(root,srv)
        if action in {"test","tools"}:
            result=_mcp_request(proc,era,2,"tools/list",{})
            tools=result.get("tools") or []
            t=Table(title=f"MCP • {name} • {era}",box=box.ROUNDED,border_style="green"); t.add_column("Tool"); t.add_column("Description")
            for row in tools:
                if isinstance(row,dict): t.add_row(str(row.get("name","")),str(row.get("description",""))[:120])
            console.print(t); return
        if action=="call":
            if not tool: raise AzzxError("mcp call requires --tool")
            try: parsed=json.loads(json_args or "{}")
            except json.JSONDecodeError as exc: raise AzzxError("--json must be valid JSON object") from exc
            if not isinstance(parsed,dict): raise AzzxError("--json must be a JSON object")
            result=_mcp_request(proc,era,2,"tools/call",{"name":tool,"arguments":parsed})
            console.print(Panel(json.dumps(result,indent=2,ensure_ascii=False),title=f"MCP RESULT • {tool}",border_style="cyan")); return
    finally:
        if proc is not None:
            _close_mcp_process(proc)
    raise AzzxError(f"Unknown MCP action: {action}")


# ---- Workspace registry -----------------------------------------------------

def workspace_registry_file() -> Path:
    setup_homes(); return CONFIG_HOME/"workspaces.json"


def load_workspace_registry() -> dict[str,str]:
    obj=load_json(workspace_registry_file(),{}); return obj if isinstance(obj,dict) else {}


def workspace_command(current: Path, action: str, name: str = "", path: str = "", forced_provider: str | None = None) -> None:
    reg=load_workspace_registry()
    if action=="list":
        t=Table(title="AZZX Workspaces",box=box.ROUNDED,border_style="cyan"); t.add_column("Name"); t.add_column("Path"); t.add_column("Exists")
        for n,p in sorted(reg.items()): t.add_row(n,p,"✓" if Path(p).expanduser().exists() else "✗")
        console.print(t if reg else "[yellow]No registered workspaces.[/]"); return
    if action=="add":
        target=Path(path).expanduser().resolve() if path else current
        if not target.is_dir(): raise AzzxError(f"Workspace path not found: {target}")
        n=name or target.name
        if not re.fullmatch(r"[A-Za-z0-9._-]+",n): raise AzzxError("Workspace name may contain letters, numbers, dot, underscore and dash.")
        reg[n]=str(target); save_json(workspace_registry_file(),reg,private=True); console.print(f"[green]✓ Workspace registered:[/] {n} → {target}"); return
    if action=="remove":
        if name in reg: del reg[name]; save_json(workspace_registry_file(),reg,private=True); console.print("[green]✓ Removed.[/]")
        else: console.print("[yellow]Workspace not found.[/]")
        return
    if action in {"open","status"}:
        if name not in reg: raise AzzxError(f"Workspace not registered: {name}")
        target=Path(reg[name]).expanduser()
        if not target.is_dir(): raise AzzxError(f"Workspace not found or stale: {name}")
        if action=="open": interactive_shell(target,forced_provider)
        else:
            files=list_project_files(target); gr=git_root(target); tasks=list(task_dir(target).glob("*.json"))
            console.print(Panel(f"Path: {target}\nFiles: {len(files)}\nGit: {gr or '-'}\nTasks: {len(tasks)}",title=f"WORKSPACE • {name}",border_style="cyan"))
        return
    raise AzzxError(f"Unknown workspace action: {action}")


# ---- Autonomous v3 developer ----------------------------------------------

def clone_repository(url: str, destination: str = "") -> Path:
    if not shutil.which("git"): raise AzzxError("git is required for clone.")
    if not re.match(r"^(https?://|git@|ssh://)",url): raise AzzxError("Only HTTP(S), git@, or ssh:// Git URLs are accepted.")
    dest=Path(destination).expanduser().resolve() if destination else Path.cwd()/Path(urllib.parse.urlparse(url).path).stem.replace(".git","")
    if dest.exists() and any(dest.iterdir()): raise AzzxError(f"Destination is not empty: {dest}")
    proc=subprocess.run(["git","clone",url,str(dest)],text=True)
    if proc.returncode!=0: raise AzzxError("git clone failed.")
    return dest.resolve()


def run_develop(root: Path, goal: str, forced_provider: str | None = None, package: bool = False) -> bool:
    tid=task_create(root,goal,forced_provider)
    create_git_checkpoint(root,f"develop-{tid}",quiet=True)
    refresh_project_index(root,quiet=True); refresh_repository_map(root,quiet=True)
    ok=task_resume(root,tid,forced_provider)
    if ok:
        refresh_project_index(root,quiet=True); refresh_repository_map(root,quiet=True)
        if load_config().get("task_auto_review",True):
            # run_multi_agent already reviews, but final project-wide checks catch regressions outside selected files.
            ok=run_tests(root,quiet=False)
    if ok and package: package_tar(root)
    console.print(Panel(f"Task #{tid}\nStatus: {'SUCCESS' if ok else 'NEEDS ATTENTION'}",title="AZZX DEVELOP",border_style="green" if ok else "yellow"))
    return ok


# ---------------------------- V4 ENGINEERING FEATURES ----------------------------

BUILTIN_SKILLS: dict[str, dict[str, Any]] = {
    "google-apps-script": {
        "name": "Google Apps Script",
        "description": "GAS/WebApp/Telegram/Drive/Sheets conventions and deployment constraints.",
        "instructions": "Treat .gs files as Google Apps Script. Preserve doGet/doPost entry points, PropertiesService configuration, Drive/Sheets quotas, UrlFetchApp behavior, and deployed Web App compatibility. Avoid Node-only APIs unless explicitly requested.",
    },
    "telegram-python": {
        "name": "Telegram Bot Python",
        "description": "Telegram bot handlers, polling/webhooks, configuration, and safe retries.",
        "instructions": "Preserve Telegram update handling, avoid blocking the event loop, keep secrets outside source, distinguish polling and webhook modes, and add bounded retry/backoff for transient HTTP failures.",
    },
    "fastapi": {
        "name": "FastAPI",
        "description": "FastAPI routing, Pydantic models, async boundaries, tests, and deployment.",
        "instructions": "Prefer explicit Pydantic schemas, dependency injection for shared state, async-safe I/O, clear HTTP errors, and API tests. Do not silently break response schemas.",
    },
    "android": {
        "name": "Android",
        "description": "Gradle/Android application structure and build-safe edits.",
        "instructions": "Respect Gradle modules, Android manifests, SDK/minSdk constraints, resource naming, and lifecycle rules. Prefer changes that remain buildable from command line Gradle.",
    },
}


def _relative_file(root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except Exception:
        return str(path)


def _resolve_local_import(root: Path, source_rel: str, import_text: str, language: str) -> str | None:
    source = root / source_rel
    if language == "python":
        token = import_text.strip().lstrip(".")
        if not token:
            return None
        parts = token.split(".")
        candidates = [root.joinpath(*parts).with_suffix(".py"), root.joinpath(*parts) / "__init__.py"]
        for c in candidates:
            if c.exists():
                return _relative_file(root, c)
        return None
    if language in {"javascript", "typescript"} and import_text.startswith("."):
        base = (source.parent / import_text).resolve()
        candidates = [base]
        for ext in (".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".json"):
            candidates.append(Path(str(base) + ext))
        for ext in (".js", ".ts", ".tsx", ".jsx"):
            candidates.append(base / ("index" + ext))
        for c in candidates:
            if c.exists() and c.is_file():
                try:
                    return str(c.relative_to(root.resolve()))
                except Exception:
                    return None
    return None


def build_dependency_graph(root: Path, quiet: bool = False) -> dict[str, Any]:
    """Build a best-effort local file dependency graph without third-party parsers."""
    ensure_workspace_state(root)
    files = list_project_files(root)
    graph: dict[str, list[str]] = {}
    reverse: dict[str, list[str]] = {}
    for path in files:
        rel = str(path.relative_to(root))
        text = safe_read_text(path)
        if text is None:
            continue
        deps: set[str] = set()
        suffix = path.suffix.lower()
        if suffix in {".py", ".pyi"}:
            try:
                tree = ast.parse(text)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            dep = _resolve_local_import(root, rel, alias.name, "python")
                            if dep and dep != rel: deps.add(dep)
                    elif isinstance(node, ast.ImportFrom) and node.module:
                        dep = _resolve_local_import(root, rel, node.module, "python")
                        if dep and dep != rel: deps.add(dep)
            except SyntaxError:
                pass
        elif suffix in {".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx"}:
            imports = re.findall(r"(?:from\s+|require\s*\(\s*)['\"]([^'\"]+)['\"]", text)
            for token in imports:
                dep = _resolve_local_import(root, rel, token, "typescript" if suffix.startswith(".t") else "javascript")
                if dep and dep != rel: deps.add(dep)
        graph[rel] = sorted(deps)
        for dep in deps:
            reverse.setdefault(dep, []).append(rel)
    for key in list(reverse):
        reverse[key] = sorted(set(reverse[key]))
    payload = {
        "version": VERSION,
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "files": graph,
        "reverse": reverse,
        "edge_count": sum(len(v) for v in graph.values()),
    }
    save_json(ensure_workspace_state(root) / "dependency_graph.json", payload)
    if not quiet:
        console.print(f"[green]✓[/] Dependency graph: {len(graph)} files, {payload['edge_count']} local edges → .azzx/dependency_graph.json")
    return payload


def impact_analysis(root: Path, target: str, depth: int | None = None) -> dict[str, Any]:
    repo = refresh_repository_map(root, quiet=True)
    deps = build_dependency_graph(root, quiet=True)
    depth = max(1, min(int(depth or load_config().get("impact_depth", 2)), 6))
    seeds: set[str] = set()
    candidate = root / target
    if candidate.exists() and candidate.is_file():
        seeds.add(str(candidate.resolve().relative_to(root.resolve())))
    else:
        defs = repo.get("definitions") or {}
        rows = defs.get(target, [])
        if not rows:
            lookup = {str(k).lower(): k for k in defs}
            actual = lookup.get(target.lower())
            if actual: rows = defs.get(actual, [])
        seeds.update(str(r.get("path")) for r in rows if r.get("path"))
    if not seeds:
        raise AzzxError(f"Impact target not found: {target}")
    reverse = deps.get("reverse") or {}
    affected: dict[str, int] = {s: 0 for s in seeds}
    frontier = set(seeds)
    for level in range(1, depth + 1):
        nxt: set[str] = set()
        for f in frontier:
            for consumer in reverse.get(f, []):
                if consumer not in affected:
                    affected[consumer] = level
                    nxt.add(consumer)
        frontier = nxt
        if not frontier:
            break
    refs = (repo.get("references") or {}).get(target, [])
    for rel in refs:
        affected.setdefault(str(rel), 1)
    count = max(0, len(affected) - len(seeds))
    risk = "HIGH" if count >= 12 else "MEDIUM" if count >= 4 else "LOW"
    result = {"target": target, "seeds": sorted(seeds), "affected": sorted(affected.items(), key=lambda x: (x[1], x[0])), "depth": depth, "risk": risk}
    table = Table(title=f"Impact Analysis • {target}", box=box.ROUNDED, border_style="magenta")
    table.add_column("Distance", justify="right"); table.add_column("File")
    for rel, level in result["affected"][:100]:
        table.add_row(str(level), rel)
    console.print(table)
    console.print(f"Risk: [bold]{risk}[/] • Seed files: {len(seeds)} • Potentially affected: {count}")
    return result


def issue_dir(root: Path) -> Path:
    d = ensure_workspace_state(root) / "issues"; d.mkdir(parents=True, exist_ok=True); return d


def _issue_path(root: Path, issue_id: str) -> Path:
    return issue_dir(root) / f"{str(issue_id).zfill(4)}.json"


def _next_issue_id(root: Path) -> str:
    ids = []
    for p in issue_dir(root).glob("*.json"):
        try: ids.append(int(p.stem))
        except ValueError: pass
    return f"{(max(ids) + 1 if ids else 1):04d}"


def issue_command(root: Path, action: str, issue_id: str = "", text: str = "", forced_provider: str | None = None) -> None:
    if action == "create":
        if not text.strip(): raise AzzxError("issue create requires a description")
        iid = _next_issue_id(root)
        row = {"id": iid, "title": text.strip(), "status": "open", "created_at": dt.datetime.now().isoformat(timespec="seconds"), "updated_at": dt.datetime.now().isoformat(timespec="seconds"), "notes": []}
        save_json(_issue_path(root, iid), row)
        console.print(f"[green]✓[/] Issue #{iid} created")
        return
    if action == "list":
        table = Table(title="Project Issues", box=box.ROUNDED, border_style="cyan")
        table.add_column("ID"); table.add_column("Status"); table.add_column("Title")
        for p in sorted(issue_dir(root).glob("*.json")):
            row = load_json(p, {})
            table.add_row(str(row.get("id", p.stem)), str(row.get("status", "?")), str(row.get("title", ""))[:100])
        console.print(table); return
    if not issue_id: raise AzzxError(f"issue {action} requires ISSUE_ID")
    path = _issue_path(root, issue_id)
    row = load_json(path, {})
    if not row: raise AzzxError(f"Issue not found: {issue_id}")
    if action == "show":
        console.print(Panel(Markdown(f"# Issue #{row.get('id')}\n\n**Status:** {row.get('status')}\n\n{row.get('title')}\n\n" + "\n".join(f"- {n}" for n in row.get("notes", []))), title="ISSUE", border_style="cyan")); return
    if action in {"close", "reopen"}:
        row["status"] = "closed" if action == "close" else "open"; row["updated_at"] = dt.datetime.now().isoformat(timespec="seconds"); save_json(path, row); console.print(f"[green]✓[/] Issue #{row['id']} → {row['status']}"); return
    if action == "solve":
        row["status"] = "investigating"; save_json(path, row)
        goal = f"Solve project issue #{row['id']}: {row['title']}. Reproduce or identify the root cause from repository evidence, apply the smallest safe fix, preserve existing behavior, and add/update tests when practical."
        ok = run_multi_agent(root, goal, forced_provider)
        row = load_json(path, row); row["status"] = "resolved" if ok else "open"; row["updated_at"] = dt.datetime.now().isoformat(timespec="seconds"); row.setdefault("notes", []).append(f"Agent solve attempt at {row['updated_at']}: {'success' if ok else 'not completed'}"); save_json(path, row)
        return
    raise AzzxError(f"Unknown issue action: {action}")


def generate_tests(root: Path, target: str = "", forced_provider: str | None = None) -> bool:
    goal = "Generate or improve tests for this project. Do not change production behavior merely to make tests pass. Prefer regression tests for observable behavior."
    if target: goal += f" Focus on: {target}."
    return run_edit_task(root, goal, "implement", forced_provider)


def run_affected_tests(root: Path) -> bool:
    gr = git_root(root)
    if not gr:
        return run_tests(root)
    try:
        proc = subprocess.run(["git", "diff", "--name-only", "HEAD"], cwd=gr, capture_output=True, text=True, timeout=10)
        changed = [x.strip() for x in proc.stdout.splitlines() if x.strip()]
    except Exception:
        changed = []
    tests = []
    all_files = list_project_files(root)
    stems = {Path(x).stem.replace("test_", "") for x in changed}
    for p in all_files:
        rel = str(p.relative_to(root))
        if "test" not in p.name.lower() and "tests" not in p.parts: continue
        low = rel.lower()
        if any(s and s.lower() in low for s in stems): tests.append(rel)
    if tests and all(Path(t).suffix == ".py" for t in tests) and shutil.which("pytest"):
        cmd = f"{shlex.quote(sys.executable)} -m pytest -q " + " ".join(shlex.quote(t) for t in tests[:30])
        return run_tests(root, cmd)
    return run_tests(root)


SECURITY_PATTERNS: list[tuple[str, str, str]] = [
    ("HIGH", "Private key material", r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    ("HIGH", "AWS access key-like token", r"\bAKIA[0-9A-Z]{16}\b"),
    ("HIGH", "Potential hardcoded secret", r"(?i)\b(?:api[_-]?key|secret|token|password)\s*[:=]\s*['\"][^'\"\n]{12,}['\"]"),
    ("MEDIUM", "Python eval/exec", r"\b(?:eval|exec)\s*\("),
    ("MEDIUM", "Shell execution with shell=True", r"subprocess\.(?:run|Popen|call|check_output)\([^\n]{0,220}shell\s*=\s*True"),
    ("MEDIUM", "Potential SQL string formatting", r"(?i)(?:SELECT|INSERT|UPDATE|DELETE)[^\n]{0,160}(?:%s|\.format\(|f['\"])"),
]


def security_scan(root: Path, external: bool = False) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for p in list_project_files(root):
        text = safe_read_text(p)
        if not text: continue
        for severity, title, pattern in SECURITY_PATTERNS:
            for m in re.finditer(pattern, text):
                findings.append({"severity": severity, "title": title, "path": str(p.relative_to(root)), "line": _line_of_offset(text, m.start()), "source": "heuristic"})
                if len(findings) >= 250: break
            if len(findings) >= 250: break
        if len(findings) >= 250: break
    if external:
        commands: list[tuple[str, list[str]]] = []
        if shutil.which("bandit") and any(p.suffix == ".py" for p in list_project_files(root)):
            commands.append(("bandit", ["bandit", "-q", "-r", ".", "-f", "json"]))
        if shutil.which("pip-audit") and (root / "requirements.txt").exists():
            commands.append(("pip-audit", ["pip-audit", "-r", "requirements.txt", "-f", "json"]))
        for name, cmd in commands:
            try:
                pr = subprocess.run(cmd, cwd=root, capture_output=True, text=True, timeout=120)
                if pr.returncode not in {0, 1}:
                    findings.append({"severity": "INFO", "title": f"{name} could not complete", "path": "", "line": 0, "source": name})
                else:
                    findings.append({"severity": "INFO", "title": f"{name} executed; inspect raw report in .azzx/security-{name}.json", "path": "", "line": 0, "source": name})
                    atomic_write(ensure_workspace_state(root) / f"security-{name}.json", pr.stdout or pr.stderr)
            except Exception as exc:
                findings.append({"severity": "INFO", "title": f"{name} error: {exc}", "path": "", "line": 0, "source": name})
    table = Table(title="Security Review", box=box.ROUNDED, border_style="red")
    table.add_column("Severity"); table.add_column("Finding"); table.add_column("Location")
    order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "INFO": 3}
    for f in sorted(findings, key=lambda x: (order.get(str(x["severity"]), 9), str(x["path"]), int(x["line"] or 0)))[:120]:
        loc = f"{f['path']}:{f['line']}" if f.get("path") else str(f.get("source", ""))
        table.add_row(str(f["severity"]), str(f["title"]), loc)
    if findings: console.print(table)
    else: console.print("[green]✓ No findings from built-in heuristic scan.[/]")
    save_json(ensure_workspace_state(root) / "security-report.json", {"generated_at": dt.datetime.now().isoformat(timespec="seconds"), "findings": findings})
    console.print("[dim]Heuristic results are leads, not proof of exploitability. Secrets are never printed.[/]")
    return findings


def benchmark_command(root: Path, command: str, runs: int | None = None) -> dict[str, Any]:
    runs = max(1, min(int(runs or load_config().get("benchmark_runs", 3)), 20))
    times: list[float] = []
    last_code = 0; last_output = ""
    for i in range(runs):
        started = time.perf_counter(); last_code, last_output = run_shell_capture(root, command, int(load_config().get("timeout_seconds", 120))); times.append(time.perf_counter() - started)
        if last_code != 0: break
    avg = sum(times) / len(times)
    result = {"command": command, "runs": len(times), "seconds": times, "average": avg, "min": min(times), "max": max(times), "exit": last_code}
    save_json(ensure_workspace_state(root) / "benchmark.json", result)
    console.print(Panel(f"Command: {command}\nRuns: {len(times)}\nAverage: {avg:.4f}s\nMin: {min(times):.4f}s\nMax: {max(times):.4f}s\nExit: {last_code}", title="BENCHMARK", border_style="cyan" if last_code == 0 else "red"))
    if last_code != 0 and last_output: console.print(Panel(last_output[-8000:], title="LAST OUTPUT", border_style="red"))
    return result


def profile_command(root: Path, command: str) -> None:
    parts = shlex.split(command)
    if parts and (Path(parts[0]).name.startswith("python") or parts[0] == sys.executable) and len(parts) >= 2 and parts[1].endswith(".py"):
        prof = [sys.executable, "-m", "cProfile", "-s", "cumulative"] + parts[1:]
        try:
            pr = subprocess.run(prof, cwd=root, capture_output=True, text=True, timeout=int(load_config().get("timeout_seconds", 120)))
            console.print(Panel((pr.stdout + pr.stderr)[-16000:], title=f"PYTHON PROFILE • exit {pr.returncode}", border_style="cyan" if pr.returncode == 0 else "red")); return
        except subprocess.TimeoutExpired: raise AzzxError("Profile timed out")
    benchmark_command(root, command)


def _sqlite_ro_connect(path: Path):
    import sqlite3
    uri = f"file:{urllib.parse.quote(str(path.resolve()))}?mode=ro"
    return sqlite3.connect(uri, uri=True)


def db_command(root: Path, action: str, database: str, sql: str = "") -> None:
    import sqlite3
    db = safe_workspace_path(root, database)
    if not db.exists(): raise AzzxError(f"Database not found: {database}")
    if action == "inspect":
        con = _sqlite_ro_connect(db)
        try:
            rows = con.execute("SELECT name, type FROM sqlite_master WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
            t = Table(title=f"SQLite • {database}", box=box.ROUNDED, border_style="cyan"); t.add_column("Type"); t.add_column("Name"); t.add_column("Columns")
            for name, typ in rows:
                cols = con.execute(f"PRAGMA table_info({json.dumps(name)})").fetchall() if typ == "table" else []
                t.add_row(str(typ), str(name), ", ".join(str(c[1]) for c in cols))
            console.print(t)
        finally: con.close()
        return
    if action in {"query", "explain"}:
        if not sql.strip(): raise AzzxError(f"db {action} requires SQL")
        normalized = re.sub(r"\s+", " ", sql.strip()).upper()
        if action == "query" and not normalized.startswith(("SELECT ", "WITH ", "PRAGMA ", "EXPLAIN ")):
            raise AzzxError("db query is read-only. Use db migrate for schema/data writes.")
        q = sql if action == "query" else "EXPLAIN QUERY PLAN " + sql
        con = _sqlite_ro_connect(db)
        try:
            cur = con.execute(q); rows = cur.fetchmany(200); headers = [d[0] for d in (cur.description or [])]
            t = Table(title=f"SQLite {action}", box=box.SIMPLE); [t.add_column(h) for h in headers]
            for row in rows: t.add_row(*(str(v) for v in row))
            console.print(t)
        finally: con.close()
        return
    if action == "migrate":
        if not sql.strip(): raise AzzxError("db migrate requires SQL or @file.sql")
        if sql.startswith("@"):
            script_path = safe_workspace_path(root, sql[1:]); sql = safe_read_text(script_path, 1_000_000) or ""
        if not sql.strip(): raise AzzxError("Migration script is empty")
        require_permission("database.write", f"Apply SQLite migration to {database}")
        if not Confirm.ask(f"Apply SQLite migration to {database}? A backup will be created first.", default=False): return
        bdir = ensure_workspace_state(root) / "backups" / f"db-{now_stamp()}"; bdir.mkdir(parents=True, exist_ok=True); shutil.copy2(db, bdir / db.name)
        con = sqlite3.connect(db)
        try:
            with con: con.executescript(sql)
            console.print(f"[green]✓ Migration applied.[/] Backup: {bdir.relative_to(root)}")
        except Exception:
            con.close(); shutil.copy2(bdir / db.name, db); raise
        finally:
            try: con.close()
            except Exception: pass
        return
    raise AzzxError(f"Unknown db action: {action}")


def detect_environment() -> dict[str, Any]:
    termux = bool(os.environ.get("TERMUX_VERSION") or "com.termux" in str(Path(sys.executable)))
    os_id = ""
    os_like = ""
    os_release = Path("/etc/os-release")
    if os_release.exists():
        for line in os_release.read_text(errors="ignore").splitlines():
            if line.startswith("ID="): os_id = line.split("=",1)[1].strip('"')
            elif line.startswith("ID_LIKE="): os_like = line.split("=",1)[1].strip('"')
    managers = [x for x in ("pkg","apt","apt-get","pacman","dnf","zypper","apk","xbps-install","emerge") if shutil.which(x)]
    tools = {x: bool(shutil.which(x)) for x in ("git","rg","python","pip","node","npm","go","cargo","java","gradle","adb","docker","podman")}
    return {"termux": termux, "id": os_id, "id_like": os_like, "package_managers": managers, "tools": tools, "platform": platform.platform(), "python": platform.python_version()}


def environment_command(fix: bool = False, install: bool = False) -> None:
    env = detect_environment()
    t = Table(title="Environment Intelligence", box=box.ROUNDED, border_style="cyan"); t.add_column("Item"); t.add_column("Value")
    t.add_row("Environment", "Termux" if env["termux"] else (env["id"] or platform.system()))
    t.add_row("Platform", env["platform"]); t.add_row("Python", env["python"]); t.add_row("Package manager", ", ".join(env["package_managers"]) or "unknown")
    console.print(t)
    tt = Table(title="Developer Tools", box=box.SIMPLE); tt.add_column("Tool"); tt.add_column("Status")
    for k,v in env["tools"].items(): tt.add_row(k, "✓" if v else "—")
    console.print(tt)
    if fix:
        missing = [x for x in ("git","rg") if not env["tools"].get(x)]
        if not missing: console.print("[green]✓ Core developer tools are available.[/]"); return
        mgr = (env["package_managers"] or [""])[0]
        packages = {"rg": "ripgrep", "git": "git"}; names=[packages[x] for x in missing]
        if mgr == "pkg": cmd=["pkg","install","-y",*names]
        elif mgr in {"apt","apt-get"}: cmd=[mgr,"install","-y",*names]
        elif mgr == "pacman": cmd=["sudo","pacman","-S","--needed","--noconfirm",*names]
        elif mgr == "dnf": cmd=["sudo","dnf","install","-y",*names]
        elif mgr == "apk": cmd=["sudo","apk","add",*names]
        else:
            console.print(f"[yellow]Missing:[/] {', '.join(missing)}. Install manually for your distro."); return
        console.print("Suggested: " + shlex.join(cmd))
        if install:
            require_permission("package.install", "Install missing core developer tools")
        if install and Confirm.ask("Run this install command?", default=False):
            code = subprocess.run(cmd).returncode
            if code != 0: raise AzzxError("Environment fix command failed")


def ci_create(root: Path, provider: str) -> Path:
    provider = provider.lower()
    if provider == "github":
        path = ".github/workflows/ci.yml"
        content = """name: CI\non:\n  push:\n  pull_request:\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v7\n      - uses: actions/setup-python@v7\n        with:\n          python-version: '3.12'\n      - run: python -m pip install -U pip\n      - run: test ! -f requirements.txt || pip install -r requirements.txt\n      - run: python -m compileall -q .\n      - run: test ! -d tests || python -m unittest discover -v\n"""
    elif provider == "gitlab":
        path = ".gitlab-ci.yml"
        content = """image: python:3.12\nstages: [test]\ntest:\n  stage: test\n  script:\n    - python -m pip install -U pip\n    - if [ -f requirements.txt ]; then pip install -r requirements.txt; fi\n    - python -m compileall -q .\n    - if [ -d tests ]; then python -m unittest discover -v; fi\n"""
    elif provider == "local":
        path = "ci.sh"
        content = """#!/usr/bin/env sh\nset -eu\npython -m compileall -q .\nif [ -d tests ]; then python -m unittest discover -v; fi\n"""
    else: raise AzzxError("CI provider must be github, gitlab, or local")
    target = safe_workspace_path(root, path)
    if target.exists() and not Confirm.ask(f"Overwrite {path}?", default=False): return target
    apply_changes(root, [{"path": path, "content": content}], f"Create {provider} CI")
    if provider == "local": target.chmod(target.stat().st_mode | stat.S_IXUSR)
    console.print(f"[green]✓ CI scaffold:[/] {path}")
    return target


def review_git_range(root: Path, rev_range: str, forced_provider: str | None = None) -> None:
    gr = git_root(root)
    if not gr: raise AzzxError("Not inside a Git repository")
    if not rev_range.strip(): rev_range = "HEAD~1..HEAD"
    try:
        pr = subprocess.run(["git","diff","--no-ext-diff",rev_range], cwd=gr, capture_output=True, text=True, timeout=20)
    except Exception as exc: raise AzzxError(f"Cannot read Git range: {exc}")
    if pr.returncode != 0: raise AzzxError(pr.stderr.strip() or "git diff failed")
    diff = pr.stdout[-60000:]
    result = get_router().chat_role([
        {"role":"system","content":"You are a strict senior code reviewer. Review only evidence in the supplied Git diff. Prioritize correctness, regressions, security, data loss, concurrency, API compatibility, and missing tests. Do not invent files or behavior."},
        {"role":"user","content":f"Review Git range {rev_range}:\n\n{diff}"},
    ], "reviewer", forced_provider)
    console.print(Panel(Markdown(result.text), title=f"CODE REVIEW • {rev_range}", border_style="magenta")); show_route(result)


def skill_store(root: Path, global_scope: bool = False) -> Path:
    d = (CONFIG_HOME / "skills") if global_scope else (ensure_workspace_state(root) / "skills")
    d.mkdir(parents=True, exist_ok=True); return d


def _skill_file_name(name: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", name.strip().lower()).strip("-.")
    if not safe: raise AzzxError("Invalid skill name")
    return safe + ".json"


def load_skills(root: Path) -> dict[str, dict[str, Any]]:
    out = {k: dict(v) for k,v in BUILTIN_SKILLS.items()}
    for d in (CONFIG_HOME / "skills", ensure_workspace_state(root) / "skills"):
        if not d.exists(): continue
        for p in d.glob("*.json"):
            row = load_json(p, {})
            if isinstance(row, dict) and row.get("id"): out[str(row["id"])] = row
    return out


def active_skill_context(root: Path) -> str:
    state = ensure_workspace_state(root)
    selection = load_json(state / "active_skill.json", {})
    sid = str(selection.get("id", "")) if isinstance(selection, dict) else ""
    if not sid: return ""
    row = load_skills(root).get(sid)
    if not row: return ""
    return f"ACTIVE PROJECT SKILL: {row.get('name', sid)}\n{row.get('instructions','')}\n"


def skill_command(root: Path, action: str, name: str = "", text: str = "", global_scope: bool = False) -> None:
    skills = load_skills(root)
    if action == "list":
        active = load_json(ensure_workspace_state(root) / "active_skill.json", {}).get("id", "")
        t=Table(title="Agent Skills",box=box.ROUNDED,border_style="cyan"); t.add_column("Active"); t.add_column("ID"); t.add_column("Description")
        for sid,row in sorted(skills.items()): t.add_row("●" if sid==active else "",sid,str(row.get("description","")))
        console.print(t); return
    if action == "show":
        if name not in skills: raise AzzxError(f"Skill not found: {name}")
        console.print(Panel(Markdown(json.dumps(skills[name], indent=2, ensure_ascii=False)), title=f"SKILL • {name}", border_style="cyan")); return
    if action == "use":
        if name not in skills: raise AzzxError(f"Skill not found: {name}")
        save_json(ensure_workspace_state(root) / "active_skill.json", {"id": name, "set_at": dt.datetime.now().isoformat(timespec="seconds")}); console.print(f"[green]✓ Active skill:[/] {name}"); return
    if action == "clear":
        p=ensure_workspace_state(root)/"active_skill.json"
        if p.exists(): p.unlink()
        console.print("[green]✓ Active skill cleared.[/]"); return
    if action == "create":
        if not name or not text.strip(): raise AzzxError("skill create requires NAME and instructions")
        sid = _skill_file_name(name)[:-5]; row={"id":sid,"name":name,"description":"Custom AZZX skill","instructions":text.strip()}; save_json(skill_store(root,global_scope)/_skill_file_name(sid),row); console.print(f"[green]✓ Skill created:[/] {sid}"); return
    raise AzzxError(f"Unknown skill action: {action}")



# ---------------------------- V5 SOFTWARE FACTORY FEATURES ----------------------------

PERMISSION_CAPABILITIES = (
    "filesystem.write", "filesystem.read", "shell.run", "package.install", "git.commit", "git.push",
    "ssh", "database.write", "network.http", "release.publish",
    "device.adb", "device.mirror", "workflow.run", "plugin.install", "process.inspect", "archive.write",
)


def permission_policy(capability: str) -> str:
    cfg = load_config()
    perms = cfg.get("permissions") or {}
    value = str(perms.get(capability, "ask")).lower()
    return value if value in {"allow", "ask", "deny"} else "ask"


def require_permission(capability: str, detail: str = "", noninteractive: bool = False) -> bool:
    policy = permission_policy(capability)
    if policy == "allow":
        return True
    if policy == "deny":
        raise AzzxError(f"Permission denied by AZZX policy: {capability}")
    if noninteractive or not sys.stdin.isatty():
        raise AzzxError(f"Permission requires confirmation: {capability}. Change it with `azzx permissions set {capability} allow`.")
    prompt = f"Allow {capability}?" + (f"\n{detail}" if detail else "")
    if not Confirm.ask(prompt, default=False):
        raise AzzxError(f"Permission not granted: {capability}")
    return True


def permissions_command(action: str, capability: str = "", value: str = "") -> None:
    cfg = load_config(); perms = dict(cfg.get("permissions") or {})
    if action == "list":
        t = Table(title="AZZX Permissions", box=box.ROUNDED, border_style="cyan")
        t.add_column("Capability"); t.add_column("Policy")
        for cap in PERMISSION_CAPABILITIES:
            t.add_row(cap, str(perms.get(cap, "ask")).upper())
        console.print(t); return
    if action == "set":
        if capability not in PERMISSION_CAPABILITIES: raise AzzxError(f"Unknown capability: {capability}")
        value = value.lower()
        if value not in {"allow", "ask", "deny"}: raise AzzxError("Permission value must be allow, ask, or deny")
        perms[capability] = value; cfg["permissions"] = perms; save_config(cfg)
        console.print(f"[green]✓[/] {capability} = {value.upper()}"); return
    if action == "reset":
        cfg["permissions"] = DEFAULT_CONFIG["permissions"]; save_config(cfg); console.print("[green]✓ Permission policies reset.[/]"); return
    raise AzzxError(f"Unknown permissions action: {action}")


def spec_dir(root: Path) -> Path:
    d = ensure_workspace_state(root) / "spec"; d.mkdir(parents=True, exist_ok=True); return d


def _spec_file(root: Path, section: str) -> Path:
    mapping = {
        "product": "product.md", "requirements": "requirements.md", "constraints": "constraints.md",
        "architecture": "architecture.md", "acceptance": "acceptance-tests.md",
    }
    if section not in mapping: raise AzzxError(f"Unknown spec section: {section}")
    return spec_dir(root) / mapping[section]


def spec_init(root: Path, description: str = "") -> None:
    defaults = {
        "product": f"# Product\n\n{description.strip() or 'Describe the product goal here.'}\n",
        "requirements": "# Requirements\n\n- [ ] Define functional requirements.\n",
        "constraints": "# Constraints\n\n- Preserve existing behavior unless explicitly changed.\n",
        "architecture": "# Architecture\n\nNot generated yet.\n",
        "acceptance": "# Acceptance Tests\n\n- [ ] Core workflow works end-to-end.\n",
    }
    for section, content in defaults.items():
        p = _spec_file(root, section)
        if not p.exists(): atomic_write(p, content)
    console.print(f"[green]✓[/] Product spec initialized in .azzx/spec/")


def spec_generate(root: Path, description: str, forced_provider: str | None = None) -> None:
    if not description.strip(): raise AzzxError("spec generate requires a product description")
    ctx, _, _ = build_workspace_context(root, description, load_config())
    result = get_router().chat_role([
        {"role":"system","content":"You are a senior product analyst and software architect. Return ONLY one JSON object with string fields: product, requirements, constraints, architecture, acceptance. Each value is concise Markdown. Ground architecture in the supplied repository if it exists; do not invent external services unless necessary."},
        {"role":"user","content":f"PRODUCT REQUEST:\n{description}\n\nCURRENT PROJECT CONTEXT:\n{ctx}"},
    ], "architect", forced_provider)
    obj = parse_json_object(result.text)
    for section in ("product","requirements","constraints","architecture","acceptance"):
        value = obj.get(section)
        if not isinstance(value, str) or not value.strip(): raise AzzxError(f"Spec generator returned invalid section: {section}")
        atomic_write(_spec_file(root, section), value.strip() + "\n")
    console.print("[green]✓ Product specification generated.[/]"); show_route(result)


def spec_command(root: Path, action: str, section: str = "", text: str = "", forced_provider: str | None = None) -> None:
    if action == "init": spec_init(root, text); return
    if action == "generate": spec_generate(root, text, forced_provider); return
    if action == "show":
        if section:
            p = _spec_file(root, section); console.print(Panel(Markdown(safe_read_text(p, 100_000) or "(empty)"), title=f"SPEC • {section}", border_style="cyan")); return
        spec_init(root)
        for sec in ("product","requirements","constraints","architecture","acceptance"):
            console.print(Panel(Markdown(safe_read_text(_spec_file(root,sec),100_000) or ""), title=sec.upper(), border_style="cyan"))
        return
    if action == "set":
        if not section or not text.strip(): raise AzzxError("spec set requires SECTION and text")
        atomic_write(_spec_file(root, section), text.strip()+"\n"); console.print(f"[green]✓[/] Spec section updated: {section}"); return
    if action == "check":
        missing=[]; placeholders=[]
        for sec in ("product","requirements","constraints","architecture","acceptance"):
            p=_spec_file(root,sec)
            if not p.exists(): missing.append(sec)
            elif "Not generated yet" in (safe_read_text(p) or ""): placeholders.append(sec)
        if missing or placeholders:
            console.print(Panel(f"Missing: {', '.join(missing) or '-'}\nPlaceholder: {', '.join(placeholders) or '-'}",title="SPEC CHECK",border_style="yellow"))
        else: console.print("[green]✓ Spec files are present.[/]")
        return
    raise AzzxError(f"Unknown spec action: {action}")


def roadmap_path(root: Path) -> Path:
    return ensure_workspace_state(root) / "roadmap.json"


def roadmap_generate(root: Path, goal: str, forced_provider: str | None = None) -> None:
    specs = []
    for sec in ("product","requirements","constraints","architecture","acceptance"):
        p=_spec_file(root,sec)
        if p.exists(): specs.append(safe_read_text(p,30_000) or "")
    ctx="\n\n".join(specs)
    result=get_router().chat_role([
        {"role":"system","content":"Return ONLY JSON with key milestones, an array of objects {id,title,status,tasks}. status must start as pending and tasks is an array of short strings. Create 3-8 ordered engineering milestones with verification work included."},
        {"role":"user","content":f"GOAL: {goal}\n\nSPEC:\n{ctx}"},
    ],"planner",forced_provider)
    obj=parse_json_object(result.text); milestones=obj.get("milestones")
    if not isinstance(milestones,list) or not milestones: raise AzzxError("Roadmap generator returned no milestones")
    clean=[]
    for i,row in enumerate(milestones,1):
        if not isinstance(row,dict): continue
        clean.append({"id":str(row.get("id") or f"M{i}"),"title":str(row.get("title") or f"Milestone {i}"),"status":"pending","tasks":[str(x) for x in (row.get("tasks") or [])][:30]})
    save_json(roadmap_path(root),{"goal":goal,"created_at":dt.datetime.now().isoformat(timespec="seconds"),"milestones":clean})
    console.print("[green]✓ Roadmap generated.[/]"); show_route(result)


def roadmap_command(root: Path, action: str, args: list[str], forced_provider: str | None = None) -> None:
    if action == "generate":
        if not args: raise AzzxError("roadmap generate requires a goal")
        roadmap_generate(root," ".join(args),forced_provider); return
    data=load_json(roadmap_path(root),{})
    if not data: raise AzzxError("No roadmap yet. Run `azzx roadmap generate ...`")
    milestones=data.get("milestones") or []
    if action in {"show","progress"}:
        t=Table(title="Project Roadmap",box=box.ROUNDED,border_style="cyan"); t.add_column("ID"); t.add_column("Status"); t.add_column("Milestone"); t.add_column("Tasks",justify="right")
        for m in milestones: t.add_row(str(m.get("id")),str(m.get("status")),str(m.get("title")),str(len(m.get("tasks") or [])))
        console.print(t)
        done=sum(1 for m in milestones if m.get("status")=="done"); pct=(100*done/len(milestones)) if milestones else 0; console.print(f"Progress: [bold]{pct:.0f}%[/] ({done}/{len(milestones)})"); return
    if action == "set":
        if len(args)<2: raise AzzxError("roadmap set requires MILESTONE_ID STATUS")
        mid,status=args[0],args[1].lower()
        if status not in {"pending","active","blocked","done"}: raise AzzxError("Status must be pending, active, blocked, or done")
        found=False
        for m in milestones:
            if str(m.get("id"))==mid: m["status"]=status; found=True; break
        if not found: raise AzzxError(f"Milestone not found: {mid}")
        save_json(roadmap_path(root),data); console.print(f"[green]✓[/] {mid} → {status}"); return
    raise AzzxError(f"Unknown roadmap action: {action}")


def select_team_roles(goal: str) -> list[str]:
    low=goal.lower(); roles=["architect","backend"]
    if any(x in low for x in ("frontend","ui","html","css","react","vue","svelte","webapp")): roles.append("frontend")
    if any(x in low for x in ("database","sql","sqlite","postgres","mysql","mongo","schema","migration")): roles.append("database")
    if any(x in low for x in ("auth","security","login","token","permission","secret","payment")): roles.append("security")
    roles.append("qa")
    return list(dict.fromkeys(roles))


def team_advice(root: Path, goal: str, forced_provider: str | None = None) -> str:
    ctx,_,_=build_workspace_context(root,goal,load_config()); router=get_router(); blocks=[]
    prompts={
        "architect":"Analyze architecture, dependencies, boundaries, and the safest implementation sequence.",
        "backend":"Focus on backend/core logic, compatibility, error handling, and data flow.",
        "frontend":"Focus on UI behavior, responsive layout, state, accessibility, and integration boundaries.",
        "database":"Focus on schema/data integrity, migrations, query behavior, rollback, and compatibility.",
        "security":"Threat-model the requested change and identify concrete security regression risks.",
        "qa":"Define acceptance checks and regression tests based on observable behavior.",
    }
    for role in select_team_roles(goal):
        with console.status(f"[cyan]{role} agent...[/]",spinner="dots"):
            res=router.chat_role([
                {"role":"system","content":prompts[role]+" Give concise engineering guidance only; do not output full source files."},
                {"role":"user","content":f"GOAL: {goal}\n\nPROJECT:\n{ctx}"},
            ],role,forced_provider)
        blocks.append(f"## {role.upper()}\n{res.text}")
    return "\n\n".join(blocks)


def run_team_agent(root: Path, goal: str, forced_provider: str | None = None) -> bool:
    advice=team_advice(root,goal,forced_provider)
    console.print(Panel(Markdown(advice),title="ENGINEERING TEAM",border_style="cyan"))
    changed=run_edit_task(root,goal,"implement",forced_provider,extra_context=advice)
    if not changed: return False
    ok=run_tests(root,quiet=True)
    findings=security_scan(root,False)
    high=sum(1 for f in findings if f.get("severity")=="HIGH")
    if not ok: console.print("[red]✗ Team implementation did not pass tests.[/]")
    if high: console.print(f"[yellow]Security gate: {high} HIGH heuristic finding(s).[/]")
    return ok


def _filtered_copy_project(root: Path, dst: Path) -> None:
    dst.mkdir(parents=True,exist_ok=True)
    for p in root.rglob("*"):
        rel=p.relative_to(root)
        if not rel.parts: continue
        if rel.parts[0] in {".azzx","dist","build"}: continue
        if any(part in IGNORE_DIRS for part in rel.parts): continue
        out=dst/rel
        if p.is_dir(): out.mkdir(parents=True,exist_ok=True); continue
        if p.is_file(): out.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(p,out)


def _text_snapshot(root: Path) -> dict[str,str]:
    snap={}
    for p in list_project_files(root):
        text=safe_read_text(p)
        if text is not None: snap[str(p.relative_to(root))]=text
    return snap


def _sandbox_changes(original: Path, sandbox: Path) -> list[dict[str,str]]:
    before=_text_snapshot(original); after=_text_snapshot(sandbox); out=[]
    for rel,content in after.items():
        if before.get(rel)!=content: out.append({"path":rel,"content":content})
    return out


def create_sandbox(root: Path, label: str = "task") -> Path:
    safe=re.sub(r"[^A-Za-z0-9._-]+","-",label).strip("-.")[:40] or "task"
    d=ensure_workspace_state(root)/"sandboxes"/f"{now_stamp()}-{safe}"; _filtered_copy_project(root,d)
    return d


def sandbox_develop(root: Path, goal: str, forced_provider: str | None = None, yes_merge: bool = False) -> bool:
    require_permission("filesystem.write", "AZZX will merge validated text changes from a sandbox into the workspace.", noninteractive=yes_merge and permission_policy("filesystem.write")!="allow")
    baseline_security=security_scan(root,False); baseline_high=sum(1 for f in baseline_security if f.get("severity")=="HIGH")
    baseline_tests=run_tests(root,quiet=True)
    sandbox=create_sandbox(root,goal[:30])
    console.print(f"[cyan]Sandbox:[/] {sandbox.relative_to(root)}")
    try:
        ok=run_team_agent(sandbox,goal,forced_provider)
        after_findings=security_scan(sandbox,False); after_high=sum(1 for f in after_findings if f.get("severity")=="HIGH")
        if not ok: raise AzzxError(f"Sandbox tests/checks failed. Sandbox kept at {sandbox}")
        if load_config().get("factory_security_gate",True) and after_high>baseline_high:
            raise AzzxError(f"Security gate blocked merge: HIGH findings increased {baseline_high} → {after_high}. Sandbox kept at {sandbox}")
        changes=_sandbox_changes(root,sandbox)
        if not changes:
            console.print("[yellow]Sandbox produced no text changes.[/]"); return False
        render_change_summary(changes,root)
        mode=str(load_config().get("mode","safe"))
        allow_merge=yes_merge or mode=="auto"
        if not allow_merge:
            allow_merge=Confirm.ask("Merge validated sandbox changes into the workspace?",default=False)
        if not allow_merge:
            console.print(f"[yellow]Not merged. Sandbox kept:[/] {sandbox}"); return False
        create_git_checkpoint(root,"pre-sandbox-merge",quiet=True)
        apply_changes(root,changes,f"Sandbox merge: {goal}")
        post_ok=run_tests(root,quiet=True)
        if load_config().get("factory_regression_gate",True) and baseline_tests and not post_ok:
            console.print("[red]Post-merge regression detected; restoring last backup.[/]")
            backup=latest_backup_dir(root)
            if backup: restore_backup(root,backup)
            return False
        console.print("[green]✓ Sandbox changes merged and validated.[/]"); return True
    finally:
        if sandbox.exists() and not load_config().get("sandbox_keep_failed",True): shutil.rmtree(sandbox,ignore_errors=True)


def regression_baseline_path(root: Path) -> Path:
    return ensure_workspace_state(root)/"regression-baseline.json"


def capture_regression_baseline(root: Path, benchmark_cmd: str = "") -> dict[str,Any]:
    syntax=syntax_check_workspace(root); test_ok=run_tests(root,quiet=True); findings=security_scan(root,False); high=sum(1 for f in findings if f.get("severity")=="HIGH")
    data={"created_at":dt.datetime.now().isoformat(timespec="seconds"),"syntax_errors":len(syntax),"tests_ok":test_ok,"security_high":high,"benchmark":None}
    if benchmark_cmd: data["benchmark"]=benchmark_command(root,benchmark_cmd)
    save_json(regression_baseline_path(root),data); console.print("[green]✓ Regression baseline captured.[/]"); return data


def regression_check(root: Path, benchmark_cmd: str = "") -> bool:
    base=load_json(regression_baseline_path(root),{})
    if not base: raise AzzxError("No regression baseline. Run `azzx regression baseline` first.")
    syntax=syntax_check_workspace(root); test_ok=run_tests(root,quiet=True); findings=security_scan(root,False); high=sum(1 for f in findings if f.get("severity")=="HIGH")
    problems=[]
    if len(syntax)>int(base.get("syntax_errors",0)): problems.append(f"syntax errors increased {base.get('syntax_errors',0)} → {len(syntax)}")
    if bool(base.get("tests_ok")) and not test_ok: problems.append("tests changed from passing to failing")
    if high>int(base.get("security_high",0)): problems.append(f"HIGH security findings increased {base.get('security_high',0)} → {high}")
    if benchmark_cmd and base.get("benchmark"):
        now=benchmark_command(root,benchmark_cmd); old=float((base.get("benchmark") or {}).get("average",0) or 0)
        if old>0 and float(now.get("average",0))>old*1.25: problems.append(f"benchmark slower by >25% ({old:.4f}s → {now['average']:.4f}s)")
    if problems: console.print(Panel("\n".join("- "+x for x in problems),title="REGRESSION BLOCKED",border_style="red")); return False
    console.print("[green]✓ Regression guard passed.[/]"); return True


def release_prepare(root: Path, version: str, forced_provider: str | None = None) -> Path:
    if not version.strip(): raise AzzxError("release-prepare requires VERSION")
    if regression_baseline_path(root).exists() and not regression_check(root): raise AzzxError("Release blocked by regression guard")
    if not run_tests(root,quiet=True): raise AzzxError("Release blocked: tests/checks failed")
    findings=security_scan(root,False); high=sum(1 for f in findings if f.get("severity")=="HIGH")
    if high and load_config().get("factory_security_gate",True): raise AzzxError(f"Release blocked: {high} HIGH security heuristic finding(s). Review .azzx/security-report.json")
    manifest=release_project(root,version)
    dist=root/"dist"; notes=dist/"RELEASE_NOTES.md"
    log=""
    gr=git_root(root)
    if gr:
        try: log=subprocess.run(["git","log","-10","--pretty=- %s"],cwd=gr,capture_output=True,text=True,timeout=10).stdout
        except Exception: pass
    atomic_write(notes,f"# Release {version}\n\n## Changes\n\n{log or '- Release candidate generated by AZZX. Review before publishing.'}\n\n## Verification\n\n- Tests/checks: PASS\n- Security gate: PASS\n- Manifest: {manifest.name}\n")
    sums=[]
    for p in sorted(dist.iterdir()):
        if p.is_file() and p.name!="checksums.txt": sums.append(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}")
    atomic_write(dist/"checksums.txt","\n".join(sums)+"\n")
    console.print(f"[green]✓ Release candidate prepared:[/] {dist}"); return manifest


def factory_develop(root: Path, goal: str, forced_provider: str | None = None, yes_merge: bool = False, package: bool = False) -> bool:
    if not goal.strip(): raise AzzxError("factory requires a goal")
    if not _spec_file(root,"product").exists(): spec_generate(root,goal,forced_provider)
    if not roadmap_path(root).exists(): roadmap_generate(root,goal,forced_provider)
    if not regression_baseline_path(root).exists(): capture_regression_baseline(root)
    ok=sandbox_develop(root,goal,forced_provider,yes_merge)
    if not ok: return False
    if not regression_check(root): return False
    if package:
        version=project_package_meta(root).get("version") or VERSION
        release_prepare(root,str(version),forced_provider)
    return True


class _DashboardHandler(__import__('http.server').server.BaseHTTPRequestHandler):
    root_path: Path = Path.cwd()
    def log_message(self, format: str, *args: Any) -> None:
        return
    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code); self.send_header("Content-Type",ctype); self.send_header("Content-Length",str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_GET(self) -> None:
        if self.path == "/api/health":
            body=json.dumps({"ok":True,"version":VERSION}).encode(); self._send(200,body,"application/json"); return
        if self.path == "/api/status":
            root=self.root_path; data={"workspace":str(root),"version":VERSION,"tasks":len(list(task_dir(root).glob('*.json'))),"issues":len(list(issue_dir(root).glob('*.json'))),"git":bool(git_root(root)),"roadmap":load_json(roadmap_path(root),{})}; body=json.dumps(data,ensure_ascii=False).encode(); self._send(200,body,"application/json"); return
        html=f"""<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width'><title>AZZX Dashboard</title><style>body{{font-family:system-ui;background:#111;color:#eee;max-width:920px;margin:auto;padding:24px}}pre{{background:#1b1b1b;padding:16px;border-radius:12px;overflow:auto}}h1{{font-size:24px}}</style></head><body><h1>AZZATSSINS LITE AGENT v{VERSION}</h1><p>{self.root_path}</p><pre id='out'>Loading…</pre><script>fetch('/api/status').then(r=>r.json()).then(x=>out.textContent=JSON.stringify(x,null,2))</script></body></html>""".encode(); self._send(200,html,"text/html; charset=utf-8")


def run_dashboard(root: Path, host: str = "127.0.0.1", port: int = 8765, open_browser: bool = False) -> None:
    import http.server, webbrowser
    if host not in {"127.0.0.1","localhost","::1"}: console.print("[yellow]Warning: dashboard is being bound beyond localhost. It has no authentication.[/]")
    handler=type("DashboardHandler",(_DashboardHandler,),{"root_path":root})
    server=http.server.ThreadingHTTPServer((host,port),handler); url=f"http://{host}:{port}/"; console.print(f"[green]AZZX dashboard:[/] {url}  [dim](Ctrl+C to stop)[/]")
    if open_browser:
        try: webbrowser.open(url)
        except Exception: pass
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()



def general_config_menu() -> None:
    while True:
        cfg = load_config()
        console.print(Panel(
            f"Mode: [cyan]{cfg.get('mode')}[/]\n"
            f"Max context: [cyan]{cfg.get('max_context_chars'):,} chars[/]\n"
            f"Max files: [cyan]{cfg.get('max_files')}[/]\n"
            f"Timeout: [cyan]{cfg.get('timeout_seconds')}s[/]\n"
            f"Debug iterations: [cyan]{cfg.get('max_debug_iterations', 4)}[/]\n"
            f"Auto test after edit: [cyan]{'ON' if cfg.get('auto_test_after_edit') else 'OFF'}[/]\n"
            f"Smart routing: [cyan]{'ON' if cfg.get('smart_routing', True) else 'OFF'}[/]",
            title="AZZX CONFIG",
            border_style="cyan",
        ))
        console.print("1. Change mode\n2. Max context chars\n3. Max context files\n4. Timeout\n5. Debug iterations\n6. Toggle auto-test\n7. Toggle smart routing\n8. Configure AI roles\n0. Back")
        choice = IntPrompt.ask("Pilih", default=0)
        if choice == 0:
            return
        if choice == 1:
            mode = Prompt.ask("Mode", choices=["safe", "normal", "auto"], default=str(cfg.get("mode", "safe")))
            cfg["mode"] = mode
        elif choice == 2:
            cfg["max_context_chars"] = IntPrompt.ask("Max chars", default=int(cfg.get("max_context_chars", 24000)))
        elif choice == 3:
            cfg["max_files"] = IntPrompt.ask("Max files", default=int(cfg.get("max_files", 8)))
        elif choice == 4:
            cfg["timeout_seconds"] = IntPrompt.ask("Timeout seconds", default=int(cfg.get("timeout_seconds", 120)))
        elif choice == 5:
            cfg["max_debug_iterations"] = IntPrompt.ask("Debug iterations", default=int(cfg.get("max_debug_iterations", 4)))
        elif choice == 6:
            cfg["auto_test_after_edit"] = not bool(cfg.get("auto_test_after_edit", False))
        elif choice == 7:
            cfg["smart_routing"] = not bool(cfg.get("smart_routing", True))
        elif choice == 8:
            save_config(cfg)
            configure_roles()
            continue
        save_config(cfg)
        console.print("[green]✓ Saved[/]")


def workspace_header(root: Path) -> None:
    cfg = load_config()
    providers = load_providers()
    pid = cfg.get("default_provider", "")
    provider = providers.get(pid, {})
    files = list_project_files(root)
    git_branch = "-"
    git = shutil.which("git")
    if git:
        try:
            proc = subprocess.run([git, "branch", "--show-current"], cwd=root, capture_output=True, text=True, timeout=3)
            if proc.returncode == 0 and proc.stdout.strip():
                git_branch = proc.stdout.strip()
        except Exception:
            pass
    try:
        sysctx = detect_system_context()
        system_label = f"{sysctx.distro_name} / {sysctx.arch}"
        pkg_label = sysctx.package_manager or "-"
    except Exception:
        system_label = platform.system()
        pkg_label = "-"
    values = [
        ("AI", provider.get("name", "not configured")),
        ("MODEL", provider.get("model", "-") or "-"),
        ("GIT", git_branch),
        ("FILES", str(len(files))),
        ("MODE", str(cfg.get("mode", "safe")).upper()),
        ("SYSTEM", system_label),
        ("PKG", pkg_label),
    ]
    if console.width >= 94:
        table = Table(box=box.SIMPLE_HEAVY, show_header=True, header_style="bold bright_cyan", expand=True)
        for label, _ in values:
            table.add_column(label, overflow="ellipsis", no_wrap=True)
        table.add_row(*[str(v) for _, v in values])
    else:
        table = Table(box=None, show_header=False, pad_edge=False)
        table.add_column(style="dim", width=9)
        table.add_column(style="cyan", overflow="fold")
        for label, value in values:
            table.add_row(label.title(), str(value))
    console.print(table)



# ---------------------------------------------------------------------------
# AZZX v10 Universal App Installer
# ---------------------------------------------------------------------------

APP_INSTALL_RECORDS = DATA_HOME / "installed_apps.json"
APP_RECIPES_HOME = CONFIG_HOME / "recipes"
ISOLATED_APPS_HOME = DATA_HOME / "isolated_apps"


@dataclass
class SystemContext:
    environment: str
    distro_id: str
    distro_name: str
    distro_like: str
    version_id: str
    arch: str
    package_manager: str
    is_root: bool
    has_sudo: bool


@dataclass
class AppPlan:
    requested: str
    app_id: str
    method: str
    manager: str
    packages: list[str] = field(default_factory=list)
    verify: list[str] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    source_url: str = ""
    trusted: bool = True
    notes: list[str] = field(default_factory=list)


# Native aliases are intentionally conservative. If a package is absent, AZZX
# probes the local repository instead of assuming that another distro's name is
# valid. Package managers remain responsible for dependency resolution.
BUILTIN_APP_RECIPES: dict[str, dict[str, Any]] = {
    "git": {"packages": {"default": ["git"]}, "verify": ["git"]},
    "curl": {"packages": {"default": ["curl"]}, "verify": ["curl"]},
    "wget": {"packages": {"default": ["wget"]}, "verify": ["wget"]},
    "ffmpeg": {"packages": {"default": ["ffmpeg"]}, "verify": ["ffmpeg"]},
    "nmap": {"packages": {"default": ["nmap"]}, "verify": ["nmap"]},
    "ripgrep": {"packages": {"default": ["ripgrep"]}, "verify": ["rg"]},
    "python": {
        "packages": {"apt": ["python3"], "pkg": ["python"], "pacman": ["python"], "default": ["python3", "python"]},
        "verify": ["python3", "python"],
    },
    "node": {
        "packages": {"apt": ["nodejs"], "pkg": ["nodejs"], "pacman": ["nodejs"], "default": ["nodejs"]},
        "verify": ["node", "nodejs"],
    },
    "nodejs": {
        "packages": {"default": ["nodejs"]},
        "verify": ["node", "nodejs"],
    },
    "nginx": {"packages": {"default": ["nginx"]}, "verify": ["nginx"]},
    "docker": {
        "packages": {"apt": ["docker.io"], "pacman": ["docker"], "dnf": ["docker"], "default": ["docker"]},
        "verify": ["docker"],
        "notes": ["Docker service setup varies by distro; AZZX installs the package but does not silently enable privileged services."],
    },
    "adb": {
        "packages": {"apt": ["adb"], "pacman": ["android-tools"], "pkg": ["android-tools"], "default": ["adb", "android-tools"]},
        "verify": ["adb"],
    },
    "java": {
        "packages": {"apt": ["default-jdk"], "pacman": ["jdk-openjdk"], "pkg": ["openjdk-21"], "dnf": ["java-latest-openjdk-devel"], "default": ["openjdk"]},
        "verify": ["java", "javac"],
    },
    "metasploit": {
        "packages": {
            "pacman": ["metasploit"],
            "apt": ["metasploit-framework", "metasploit"],
            "pkg": ["metasploit"],
            "default": ["metasploit-framework", "metasploit"],
        },
        "verify": ["msfconsole", "/opt/metasploit-framework/bin/msfconsole"],
        "official_script": {
            "url": "https://raw.githubusercontent.com/rapid7/metasploit-omnibus/master/config/templates/metasploit-framework-wrappers/msfupdate.erb",
            "environments": ["linux", "wsl", "container"],
            "architectures": ["x86_64", "amd64"],
            "label": "Rapid7 official Metasploit Framework nightly installer",
        },
        "notes": [
            "AZZX prefers a native distro package when available.",
            "The official Rapid7 fallback is not used automatically on Termux.",
        ],
    },
}


def _read_os_release() -> dict[str, str]:
    data: dict[str, str] = {}
    path = Path("/etc/os-release")
    if not path.exists():
        return data
    try:
        for raw in path.read_text(errors="ignore").splitlines():
            if "=" not in raw or raw.lstrip().startswith("#"):
                continue
            k, v = raw.split("=", 1)
            data[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return data


def detect_system_context() -> SystemContext:
    arch = platform.machine() or "unknown"
    prefix = os.environ.get("PREFIX", "")
    termux = bool(os.environ.get("TERMUX_VERSION")) or "com.termux" in prefix
    release = _read_os_release()
    distro_id = release.get("ID", "linux").lower()
    distro_name = release.get("PRETTY_NAME") or release.get("NAME") or platform.system() or "Linux"
    distro_like = release.get("ID_LIKE", "").lower()
    version_id = release.get("VERSION_ID", "")

    if termux:
        environment = "termux"
        distro_id = "termux"
        distro_name = "Termux"
        distro_like = "android"
    else:
        environment = "linux"
        try:
            proc_version = Path("/proc/version").read_text(errors="ignore").lower()
        except OSError:
            proc_version = ""
        if "microsoft" in proc_version or os.environ.get("WSL_DISTRO_NAME"):
            environment = "wsl"
        elif Path("/.dockerenv").exists() or os.environ.get("container"):
            environment = "container"
        elif os.environ.get("PROOT_LOADER") or os.environ.get("PROOT_TMP_DIR"):
            environment = "proot"

    candidates: list[tuple[str, str]] = []
    if termux:
        candidates.append(("pkg", "pkg"))
    candidates.extend([
        ("apt", "apt-get"),
        ("pacman", "pacman"),
        ("dnf", "dnf"),
        ("yum", "yum"),
        ("zypper", "zypper"),
        ("apk", "apk"),
        ("xbps", "xbps-install"),
        ("emerge", "emerge"),
    ])
    manager = ""
    for label, executable in candidates:
        if shutil.which(executable):
            manager = label
            break
    is_root = bool(hasattr(os, "geteuid") and os.geteuid() == 0)
    return SystemContext(
        environment=environment,
        distro_id=distro_id,
        distro_name=distro_name,
        distro_like=distro_like,
        version_id=version_id,
        arch=arch,
        package_manager=manager,
        is_root=is_root,
        has_sudo=bool(shutil.which("sudo")),
    )


def _sanitize_package_name(name: str) -> str:
    value = name.strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9+._:@-]*", value):
        raise AzzxError(f"Invalid package/application name: {name!r}")
    return value


def _recipe_dir() -> Path:
    APP_RECIPES_HOME.mkdir(parents=True, exist_ok=True)
    return APP_RECIPES_HOME


def _validate_external_recipe(obj: dict[str, Any], source: Path) -> dict[str, Any]:
    # User recipes may define native package aliases and verifier executables.
    # Arbitrary shell/install scripts are deliberately ignored.
    app_id = str(obj.get("id") or source.stem).strip().lower()
    _sanitize_package_name(app_id)
    packages = obj.get("packages") or {}
    if not isinstance(packages, dict):
        raise AzzxError(f"Recipe {source} has invalid packages mapping")
    clean_packages: dict[str, list[str]] = {}
    for manager, vals in packages.items():
        if isinstance(vals, str):
            vals = [vals]
        if not isinstance(vals, list):
            continue
        clean_packages[str(manager)] = [_sanitize_package_name(str(x)) for x in vals]
    verify = obj.get("verify") or []
    if isinstance(verify, str):
        verify = [verify]
    return {
        "id": app_id,
        "packages": clean_packages,
        "verify": [str(x) for x in verify if isinstance(x, str)],
        "notes": [str(x) for x in (obj.get("notes") or []) if isinstance(x, str)],
        "external": True,
    }


def load_app_recipes() -> dict[str, dict[str, Any]]:
    recipes = {k: dict(v) for k, v in BUILTIN_APP_RECIPES.items()}
    for path in sorted(_recipe_dir().glob("*.json")):
        try:
            raw = load_json(path, {})
            if not isinstance(raw, dict):
                continue
            rec = _validate_external_recipe(raw, path)
            recipes[rec["id"]] = rec
        except Exception:
            continue
    return recipes


def _manager_alias_key(manager: str) -> str:
    return "dnf" if manager == "yum" else manager


def app_package_candidates(app: str, manager: str, recipes: dict[str, dict[str, Any]] | None = None) -> list[str]:
    app_id = _sanitize_package_name(app.lower())
    recipes = recipes or load_app_recipes()
    recipe = recipes.get(app_id, {})
    mapping = recipe.get("packages") or {}
    key = _manager_alias_key(manager)
    vals = mapping.get(key) or mapping.get(manager) or mapping.get("default") or [app_id]
    if isinstance(vals, str):
        vals = [vals]
    result: list[str] = []
    for item in vals:
        try:
            clean = _sanitize_package_name(str(item))
        except AzzxError:
            continue
        if clean not in result:
            result.append(clean)
    if app_id not in result:
        result.append(app_id)
    return result


def _privilege_prefix(ctx: SystemContext) -> list[str]:
    if ctx.environment == "termux" or ctx.is_root:
        return []
    if ctx.has_sudo:
        return ["sudo"]
    if shutil.which("doas"):
        return ["doas"]
    raise AzzxError("This package manager needs administrator privileges, but neither sudo nor doas is available.")


def package_query_command(manager: str, package: str) -> list[str] | None:
    package = _sanitize_package_name(package)
    table = {
        "pkg": ["pkg", "show", package],
        "apt": ["apt-cache", "show", package],
        "pacman": ["pacman", "-Si", package],
        "dnf": ["dnf", "info", package],
        "yum": ["yum", "info", package],
        "zypper": ["zypper", "--non-interactive", "info", package],
        "apk": ["apk", "search", "-x", package],
        "xbps": ["xbps-query", "-Rs", f"^{package}-"],
        "emerge": ["emerge", "--search", package],
    }
    cmd = table.get(manager)
    if not cmd or not shutil.which(cmd[0]):
        return None
    return cmd


def package_available(manager: str, package: str, timeout: int = 12) -> bool:
    cmd = package_query_command(manager, package)
    if not cmd:
        return False
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except Exception:
        return False
    if proc.returncode != 0:
        return False
    output = (proc.stdout + "\n" + proc.stderr).strip().lower()
    if manager == "apk":
        return any(line.split("-")[0] == package.lower() or line.startswith(package.lower() + "-") for line in output.splitlines())
    if manager == "xbps":
        return package.lower() in output
    if manager == "emerge":
        return "[ results for search key" in output and "0 matches" not in output
    return bool(output) or proc.returncode == 0


def package_action_command(ctx: SystemContext, action: str, packages: list[str]) -> list[str]:
    if not ctx.package_manager:
        raise AzzxError("No supported native package manager was detected.")
    packages = [_sanitize_package_name(x) for x in packages]
    mgr = ctx.package_manager
    prefix = _privilege_prefix(ctx)
    if mgr == "pkg":
        verb = {"install": "install", "remove": "uninstall", "update": "install"}.get(action)
        if not verb: raise AzzxError(f"Unsupported package action: {action}")
        return ["pkg", verb, "-y", *packages]
    if mgr == "apt":
        if action == "install": return prefix + ["apt-get", "install", "-y", *packages]
        if action == "remove": return prefix + ["apt-get", "remove", "-y", *packages]
        if action == "update": return prefix + ["apt-get", "install", "--only-upgrade", "-y", *packages]
    if mgr == "pacman":
        if action in {"install", "update"}: return prefix + ["pacman", "-S", "--needed", "--noconfirm", *packages]
        if action == "remove": return prefix + ["pacman", "-R", "--noconfirm", *packages]
    if mgr in {"dnf", "yum"}:
        exe = mgr
        if action == "install": return prefix + [exe, "install", "-y", *packages]
        if action == "remove": return prefix + [exe, "remove", "-y", *packages]
        if action == "update": return prefix + [exe, "upgrade", "-y", *packages]
    if mgr == "zypper":
        if action == "install": return prefix + ["zypper", "--non-interactive", "install", *packages]
        if action == "remove": return prefix + ["zypper", "--non-interactive", "remove", *packages]
        if action == "update": return prefix + ["zypper", "--non-interactive", "update", *packages]
    if mgr == "apk":
        if action == "install": return prefix + ["apk", "add", *packages]
        if action == "remove": return prefix + ["apk", "del", *packages]
        if action == "update": return prefix + ["apk", "upgrade", *packages]
    if mgr == "xbps":
        if action in {"install", "update"}: return prefix + ["xbps-install", "-Sy", *packages]
        if action == "remove": return prefix + ["xbps-remove", "-Ry", *packages]
    if mgr == "emerge":
        if action in {"install", "update"}: return prefix + ["emerge", "--ask=n", *packages]
        if action == "remove": return prefix + ["emerge", "--ask=n", "--depclean", *packages]
    raise AzzxError(f"Unsupported package manager/action combination: {mgr}/{action}")


def package_search_command(manager: str, query: str) -> list[str] | None:
    q = query.strip()
    if not q:
        return None
    table = {
        "pkg": ["pkg", "search", q],
        "apt": ["apt-cache", "search", q],
        "pacman": ["pacman", "-Ss", q],
        "dnf": ["dnf", "search", q],
        "yum": ["yum", "search", q],
        "zypper": ["zypper", "--non-interactive", "search", q],
        "apk": ["apk", "search", q],
        "xbps": ["xbps-query", "-Rs", q],
        "emerge": ["emerge", "--search", q],
    }
    cmd = table.get(manager)
    if not cmd or not shutil.which(cmd[0]):
        return None
    return cmd


def _verify_app(candidates: list[str]) -> tuple[bool, str]:
    for value in candidates:
        if value.startswith("/"):
            p = Path(value)
            if p.exists() and os.access(p, os.X_OK):
                return True, str(p)
        else:
            found = shutil.which(value)
            if found:
                return True, found
    return False, ""


def _official_script_allowed(recipe: dict[str, Any], ctx: SystemContext) -> bool:
    spec = recipe.get("official_script")
    if not isinstance(spec, dict):
        return False
    envs = [str(x) for x in spec.get("environments", [])]
    arches = [str(x).lower() for x in spec.get("architectures", [])]
    if envs and ctx.environment not in envs:
        return False
    if arches and ctx.arch.lower() not in arches:
        return False
    url = str(spec.get("url") or "")
    parsed = urllib.parse.urlparse(url)
    return parsed.scheme == "https" and parsed.netloc in {"raw.githubusercontent.com", "github.com", "downloads.metasploit.com"}


def resolve_app_plan(app: str, probe: bool = True) -> AppPlan:
    app_id = _sanitize_package_name(app.lower())
    ctx = detect_system_context()
    recipes = load_app_recipes()
    recipe = recipes.get(app_id, {})
    verify = [str(x) for x in (recipe.get("verify") or [app_id])]
    notes = [str(x) for x in (recipe.get("notes") or [])]
    manager = ctx.package_manager
    candidates = app_package_candidates(app_id, manager, recipes) if manager else []
    chosen = ""
    if manager:
        if probe:
            with console.status(f"[cyan]Checking {manager} repositories for {app_id}...[/]", spinner="dots"):
                for candidate in candidates:
                    if package_available(manager, candidate):
                        chosen = candidate
                        break
        elif candidates:
            chosen = candidates[0]
    if chosen:
        return AppPlan(
            requested=app,
            app_id=app_id,
            method="native",
            manager=manager,
            packages=[chosen],
            verify=verify,
            steps=[
                f"Use {manager} package manager",
                f"Install package: {chosen}",
                "Let the package manager resolve/download dependencies",
                "Verify application executable",
                "Record installation in AZZX history",
            ],
            notes=notes,
        )
    if recipe and _official_script_allowed(recipe, ctx):
        spec = recipe["official_script"]
        return AppPlan(
            requested=app,
            app_id=app_id,
            method="official-script",
            manager=manager,
            verify=verify,
            source_url=str(spec.get("url")),
            steps=[
                f"Download trusted installer: {spec.get('label', 'official installer')}",
                "Calculate and display SHA-256 of downloaded installer",
                "Execute installer after permission/confirmation",
                "Verify application executable",
                "Record installation in AZZX history",
            ],
            notes=notes + ["Trusted vendor script fallback is used only when no native package is available."],
        )
    return AppPlan(
        requested=app,
        app_id=app_id,
        method="unresolved",
        manager=manager,
        verify=verify,
        steps=["Search the native repository", "Check AZZX trusted recipes", "Stop before executing an untrusted installation method"],
        trusted=False,
        notes=notes + ["No verified native package or trusted executable recipe was found for this system."],
    )


def render_app_plan(plan: AppPlan, ctx: SystemContext | None = None) -> None:
    ctx = ctx or detect_system_context()
    title = Text.assemble(("APP INSTALL PLAN", "bold bright_cyan"), (f"  {plan.app_id}", "bold white"))
    info = Table(box=box.SIMPLE, show_header=False, pad_edge=False)
    info.add_column(style="dim", width=14)
    info.add_column(style="white")
    info.add_row("System", f"{ctx.distro_name} ({ctx.environment})")
    info.add_row("Architecture", ctx.arch)
    info.add_row("Package mgr", plan.manager or "none")
    info.add_row("Method", plan.method)
    info.add_row("Package", ", ".join(plan.packages) or "-")
    info.add_row("Trusted", "YES" if plan.trusted else "NO / unresolved")
    steps = Table(box=box.MINIMAL, show_header=False)
    steps.add_column("#", style="cyan", width=3)
    steps.add_column("Step")
    for i, step in enumerate(plan.steps, 1):
        steps.add_row(str(i), step)
    groups: list[Any] = [title, info, Rule(style="cyan"), steps]
    if plan.notes:
        groups.extend([Rule(style="dim"), Text("\n".join("• " + n for n in plan.notes), style="yellow")])
    console.print(Panel(Group(*groups), border_style="bright_cyan", box=box.ROUNDED))


def _run_live_process(cmd: list[str], title: str, cwd: Path | None = None) -> int:
    cfg = load_config()
    max_lines = max(4, int(cfg.get("app_install_output_lines", 10)))
    shown = " ".join(shlex.quote(x) for x in cmd)
    lines: list[str] = []
    proc = subprocess.Popen(cmd, cwd=str(cwd) if cwd else None, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    with Live(console=console, refresh_per_second=8, transient=False) as live:
        live.update(Panel(Text(f"Starting...\n\n$ {shown}", style="cyan"), title=title, border_style="cyan"))
        assert proc.stdout is not None
        for raw in proc.stdout:
            line = raw.rstrip()
            if line:
                lines.append(line)
                tail = lines[-max_lines:]
                body = Text("\n".join(tail))
                live.update(Panel(body, title=f"{title}  •  running", subtitle="$ " + shown, border_style="bright_cyan"))
        rc = proc.wait()
        tail = lines[-max_lines:] or ["(no output)"]
        style = "green" if rc == 0 else "red"
        live.update(Panel(Text("\n".join(tail)), title=f"{title}  •  {'DONE' if rc == 0 else 'FAILED'}", subtitle=f"exit {rc}", border_style=style))
    return rc


def _load_install_records() -> dict[str, Any]:
    data = load_json(APP_INSTALL_RECORDS, {})
    return data if isinstance(data, dict) else {}


def _save_install_records(data: dict[str, Any]) -> None:
    DATA_HOME.mkdir(parents=True, exist_ok=True)
    save_json(APP_INSTALL_RECORDS, data, private=True)


def _record_install(plan: AppPlan, verify_path: str = "") -> None:
    records = _load_install_records()
    records[plan.app_id] = {
        "app": plan.app_id,
        "requested": plan.requested,
        "method": plan.method,
        "manager": plan.manager,
        "packages": plan.packages,
        "verify": plan.verify,
        "verify_path": verify_path,
        "source_url": plan.source_url,
        "installed_at": dt.datetime.now().isoformat(timespec="seconds"),
        "system": detect_system_context().__dict__,
    }
    _save_install_records(records)


def _isolated_app_dir(app: str) -> Path:
    app_id = _sanitize_package_name(app.lower())
    base = ISOLATED_APPS_HOME.resolve()
    target = (base / app_id).resolve()
    try:
        target.relative_to(base)
    except ValueError as exc:
        raise AzzxError("Invalid isolated application path") from exc
    return target


def resolve_isolated_plan(app: str) -> AppPlan:
    app_id = _sanitize_package_name(app.lower())
    target = _isolated_app_dir(app_id)
    return AppPlan(
        requested=app,
        app_id=app_id,
        method="python-venv",
        manager="python/pip",
        packages=[app_id],
        verify=[],
        steps=[
            f"Create isolated Python venv: {target}",
            f"Install PyPI package: {app_id}",
            "Let pip resolve Python dependencies inside the isolated venv",
            "Detect generated CLI executables",
            "Record isolated environment in AZZX history",
        ],
        notes=["Isolated mode is intended for Python/PyPI CLI packages. It does not replace native OS packages for desktop/system applications."],
    )


def _discover_venv_commands(venv: Path) -> list[str]:
    bindir = venv / ("Scripts" if os.name == "nt" else "bin")
    if not bindir.exists():
        return []
    ignore = {"python", "python3", "pip", "pip3", "activate", "activate.csh", "activate.fish", "Activate.ps1"}
    out: list[str] = []
    for path in sorted(bindir.iterdir()):
        if path.name in ignore or path.name.startswith("python") or path.name.startswith("pip"):
            continue
        if path.is_file() and os.access(path, os.X_OK):
            out.append(str(path.resolve()))
    return out


def _record_isolated_install(plan: AppPlan, venv: Path, commands: list[str]) -> None:
    _record_install(plan, commands[0] if commands else "")
    records = _load_install_records()
    rec = records.get(plan.app_id, {})
    rec["venv"] = str(venv)
    rec["verify"] = commands
    rec["commands"] = commands
    records[plan.app_id] = rec
    _save_install_records(records)


def install_app(app: str, plan_only: bool = False, dry_run: bool = False, yes: bool = False, force: bool = False, isolated: bool = False) -> bool:
    app_id = _sanitize_package_name(app.lower())
    ctx = detect_system_context()
    if isolated:
        plan = resolve_isolated_plan(app_id)
        venv = _isolated_app_dir(app_id)
        existing_commands = _discover_venv_commands(venv) if venv.exists() else []
        ok, where = (bool(existing_commands), existing_commands[0] if existing_commands else "")
    else:
        recipe = load_app_recipes().get(app_id, {})
        verify = [str(x) for x in (recipe.get("verify") or [app_id])]
        ok, where = _verify_app(verify)
        if ok and not force and not plan_only and not dry_run:
            console.print(Panel(f"[green]✓ {app_id} is already available[/]\n[dim]{where}[/]", title="APP READY", border_style="green"))
            return True
        plan = resolve_app_plan(app_id, probe=True)
    if ok:
        plan.notes.append(f"Executable is already present: {where}")
    render_app_plan(plan, ctx)
    if plan_only:
        return True
    if plan.method == "unresolved":
        raise AzzxError(f"No trusted installation method was resolved for '{app_id}'. Try `azzx app search {app_id}` or add a native-package recipe in {APP_RECIPES_HOME}.")
    if dry_run:
        console.print("[yellow]DRY RUN:[/] no system changes were made.")
        return True
    require_permission("package.install", f"Install application: {app_id}")
    if not yes and not Confirm.ask(f"Install {app_id} using {plan.method}?", default=False):
        console.print("[yellow]Installation cancelled.[/]")
        return False

    if plan.method == "native":
        cmd = package_action_command(ctx, "install", plan.packages)
        rc = _run_live_process(cmd, f"Installing {app_id}")
        if rc != 0:
            raise AzzxError(f"{ctx.package_manager} installation failed with exit code {rc}.")
    elif plan.method == "python-venv":
        require_permission("network.http", f"Download Python package/dependencies for {app_id}")
        venv = _isolated_app_dir(app_id)
        if force and venv.exists(): shutil.rmtree(venv)
        venv.parent.mkdir(parents=True, exist_ok=True)
        if not venv.exists():
            rc = _run_live_process([sys.executable, "-m", "venv", str(venv)], f"Creating isolated environment: {app_id}")
            if rc != 0: raise AzzxError("Could not create isolated Python environment.")
        py = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        rc = _run_live_process([str(py), "-m", "pip", "install", "--upgrade", "pip"], f"Preparing pip: {app_id}")
        if rc != 0: raise AzzxError("Could not prepare pip in isolated environment.")
        rc = _run_live_process([str(py), "-m", "pip", "install", app_id], f"Installing isolated app: {app_id}")
        if rc != 0: raise AzzxError(f"PyPI isolated installation failed for {app_id}.")
        commands = _discover_venv_commands(venv)
        _record_isolated_install(plan, venv, commands)
        if commands:
            console.print(Panel("\n".join(commands), title="ISOLATED COMMANDS", border_style="green"))
        else:
            console.print("[yellow]Package installed in the venv, but no standalone CLI executable was detected.[/]")
        return True
    elif plan.method == "official-script":
        require_permission("network.http", f"Download trusted installer for {app_id}")
        require_permission("shell.run", f"Execute trusted vendor installer for {app_id}")
        with console.status("[cyan]Downloading official installer...[/]", spinner="earth"):
            try:
                response = httpx.get(plan.source_url, follow_redirects=True, timeout=60)
                response.raise_for_status()
            except Exception as exc:
                raise AzzxError(f"Official installer download failed: {exc}") from exc
        data = response.content
        sha = hashlib.sha256(data).hexdigest()
        console.print(f"[dim]Downloaded SHA-256:[/] [cyan]{sha}[/]")
        with tempfile.TemporaryDirectory(prefix="azzx-install-") as td:
            script = Path(td) / f"install-{app_id}"
            script.write_bytes(data)
            script.chmod(0o700)
            rc = _run_live_process([str(script)], f"Vendor installer: {app_id}")
            if rc != 0:
                raise AzzxError(f"Official installer failed with exit code {rc}.")
    ok, where = _verify_app(plan.verify)
    if not ok:
        console.print("[yellow]Installation command completed, but the expected executable was not found in PATH yet.[/]")
    else:
        console.print(Panel(f"[bold green]✓ INSTALLATION VERIFIED[/]\n{where}", border_style="green"))
    _record_install(plan, where)
    return True


def _isolated_record_health(app_id: str, rec: dict[str, Any]) -> tuple[bool, str]:
    venv = Path(str(rec.get("venv") or ""))
    py = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not py.exists():
        return False, ""
    try:
        proc = subprocess.run([str(py), "-m", "pip", "show", app_id], capture_output=True, text=True, timeout=10)
        return (proc.returncode == 0, str(venv))
    except Exception:
        return False, ""


def installed_apps() -> dict[str, Any]:
    records = _load_install_records()
    table = Table(title="AZZX Installed Applications", box=box.ROUNDED, header_style="bold cyan")
    table.add_column("Application")
    table.add_column("Method")
    table.add_column("Package")
    table.add_column("Status")
    table.add_column("Installed")
    for name, rec in sorted(records.items()):
        verify = [str(x) for x in (rec.get("verify") or [name])]
        if rec.get("method") == "python-venv":
            ok, _ = _isolated_record_health(name, rec)
        else:
            ok, _ = _verify_app(verify)
        table.add_row(name, str(rec.get("method", "-")), ", ".join(rec.get("packages") or []) or "-", "[green]READY[/]" if ok else "[yellow]MISSING[/]", str(rec.get("installed_at", "-")))
    if records:
        console.print(table)
    else:
        console.print(Panel("No applications have been recorded by AZZX yet.", title="INSTALLED", border_style="dim"))
    return records


def uninstall_app(app: str, yes: bool = False, dry_run: bool = False) -> bool:
    app_id = _sanitize_package_name(app.lower())
    records = _load_install_records()
    rec = records.get(app_id)
    if not rec:
        raise AzzxError(f"'{app_id}' is not in AZZX installation history. AZZX will not guess an uninstall command for untracked software.")
    if rec.get("method") == "python-venv":
        venv = Path(str(rec.get("venv") or "")).expanduser().resolve()
        base = ISOLATED_APPS_HOME.resolve()
        try: venv.relative_to(base)
        except ValueError as exc: raise AzzxError("Refusing to remove an isolated path outside AZZX data directory.") from exc
        console.print(Panel(str(venv), title=f"UNINSTALL ISOLATED {app_id}", border_style="yellow"))
        if dry_run: return True
        require_permission("package.install", f"Remove isolated application: {app_id}")
        if not yes and not Confirm.ask(f"Remove isolated environment for {app_id}?", default=False): return False
        if venv.exists(): shutil.rmtree(venv)
        records.pop(app_id, None); _save_install_records(records)
        return True
    if rec.get("method") != "native" or not rec.get("packages"):
        raise AzzxError("Safe automatic uninstall is available for native-package and AZZX-isolated installs. This installation used a vendor installer.")
    ctx = detect_system_context()
    cmd = package_action_command(ctx, "remove", [str(x) for x in rec.get("packages", [])])
    console.print(Panel("$ " + " ".join(shlex.quote(x) for x in cmd), title=f"UNINSTALL {app_id}", border_style="yellow"))
    if dry_run:
        console.print("[yellow]DRY RUN:[/] no system changes were made.")
        return True
    require_permission("package.install", f"Uninstall application: {app_id}")
    if not yes and not Confirm.ask(f"Remove {app_id}? Shared dependencies will be left to the package manager policy.", default=False):
        return False
    rc = _run_live_process(cmd, f"Removing {app_id}")
    if rc != 0:
        raise AzzxError(f"Uninstall failed with exit code {rc}.")
    records.pop(app_id, None)
    _save_install_records(records)
    return True


def update_app(app: str, yes: bool = False, dry_run: bool = False) -> bool:
    app_id = _sanitize_package_name(app.lower())
    rec = _load_install_records().get(app_id)
    if rec and rec.get("method") == "python-venv":
        venv = Path(str(rec.get("venv") or ""))
        py = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        if not py.exists(): raise AzzxError(f"Isolated environment for {app_id} is missing. Run `azzx repair {app_id}`.")
        cmd = [str(py), "-m", "pip", "install", "--upgrade", app_id]
    elif rec and rec.get("method") == "native" and rec.get("packages"):
        ctx = detect_system_context()
        cmd = package_action_command(ctx, "update", [str(x) for x in rec.get("packages", [])])
    elif app_id == "metasploit" and shutil.which("msfupdate"):
        cmd = [shutil.which("msfupdate") or "msfupdate"]
    else:
        plan = resolve_app_plan(app_id, probe=True)
        if plan.method != "native":
            raise AzzxError(f"No safe automatic update strategy is available for '{app_id}'.")
        ctx = detect_system_context()
        cmd = package_action_command(ctx, "update", plan.packages)
    console.print(Panel("$ " + " ".join(shlex.quote(x) for x in cmd), title=f"UPDATE {app_id}", border_style="cyan"))
    if dry_run:
        return True
    require_permission("package.install", f"Update application: {app_id}")
    if not yes and not Confirm.ask(f"Update {app_id}?", default=False):
        return False
    return _run_live_process(cmd, f"Updating {app_id}") == 0


def update_all_apps(yes: bool = False, dry_run: bool = False) -> bool:
    records = _load_install_records()
    if not records:
        console.print("[yellow]No AZZX-tracked applications to update.[/]")
        return True
    failures: list[str] = []
    for name in sorted(records):
        console.print(Rule(f"Updating {name}", style="cyan"))
        try:
            if not update_app(name, yes=yes, dry_run=dry_run): failures.append(name)
        except AzzxError as exc:
            failures.append(name); console.print(Panel(str(exc), title=f"UPDATE FAILED: {name}", border_style="red"))
    if failures:
        console.print(f"[yellow]Completed with failures:[/] {', '.join(failures)}")
        return False
    console.print("[green]✓ All AZZX-tracked applications processed.[/]")
    return True


def repair_app(app: str, yes: bool = False, dry_run: bool = False) -> bool:
    app_id = _sanitize_package_name(app.lower())
    records = _load_install_records()
    rec = records.get(app_id, {})
    verify = [str(x) for x in (rec.get("verify") or load_app_recipes().get(app_id, {}).get("verify") or [app_id])]
    if rec.get("method") == "python-venv":
        ok, where = _isolated_record_health(app_id, rec)
    else:
        ok, where = _verify_app(verify)
    if ok:
        console.print(Panel(f"[green]✓ {app_id} verification passed[/]\n[dim]{where}[/]", title="REPAIR CHECK", border_style="green"))
        return True
    console.print(Panel(f"[yellow]{app_id} executable is missing or unhealthy.[/]\nAZZX will attempt a reinstall using the trusted resolver.", title="REPAIR", border_style="yellow"))
    return install_app(app_id, dry_run=dry_run, yes=yes, force=True, isolated=(rec.get("method") == "python-venv"))


def app_search(query: str) -> list[str]:
    ctx = detect_system_context()
    if not ctx.package_manager:
        raise AzzxError("No supported package manager was detected.")
    cmd = package_search_command(ctx.package_manager, query)
    if not cmd:
        raise AzzxError(f"Search is not supported for package manager {ctx.package_manager}.")
    with console.status(f"[cyan]Searching {ctx.package_manager} repositories...[/]", spinner="dots"):
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=35)
        except Exception as exc:
            raise AzzxError(f"Package search failed: {exc}") from exc
    raw = (proc.stdout or proc.stderr or "").strip()
    lines = [line for line in raw.splitlines() if line.strip()]
    shown = lines[:40]
    console.print(Panel("\n".join(shown) if shown else "No results.", title=f"SEARCH: {query}", border_style="cyan"))
    if len(lines) > len(shown):
        console.print(f"[dim]Showing {len(shown)} of {len(lines)} lines.[/]")
    return lines


def app_info(app: str) -> AppPlan:
    plan = resolve_app_plan(app, probe=True)
    render_app_plan(plan)
    ok, where = _verify_app(plan.verify)
    console.print(f"[dim]Executable:[/] {'[green]READY[/] ' + where if ok else '[yellow]not currently found[/]'}")
    return plan


def app_recipes_table() -> None:
    recipes = load_app_recipes()
    table = Table(title="AZZX App Recipes", box=box.ROUNDED, header_style="bold cyan")
    table.add_column("ID")
    table.add_column("Native aliases")
    table.add_column("Verifier")
    table.add_column("Type")
    for app_id, rec in sorted(recipes.items()):
        aliases = rec.get("packages") or {}
        count = sum(len(v if isinstance(v, list) else [v]) for v in aliases.values()) if isinstance(aliases, dict) else 0
        table.add_row(app_id, str(count), ", ".join(rec.get("verify") or []) or "-", "custom" if rec.get("external") else "builtin")
    console.print(table)
    console.print(f"[dim]Custom recipe directory:[/] {APP_RECIPES_HOME}")


def render_system_card() -> SystemContext:
    ctx = detect_system_context()
    table = Table(box=box.SIMPLE, show_header=False)
    table.add_column(style="dim", width=15)
    table.add_column(style="cyan")
    table.add_row("Environment", ctx.environment)
    table.add_row("Distribution", ctx.distro_name)
    table.add_row("Distro ID", ctx.distro_id)
    table.add_row("Architecture", ctx.arch)
    table.add_row("Package manager", ctx.package_manager or "not detected")
    privilege = "root" if ctx.is_root else ("sudo available" if ctx.has_sudo else ("doas available" if shutil.which("doas") else "user / no sudo-doas"))
    table.add_row("Privilege", privilege)
    console.print(Panel(table, title="SYSTEM / PACKAGE ENGINE", border_style="bright_cyan"))
    return ctx


def render_home_screen(root: Path) -> None:
    code = Table.grid(padding=(0, 1))
    code.add_column(style="bold cyan", width=14)
    code.add_column()
    for cmd, desc in [
        ("/fix", "Repair code"), ("/agent", "Multi-agent task"), ("/factory", "Software factory"),
        ("/test", "Run tests"), ("/map", "Repository intelligence"), ("/security", "Security scan")
    ]:
        code.add_row(cmd, desc)
    apps = Table.grid(padding=(0, 1))
    apps.add_column(style="bold magenta", width=14)
    apps.add_column()
    for cmd, desc in [
        ("/apps", "Application Center"), ("/install APP", "Smart install"), ("/installed", "Installation history"),
        ("/repair APP", "Repair app"), ("/env", "System detection"), ("/doctor", "AZZX health")
    ]:
        apps.add_row(cmd, desc)
    panels = [
        Panel(code, title="◈ CODE / ENGINEERING", border_style="cyan", box=box.ROUNDED),
        Panel(apps, title="◆ SYSTEM / APPS", border_style="magenta", box=box.ROUNDED),
    ]
    if console.width >= 86:
        console.print(Columns(panels, equal=True, expand=True))
    else:
        for panel in panels:
            console.print(panel)


def app_center_menu() -> None:
    while True:
        console.clear()
        banner(compact=True)
        ctx = render_system_card()
        records = _load_install_records()
        console.print(Panel(
            f"[bold]{len(records)}[/] AZZX-tracked apps  •  [bold]{len(load_app_recipes())}[/] recipes  •  package manager [bold cyan]{ctx.package_manager or '-'}[/]",
            title="APPLICATION CENTER", border_style="magenta"
        ))
        menu = Table(box=box.SIMPLE_HEAVY, show_header=False)
        menu.add_column(style="bold magenta", width=5)
        menu.add_column(style="white")
        for key, text in [("1", "Install application"), ("2", "Search repository"), ("3", "Installed applications"), ("4", "Repair application"), ("5", "Update application"), ("6", "Uninstall application"), ("7", "Browse recipes"), ("8", "Update all AZZX-tracked applications"), ("0", "Back")]:
            menu.add_row(key, text)
        console.print(menu)
        choice = Prompt.ask("[bold cyan]Select[/]", default="0").strip()
        try:
            if choice == "0": return
            if choice == "1": install_app(Prompt.ask("Application"))
            elif choice == "2": app_search(Prompt.ask("Search"))
            elif choice == "3": installed_apps()
            elif choice == "4": repair_app(Prompt.ask("Application"))
            elif choice == "5": update_app(Prompt.ask("Application"))
            elif choice == "6": uninstall_app(Prompt.ask("Application"))
            elif choice == "7": app_recipes_table()
            elif choice == "8": update_all_apps()
        except AzzxError as exc:
            console.print(Panel(str(exc), title="APP ERROR", border_style="red"))
        Prompt.ask("\nEnter to continue", default="")


def detect_natural_intent(text: str) -> str:
    lower = text.strip().lower()
    if re.match(r"^(kenapa|mengapa|jelaskan|apa fungsi|how|why|explain|what does|tanya|ask)\b", lower):
        return "ask"
    if re.match(r"^(review|audit|cek project|cek kode|periksa project|periksa kode)\b", lower):
        return "review"
    if re.match(r"^(tambah|tambahkan|buat fitur|add|implement|buatkan fitur)\b", lower):
        return "implement"
    return "fix"


def print_interactive_help() -> None:
    table = Table(title="Commands", box=box.SIMPLE, header_style="bold cyan")
    table.add_column("Command")
    table.add_column("Function")
    commands = [
        ("/fix <request>", "Analyze and modify code"),
        ("/add <request>", "Add feature / files"),
        ("/ask <question>", "Ask about project without editing"),
        ("/review [focus]", "Code review without editing"),
        ("/debug <command>", "Run command, then repair failure"),
        ("/autodebug <command>", "Run → fix → retry loop"),
        ("/agent <goal>", "Planner → Coder → Reviewer → Tester pipeline"),
        ("/factory <goal>", "Spec → sandbox team → regression → optional release"),
        ("/security", "Static security review"),
        ("/test [command]", "Run syntax checks and tests"),
        ("/memory", "Show persistent project memory"),
        ("/remember <note>", "Store a project rule/decision"),
        ("/index", "Refresh project index"),
        ("/architect", "Generate architecture.md"),
        ("/map", "Refresh repository/symbol intelligence"),
        ("/symbol <name>", "Find symbol definitions/references"),
        ("/tasks", "List persistent tasks"),
        ("/task create <goal>", "Create a persistent task"),
        ("/task resume <id>", "Resume a persistent task"),
        ("/diagnose [command]", "Collect runtime/Git/dependency diagnostics"),
        ("/build [target]", "Build or package the project"),
        ("/release [version]", "Test and create release archive/manifest"),
        ("/develop <goal>", "Autonomous plan → code → review → test"),
        ("/deps", "Dependency report"),
        ("/apps", "Open Universal Application Center"),
        ("/install <app>", "Resolve dependencies and install an app"),
        ("/installed", "Show applications installed through AZZX"),
        ("/update <app>", "Update an AZZX-tracked app"),
        ("/repair <app>", "Verify and repair an app"),
        ("/uninstall <app>", "Safely uninstall an AZZX-tracked native package"),
        ("/env", "Show OS/distro/package-manager detection"),
        ("/ai", "AI providers, keys, models, fallback"),
        ("/files", "Scan workspace files"),
        ("/diff", "Diff latest AZZX change"),
        ("/undo", "Restore latest backup"),
        ("/history", "Recent AZZX actions"),
        ("/doctor", "System/provider configuration check"),
        ("/config", "Agent settings"),
        ("/clear", "Clear terminal"),
        ("/exit", "Exit AZZX"),
    ]
    for a, b in commands:
        table.add_row(a, b)
    console.print(table)
    console.print("[dim]Natural language tanpa slash juga bisa. AZZX akan menebak intent ask/review/fix/implement.[/]")


def interactive_shell(root: Path, forced_provider: str | None = None) -> None:
    ensure_workspace_state(root)
    while True:
        console.clear()
        banner(root)
        workspace_header(root)
        render_home_screen(root)
        console.print("\n[dim]/help commands • /apps Application Center • /ai AI Configure • /exit keluar[/]")
        try:
            raw = Prompt.ask("\n[bold cyan]azzx[/]").strip()
        except (EOFError, KeyboardInterrupt):
            console.print()
            return
        if not raw:
            continue
        try:
            if raw in {"/exit", "/quit", "exit", "quit"}:
                return
            if raw == "/help":
                print_interactive_help()
            elif raw == "/ai":
                ai_config_menu()
            elif raw == "/files" or raw == "/scan":
                scan_workspace(root)
            elif raw == "/diff":
                show_diff(root)
            elif raw == "/undo":
                undo_last(root)
            elif raw == "/history":
                show_history(root)
            elif raw == "/doctor":
                doctor(False)
            elif raw == "/config":
                general_config_menu()
            elif raw == "/clear":
                continue
            elif raw.startswith("/ask "):
                run_ask(root, raw[5:].strip(), forced_provider)
            elif raw.startswith("/review"):
                run_review(root, raw[len("/review"):].strip(), forced_provider)
            elif raw.startswith("/fix "):
                run_edit_task(root, raw[5:].strip(), "fix", forced_provider)
            elif raw.startswith("/add "):
                run_edit_task(root, raw[5:].strip(), "add", forced_provider)
            elif raw.startswith("/implement "):
                run_edit_task(root, raw[11:].strip(), "implement", forced_provider)
            elif raw.startswith("/debug "):
                run_debug(root, raw[7:].strip(), forced_provider)
            elif raw.startswith("/autodebug "):
                run_debug_loop(root, raw[11:].strip(), forced_provider)
            elif raw.startswith("/agent "):
                run_multi_agent(root, raw[7:].strip(), forced_provider)
            elif raw.startswith("/factory "):
                factory_develop(root, raw[len("/factory "):].strip(), forced_provider, False, False)
            elif raw == "/security":
                security_scan(root, False)
            elif raw.startswith("/test"):
                cmd = raw[len("/test"):].strip() or None
                run_tests(root, cmd)
            elif raw == "/memory":
                show_project_memory(root)
            elif raw.startswith("/remember "):
                remember_project(root, raw[10:].strip())
            elif raw == "/index":
                refresh_project_index(root)
            elif raw == "/architect":
                generate_architecture(root, forced_provider)
            elif raw == "/map":
                show_repository_map(root)
            elif raw.startswith("/symbol "):
                show_symbol(root, raw[8:].strip(), False)
            elif raw.startswith("/refs "):
                show_symbol(root, raw[6:].strip(), True)
            elif raw == "/tasks":
                task_list(root)
            elif raw.startswith("/task create "):
                task_create(root, raw[len("/task create "):].strip(), forced_provider)
            elif raw.startswith("/task resume "):
                task_resume(root, raw[len("/task resume "):].strip(), forced_provider)
            elif raw.startswith("/diagnose"):
                run_diagnose(root, raw[len("/diagnose"):].strip(), forced_provider)
            elif raw.startswith("/build"):
                run_build(root, raw[len("/build"):].strip() or "auto")
            elif raw.startswith("/release"):
                release_project(root, raw[len("/release"):].strip())
            elif raw.startswith("/research "):
                run_research(root, raw[len("/research "):].strip(), "", forced_provider)
            elif raw.startswith("/develop "):
                run_develop(root, raw[len("/develop "):].strip(), forced_provider, False)
            elif raw == "/mcp":
                mcp_command(root, "list")
            elif raw == "/workspace":
                workspace_command(root, "list", forced_provider=forced_provider)
            elif raw == "/apps":
                app_center_menu()
            elif raw == "/installed":
                installed_apps()
            elif raw == "/env":
                render_system_card()
            elif raw.startswith("/install "):
                parts = shlex.split(raw[len("/install "):])
                if not parts: raise AzzxError("/install requires an application name")
                install_app(parts[0], plan_only=("--plan" in parts[1:]), dry_run=("--dry-run" in parts[1:]), isolated=("--isolated" in parts[1:]))
            elif raw == "/update --all":
                update_all_apps()
            elif raw.startswith("/update "):
                update_app(raw[len("/update "):].strip())
            elif raw.startswith("/repair "):
                repair_app(raw[len("/repair "):].strip())
            elif raw.startswith("/uninstall "):
                uninstall_app(raw[len("/uninstall "):].strip())
            elif raw == "/deps":
                show_dependencies(root, False)
            elif raw.lower().startswith("install "):
                install_app(raw.split(None, 1)[1])
            elif raw.lower().startswith("pasang "):
                install_app(raw.split(None, 1)[1])
            elif raw.startswith("/"):
                console.print("[yellow]Command tidak dikenal. Gunakan /help.[/]")
            else:
                intent = detect_natural_intent(raw)
                if intent == "ask":
                    run_ask(root, raw, forced_provider)
                elif intent == "review":
                    run_review(root, raw, forced_provider)
                else:
                    run_edit_task(root, raw, intent, forced_provider)
        except AzzxError as exc:
            console.print(Panel(str(exc), title="ERROR", border_style="red"))
        except KeyboardInterrupt:
            console.print("\n[yellow]Operasi dibatalkan.[/]")
        Prompt.ask("\nEnter untuk kembali", default="")


def resolve_workspace(raw: str | None) -> Path:
    root = Path(raw).expanduser() if raw else Path.cwd()
    root = root.resolve()
    if not root.exists() or not root.is_dir():
        raise AzzxError(f"Workspace tidak ditemukan: {root}")
    return root


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="azzx",
        description="AZZATSSINS LITE AGENT — AI engineering agent + universal application installer",
    )
    parser.add_argument("--path", "-p", help="Workspace directory. Default: current directory")
    parser.add_argument("--ai", dest="forced_provider", help="Force configured provider ID for this command")
    parser.add_argument("--version", action="store_true", help="Show version")
    sub = parser.add_subparsers(dest="command")

    for name in ("ask", "fix", "add", "implement", "agent"):
        sp = sub.add_parser(name)
        sp.add_argument("text", nargs="+", help="Instruction/question")
    create = sub.add_parser("create", help="Create a new project or scaffold")
    create.add_argument("text", nargs="+", help="Project description")
    create.add_argument("--name", help="Create inside a new child directory")
    review = sub.add_parser("review")
    review.add_argument("focus", nargs="*", help="Optional review focus")
    debug = sub.add_parser("debug")
    debug.add_argument("shell_command", nargs="+", help="Command to execute, e.g. python main.py")
    autodebug = sub.add_parser("autodebug")
    autodebug.add_argument("shell_command", nargs="+", help="Command to repeatedly run/fix")
    autodebug.add_argument("--iterations", type=int, default=None)
    testp = sub.add_parser("test")
    testp.add_argument("shell_command", nargs="*", help="Optional custom test command")
    deps = sub.add_parser("deps")
    deps.add_argument("--install", action="store_true", help="Install requirements.txt after confirmation")
    remember = sub.add_parser("remember")
    remember.add_argument("text", nargs="+", help="Project rule/decision to remember")
    sub.add_parser("memory")
    sub.add_parser("index")
    sub.add_parser("architect")
    sub.add_parser("map")
    impact = sub.add_parser("impact", help="Analyze files/symbols affected by a change")
    impact.add_argument("target")
    impact.add_argument("--depth", type=int, default=None)
    issuep = sub.add_parser("issue", help="Manage reproducible project issues")
    issuep.add_argument("action", choices=["list","create","show","solve","close","reopen"])
    issuep.add_argument("issue_args", nargs=argparse.REMAINDER)
    testsp = sub.add_parser("tests", help="Generate or run focused tests")
    testsp.add_argument("action", choices=["generate","affected","run"])
    testsp.add_argument("test_args", nargs=argparse.REMAINDER)
    securityp = sub.add_parser("security", help="Static security review")
    securityp.add_argument("--external", action="store_true", help="Also run installed external scanners")
    bench = sub.add_parser("benchmark", help="Benchmark a command")
    bench.add_argument("shell_command", nargs="+")
    bench.add_argument("--runs", type=int, default=None)
    profilep = sub.add_parser("profile", help="Profile Python command or benchmark another command")
    profilep.add_argument("shell_command", nargs="+")
    dbp = sub.add_parser("db", help="SQLite inspection and safe migration")
    dbp.add_argument("action", choices=["inspect","query","explain","migrate"])
    dbp.add_argument("database")
    dbp.add_argument("sql", nargs=argparse.REMAINDER)
    envp = sub.add_parser("env", help="Inspect OS/distro and developer tools")
    envp.add_argument("--fix", action="store_true")
    envp.add_argument("--install", action="store_true")
    cip = sub.add_parser("ci", help="Create CI scaffold")
    cip.add_argument("provider", choices=["github","gitlab","local"])
    rr = sub.add_parser("review-range", help="AI review a Git revision range")
    rr.add_argument("range", nargs="?", default="HEAD~1..HEAD")
    skillp = sub.add_parser("skill", help="Manage project engineering skills")
    skillp.add_argument("action", choices=["list","show","use","clear","create"])
    skillp.add_argument("name", nargs="?", default="")
    skillp.add_argument("skill_args", nargs=argparse.REMAINDER)
    skillp.add_argument("--global", dest="global_scope", action="store_true")
    sym = sub.add_parser("symbol")
    sym.add_argument("name")
    refs = sub.add_parser("refs")
    refs.add_argument("name")
    taskp = sub.add_parser("task")
    taskp.add_argument("action", choices=["list", "create", "show", "resume", "pause", "done"])
    taskp.add_argument("task_args", nargs=argparse.REMAINDER)
    diagnose = sub.add_parser("diagnose")
    diagnose.add_argument("shell_command", nargs="*")
    watchp = sub.add_parser("watch")
    watchp.add_argument("shell_command", nargs="+", help="Command to watch")
    watchp.add_argument("--cycles", type=int, default=3)
    watchp.add_argument("--interval", type=int, default=5)
    buildp = sub.add_parser("build")
    buildp.add_argument("target", nargs="?", default="auto", choices=["auto","native","python","node","go","rust","make","tar","archive","portable","deb","arch","apk","web","executable"])
    releasep = sub.add_parser("release")
    releasep.add_argument("version", nargs="?", default="")
    research = sub.add_parser("research")
    research.add_argument("text", nargs="+")
    research.add_argument("--domain", default="")
    mcp = sub.add_parser("mcp")
    mcp.add_argument("action", choices=["list","add","remove","test","tools","call"])
    mcp.add_argument("name", nargs="?", default="")
    mcp.add_argument("mcp_args", nargs=argparse.REMAINDER)
    wsp = sub.add_parser("workspace")
    wsp.add_argument("action", choices=["list","add","remove","open","status"])
    wsp.add_argument("name", nargs="?", default="")
    wsp.add_argument("workspace_path", nargs="?", default="")
    develop = sub.add_parser("develop")
    develop.add_argument("text", nargs="+")
    develop.add_argument("--package", action="store_true")
    develop.add_argument("--direct", action="store_true", help="Use legacy direct-edit flow instead of sandbox")
    develop.add_argument("--yes-merge", action="store_true", help="Merge validated sandbox changes without merge prompt")
    clonep = sub.add_parser("clone")
    clonep.add_argument("url")
    clonep.add_argument("destination", nargs="?", default="")
    sub.add_parser("roles")
    gitp = sub.add_parser("git")
    gitp.add_argument("action", choices=["status", "diff", "checkpoint", "branch", "commit"])
    gitp.add_argument("value", nargs="*", help="Label, branch name, or commit message")
    pluginp = sub.add_parser("plugin")
    pluginp.add_argument("action", choices=["list", "add", "remove", "run", "install", "load"])
    pluginp.add_argument("name", nargs="?", default="")
    pluginp.add_argument("plugin_cmd", nargs="?", default="")
    pluginp.add_argument("extra", nargs=argparse.REMAINDER)
    pluginp.add_argument("--global", dest="global_scope", action="store_true")
    pluginp.add_argument("--force", action="store_true", help="Overwrite on plugin install")
    docs = sub.add_parser("docs")
    docs.add_argument("url")
    docs.add_argument("question", nargs="+", help="Question about this documentation page")
    remote = sub.add_parser("remote")
    remote.add_argument("host")
    remote.add_argument("remote_path")
    remote.add_argument("azzx_args", nargs=argparse.REMAINDER)
    sub.add_parser("ai")
    sub.add_parser("diff")
    undo = sub.add_parser("undo")
    undo.add_argument("-y", "--yes", action="store_true")
    doctor_p = sub.add_parser("doctor")
    doctor_p.add_argument("--online", action="store_true", help="Try provider /models endpoints")
    sub.add_parser("scan")
    hist = sub.add_parser("history")
    hist.add_argument("--limit", type=int, default=20)
    sub.add_parser("config")
    mode = sub.add_parser("mode")
    mode.add_argument("value", choices=["safe", "normal", "auto"])
    perm = sub.add_parser("permissions", help="Inspect or change autonomous tool permissions")
    perm.add_argument("action", choices=["list","set","reset"], nargs="?", default="list")
    perm.add_argument("capability", nargs="?", default="")
    perm.add_argument("value", nargs="?", default="")
    specp = sub.add_parser("spec", help="Product requirements and architecture specification")
    specp.add_argument("action", choices=["init","generate","show","set","check"])
    specp.add_argument("section", nargs="?", default="")
    specp.add_argument("spec_args", nargs=argparse.REMAINDER)
    road = sub.add_parser("roadmap", help="Persistent engineering milestones")
    road.add_argument("action", choices=["generate","show","progress","set"])
    road.add_argument("roadmap_args", nargs=argparse.REMAINDER)
    team = sub.add_parser("team", help="Run specialized engineering agents")
    team.add_argument("text", nargs="+")
    sand = sub.add_parser("sandbox", help="Develop in an isolated copy, validate, then merge")
    sand.add_argument("text", nargs="+")
    sand.add_argument("--yes-merge", action="store_true")
    reg = sub.add_parser("regression", help="Capture/check regression baseline")
    reg.add_argument("action", choices=["baseline","check"])
    reg.add_argument("--benchmark", default="")
    relp = sub.add_parser("release-prepare", help="Create a gated release candidate")
    relp.add_argument("version")
    factory = sub.add_parser("factory", help="Spec → roadmap → sandbox team → regression → optional package")
    factory.add_argument("text", nargs="+")
    factory.add_argument("--yes-merge", action="store_true")
    factory.add_argument("--package", action="store_true")
    installp = sub.add_parser("install", help="Universal application installer")
    installp.add_argument("app")
    installp.add_argument("--plan", action="store_true", help="Show resolved installation plan only")
    installp.add_argument("--dry-run", action="store_true", help="Resolve and display actions without changing the system")
    installp.add_argument("-y", "--yes", action="store_true", help="Skip final AZZX confirmation (permission policy still applies)")
    installp.add_argument("--force", action="store_true", help="Reinstall even if executable is already present")
    installp.add_argument("--isolated", action="store_true", help="Install a Python/PyPI CLI package inside an AZZX-managed venv")
    uninstallp = sub.add_parser("uninstall", help="Uninstall an application tracked by AZZX")
    uninstallp.add_argument("app")
    uninstallp.add_argument("--dry-run", action="store_true")
    uninstallp.add_argument("-y", "--yes", action="store_true")
    updatep = sub.add_parser("update", help="Update an application")
    updatep.add_argument("app", nargs="?")
    updatep.add_argument("--all", action="store_true", help="Update every AZZX-tracked application")
    updatep.add_argument("--dry-run", action="store_true")
    updatep.add_argument("-y", "--yes", action="store_true")
    repairp = sub.add_parser("repair", help="Verify and repair an application")
    repairp.add_argument("app")
    repairp.add_argument("--dry-run", action="store_true")
    repairp.add_argument("-y", "--yes", action="store_true")
    sub.add_parser("installed", help="List applications installed/tracked by AZZX")
    appp = sub.add_parser("app", help="Search/info for the Universal Application Center")
    appp.add_argument("action", choices=["search", "info", "recipes", "system"])
    appp.add_argument("app_args", nargs=argparse.REMAINDER)
    dash = sub.add_parser("dashboard", help="Local read-only project dashboard")
    dash.add_argument("--host", default="127.0.0.1")
    dash.add_argument("--port", type=int, default=8765)
    dash.add_argument("--open", action="store_true")

    # --- v7–v10 Universal Toolkit / Automation / Device / Plugins ---
    tools_p = sub.add_parser("tools", help="List or run deterministic tools (v10 registry)")
    tools_sub = tools_p.add_subparsers(dest="tools_action")
    tools_sub.add_parser("list", help="List registered tools")
    trun = tools_sub.add_parser("run", help="Run a registered tool")
    trun.add_argument("name")
    trun.add_argument("--args", default="{}", help="JSON object of arguments")
    trun.add_argument("-y", "--yes", action="store_true")

    nl_p = sub.add_parser("nl", help="Natural-language shortcut to safe toolkit ops")
    nl_p.add_argument("text", nargs="+")
    nl_p.add_argument("-y", "--yes", action="store_true")

    tk = sub.add_parser("toolkit", help="v7 Universal Toolkit shortcuts")
    tk.add_argument("kind", choices=["search", "largest", "duplicates", "hash", "health", "info", "processes", "git-status", "connectivity", "website"])
    tk.add_argument("--path", default=".")
    tk.add_argument("--pattern", default="*")
    tk.add_argument("--limit", type=int, default=20)
    tk.add_argument("--algorithm", default="sha256")
    tk.add_argument("--url", default="")
    tk.add_argument("-y", "--yes", action="store_true")

    wf = sub.add_parser("workflow", help="v8 Workflow engine (registered tools only)")
    wf.add_argument("action", choices=["list", "create", "show", "run", "delete"])
    wf.add_argument("name", nargs="?", default="")
    wf.add_argument("--steps", default="", help="JSON steps for create")
    wf.add_argument("--description", default="")
    wf.add_argument("-y", "--yes", action="store_true", help="overwrite / noninteractive")

    mir = sub.add_parser("mirror", help="Android screen mirroring via scrcpy (realistic DeX-like)")
    mir.add_argument("action", choices=["detect", "status", "devices", "start", "stop"])
    mir.add_argument("--serial", default="")
    mir.add_argument("--max-size", type=int, default=0)
    mir.add_argument("--bit-rate", type=int, default=0)
    mir.add_argument("--fullscreen", action="store_true")
    mir.add_argument("--dry-run", action="store_true")
    mir.add_argument("-y", "--yes", action="store_true")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.version:
        console.print(f"{APP_NAME} {VERSION}")
        return 0
    setup_homes()

    try:
        if args.command == "ai":
            ai_config_menu()
            return 0
        if args.command == "config":
            general_config_menu()
            return 0
        if args.command == "mode":
            cfg = load_config()
            cfg["mode"] = args.value
            save_config(cfg)
            console.print(f"[green]✓[/] Mode = {args.value.upper()}")
            return 0
        if args.command == "permissions":
            permissions_command(args.action, args.capability, args.value)
            return 0
        if args.command == "doctor":
            doctor(args.online)
            return 0
        if args.command == "roles":
            first_run_wizard()
            configure_roles()
            return 0
        if args.command == "remote":
            remote_command(args.host, args.remote_path, args.azzx_args)
            return 0

        ai_commands = {None, "ask", "fix", "add", "implement", "agent", "create", "review", "debug", "autodebug", "architect", "docs", "diagnose", "research", "develop", "review-range", "team", "sandbox", "factory"} | ({"task"} if getattr(args, "action", "") in {"create", "resume"} else set())
        needs_ai = args.command in ai_commands or (args.command == "issue" and getattr(args, "action", "") == "solve") or (args.command == "tests" and getattr(args, "action", "") == "generate") or (args.command == "spec" and getattr(args, "action", "") == "generate") or (args.command == "roadmap" and getattr(args, "action", "") == "generate")
        if needs_ai:
            first_run_wizard()
        root = resolve_workspace(args.path)
        forced = args.forced_provider
        if forced and forced not in load_providers():
            raise AzzxError(f"Provider '{forced}' belum dikonfigurasi. Cek dengan: azzx ai")

        if not args.command:
            interactive_shell(root, forced)
            return 0
        if args.command == "ask":
            run_ask(root, " ".join(args.text), forced)
        elif args.command == "spec":
            vals=list(args.spec_args or [])
            if args.action in {"init","generate"}:
                text=" ".join(([args.section] if args.section else []) + vals)
                spec_command(root,args.action,"",text,forced)
            elif args.action == "set":
                spec_command(root,"set",args.section," ".join(vals),forced)
            else:
                spec_command(root,args.action,args.section,"",forced)
        elif args.command == "roadmap":
            roadmap_command(root,args.action,list(args.roadmap_args or []),forced)
        elif args.command == "team":
            if not run_team_agent(root," ".join(args.text),forced): return 3
        elif args.command == "sandbox":
            if not sandbox_develop(root," ".join(args.text),forced,args.yes_merge): return 3
        elif args.command == "regression":
            if args.action == "baseline": capture_regression_baseline(root,args.benchmark)
            elif not regression_check(root,args.benchmark): return 3
        elif args.command == "release-prepare":
            release_prepare(root,args.version,forced)
        elif args.command == "factory":
            if not factory_develop(root," ".join(args.text),forced,args.yes_merge,args.package): return 3
        elif args.command == "install":
            if not install_app(args.app, args.plan, args.dry_run, args.yes, args.force, args.isolated): return 3
        elif args.command == "uninstall":
            if not uninstall_app(args.app, args.yes, args.dry_run): return 3
        elif args.command == "update":
            if args.all:
                if not update_all_apps(args.yes, args.dry_run): return 3
            else:
                if not args.app: raise AzzxError("update requires APP or --all")
                if not update_app(args.app, args.yes, args.dry_run): return 3
        elif args.command == "repair":
            if not repair_app(args.app, args.yes, args.dry_run): return 3
        elif args.command == "installed":
            installed_apps()
        elif args.command == "app":
            vals=list(args.app_args or [])
            if args.action == "search":
                if not vals: raise AzzxError("app search requires a query")
                app_search(" ".join(vals))
            elif args.action == "info":
                if not vals: raise AzzxError("app info requires an application name")
                app_info(vals[0])
            elif args.action == "recipes": app_recipes_table()
            elif args.action == "system": render_system_card()
        elif args.command == "dashboard":
            run_dashboard(root,args.host,args.port,args.open)
        elif args.command == "create":
            create_project(root, " ".join(args.text), args.name, forced)
        elif args.command == "agent":
            run_multi_agent(root, " ".join(args.text), forced)
        elif args.command == "fix":
            run_edit_task(root, " ".join(args.text), "fix", forced)
        elif args.command == "add":
            run_edit_task(root, " ".join(args.text), "add", forced)
        elif args.command == "implement":
            run_edit_task(root, " ".join(args.text), "implement", forced)
        elif args.command == "review":
            run_review(root, " ".join(args.focus), forced)
        elif args.command == "debug":
            run_debug(root, " ".join(args.shell_command), forced)
        elif args.command == "autodebug":
            run_debug_loop(root, " ".join(args.shell_command), forced, args.iterations)
        elif args.command == "test":
            run_tests(root, " ".join(args.shell_command) if args.shell_command else None)
        elif args.command == "deps":
            show_dependencies(root, args.install)
        elif args.command == "remember":
            remember_project(root, " ".join(args.text))
        elif args.command == "memory":
            show_project_memory(root)
        elif args.command == "index":
            refresh_project_index(root)
        elif args.command == "architect":
            generate_architecture(root, forced)
        elif args.command == "map":
            show_repository_map(root)
        elif args.command == "impact":
            impact_analysis(root, args.target, args.depth)
        elif args.command == "issue":
            vals = list(args.issue_args or [])
            if args.action == "list": issue_command(root, "list", forced_provider=forced)
            elif args.action == "create":
                if not vals: raise AzzxError("issue create requires a description")
                issue_command(root, "create", text=" ".join(vals), forced_provider=forced)
            else:
                if not vals: raise AzzxError(f"issue {args.action} requires ISSUE_ID")
                issue_command(root, args.action, vals[0], " ".join(vals[1:]), forced)
        elif args.command == "tests":
            vals = list(args.test_args or [])
            if args.action == "generate":
                generate_tests(root, " ".join(vals), forced)
            elif args.action == "affected":
                if not run_affected_tests(root): return 3
            else:
                if not run_tests(root, " ".join(vals) if vals else None): return 3
        elif args.command == "security":
            security_scan(root, args.external)
        elif args.command == "benchmark":
            benchmark_command(root, " ".join(args.shell_command), args.runs)
        elif args.command == "profile":
            profile_command(root, " ".join(args.shell_command))
        elif args.command == "db":
            db_command(root, args.action, args.database, " ".join(args.sql))
        elif args.command == "env":
            environment_command(args.fix or args.install, args.install)
        elif args.command == "ci":
            ci_create(root, args.provider)
        elif args.command == "review-range":
            review_git_range(root, args.range, forced)
        elif args.command == "skill":
            vals = list(args.skill_args or [])
            skill_command(root, args.action, args.name, " ".join(vals), args.global_scope)
        elif args.command == "symbol":
            show_symbol(root, args.name, False)
        elif args.command == "refs":
            show_symbol(root, args.name, True)
        elif args.command == "task":
            vals = list(args.task_args or [])
            if args.action == "create":
                if not vals: raise AzzxError("task create requires a goal")
                task_command(root, args.action, "", " ".join(vals), forced)
            elif args.action == "list":
                task_command(root, args.action, "", "", forced)
            else:
                if not vals: raise AzzxError(f"task {args.action} requires TASK_ID")
                task_command(root, args.action, vals[0], " ".join(vals[1:]), forced)
        elif args.command == "diagnose":
            run_diagnose(root, " ".join(args.shell_command), forced)
        elif args.command == "watch":
            watch_command(root, " ".join(args.shell_command), args.cycles, args.interval, forced)
        elif args.command == "build":
            if not run_build(root, args.target): raise AzzxError("Build failed.")
        elif args.command == "release":
            release_project(root, args.version)
        elif args.command == "research":
            run_research(root, " ".join(args.text), args.domain, forced)
        elif args.command == "mcp":
            vals = list(args.mcp_args or [])
            if args.action == "add":
                if not args.name or not vals: raise AzzxError("mcp add requires NAME COMMAND [ARGS...]")
                mcp_command(root, "add", args.name, vals[0], vals[1:])
            elif args.action == "call":
                if not args.name or not vals: raise AzzxError("mcp call requires NAME TOOL [JSON_ARGS]")
                mcp_command(root, "call", args.name, tool=vals[0], json_args=(vals[1] if len(vals) > 1 else "{}"))
            else:
                mcp_command(root, args.action, args.name)
        elif args.command == "workspace":
            workspace_command(root, args.action, args.name, args.workspace_path, forced)
        elif args.command == "develop":
            goal=" ".join(args.text)
            if args.direct:
                if not run_develop(root, goal, forced, args.package): return 3
            else:
                if not sandbox_develop(root, goal, forced, args.yes_merge): return 3
                if args.package: release_prepare(root, str(project_package_meta(root).get("version") or VERSION), forced)
        elif args.command == "clone":
            target=clone_repository(args.url, args.destination); console.print(f"[green]✓ Cloned:[/] {target}"); refresh_project_index(target, quiet=True); refresh_repository_map(target, quiet=True)
        elif args.command == "git":
            git_command(root, args.action, " ".join(args.value))
        elif args.command == "plugin":
            if args.action in ("install", "load"):
                from azzx.cli_v10 import cmd_plugin
                return cmd_plugin(args.action, getattr(args, "name", "") or "", getattr(args, "force", False))
            plugin_command(root, args.action, args.name, args.plugin_cmd, " ".join(args.extra), args.global_scope)
        elif args.command == "docs":
            fetch_docs(root, args.url, " ".join(args.question), forced)
        elif args.command == "diff":
            show_diff(root)
        elif args.command == "undo":
            undo_last(root, args.yes)
        elif args.command == "scan":
            scan_workspace(root)
        elif args.command == "history":
            show_history(root, max(1, args.limit))

        elif args.command == "tools":
            from azzx.cli_v10 import cmd_tools_list, cmd_tool_run
            if getattr(args, "tools_action", None) == "run":
                return cmd_tool_run(args.name, getattr(args, "args", "{}"), getattr(args, "yes", False))
            return cmd_tools_list()
        elif args.command == "nl":
            from azzx.cli_v10 import cmd_nl
            return cmd_nl(" ".join(args.text), getattr(args, "yes", False))
        elif args.command == "toolkit":
            from azzx.cli_v10 import cmd_toolkit
            return cmd_toolkit(
                args.kind, path=args.path, pattern=args.pattern, limit=args.limit,
                algorithm=args.algorithm, url=args.url, yes=args.yes,
            )
        elif args.command == "workflow":
            from azzx.cli_v10 import cmd_workflow
            return cmd_workflow(args.action, args.name, getattr(args, "steps", ""), getattr(args, "description", ""), getattr(args, "yes", False))
        elif args.command == "mirror":
            from azzx.cli_v10 import cmd_mirror
            return cmd_mirror(
                args.action, serial=args.serial, max_size=args.max_size,
                bit_rate=args.bit_rate, fullscreen=args.fullscreen,
                dry_run=args.dry_run, yes=args.yes,
            )

        return 0
    except AzzxError as exc:
        console.print(Panel(str(exc), title="AZZX ERROR", border_style="red"))
        return 2
    except KeyboardInterrupt:
        console.print("\n[yellow]Dibatalkan.[/]")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
