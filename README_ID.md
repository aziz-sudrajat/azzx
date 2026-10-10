# AZZX v10.6 — Sahabat AI Pribadimu

**Satu AI agent terpadu untuk terminal.** Ngobrol dengannya seperti teman, biarkan
dia merencanakan dan mengeksekusi tugas secara mandiri, dan jalankan di mana saja —
dari PC kentang sampai HP Android dengan Termux.

```bash
bash install.sh                 # install ke ~/.local/share + perintah `azzx`
azzx setup                      # kenalkan namamu (tersimpan lokal, privat)
azzx chat                       # ngobrol dengan companion
azzx auto "rapikan folder download"   # otonom: rencana → setujui → eksekusi → belajar
```

[![Version](https://img.shields.io/badge/version-10.5.0-cyan)](./VERSION)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](.)
[![Platform](https://img.shields.io/badge/platform-Termux%20%7C%20Linux-green)](.)

> 🇬🇧 English version: [README.md](./README.md).

---

## Daftar isi

1. [Apa itu AZZX?](#1-apa-itu-azzx)
2. [Instalasi (2 menit, ringan untuk kentang)](#2-instalasi)
3. [Mulai cepat](#3-mulai-cepat)
4. [Referensi command](#4-referensi-command)
5. [Cara kerja](#5-cara-kerja)
6. [Konfigurasi](#6-konfigurasi)
7. [FAQ](#7-faq)

---

## 1. Apa itu AZZX?

AZZX adalah **AI agent pribadi berbasis terminal**. Beda dengan chatbot biasa, dia bisa
*bertindak*: menjalankan perintah di sandbox, membuat rencana lalu mengeksekusinya
langkah demi langkah, mengingat yang kamu ajarkan, membuat skill baru dari pengalaman,
bahkan bisa dihubungi dari HP lewat Telegram.

**Prinsip desain**

- **Satu agent, tanpa mode.** Semua fitur adalah command native dari agent yang sama.
- **Ringan.** Cuma 2 dependensi Python (`httpx`, `rich`). Kecerdasannya datang dari
  AI provider (API), jadi laptop kentang pun dapat agent kelas penuh.
- **Deny-first.** Permission `deny` bersifat **absolut** — tidak bisa dilewati `-y`,
  queue, workflow, atau autonomous run.
- **Skill trust-gated.** Skill baru terinstall dalam keadaan *untrusted + disabled*;
  kamu review dulu, baru `trust` + `enable`.
- **Privat.** Memori, profil, dan API key tetap di perangkatmu.

---

## 2. Instalasi

**Syarat:** Python 3.10+, ~50 MB disk, ~100 MB RAM. Itu saja.

```bash
# Disarankan — script installer (venv + dep + launcher `azzx` di PATH)
bash install.sh
# Termux (Android)
pkg install python git && bash install.sh
# Manual (tanpa installer): butuh Python 3.10+
python3 -m venv .venv && . .venv/bin/activate
pip install httpx rich
python3 azzx_cli.py --version
```

Cek instalasi:

```bash
azzx doctor     # Python, dep, disk, memori, provider — semua hijau?
azzx --version
```

Konfigurasi AI provider (OpenAI-compatible, Anthropic, Cohere, atau Ollama lokal):

```bash
azzx ai         # setup provider interaktif (key masuk ke vault aman)
```

> Belum punya provider? Command yang tidak butuh AI (`exec`, `checkpoint`,
> `schedule`, `doctor`, …) tetap jalan offline.

---

## 3. Mulai cepat

```bash
azzx setup
# → "Namamu siapa?" — AZZX mengenal namamu, bahasamu, zona waktumu.
#   Tersimpan di ~/.config/azzx/profile.json (chmod 600, tidak keluar perangkat).

azzx chat
# → companion interaktif dengan slash command:
#   /plan <tujuan>  /auto <tujuan>  /remember <fakta>  /learn  /memory <q>  /quit

azzx auto "cek kesehatan sistem lalu ringkas dalam Bahasa Indonesia"
# → membuat rencana, minta persetujuan, eksekusi via tool asli,
#   checkpoint sebelum langkah berisiko, lalu belajar dari hasilnya.

azzx learn list
# → review apa yang dipelajari agent; setujui yang layak jadi memori/skill.

azzx gui
# → web UI akrab seperti ChatGPT di http://127.0.0.1:8766 (chat, streaming, aksi cepat)
```

---

## 4. Referensi command

Setiap command: fungsi + contoh. `azzx <command> --help` untuk flag lengkap.

### Companion & chat

| Command | Fungsi | Contoh |
|---|---|---|
| `azzx setup` | Setup awal: nama, bahasa, catatan (lokal saja) | `azzx setup` |
| `azzx chat` | Companion interaktif + streaming + slash command | `azzx chat` |
| `azzx gui` | Web UI akrab seperti ChatGPT (streaming chat, aksi cepat) | `azzx gui --open` |
| `azzx gateway telegram` | Jalankan AZZX sebagai bot Telegram di HP | `azzx gateway telegram --token $TG --allow-from 123456` |

Slash command di `azzx chat`: `/plan`, `/auto`, `/agent`, `/learn`,
`/remember <fakta>`, `/memory <q>`, `/skills`, `/trace`, `/clear`, `/quit`.

### Agent otonom

| Command | Fungsi | Contoh |
|---|---|---|
| `azzx auto "<tujuan>"` | **Rencana → setujui → eksekusi → belajar**, mandiri penuh | `azzx auto "backup project ke /tmp/bak" -y` |
| `azzx agent "<tugas>"` | Pipeline multi-agent (planner → researcher → coder → reviewer → tester → security) | `azzx agent "refactor auth.py"` |
| `azzx agent --roles` | Lihat 6 role dan tool yang boleh dipakai tiap role | `azzx agent --roles` |

Flag `auto`: `-y` (lewati persetujuan — hati-hati), `--max-steps N` (default 25),
`--workdir PATH`. Langkah berisiko otomatis di-checkpoint.

### Perencanaan & pembelajaran

| Command | Fungsi | Contoh |
|---|---|---|
| `azzx plan "<tujuan>"` | Buat rencana eksekusi eksplisit (tersimpan di `.azzx/plans/`) | `azzx plan "deploy ke VPS"` |
| `azzx plan "<tujuan>" --execute` | Tampilkan rencana, lalu eksekusi | `azzx plan "bersihkan /tmp" --execute -y` |
| `azzx learn list` | Lihat hasil belajar yang staged (memori + draft skill) | `azzx learn list` |
| `azzx learn approve memory 0` | Setujui memori staged → masuk memori jangka panjang | `azzx learn approve memory 0` |
| `azzx learn approve skill 0` | Install draft skill (untrusted+disabled; review dulu!) | `azzx learn approve skill 0` |
| `azzx learn discard <jenis> <i>` | Buang proposal | `azzx learn discard skill 1` |

Agent juga mencatat kerjanya sendiri via tool `todo.add` / `todo.list` /
`todo.done` / `todo.clear`.

### Memori

| Command | Fungsi | Contoh |
|---|---|---|
| `azzx recall search "<q>"` | Cari memori (keyword + semantik) | `azzx recall search "preferensi deploy"` |
| `azzx recall add "<fakta>"` | Simpan memori manual | `azzx recall add "VPS di 192.0.2.10"` |
| `azzx recall list` | Daftar memori | `azzx recall list --limit 20` |
| `azzx recall delete <id>` | Hapus memori | `azzx recall delete 42` |
| `azzx recall stats` | Statistik memori | `azzx recall stats` |
| `azzx remember "<catatan>"` | Tambah ke memori *project* (`.azzx/memory.md`) | `azzx remember "pakai uv, bukan pip"` |

Rahasia (API key, token, private key) **ditolak** di gerbang memori.

### Eksekusi sandbox

| Command | Fungsi | Contoh |
|---|---|---|
| `azzx exec run -- <cmd>` | Jalankan perintah di sandbox (cwd jail, timeout, output cap, env dibersihkan) | `azzx exec run -- python3 script.py` |
| `azzx exec run --backend docker -- <cmd>` | Isolasi kuat: Docker, `--network none`, 512 MB | `azzx exec run --backend docker -- ./build.sh` |
| `azzx exec backends` | Lihat backend tersedia | `azzx exec backends` |

Agent memakai tool `sandbox.exec` untuk hal yang sama. Batas jujur: backend
`local` tidak bisa memblokir akses network — pakai `docker` jika itu penting.

### Penjadwalan

| Command | Fungsi | Contoh |
|---|---|---|
| `azzx schedule add <tool>` | Jalankan tool tiap N detik | `azzx schedule add sys.health --every 3600` |
| `azzx schedule add <tool> --cron "<expr>"` | Sintaks cron (tanpa dependensi baru) | `azzx schedule add sys.health --cron "*/15 9-17 * * 1-5"` |
| `azzx schedule list` | Daftar job | `azzx schedule list` |
| `azzx schedule run-due` | Eksekusi job yang jatuh tempo (panggil dari cron/systemd) | `*/5 * * * * azzx schedule run-due` |
| `azzx schedule remove <id>` | Hapus job | `azzx schedule remove a1b2c3` |

### Skill & MCP

| Command | Fungsi | Contoh |
|---|---|---|
| `azzx skills list` | Daftar skill terinstall | `azzx skills list` |
| `azzx skills install <dir\|url>` | Install dari direktori **atau URL git** (untrusted+disabled) | `azzx skills install https://github.com/…/my-skill` |
| `azzx skills trust <id>` | Tandai trusted setelah review kode | `azzx skills trust my-skill` |
| `azzx skills enable <id>` | Aktifkan skill trusted (daftar sebagai tool `skill.<id>`) | `azzx skills enable my-skill` |
| `azzx skills invoke <id>` | Panggil skill langsung | `azzx skills invoke my-skill --args '{}'` |
| `azzx skills find "<q>"` | Cari skill | `azzx skills find "pdf"` |
| `azzx mcp list` | Daftar MCP server | `azzx mcp list` |
| `azzx mcp add <nama> <cmd>` | Tambah MCP server (stdio) | `azzx mcp add files npx -y @modelcontextprotocol/server-filesystem /tmp` |
| `azzx mcp tools <nama>` | Lihat tool dari server | `azzx mcp tools files` |
| `azzx mcp call <nama> <tool>` | Panggil tool MCP | `azzx mcp call files read_file '{"path":"/tmp/a.txt"}'` |

Agent juga bisa memanggil tool MCP sendiri via tool registry `mcp.call`
(permission `mcp.execute`).

### Sesi & checkpoint

| Command | Fungsi | Contoh |
|---|---|---|
| `azzx session start <project> [judul]` | Mulai jurnal sesi | `azzx session start webku "refactor auth"` |
| `azzx session log <id> <pesan>` | Catat event | `azzx session log sess_abc "selesai migrasi"` |
| `azzx session resume <id>` | Pulihkan konteks sesi | `azzx session resume sess_abc` |
| `azzx session search "<q>"` | Cari di judul, ringkasan, dan event | `azzx session search "migrasi"` |
| `azzx session stale` | Temukan sesi yang terinterupsi | `azzx session stale --hours 48` |
| `azzx checkpoint create` | Snapshot direktori kerja (tarball, tanpa git) | `azzx checkpoint create --label "sebelum refactor"` |
| `azzx checkpoint rollback <id>` | Kembalikan snapshot | `azzx checkpoint rollback 20261010-120000-123456` |
| `azzx checkpoint list` | Daftar checkpoint | `azzx checkpoint list` |
| `azzx trace` | Timeline eksekusi (debugging) | `azzx trace --limit 30` |

### Antrean background

| Command | Fungsi | Contoh |
|---|---|---|
| `azzx queue add <tool>` | Antrekan tool untuk eksekusi background | `azzx queue add sys.health --args '{}'` |
| `azzx queue list` | Daftar job (queued/running/done/error) | `azzx queue list` |
| `azzx queue cancel <id>` | Batalkan job | `azzx queue cancel abc123` |
| `azzx queue resume <id>` | Lanjutkan job terinterupsi | `azzx queue resume abc123` |

### Coding & engineering

| Command | Fungsi | Contoh |
|---|---|---|
| `azzx ask "<q>"` | Tanya AI tentang projectmu | `azzx ask "di mana bug login?"` |
| `azzx fix "<deskripsi>"` | Perbaiki kode via AI | `azzx fix "null pointer di handler"` |
| `azzx add "<deskripsi>"` | Implementasikan fitur | `azzx add "tambah retry ke client"` |
| `azzx review` | Review kode statis | `azzx review --focus security` |
| `azzx test` | Jalankan test | `azzx test` |
| `azzx debug <cmd>` | Jalankan + diagnosa perintah gagal | `azzx debug "python3 main.py"` |
| `azzx autodebug <cmd>` | Loop: run → fix → run | `azzx autodebug "pytest -x"` |
| `azzx implement "<deskripsi>"` | Tugas implementasi besar | `azzx implement "tambah caching"` |
| `azzx create "<deskripsi>"` | Scaffold project baru | `azzx create "REST API dengan FastAPI"` |
| `azzx architect` | Analisis arsitektur | `azzx architect` |
| `azzx factory "<spesifikasi>"` | Spec → roadmap → tim sandbox → regresi → package | `azzx factory "todo app"` |
| `azzx sandbox "<tugas>"` | Kembangkan di salinan terisolasi, validasi, lalu merge | `azzx sandbox "tambah fitur X"` |
| `azzx develop "<tujuan>"` | Sesi development terpandu | `azzx develop "selesaikan issue #12"` |
| `azzx team "<tujuan>"` | Run tim multi-role | `azzx team "audit keamanan"` |

### Browsing web (otonom)

| Command | Fungsi | Contoh |
|---|---|---|
| `azzx webauto "<tugas>"` | **Browsing yang solve sendiri:** cari, buka halaman, ikuti link sampai bisa menjawab (read-only) | `azzx webauto "berapa harga kopi robusta hari ini"` |
| `azzx browse search "<q>"` | Cari di web (DuckDuckGo) | `azzx browse search "harga kopi"` |
| `azzx browse fetch <url>` | Ambil halaman sebagai teks bersih (tanpa JS) | `azzx browse fetch https://example.com` |
| `azzx browse links <url>` | Daftar link keluar dari halaman | `azzx browse links https://example.com` |

Flag `webauto`: `--start-url URL` (lewati pencarian), `--max-steps N` (default 12).
Agent hanya mengikuti link yang benar-benar ada di halaman — URL halusinasi
diblokir. Tool agent: `web.search`, `web.fetch`, `web.links` (permission
`web.read`). Batas jujur: web teks saja, tanpa JavaScript — untuk situs JS-heavy
pakai Playwright sendiri (sengaja tidak di-bundle).

### Konektor aplikasi

| Command | Fungsi | Contoh |
|---|---|---|
| `azzx connector setup github` | Hubungkan GitHub via personal access token | `azzx connector setup github` |
| `azzx connector setup email` | Hubungkan email via IMAP/SMTP (app password) | `azzx connector setup email` |
| `azzx connector list` | Daftar konektor | `azzx connector list` |

Tool agent: `github.repos`, `github.list_issues`, `github.create_issue`,
`email.inbox`, `email.send`. Google Drive butuh OAuth2 app Google Cloud —
ditunda, didokumentasikan di kode.

### Toolkit sistem

| Command | Fungsi | Contoh |
|---|---|---|
| `azzx install <app>` | Installer aplikasi universal (200+ app, sadar distro) | `azzx install ffmpeg` |
| `azzx toolkit sys` | Info sistem, health, proses, service | `azzx toolkit sys --action health` |
| `azzx toolkit net` | Cek network | `azzx toolkit net --action connectivity` |
| `azzx toolkit fs` | Operasi filesystem | `azzx toolkit fs --action list --path .` |
| `azzx toolkit media` | Utilitas media | `azzx toolkit media --action info --file a.mp3` |
| `azzx tools list` | Daftar *semua* tool terdaftar | `azzx tools list` |
| `azzx tools run <tool>` | Jalankan satu tool langsung | `azzx tools run sys.health` |
| `azzx nl "<teks>"` | Bahasa natural → tool call | `azzx nl "cek kesehatan disk"` |
| `azzx workflow …` | Workflow deterministik multi-langkah | `azzx workflow list` |
| `azzx dashboard` | Dashboard web | `azzx dashboard --port 8080` |

### Perangkat Android

| Command | Fungsi | Contoh |
|---|---|---|
| `azzx mirror start` | Mirror layar Android via scrcpy | `azzx mirror start --serial ABC123` |
| `azzx mirror status` | Status mirror | `azzx mirror status` |
| `azzx mirror stop` | Hentikan mirror | `azzx mirror stop` |

### Keamanan & permission

| Command | Fungsi | Contoh |
|---|---|---|
| `azzx permissions list` | Tabel kebijakan permission | `azzx permissions list` |
| `azzx permissions set <cap> <allow\|prompt\|deny>` | Ubah kebijakan | `azzx permissions set network.http deny` |

Kebijakan: `allow` (tanpa prompt), `prompt` (tanya dulu), `deny` (**absolut**).

### Utilitas

| Command | Fungsi | Contoh |
|---|---|---|
| `azzx doctor` | Cek kesehatan (Python, tools, provider, disk, memori) | `azzx doctor` |
| `azzx ai` | Konfigurasi AI provider | `azzx ai` |
| `azzx config` | Lihat konfigurasi | `azzx config` |
| `azzx update` | Self-update | `azzx update` |
| `azzx --version` | Versi | `azzx --version` |

> Shim legacy: `azzx hermes` mencetak panduan migrasi (exit 2). Tidak ada mode
> Hermes terpisah — semuanya satu agent terpadu.

---

## 5. Cara kerja

```text
Kamu (chat / auto / Telegram / CLI)
        ↓
Lapisan companion (persona, profil, memori jangka panjang)
        ↓
Planner → rencana eksplisit (`.azzx/plans/`) → persetujuanmu
        ↓
Autonomous runner → tool call HANYA via registry
        ↓                    ↓ gerbang permission deny-first
Tool Registry → sandbox.exec · sys.* · mcp.call · skill.* · todo.* …
        ↓
Checkpoint sebelum langkah berisiko · trace semua · distilasi pembelajaran
```

**Loop otonomi:** `rencana → setujui → eksekusi → checkpoint → belajar`.
Hasil belajar selalu *staged*, tidak pernah diterapkan diam-diam — kamu review
via `azzx learn`.

---

## 6. Konfigurasi

- `~/.config/azzx/` — `config.json`, provider, `profile.json`, `mcp.json`, vault
- `~/.local/share/azzx/` — DB memori, sesi, checkpoint, hasil belajar, queue
- `.azzx/` (per project) — rencana, memori project, skill lokal

API key tersimpan di secure vault bawaan OS, tidak pernah di chat/file.

---

## 7. FAQ

**Apakah jalan di laptop kentang?**
Ya. Butuh Python 3.10+ dan ~100 MB RAM. Kecerdasan datang dari AI provider via
API — mesinmu hanya menjalankan harness. Cek dengan `azzx doctor`.

**Bisa offline?**
Command non-AI (`exec`, `checkpoint`, `schedule`, `doctor`, …) jalan offline.
Panggilan provider butuh internet (atau Ollama lokal).

**Aman dibiarkan jalan otonom?**
`deny` absolut dan tidak bisa dilewati. Rencana ditampilkan sebelum eksekusi
(kecuali kamu pakai `-y`). Langkah berisiko di-checkpoint; `rollback` memulihkan.

**Bedanya dengan Hermes (Nous Research)?**
Jawaban jujur di [`docs/HERMES_FEATURE_GAP_ID.md`](./docs/HERMES_FEATURE_GAP_ID.md):
Hermes adalah *platform* yang lebih besar (60+ tool, 30+ aplikasi messaging,
voice, desktop app). AZZX unggul di toolkit Linux/Termux, installer universal,
Android mirroring, workflow deterministik — dan kini menyamai loop *agent* inti
Hermes: rencana, sandbox, checkpoint, pembelajaran, otonomi.

**Apakah AZZX bisa mengendalikan browser beneran seperti Playwright?**
`azzx browse` adalah pembaca ringan (tanpa JS). Bundle Playwright penuh butuh
~300 MB disk + RAM besar dan merusak janji "jalan di kentang", jadi sengaja
tidak disertakan. Kalau butuh, install Playwright sendiri dan kendalikan via
`azzx exec` / `sandbox.exec`.

**Aplikasi apa saja yang bisa dihubungkan?**
GitHub dan email hari ini (`azzx connector setup`). Google Drive butuh OAuth2
app Google Cloud — itu kerja manual di console Google; belum dibuat.

**Lapor bug ke mana?**
Issue di `https://github.com/aziz-sudrajat/azzx`.

---

*AZZX v10.6 — "Connected". MIT License.*
