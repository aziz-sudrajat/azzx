# GitHub push guide — AZZX v10.6.0 "Connected"

Target: `https://github.com/aziz-sudrajat/azzx.git`
Archive: `AZZX_v10.6_READY_TO_PUSH.zip` (96 files, ~840 KB)
SHA256: `cb5265fbf19dafc94bc2fca99ab6df1c21d29808652f625cebe8b1962ababc1e`

> The ZIP contains no `.git/` history, no secrets, no caches. You push it
> yourself — nothing here pushes automatically.

## 1. Di Termux: siapkan direktori dan unduh ZIP

```bash
pkg install -y git unzip python
mkdir -p ~/azzx-push && cd ~/azzx-push
# unduh AZZX_v10.6_READY_TO_PUSH.zip ke direktori ini, lalu:
unzip -q AZZX_v10.6_READY_TO_PUSH.zip
ls
cat VERSION   # harusnya 10.6.0
```

Verifikasi integritas (opsional tapi disarankan):

```bash
sha256sum AZZX_v10.6_READY_TO_PUSH.zip
# harus sama persis dengan SHA di atas
grep -RIE --exclude='test_core.py' --exclude='README*' \
  '(sk-[A-Za-z0-9]{20,}|AIza[0-9A-Za-z_-]{20,})' . \
  && echo "LEAK?" || echo "bersih"
```

## 2. Clone repo dan buat branch rilis

```bash
cd ~
git clone https://github.com/aziz-sudrajat/azzx.git azzx-repo
cd azzx-repo
git log --oneline -3        # pastikan ini repo yang benar
git checkout -b release/v10.6.0
```

## 3. Timpa tree dengan isi rilis

```bash
# Hapus semua kecuali .git, lalu salin isi rilis:
find . -mindepth 1 -maxdepth 1 ! -name '.git' -exec rm -rf {} +
cp -r ~/azzx-push/. .
git add -A
git status --short | head -40
```

## 4. Sanity check sebelum commit

```bash
python3 -m py_compile azzx_cli.py
PYTHONPATH=. python3 -m unittest discover -s tests -p 'test_*.py' 2>&1 | tail -3
# ekspektasi: Ran 163 tests ... OK
```

## 5. Commit dan push (tanpa force)

```bash
git commit -m "Release AZZX v10.6.0: Connected

- azzx gui: friendly ChatGPT-like web chat UI (SSE streaming, /api/auto)
- Web browsing otonom: azzx webauto (search->read->decide->follow->answer),
  azzx browse search/fetch/links, web.search/fetch/links agent tools
- Connectors: azzx connector setup (GitHub PAT, email IMAP/SMTP);
  github.* dan email.* agent tools
- Cron scheduler: azzx schedule add --cron
- Companion: azzx setup/chat, /remember, Telegram gateway (/auto+/autoy)
- Sandbox: azzx exec run (local+docker), sandbox.exec tool
- Planning/learning: azzx plan/learn, todo.* tools, staged proposals
- Checkpoints: create/rollback (overlay + pre-rollback safety)/prune
- Session search, MCP agent tool (mcp.call), skills install dari git URL
- Audit fixes: todo ID monotonic, rollback semantics jujur, Telegram
  approval via chat, SMTP 465, GUI run-cap
- README.md + README_ID.md ditulis ulang (tiap command ada contoh)
- Wallet DIHAPUS per permintaan user (tidak bisa buat dompet asli)
Lihat CHANGELOG.md."

git push -u origin release/v10.6.0
```

Lalu buka pull request `release/v10.6.0` → `main` di GitHub dan merge di sana.

### Varian langsung ke main (aman, tanpa force)

```bash
git checkout main
git pull --ff-only origin main
git merge --no-ff release/v10.6.0 -m "Merge release v10.6.0"
git push origin main
```

## 6. Tag rilis (opsional)

```bash
git tag -a v10.6.0 -m "AZZX v10.6.0 — Connected"
git push origin v10.6.0
```

Jangan pernah `push --force`.
