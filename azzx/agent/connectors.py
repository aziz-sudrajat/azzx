"""App connectors for AZZX (v10.6): GitHub + Email.

Configuration lives in ``~/.config/azzx/connectors.json`` (non-secret settings
only); secrets live in the SecretVault. ``azzx connector setup <name>`` walks
through interactive setup.

Connectors included:
- ``github`` — GitHub REST API via personal access token (no OAuth needed).
  Tools: ``github.repos``, ``github.list_issues``, ``github.create_issue``.
- ``email`` — IMAP inbox + SMTP send via the standard library (works with
  Gmail app-passwords, Fastmail, self-hosted, ...).
  Tools: ``email.inbox``, ``email.send``.

Deliberately NOT included: Google Drive — it requires a Google Cloud OAuth2
app (client ID/secret + consent screen), which cannot be set up from a CLI
without the user doing console work. Documented in the README instead.

All connector tools are permission-gated (``connector.github`` /
``connector.email``) and every secret travels through the vault, never chat.
"""
from __future__ import annotations

import getpass
import json
from pathlib import Path
from typing import Any

from azzx.core import AzzxError, CONFIG_HOME

CONNECTORS_FILE = Path(CONFIG_HOME) / "connectors.json"


def load_connectors() -> dict[str, dict[str, Any]]:
    try:
        data = json.loads(CONNECTORS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_connectors(data: dict[str, dict[str, Any]]) -> None:
    CONNECTORS_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONNECTORS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    try:
        CONNECTORS_FILE.chmod(0o600)
    except Exception:
        pass


def _vault() -> Any:
    import azzx_cli
    return azzx_cli.SecretVault()


# ---------------------------------------------------------------------------
# GitHub (PAT)
# ---------------------------------------------------------------------------
def _github_headers() -> dict[str, str]:
    token = _vault().get("github_pat")
    if not token:
        raise AzzxError("GitHub not connected: run `azzx connector setup github`")
    return {"Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"}


def _github_api(method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
    import httpx
    url = "https://api.github.com" + path
    try:
        resp = httpx.request(method, url, headers=_github_headers(),
                             json=payload, timeout=30)
    except Exception as exc:
        raise AzzxError(f"GitHub request failed: {exc}")
    if resp.status_code == 401:
        raise AzzxError("GitHub: token invalid (401) — re-run `azzx connector setup github`")
    if resp.status_code == 403 and "rate limit" in resp.text.lower():
        raise AzzxError("GitHub: rate limit exceeded")
    if resp.status_code >= 400:
        raise AzzxError(f"GitHub API {resp.status_code}: {resp.text[:200]}")
    return resp.json()


def github_repos(limit: int = 30) -> list[dict[str, Any]]:
    data = _github_api("GET", f"/user/repos?per_page={max(1, min(int(limit), 100))}&sort=updated")
    return [{"name": r.get("full_name"), "private": r.get("private"),
             "url": r.get("html_url"), "updated": r.get("updated_at")}
            for r in data if isinstance(r, dict)]


def github_list_issues(repo: str, state: str = "open", limit: int = 20) -> list[dict[str, Any]]:
    data = _github_api("GET", f"/repos/{repo}/issues?state={state}&per_page={max(1, min(int(limit), 100))}")
    return [{"number": i.get("number"), "title": i.get("title"),
             "state": i.get("state"), "url": i.get("html_url")}
            for i in data if isinstance(i, dict) and "pull_request" not in i]


def github_create_issue(repo: str, title: str, body: str = "") -> dict[str, Any]:
    if not title.strip():
        raise AzzxError("issue title required")
    data = _github_api("POST", f"/repos/{repo}/issues",
                       {"title": title[:200], "body": body[:10000]})
    return {"number": data.get("number"), "url": data.get("html_url")}


# ---------------------------------------------------------------------------
# Email (IMAP/SMTP, stdlib only)
# ---------------------------------------------------------------------------
def _email_cfg() -> dict[str, Any]:
    cfg = load_connectors().get("email") or {}
    if not cfg.get("imap_host") or not cfg.get("username"):
        raise AzzxError("Email not connected: run `azzx connector setup email`")
    password = _vault().get("email_password")
    if not password:
        raise AzzxError("Email password missing from vault")
    return {"imap_host": cfg["imap_host"], "imap_port": int(cfg.get("imap_port", 993)),
            "smtp_host": cfg.get("smtp_host", ""), "smtp_port": int(cfg.get("smtp_port", 587)),
            "username": cfg["username"], "password": password}


def email_inbox(limit: int = 10, mailbox: str = "INBOX") -> list[dict[str, Any]]:
    import imaplib
    import email as email_mod
    from email.header import decode_header

    cfg = _email_cfg()

    def _decode(value: Any) -> str:
        if not value:
            return ""
        parts = []
        for chunk, enc in decode_header(str(value)):
            if isinstance(chunk, bytes):
                parts.append(chunk.decode(enc or "utf-8", errors="replace"))
            else:
                parts.append(chunk)
        return "".join(parts)

    try:
        conn = imaplib.IMAP4_SSL(cfg["imap_host"], cfg["imap_port"])
        conn.login(cfg["username"], cfg["password"])
    except Exception as exc:
        raise AzzxError(f"IMAP login failed: {exc}")
    try:
        conn.select(mailbox)
        _typ, data = conn.search(None, "ALL")
        ids = (data[0] or b"").split()
        out = []
        for mid in ids[-max(1, min(int(limit), 50)):][::-1]:
            _typ, msg_data = conn.fetch(mid, "(RFC822.HEADER)")
            raw = msg_data[0][1] if msg_data and msg_data[0] else b""
            msg = email_mod.message_from_bytes(raw)
            out.append({
                "id": mid.decode(),
                "from": _decode(msg.get("From"))[:120],
                "subject": _decode(msg.get("Subject"))[:160],
                "date": str(msg.get("Date", ""))[:60],
            })
        return out
    finally:
        try:
            conn.logout()
        except Exception:
            pass


def email_send(to: str, subject: str, body: str) -> dict[str, Any]:
    import smtplib
    from email.message import EmailMessage

    cfg = _email_cfg()
    if not cfg["smtp_host"]:
        raise AzzxError("SMTP host not configured")
    if not to.strip() or "@" not in to:
        raise AzzxError("valid recipient required")
    msg = EmailMessage()
    msg["From"] = cfg["username"]
    msg["To"] = to.strip()
    msg["Subject"] = subject[:200] or "(no subject)"
    msg.set_content(body or "")
    try:
        if int(cfg["smtp_port"]) == 465:
            # SMTPS: TLS from the start, no STARTTLS.
            with smtplib.SMTP_SSL(cfg["smtp_host"], cfg["smtp_port"], timeout=30) as smtp:
                smtp.login(cfg["username"], cfg["password"])
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(cfg["smtp_host"], cfg["smtp_port"], timeout=30) as smtp:
                smtp.starttls()
                smtp.login(cfg["username"], cfg["password"])
                smtp.send_message(msg)
    except Exception as exc:
        raise AzzxError(f"SMTP send failed: {exc}")
    return {"sent": True, "to": to.strip()}


# ---------------------------------------------------------------------------
# Setup flows
# ---------------------------------------------------------------------------
def setup_github() -> dict[str, Any]:
    print("GitHub connector — buat Personal Access Token di "
          "https://github.com/settings/tokens (scope: repo).")
    token = getpass.getpass("GitHub PAT (tidak ditampilkan): ").strip()
    if not token:
        raise AzzxError("token required")
    _vault().set("github_pat", token)
    connectors = load_connectors()
    connectors["github"] = {"type": "github", "auth": "vault:github_pat"}
    save_connectors(connectors)
    me = _github_api("GET", "/user")
    return {"connected": "github", "as": me.get("login")}


def setup_email() -> dict[str, Any]:
    print("Email connector — IMAP untuk baca, SMTP untuk kirim.")
    print("Gmail: pakai App Password (https://myaccount.google.com/apppasswords).")
    imap_host = input("IMAP host [imap.gmail.com]: ").strip() or "imap.gmail.com"
    imap_port_s = input("IMAP port [993]: ").strip() or "993"
    smtp_host = input("SMTP host [smtp.gmail.com]: ").strip() or "smtp.gmail.com"
    smtp_port_s = input("SMTP port [587]: ").strip() or "587"
    username = input("Username/email: ").strip()
    password = getpass.getpass("Password/app-password (tidak ditampilkan): ")
    if not username or not password:
        raise AzzxError("username and password required")
    try:
        imap_port, smtp_port = int(imap_port_s), int(smtp_port_s)
    except ValueError:
        raise AzzxError("ports must be numbers")
    _vault().set("email_password", password)
    connectors = load_connectors()
    connectors["email"] = {"type": "email", "imap_host": imap_host,
                           "imap_port": imap_port, "smtp_host": smtp_host,
                           "smtp_port": smtp_port, "username": username,
                           "password": "vault:email_password"}
    save_connectors(connectors)
    return {"connected": "email", "as": username}


def register_connector_tools() -> None:
    from azzx.core import REGISTRY, ToolSpec

    REGISTRY.register(ToolSpec(
        name="github.repos", description="List your GitHub repositories.",
        permissions=["connector.github"],
        handler=lambda limit=30: github_repos(limit), schema={"limit": "int"}))
    REGISTRY.register(ToolSpec(
        name="github.list_issues", description="List issues of a repo.",
        permissions=["connector.github"], handler=github_list_issues,
        schema={"repo": "str owner/name (required)", "state": "str", "limit": "int"}))
    REGISTRY.register(ToolSpec(
        name="github.create_issue", description="Create a GitHub issue.",
        permissions=["connector.github"], handler=github_create_issue,
        schema={"repo": "str (required)", "title": "str (required)", "body": "str"}))
    REGISTRY.register(ToolSpec(
        name="email.inbox", description="Read the latest emails (headers only).",
        permissions=["connector.email"],
        handler=lambda limit=10, mailbox="INBOX": email_inbox(limit, mailbox),
        schema={"limit": "int", "mailbox": "str"}))
    REGISTRY.register(ToolSpec(
        name="email.send", description="Send an email via SMTP.",
        permissions=["connector.email"], handler=email_send,
        schema={"to": "str (required)", "subject": "str", "body": "str"}))
