# AZZATSSINS LITE AGENT v10.3.0 — Panduan Indonesia

AZZX adalah agent CLI untuk coding dan toolkit sistem di Linux/Termux, dengan registry tool terpusat, permission, memory lokal, multi-agent role, queue, dan workflow yang dibatasi ke tool terdaftar.

## Fitur utama

- **Coding & engineering:** review, debug, tests, Git, sandbox, factory, release.
- **Toolkit:** file, hash, archive, JSON, media, network, proses, dan system health.
- **Workflow & plugins:** workflow hanya memanggil tool terdaftar; plugin tetap harus dipercaya dan ditinjau.
- **Android/Termux:** deteksi ADB/Termux API dan screen mirroring via scrcpy.
- **Agent layer:** SQLite memory dengan pencarian keyword + TF-IDF ringan, role delegation, tracing, streaming provider tertentu, dan image request untuk model yang mendukung.
- **Queue reliability (10.3):** persistensi task yang lebih aman, snapshot atomik, dan regresi test.
- **Scheduler (10.3):** jadwalkan tool terdaftar pada interval tertentu. Scheduler bukan daemon; jalankan `run-due` secara manual atau dari cron/systemd.

## Instalasi

```bash
unzip AZZATSSINS_LITE_AGENT_v10.3.0.zip
cd AZZATSSINS_LITE_AGENT_v10.3.0
chmod +x *.sh
./install.sh --check
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
azzx hermes queue list
azzx hermes memory "preferensi proyek"
azzx hermes trace
```

## Scheduler

```bash
# Tambah job tiap jam; interval minimum 60 detik
azzx hermes schedule add sys.info --every 3600 --name "info per jam" --args '{}'
azzx hermes schedule list
azzx hermes schedule run-due
azzx hermes schedule remove JOB_ID
```

Agar otomatis, jalankan `crontab -e` dan tambahkan `* * * * * /path/absolut/azzx hermes schedule run-due`. Ganti path dengan lokasi executable `azzx` yang benar. Pastikan permission tool sudah dikonfigurasi agar job dapat berjalan tanpa prompt interaktif. Jadwalkan hanya tool yang kamu pahami.

## Batasan penting

- TF-IDF adalah pencarian teks lokal, bukan neural embedding.
- Multi-agent role saat ini merupakan orkestrasi ringan; label role tidak menjamin reasoning independen atau kualitas hasil tertentu.
- Streaming/vision tergantung provider dan model; belum semua kombinasi diuji langsung.
- CI offline tidak menggantikan pengujian installer pada distro dan perangkat sungguhan.
- Jangan jalankan seluruh agent sebagai root dan jangan commit API key/config pribadi.
