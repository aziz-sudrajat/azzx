"""Minimal Telegram gateway for AZZX (v10.5): your companion on your phone.

Long-polling via httpx (no new dependencies). Incoming messages are handled
as companion chat; slash commands are supported:

    /start | /help   this help
    /auto <goal>     autonomous run (plan -> approve -> execute -> learn)
    /plan <goal>     show an execution plan
    /remember <fact> store a fact about you

Safety:
- Bot token from ``--token`` or ``AZZX_TELEGRAM_TOKEN`` env; never logged.
- ``--allow-from <chat_id,...>`` restricts who may talk to the bot.
  Without it, ANYONE who finds the bot can run tools as you — the gateway
  prints a loud warning in that case.
- Autonomous runs from Telegram always require the plan approval step
  unless ``--yes`` is passed (same policy as the CLI).
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from azzx.core import AzzxError, DATA_HOME

API = "https://api.telegram.org"


class TelegramGateway:
    def __init__(self, token: str, allow_from: set[int] | None = None,
                 auto_approve: bool = False) -> None:
        token = (token or "").strip()
        if not token or ":" not in token:
            raise AzzxError("Telegram bot token looks invalid")
        self.token = token
        self.allow_from = allow_from
        self.auto_approve = auto_approve
        self._state = Path(DATA_HOME) / "gateway" / "telegram.json"
        self._state.parent.mkdir(parents=True, exist_ok=True)
        self._offset = 0
        try:
            self._offset = int(json.loads(self._state.read_text(encoding="utf-8")).get("offset", 0))
        except Exception:
            pass

    # -- http ------------------------------------------------------------
    def _api(self, method: str, **params: Any) -> Any:
        import httpx
        # Token goes in the URL path (Telegram Bot API convention); never logged.
        url = f"{API}/bot{self.token}/{method}"
        resp = httpx.post(url, json=params, timeout=40)
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ok"):
            raise AzzxError(f"Telegram API error: {data}")
        return data.get("result")

    def _save_offset(self) -> None:
        self._state.write_text(json.dumps({"offset": self._offset}), encoding="utf-8")

    # -- loop ------------------------------------------------------------
    def run_forever(self, on_log=None) -> None:
        log = on_log or (lambda m: print(m, flush=True))
        me = self._api("getMe")
        log(f"Telegram gateway live as @{me.get('username')} (id {me.get('id')}). Press Ctrl+C to stop.")
        if not self.allow_from:
            log("WARNING: no --allow-from set — ANYONE who messages this bot can run AZZX tools as you.")
        try:
            while True:
                try:
                    updates = self._api("getUpdates", offset=self._offset, timeout=30,
                                        allowed_updates=["message"])
                except Exception as exc:
                    log(f"poll error: {exc}; retrying in 5s")
                    time.sleep(5)
                    continue
                for upd in updates or []:
                    self._offset = max(self._offset, int(upd.get("update_id", 0)) + 1)
                    self._save_offset()
                    try:
                        self._handle_update(upd, log)
                    except Exception as exc:
                        log(f"handler error: {exc}")
        except KeyboardInterrupt:
            log("Telegram gateway stopped.")

    def _handle_update(self, upd: dict[str, Any], log) -> None:
        msg = upd.get("message") or {}
        chat = msg.get("chat") or {}
        chat_id = chat.get("id")
        text = (msg.get("text") or "").strip()
        if not chat_id or not text:
            return
        if self.allow_from and chat_id not in self.allow_from:
            log(f"ignored message from unauthorized chat {chat_id}")
            return
        log(f"<- [{chat_id}] {text[:80]}")
        reply = self._respond(text)
        self._send(chat_id, reply)
        log(f"-> [{chat_id}] {reply[:80]}")

    def _send(self, chat_id: int, text: str) -> None:
        # Telegram cap: 4096 chars per message.
        chunk = (text or "(empty reply)")[:4000]
        self._api("sendMessage", chat_id=chat_id, text=chunk)

    # -- brain -----------------------------------------------------------
    def _respond(self, text: str) -> str:
        from azzx.agent.companion import companion_system_prompt, remember_fact
        from azzx.agent.orchestrator import assemble_memory_prompt
        from azzx.agent.providers import default_router

        if text.startswith("/remember "):
            try:
                res = remember_fact(text[len("/remember "):])
                return f"Diingat: {res['stored']}"
            except Exception as exc:
                return f"Tidak disimpan: {exc}"
        if text.startswith("/plan "):
            from azzx.agent.planning import generate_plan, render_plan_text
            try:
                plan = generate_plan(text[len("/plan "):].strip())
                return render_plan_text(plan)[:3500]
            except Exception as exc:
                return f"Gagal membuat rencana: {exc}"
        if text.startswith("/autoy "):
            # Explicit "yes" variant: plan is shown in the reply, then executed.
            return self._run_auto(text[len("/autoy "):].strip(), auto_approve=True)
        if text.startswith("/auto "):
            if self.auto_approve:
                return self._run_auto(text[len("/auto "):].strip(), auto_approve=True)
            # No terminal on a headless gateway, so input() approval is
            # impossible: show the plan and let the user confirm via /autoy.
            from azzx.agent.planning import generate_plan, render_plan_text
            goal = text[len("/auto "):].strip()
            try:
                plan = generate_plan(goal)
            except Exception as exc:
                return f"Gagal membuat rencana: {exc}"
            preview = render_plan_text(plan)[:3000]
            return (f"{preview}\n\n—\nKirim `/autoy {goal[:100]}` untuk mengeksekusi "
                    "rencana ini.")
        if text.startswith("/start") or text.startswith("/help"):
            return self._respond_help()

        router = default_router()
        messages = [
            {"role": "system", "content": companion_system_prompt()},
            {"role": "user", "content": assemble_memory_prompt(text)},
        ]
        try:
            result = router.chat(messages, max_tokens=800)
            return result.text.strip() or "(tidak ada jawaban)"
        except Exception as exc:
            return f"Maaf, ada gangguan: {exc}"

    def _respond_help(self) -> str:
        return ("Halo! Aku AZZX 🤖\n\n"
                "/auto <tujuan> — lihat rencana dulu\n"
                "/autoy <tujuan> — setujui & jalankan otonom\n"
                "/plan <tujuan> — buatkan rencana saja\n"
                "/remember <fakta> — ingat sesuatu tentangmu\n"
                "atau kirim pesan biasa untuk ngobrol.")

    def _run_auto(self, goal: str, auto_approve: bool) -> str:
        from azzx.agent.autonomy import AutonomousRunner
        runner = AutonomousRunner(auto_approve=auto_approve, namespace="telegram")
        try:
            result = runner.run(goal)
        except Exception as exc:
            return f"Gagal: {exc}"
        if result.get("status") == "needs_clarification":
            return "Perlu klarifikasi:\n" + "\n".join("? " + q for q in result["questions"])
        return (f"Status: {result['status']} — "
                f"{result['steps_completed']} langkah ok, {result['steps_failed']} gagal.")

    def _respond_help(self) -> str:
        return ("Halo! Aku AZZX 🤖\n\n"
                "/auto <tujuan> — lihat rencana dulu\n"
                "/autoy <tujuan> — setujui & jalankan otonom\n"
                "/plan <tujuan> — buatkan rencana saja\n"
                "/remember <fakta> — ingat sesuatu tentangmu\n"
                "atau kirim pesan biasa untuk ngobrol.")

        router = default_router()
        messages = [
            {"role": "system", "content": companion_system_prompt()},
            {"role": "user", "content": assemble_memory_prompt(text)},
        ]
        try:
            result = router.chat(messages, max_tokens=800)
            return result.text.strip() or "(tidak ada jawaban)"
        except Exception as exc:
            return f"Maaf, ada gangguan: {exc}"
