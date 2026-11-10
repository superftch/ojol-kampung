# Ojol KampungSebelah

Automation Ojol dengan browser **headless**, Google ADK dan **Browser Harness MCP**. Kontrol melalui tombol Telegram; login lewat import cookie sesi game. Tidak memakai Chrome desktop, mouse atau keyboard host.

- Tanpa batas trip/durasi secara default; saldo utama minimum **20 koin**.
- Mengikuti countdown game, mengambil ongkos, lalu melanjutkan order.
- Mengisi bensin/kuota/kondisi lewat tombol **mata**, memilih produk berdasarkan biaya per poin tanpa overflow.
- Laporan harian WIB: payout diterima, biaya dan laba bersih; tanggal bisa dipilih.
- Notifikasi event ON/OFF persisten. Error selalu STOP dan dilaporkan; klik yang belum pasti tidak diulang.

Gunakan hanya dengan izin operator game. Satu akun, satu worker dan satu volume aktif. Login Google/noVNC tidak diperlukan.

## Deploy server

Prasyarat: Linux amd64/arm64, Docker Engine dengan Compose, koneksi keluar untuk game/Telegram, dan domain Cloudflare untuk form import. Container dibatasi 2 CPU / 2 GiB RAM; sisakan resource untuk OS dan proxy.

```sh
git clone git@github.com:superftch/ojol-kampung.git
cd ojol-kampung
cp .env.example .env
chmod 600 .env
mkdir -p .secrets
chmod 700 .secrets
```

Isi `.env` langsung di server:

| Variabel | Isi |
|---|---|
| `OJOL_ENV` | `production` |
| `OJOL_OPERATOR_AUTHORIZED` | `true` setelah izin operator tersedia |
| `OJOL_MANAGED_BROWSER` | `true` |
| `OJOL_TELEGRAM_BOT_TOKEN` | Token BotFather |
| `OJOL_TELEGRAM_CHAT_ID` | ID chat pribadi; buka bot dan tekan Start dahulu |
| `OJOL_LOGIN_PUBLIC_URL` | `https://ojolkampung.sftch.web.id` |
| `OJOL_TUNNEL_ENABLED` | `true` untuk connector dalam container |
| `OJOL_MIN_BALANCE` | `20` atau lebih |
| `OJOL_MAX_JOBS`, `OJOL_MAX_MINUTES`, `OJOL_MAX_SPEND` | Kosong untuk tanpa batas |

Simpan token connector dari dashboard Cloudflare ke `.secrets/cloudflared-token` melalui editor di server, lalu `chmod 600 .secrets/cloudflared-token`. File ini wajib untuk Compose; tidak masuk image/Git.

```sh
docker compose build app
docker compose up -d
curl -fsS http://127.0.0.1:6080/health
docker compose logs --tail 50 app
```

Konfigurasi production ditolak jika Telegram belum lengkap, origin bukan HTTPS atau saldo minimum di bawah 20. Konfigurasi dipasang sebagai Compose secret saat runtime; tidak disertakan dalam image. Browser dan proses aplikasi berjalan sebagai UID1000 setelah bootstrap permission volume.

Image runtime tidak menyimpan uv atau cache dependency; uv dipakai sementara saat build dan tersedia pada test stage CI. Direktori/permission volume disiapkan entrypoint saat startup.

Satu service Compose, satu container: control service, Chromium, worker/bot dan cloudflared. Hanya `127.0.0.1:6080` dipublikasikan; CDP9222 dan metrics2000 tetap internal. Restart container ikut me-restart seluruh proses.

### Domain Cloudflare permanen

Connector sudah berada dalam image, versi2026.10.7 dipin dengan digest. Tidak perlu menjalankan container cloudflared kedua. Pada dashboard tunnel, tambahkan Published application route:

| Pengaturan | Nilai |
|---|---|
| Public hostname | `ojolkampung.sftch.web.id` |
| Service type | **HTTP** |
| Service URL | **`http://localhost:6080`** |

`localhost` menunjuk app karena connector dan app berada dalam container yang sama. TLS publik disediakan Cloudflare. Token connector tidak mengatur route/DNS; simpan route hostname tersebut pada dashboard.

Token dimuat lewat [parameter resmi `--token-file`](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/configure-tunnels/run-parameters/#token-file), bukan nilai token pada argv/environment. Bootstrap menyalinnya ke file UID1000 mode0600 di volume. Jangan membagikan volume atau file token.

Control service memantau proses connector. Jika cloudflared keluar, worker STOP dan bot melaporkan stage `tunnel.process_exit`. Tombol Import Cookie atau Jalankan Ojol mencoba memulai connector kembali; gameplay tidak diulang otomatis. Reconnect jaringan sementara ditangani cloudflared selama prosesnya hidup.

`/health` mencatat proses tunnel hidup, bukan bukti koneksi edge. Periksa koneksi connector:

```sh
docker compose exec -u app app python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:2000/ready',timeout=3).status)"
```

Domain production dari `.env` mengalahkan URL Quick Tunnel lama di volume. Setelah ganti `.env` atau token, jalankan `docker compose up -d --force-recreate app`. Jangan aktifkan connector atau worker akun yang sama pada dua server saat migrasi.

### Mulai lewat Telegram

| Tombol | Fungsi |
|---|---|
| **Import Cookie** | Stop worker dan kirim link form HTTPS sekali pakai, berlaku15menit |
| **Jalankan Ojol** | Mulai worker headless tanpa batas default |
| **Hentikan Ojol** | Stop worker dengan tetap menyimpan profil dan ledger |
| **Status** | Resource, saldo, tahap, countdown estimasi dan status notifikasi |
| **Laba Bersih** | Hari ini WIB; navigasi hari/tanggal dan transaksi terakhir |
| **Notifikasi ON / OFF** | Aktifkan/nonaktifkan semua event rutin; error+STOP selalu aktif |

Import hanya menerima cookie sesi `__Secure-better-auth.session_token` milik `www.kampungsebelah.com`, sebagai nilai atau JSON cookie. Nilai cookie tidak masuk chat Telegram, argv atau log. Form memerlukan sesi HttpOnly dan CSRF yang terikat ke sesi; akses dicabut setelah import berhasil. Profil browser dalam volume menyimpan sesi tersebut.

Tanggal laporan bisa dipilih dengan tombol inline atau diketik `YYYY-MM-DD` / `DD-MM-YYYY`, tanpa slash command. Pendapatan berasal dari payout di riwayat game, bukan seluruh selisih dompet. Belanja manual di luar worker tidak otomatis tercatat sebagai biaya automation.

## Data, log dan pemulihan

Volume `state` menyimpan profil Chromium, `history.sqlite3`, status, katalog dan pengaturan. `docker compose down` mempertahankannya; **`down -v` menghapus data**.

Log worker masuk `docker compose logs` dengan rotasi maksimal3file×10MiB. Salinan notifikasi terkirim/disenyapkan dibersihkan setelah7hari; notifikasi pending, event SQLite dan ledger keuangan tetap disimpan. SQLite memakai WAL untuk pembacaan laporan bersamaan dengan worker.

```sh
# Hari ini / tanggal tertentu / seluruh riwayat
docker compose exec -u app app python main.py profit
docker compose exec -u app app python main.py profit --date 2026-01-02
docker compose exec -u app app python main.py profit --all-time

# Rekonsiliasi read-only game ketika worker berhenti
docker compose exec -u app app python main.py reconcile
```

Timeout klik menghasilkan aksi `uncertain` dan memblokir start baru. Rekonsiliasi hanya mengubah ledger bila bukti memadai; tidak mengirim ulang klik. Klaim lama bisa dipulihkan dari satu receipt dengan rute, menit dan kenaikan payout yang cocok. Bila bukti tidak cukup, tetap STOP; jangan menghapus database untuk memaksa replay.

Jika STOP pada `job.complete.verify`, tekan Hentikan Ojol, update image, lalu jalankan `docker compose exec -u app app python main.py reconcile`. Untuk klaim ongkos, perubahan history saja tidak cukup: receipt, rute, waktu dan kenaikan hasil harian harus cocok. Setelah aksi terverifikasi, tekan Jalankan Ojol. Jika masih belum pasti, simpan output rekonsiliasi dan log; jangan paksa status database. Error start yang diblokir ditandai `cli.run`, tidak memakai stage verifikasi dari PID worker sebelumnya.

Saat pesan game menyatakan karakter tidur, worker berhenti sebelum mencari order atau belanja. Bangunkan karakter melalui game. Untuk pencarian lama yang belum pasti, `reconcile` mengambil dua snapshot setelah refresh, terpisah1detik. Jika keduanya stabil, tidak ada order aktif/ditawarkan, saldo/hasil/history tetap sama pada hari WIB yang sama dan resource tidak bertambah, pencarian ditutup sebagai `closed_idle`. Penurunan resource dicatat dalam event tanpa menebak penyebabnya; hasil klik lama tetap ditandai tidak diketahui, tanpa klik ulang dan tanpa membuat pendapatan/biaya koin. Ini tidak berlaku untuk klaim ongkos atau pembelian. Bila bukti tidak cocok, aksi tetap diblokir dan output menampilkan perbandingan snapshot. Status `Mencari…` diterima sebagai pencarian sedang diproses; worker menunggu paling lama30detik tanpa klik duplikat.

Start worker, `inspect`/`doctor` dan `reconcile` menyegarkan tab automation yang digunakan kembali melalui MCP. Pembacaan menunggu dokumen baru dan navigasi Kerja siap, sehingga perubahan seperti Bangun dari browser lain tidak tertahan di UI lama. Tab baru cukup dimuat sekali. Refresh tidak diulang saat timeout dan tidak mengirim ulang klik order/pembelian.

### Backup dan update

Backup konsisten seluruh profil/ledger, tanpa worker aktif:

```sh
umask 077
docker compose stop app
docker compose run --rm --no-deps -T --entrypoint tar app -C /data -czf - runtime > state-backup.tar.gz
docker compose start app
```

Arsip memuat sesi akun; simpan privat di luar repo. Untuk restore:

```sh
docker compose stop app
docker compose run --rm --no-deps -T --entrypoint tar app -C /data -xzf - < state-backup.tar.gz
docker compose start app
```

Pertahankan UID1000. Alternatif pemindahan server: backup ledger dan import cookie baru; jangan menjalankan akun yang sama pada kedua server.

```sh
# Update source dan image; tidak menghapus volume.
git pull --ff-only
docker compose build app
docker compose up -d
```

Setelah restart/deploy, gameplay **tidak** otomatis dimulai. Periksa Status dan tekan Jalankan Ojol. Sesi yang terputus atau hasil klik belum pasti tetap membutuhkan pemeriksaan. `/health` menunjukkan kesehatan control service/browser, bukan jaminan job game berhasil.

## Pengembangan dan pemeriksaan

Python3.12 dan `uv` diperlukan untuk menjalankan tooling lokal:

```sh
uv sync --frozen
uv run ruff check .
uv run ruff format --check .
uv run python scripts/test.py --prepare
uv run python scripts/test.py
# Jalur CI yang sama, tanpa secret/volume akun:
docker build --target test -t ojol-kampung:test .
```

`.env.testing` harus lokal dan tidak pernah dilacak Git, sekalipun dummy. Runner memuat file itu secara eksplisit, membuang env shell, mengisolasi HOME/tmp/cache/SQLite dan memblokir jaringan. Tidak ada fallback ke `.env`. Tests mencakup MCP stdio discovery tanpa Chrome, state machine, uang/receipt, batas hari WIB, cookie/CSRF, private-chat authorization dan timeout tanpa replay.

Mode lokal untuk Chrome CDP atau Quick Tunnel memakai `OJOL_ENV=local`; tetap gunakan runtime terpisah dan hentikan worker lain pada akun yang sama. Utilitas `python -m ojol.session_transfer to-docker` tersedia untuk transfer sesi Chrome lokal melalui MCP/stdin, bukan mengirim cookie ke Telegram.

[Arsitektur](docs/architecture.md) · [ADK MCP](https://adk.dev/tools-custom/mcp-tools/) · [Browser Harness MCP](https://github.com/browser-use/browser-harness/blob/main/docs/MCP.md) · [Telegram Bot API](https://core.telegram.org/bots/api)
