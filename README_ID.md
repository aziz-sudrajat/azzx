# AZZATSSINS LITE AGENT v10.4.0 — Panduan Indonesia

AZZX adalah agent CLI untuk coding dan toolkit sistem di Linux/Termux: satu agent terpadu dengan registry tool terpusat, permission, memory lokal, role multi-agent, queue, session, skill, dan workflow yang dibatasi ke tool terdaftar.

## Fitur utama

- **Coding & engineering:** review, debug, tests, Git, sandbox, factory, release.
- **Toolkit:** file, hash, archive, JSON, media, network, proses, dan system health.
- **Workflow & plugins:** workflow hanya memanggil tool terdaftar; plugin tetap harus dipercaya dan ditinjau.
- **Android/Termux:** deteksi ADB/Termux API dan screen mirroring via scrcpy.
- **Agent terpadu (10.4):** `azzx agent` menjalankan role planner/researcher/coder/reviewer/tester/security lewat AI provider yang dikonfigurasi — tanpa mode terpisah. Mode `azzx hermes` sudah dihapus; jalankan `azzx hermes` untuk melihat tabel migrasinya.
- **Memory:** SQLite lokal dengan pencarian keyword + semantik TF-IDF (ringan, tanpa ML berat), batas shared/private, cakupan project, dan penolakan otomatis bila konten terlihat seperti secret.
- **Queue & scheduler:** background task dengan status cancel/interrupted/resume; scheduler interval untuk tool terdaftar (bukan daemon — jalankan `run-due` dari cron).
- **Session:** jurnal sesi dengan resume (mengembalikan ringkasan + event + konteks project).
- **Skill:** registry skill native yang tervalidasi dan hanya jalan setelah di-trust + enable.

## Instalasi

```bash
unzip AZZX_v10_NEXT_READY_TO_PUSH.zip
cd AZZX_v10_NEXT_READY_TO_PUSH
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
azzx agent "review modul auth" --agents planner,reviewer,security
azzx agent --roles
azzx recall search "preferensi proyek"
azzx recall add "deploy memakai blue-green" --tags deploy --project web
azzx queue submit sys.health --args '{}' -y
azzx queue list
azzx trace --limit 20
azzx session start web "kerja deploy"
azzx skills find "uppercase"
```

## Scheduler

```bash
# Tambah job tiap jam; interval minimum 60 detik
azzx schedule add sys.info --every 3600 --name "info per jam" --args '{}'
azzx schedule list
azzx schedule run-due
azzx schedule remove JOB_ID
```

Agar otomatis, jalankan `crontab -e` dan tambahkan `* * * * * /path/absolut/azzx schedule run-due`. Ganti path dengan lokasi executable `azzx` yang benar. Background job tidak pernah menampilkan prompt: tool yang permission-nya bukan `allow` butuh `-y` saat submit (atau set permission-nya ke `allow`). `deny` bersifat mutlak — tidak bisa dilewati oleh `-y`, workflow, maupun queue. Jadwalkan hanya tool yang kamu pahami.

## Batasan penting

- TF-IDF adalah pencarian teks lokal, bukan neural embedding.
- Role multi-agent memanggil AI provider yang dikonfigurasi; tanpa provider, perintah `azzx agent` akan gagal dengan pesan yang jelas (tidak ada jawaban simulasi).
- Parallel multi-agent hanya untuk role read-only.
- Task yang owner-nya mati ditandai `interrupted` dan tidak diulang otomatis — cek efek sampingnya dulu, lalu `azzx queue resume`.
- Streaming/vision tergantung provider dan model; belum semua kombinasi diuji langsung.
- CI offline tidak menggantikan pengujian installer pada distro dan perangkat sungguhan.
- Jangan jalankan seluruh agent sebagai root dan jangan commit API key/config pribadi.
