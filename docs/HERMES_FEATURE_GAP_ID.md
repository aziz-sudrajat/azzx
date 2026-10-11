# Gap Analysis: Fitur Hermes (Nous Research) yang Lebih Bagus dari AZZX

> Dokumen jujur — dibuat 2026-10-10. Setiap fitur Hermes yang unggul dicatat,
> lalu diklasifikasikan: **sudah diimplementasikan di v10.5**, **diimplementasikan
> sekarang**, atau **ditunda dengan alasan jujur**. Tidak ada yang ditutupi.

Sumber: dokumentasi resmi Hermes (`hermes-agent.nousresearch.com/docs`) dan
repo `github.com/NousResearch/hermes-agent`, riset 2026-10-10.

---

## 1. SUDAH diimplementasikan di AZZX v10.5

| # | Fitur Hermes | Implementasi AZZX v10.5 |
|---|---|---|
| 1 | Learning loop — membuat skill dari pengalaman, kurasi memori | `azzx/agent/learning.py` + `azzx learn` — distilasi pasca-tugas jadi proposal memori/skill yang **staged** (tidak silent, sesuai trust-gate v10.4) |
| 2 | `/plan` — rencana eksekusi eksplisit | `azzx plan "<goal>"` — rencana terstruktur berbasis tool, disimpan di `.azzx/plans/`, opsional `--execute` |
| 3 | `todo` — checklist kerja agen | Tools `todo.add/list/done/clear` terdaftar di registry (bisa dipakai agen) |
| 4 | Sandbox eksekusi (7 backend terminal di Hermes) | `azzx/agent/sandbox.py` + `azzx exec run -- <cmd>` — backend `local` (cwd jail, timeout, output cap, secret scrub, RLIMIT) dan `docker` (`--network none`, 512MB). Tool `sandbox.exec` untuk agen |
| 5 | Checkpoint/rollback (shadow git di Hermes) | `azzx checkpoint create/list/rollback` — snapshot tarball + manifest, tanpa dependensi git (jalan di Termux) |
| 6 | Autonomous execution | `azzx auto "<goal>"` — plan → approve → execute via `run_tool_call` (deny-first tetap absolut) → checkpoint sebelum langkah berisiko → replan 1x saat gagal → learning |
| 7 | Mode interaktif | `azzx chat` — REPL dengan slash commands (`/plan`, `/auto`, `/learn`, `/memory`, `/skills`, `/trace`), streaming, konteks memori |
| 8 | Approval mode (smart/manual/off) | Sudah ada sejak v10.4 (`allow/prompt/deny` + `-y`); v10.5 mempertahankannya di semua loop otonom |

## 2. Diimplementasikan SEKARANG (v10.5 lanjutan)

| # | Fitur Hermes | Implementasi AZZX | Catatan jujur |
|---|---|---|---|
| 9 | Companion — agen sahabat yang personal | `azzx chat` persona companion (ingat nama user, gaya hangat), `/remember`, `azzx setup` (simpan nama + preferensi) | Hermes tidak punya "companion persona" eksplisit; ini diferensiasi AZZX |
| 10 | Messaging gateway (30+ platform) | **Telegram gateway minimal** (`azzx gateway telegram`) — long-polling via httpx (tanpa dep baru), teruskan pesan → `azzx agent`, balas jawaban | Hanya Telegram dulu; 30 platform butuh infrastruktur & biaya. Jujur: ini 1/30 |
| 11 | Persistent cron jobs | **Cron syntax di scheduler** — `azzx schedule add --cron "*/5 * * * *"` (parser cron minimal tanpa dep baru) | Hermes kirim ke messaging; AZZX kirim ke queue/tool lokal |
| 12 | Skills Hub / marketplace | `azzx skills install <git-url>` — install skill dari repo git (clone dangkal + validasi manifest) | Bukan marketplace 88k skill; hanya mekanisme distribusi |
| 13 | Session search (FTS5) | `azzx session search <query>` — full-text search di jurnal sesi SQLite | — |
| 14 | MCP (Model Context Protocol) | **MCP client minimal** — `azzx mcp servers/tools/call` via stdio (NDJSON JSON-RPC): `initialize`, `tools/list`, `tools/call`; tool remote jadi `mcp.<alias>.<tool>` | Hanya stdio; belum HTTP/SSE, belum OAuth |
| 15 | `doctor` — cek kesehatan instalasi | `azzx doctor` — cek Python, dep, disk, memori, provider, Termux | Penting untuk target "laptop kentang" |
| 16 | Ringan di perangkat lemah | Tidak ada dep baru di v10.5 (tetap `httpx` + `rich` saja); lazy imports; `rich` punya fallback non-rich | Kualitas agen = model provider (API), bukan CPU lokal — laptop kentang tetap dapat agen kelas penuh |

## 3. DITUNDA — alasan jujur

| # | Fitur Hermes | Alasan penundaan |
|---|---|---|
| 17 | Voice mode (STT/TTS, wake word) | Butuh layanan STT/TTS eksternal + audio pipeline; di luar scope CLI tool. Tidak dipalsukan |
| 18 | Desktop app (macOS/Windows) | Butuh framework GUI + build pipeline per-OS; AZZX tetap CLI-first |
| 19 | Browser automation (navigation/snapshot/vision) | Butuh browser driver (playwright/selenium = dep berat, boros RAM — bertentangan dengan target kentang) |
| 20 | 30+ messaging platform | Hanya Telegram yang feasible tanpa biaya/infra; WhatsApp/Slack/Discord butuh API key berbayar atau server |
| 21 | ACP (integrasi VS Code/Zed/JetBrains) | Protokol editor spesifik; belum ada permintaan konkret |
| 22 | Skills Hub 88k / deep-link install | Butuh layanan hosting + moderasi; `install <git-url>` adalah fondasinya |
| 23 | A2A (agent-to-agent protocol) | Protokol antar-agen; nilai nyata muncul saat ada ekosistem |
| 24 | Mixture-of-Agents (advisor + aggregator) | Multi-agent AZZX (planner→coder→reviewer→tester→security) sudah mencakup semangatnya; MoA penuh = biaya token N× lipat |
| 25 | 7 backend terminal (Modal, Daytona, SSH, dsb.) | `local` + `docker` mencakup 90% kebutuhan; backend cloud butuh akun/kuota |

## 4. Area di mana AZZX TETAP unggul (tidak perlu ditiru)

- Toolkit Linux/Termux (installer aplikasi universal, `sys.*`, `net.*`, `media.*`)
- Android mirroring via scrcpy/ADB (`azzx mirror`)
- Workflow deterministik terkunci ke tool terdaftar (`azzx workflow`)
- Deny-first permission yang tidak bisa di-bypass `-y`/queue/workflow
- Ukuran kecil & deterministik: instalasi ~menit, jalan di Termux

---

**Prinsip v10.5:** tiru yang memperkuat AZZX sebagai *agen*, bukan yang
menambah *permukaan produk*. Setiap fitur baru wajib: (1) tanpa dep berat
baru, (2) lolos deny-first, (3) ada test.

---

## 5. Update v10.6.2/v10.6.3 (2026-10-11) — hasil testing di mesin + perbandingan ulang

### Yang baru di AZZX

| # | Fitur | Status vs Hermes | Catatan jujur |
|---|---|---|---|
| 26 | Auditor agent (`azzx audit list/stats/report --judge`) | **Diferensiasi AZZX** | Hermes punya trajectory export (untuk training), learning timeline, dan auditing enterprise. AZZX: setiap tool call terekam (argumen di-redact, durasi, hasil); laporan berbasis **aturan objektif** (kegagalan berulang, denial, tool berisiko, timeout) + skor 0-100; `--judge` memakai LLM sebagai juri. Relevan: kritik Tech Times bahwa skill-loop Hermes bias memuji diri sendiri (*self-congratulation bias*) — auditor AZZX menilai dengan aturan dulu, bukan penilaian diri sendiri |
| 27 | Token compressor (`azzx compress`, dipakai otomatis oleh `azzx ask`) | **Pendekatan berbeda, kompetitif** | Hermes memakai auxiliary model slot untuk kompresi konteks (bayar token untuk hemat token). AZZX: `signatures` via AST Python (hemat 70-90%, gratis, tanpa token), `extractive` fokus-query, `head_tail`, `summarize` (LLM, opsional) |
| 28 | GUI web chat (`azzx gui`) | Mengejar, belum setara | Hermes: desktop app + dashboard Models/sessions. AZZX: single-file web UI (stdlib saja), SSE streaming. Cukup untuk companion, bukan IDE |
| 29 | Konektor GitHub + Email IMAP/SMTP | Mengejar, jauh | Hermes: katalog MCP + 30+ platform messaging + plugin. AZZX: 2 konektor. Google Drive ditunda (butuh OAuth2 app manual) |
| 30 | `webauto` (browse otonom read-only) | Mengejar, belum setara | Hermes: browser automation penuh (navigate/snapshot/vision, multi-backend). AZZX: fetch/search + loop search→read→decide, read-only, SSRF guard. Playwright penuh ditunda (300MB+, lawan target kentang) |
| 31 | Fix sandbox Android (RLIMIT_AS → SIGABRT) | **Unggul di Termux** | Ditemukan via testing di Termux: cap address-space 512MB membuat Bionic abort semua proses. Sekarang dilewati di Android. Hermes juga dukung Termux, tapi fiks semacam ini menunjukkan perhatian AZZX ke platform lemah |

### Hasil testing AZZX v10.6.3 di mesin (2026-10-11)

- 182–183 unit test lolos di Python 3.10/3.11/3.12/3.14; selftest 7/7
- Fungsional: `compress` (8.975→1.539 chars), `audit` end-to-end, `exec run`,
  `checkpoint`, `plan`, GUI (HTTP 200), permission deny — semua OK
- Bug ditemukan & diperbaiki saat testing: klasifikasi denial di auditor
  (`PermissionDenied` terdeteksi sebagai `error`, bukan `denied`)
- `browse search` gagal di VM ini karena egress proxy meng-intercept TLS
  (environmental, bukan bug kode)

### Skor jujur per kategori (update)

| Kategori | Hermes | AZZX v10.6.3 |
|---|---|---|
| Jumlah built-in tools | ✅ 60+ | ~45 (mengejar) |
| Messaging gateway | ✅ 30+ platform | 1 (Telegram) |
| Browser automation | ✅ penuh + vision | Read-only |
| Voice | ✅ | ❌ |
| Learning loop | ✅ auto-create skills | Staged/trust-gated (lebih aman, kurang otonom) |
| **Auditability kerja agen** | Trajectory + enterprise | ✅ **Rule-based + LLM judge per run** |
| **Kompresi konteks** | Auxiliary model (bayar) | ✅ **AST gratis** |
| **Ringan (kentang/Termux)** | Bootstrap Python 3.14+Node+FFmpeg | ✅ **httpx+rich saja** |
| Permission model | Smart approvals | ✅ Deny-first absolut |
| Multi-agent | ✅ Bot Mode, MoA, A2A | Roles + queue (sederhana) |
| Ekosistem | ✅ 252k stars | Solo project |
