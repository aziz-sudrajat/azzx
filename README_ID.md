# AZZATSSINS LITE AGENT v10.0 — Panduan Indonesia

AZZX v10 adalah **Universal Agent Layer**: AI sebagai orkestrator, tool deterministik sebagai eksekutor.

## Fitur baru

- **v7 Toolkit** — cari file, file terbesar, duplikat, hash, arsip, JSON, FFmpeg, jaringan, proses, git, health
- **v8 Workflow** — otomatisasi hanya dari tool terdaftar (bukan shell bebas)
- **v8 Mirror** — mirroring layar Android ke desktop via **scrcpy** (realistis, bukan DeX penuh)
- **v9 Plugin** — `manifest.json` + permission + validasi
- **v10** — registry tool terpusat; fondasi coding agent + installer v6 tetap ada

## Instalasi

```bash
unzip AZZATSSINS_LITE_AGENT_v10.0.zip
cd AZZATSSINS_LITE_AGENT_v10.0
chmod +x *.sh
./install.sh
azzx --version
```

## Perintah cepat

```bash
azzx toolkit health
azzx nl "status git"
azzx workflow create cek --steps '[{"tool":"sys.health","args":{}}]'
azzx mirror detect
azzx mirror start --dry-run
azzx plugin install examples/sample-plugin
azzx install scrcpy --plan
```

## Mirror Android

Butuh **scrcpy** + **adb** di komputer. Perintah `azzx mirror start` menampilkan layar HP di desktop dan memungkinkan kontrol mouse/keyboard.

Ini **bukan** Samsung DeX (mode desktop di dalam HP). DeX penuh memerlukan dukungan OEM/sistem Android.

## Keamanan

- Workflow tidak bisa memanggil shell arbitrer
- Argumen scrcpy/adb di-whitelist
- Plugin wajib deklarasi permission yang dikenal
- Extract arsip menolak path `../`
