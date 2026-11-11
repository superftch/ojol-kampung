# Ojol KampungSebelah

Automation Ojol multi-account dengan **HTTP MCP + Google ADK**. Satu bot Telegram melayani beberapa user dalam whitelist; setiap user bisa memiliki beberapa akun game. `OJOL_TELEGRAM_CHAT_ID` menjadi admin. Chrome, Browser Harness, fallback browser, dan migrasi profil browser dihapus.

- Default **3 akun per user**, **3 worker aktif global**; admin dapat mengubahnya tanpa restart.
- **1 akun = 1 subprocess worker**, dengan MCP, cookie, SQLite ledger, status dan pengaturan notifikasi sendiri. Semua berjalan dalam satu container aplikasi.
- Tanpa batas trip/durasi default; saldo utama production minimal **20 koin**.
- Pembacaan HTTP sementara gagal dicoba maksimal 3 kali (backoff 1/2 detik). Transaksi dikirim sekali; hasil ambigu menghentikan akun dan memblokir replay.
- Laporan laba harian WIB dan tombol navigasi tanggal terikat ke akun asal. Notifikasi diberi nama akun dan hanya dikirim ke pemiliknya.

Gunakan dengan izin operator game. Satu akun game jangan dijalankan bersamaan di server/aplikasi lain. Fingerprint cookie menolak cookie sama pada dua slot akun, termasuk arsip; dua sesi berbeda milik akun game sama belum bisa diidentifikasi tanpa ID pemain stabil dari API.

## Management Telegram

Admin pertama adalah ID pribadi dalam `OJOL_TELEGRAM_CHAT_ID`; ID ini selalu boleh masuk dan tidak bisa dicabut lewat bot. User lain ditolak sampai admin menambahkan ID numeriknya. Kontrol hanya menerima private chat dengan `chat.id == from.id`; grup dan callback milik user lain ditolak.

Saat user ditambahkan atau diaktifkan ulang, bot mengirim menu utama ke chat pribadi user. Jika user belum pernah membuka bot, minta user menekan **Start** dahulu; [Telegram melarang bot memulai percakapan pribadi](https://core.telegram.org/bots#how-are-bots-different-from-users). Jika tombol belum terlihat, admin bisa memilih **Kirim Menu**, atau user mengirim pesan **menu** ke bot. Setelah menu muncul: **Tambah Akun → ketik nama → Import Cookie**.

Semua operasi bot memakai tombol. Ketik hanya nilai yang diminta: ID Telegram, nama akun, batas angka, atau tanggal. Tidak perlu mengetik perintah. Tombol **Batal** selalu bisa membatalkan input; **Menu Utama** mengembalikan tombol utama.

| Aksi admin | Alur tombol |
|---|---|
| Lihat whitelist, kuota dan worker aktif | **Management → Daftar User** |
| Tambah user | **Management → Tambah User**, lalu ketik ID Telegram |
| Aktifkan ulang user | **Daftar User → pilih user → Aktifkan Akses** |
| Kirim ulang tombol utama user | **Daftar User → pilih user → Kirim Menu** |
| Cabut akses dan hentikan seluruh akun user | **Daftar User → pilih user → Cabut Akses → Ya, Cabut Akses** |
| Default akun per user | **Management → Batas Akun Default**, lalu ketik angka |
| Override akun user tertentu | **Daftar User → pilih user → Ubah Batas Akun**, lalu ketik angka |
| Batas worker aktif global | **Management → Batas Worker**, lalu ketik angka |

Batas valid 1–100. Override management disimpan di `accounts.sqlite3` dan mengalahkan default env setelah restart. Menurunkan batas tidak menghapus akun atau memutus worker yang sudah aktif; batas berlaku pada tambah/pulihkan/start berikutnya. Override user yang sudah dibuat tetap mengalahkan default global. Pencabutan whitelist menghentikan worker user, mencabut tiket/sesi import, dan membatalkan notifikasi pending; data/history tetap disimpan. Aktivasi ulang tidak otomatis menjalankan game.

| Aksi user | Alur tombol |
|---|---|
| Daftar dan pilih akun | **Akun Saya → Pilih nama akun** |
| Tambah akun | **Tambah Akun**, lalu ketik nama |
| Ubah nama | **Akun Saya → Pilih akun → Ubah Nama**, lalu ketik nama baru |
| Arsipkan akun | **Akun Saya → Pilih akun → Arsipkan Akun → Ya, Arsipkan** |
| Pulihkan arsip | **Akun Saya → Pulihkan nama akun** |
| Login akun terpilih | **Import Cookie** |
| Mulai/hentikan akun terpilih | **Jalankan Ojol** / **Hentikan Ojol** |
| Resource, saldo dan countdown | **Status** |
| Laporan harian WIB | **Laba Bersih**, tombol hari atau **Pilih tanggal**, lalu ketik tanggal |
| Event rutin | **Notifikasi ON / OFF** |

Akun baru atau akun yang dipulihkan langsung terpilih. Ganti pilihan tidak menghentikan akun lain. Arsip menghentikan worker dan mencabut akses import, membebaskan kuota akun, tanpa menghapus ledger/cookie. Daftar akun dan user memiliki tombol halaman berikutnya/sebelumnya; tidak perlu menyalin ID akun. Form input yang belum selesai dibatalkan saat bot restart. Konfirmasi arsip/cabut akses yang sudah dibatalkan tidak berlaku lagi.

Import hanya menerima cookie sesi `__Secure-better-auth.session_token` milik `www.kampungsebelah.com`, sebagai nilai atau JSON cookie. Cookie tidak dikirim melalui Telegram/argv/log. Link HTTPS sekali pakai berlaku 15 menit, memakai cookie HttpOnly dengan path akun dan CSRF terikat sesi. Kandidat sesi diverifikasi lewat HTTP MCP lalu dipasang atomik; kegagalan tidak mengganti sesi lama. Nama akun ditampilkan pada form supaya tujuan import jelas.

## Development lokal

Gunakan [panduan Docker lokal dan bot Telegram development](docs/local-development.md) untuk pengujian sebelum deploy. Compose lokal memakai port 6081 dan volume development sendiri.

## Deploy dan upgrade

Prasyarat: Linux amd64/arm64, Docker Engine + Compose, koneksi game/Telegram, domain Cloudflare. Container memakai batas 2 CPU / 2 GiB RAM; angka worker default adalah batas awal konservatif, **belum benchmark kapasitas**.

```sh
git clone git@github.com:superftch/ojol-kampung.git
cd ojol-kampung
cp .env.example .env
chmod 600 .env
mkdir -p .secrets
chmod 700 .secrets
```

Isi `.env` di server; jangan commit:

| Variabel | Nilai |
|---|---|
| `OJOL_ENV` | `production` |
| `OJOL_OPERATOR_AUTHORIZED` | `true` setelah izin operator tersedia |
| `OJOL_CORE` | `http`; nilai lain ditolak |
| `OJOL_TELEGRAM_BOT_TOKEN` | Token BotFather |
| `OJOL_TELEGRAM_CHAT_ID` | Telegram ID **admin**, buka bot dan Start dahulu |
| `OJOL_MAX_ACCOUNTS_PER_USER` | `3` default sebelum override management |
| `OJOL_MAX_ACTIVE_WORKERS` | `3` default sebelum override management |
| `OJOL_LOGIN_PUBLIC_URL` | Origin HTTPS form, misalnya `https://ojolkampung.sftch.web.id` |
| `OJOL_TUNNEL_ENABLED` | `true` untuk connector dalam container |
| `OJOL_MIN_BALANCE` | `20` atau lebih |
| `OJOL_MAX_JOBS`, `OJOL_MAX_MINUTES`, `OJOL_MAX_SPEND` | Kosong untuk tanpa batas |

Simpan token connector pada `.secrets/cloudflared-token`, mode0600. Cloudflared terpasang dalam image dengan versi/digest tetap; tidak perlu container kedua. Di dashboard Cloudflare, Published application route untuk domain harus menuju **HTTP `http://localhost:6080`**. Token dibaca lewat file privat, bukan argv/env. Port aplikasi hanya diterbitkan ke loopback6080; metrics connector loopback2000.

```sh
docker compose build app
docker compose up -d
curl -fsS http://127.0.0.1:6080/health
docker compose logs --tail 50 app
```

Production menolak Telegram kosong, origin tanpa HTTPS, dan saldo minimum di bawah20. Proses berjalan sebagai UID1000. Docker mengelola rotasi log3file×10MiB. Tidak memasang Docker socket atau memberi bot kewenangan membuat container.

Saat upgrade dari versi satu akun, **Utama** milik admin otomatis menunjuk direktori runtime lama. Ledger, cookie HTTP, dan pengaturan tidak dipindah/dihapus. Profil Chrome lama dibiarkan sebagai arsip tetapi tidak dibaca; jika hanya profil Chrome yang tersedia, lakukan **Import Cookie** baru. Hapus variabel lama `OJOL_MANAGED_BROWSER`, `OJOL_CDP_URL`, dan `OJOL_BROWSER_FALLBACK` dari konfigurasi; pastikan `OJOL_CORE=http`.

Setelah mengganti konfigurasi/secret atau image, recreate aplikasi. Gameplay tidak otomatis dimulai setelah restart; pilih akun, periksa Status, lalu Jalankan Ojol. Jika connector keluar, seluruh worker dihentikan dan admin diberi laporan `tunnel.process_exit`; tombol Import Cookie/Jalankan Ojol mencoba memulai connector lagi. `/health` membuktikan control service hidup, bukan keberhasilan game atau koneksi edge. Readiness connector:

```sh
docker compose exec -u app app python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:2000/ready',timeout=3).status)"
```

## Data dan pemulihan

Volume `state`: `runtime/accounts.sqlite3` menyimpan whitelist/kuota/ownership; akun baru berada di `runtime/accounts/<ID>/`; **Utama** memakai `runtime/`. Setiap direktori akun memiliki cookie0600, ledger SQLite WAL, status, lock worker dan outbox notifikasi. Delivery `.sent`/`.muted` kedaluwarsa setelah7hari; event/ledger dan notifikasi pending tetap tersimpan.

Pendapatan berasal dari receipt payout, bukan seluruh kenaikan dompet. Belanja manual di luar worker tidak otomatis menjadi biaya automation. Karakter tidur menghentikan worker sebelum order/belanja; bangunkan lewat game.

Untuk bensin, kondisi motor, dan kuota, worker mengutamakan nama toko yang mengandung **Akademis.ai** tanpa membedakan kapital. Pembelian harus memenuhi target isi ulang, kapasitas, anggaran, dan saldo minimum. Jika tidak ada rencana Akademis.ai yang layak, cadangannya adalah SPBU untuk bensin, bengkel untuk kondisi motor, dan konter untuk kuota. SPBU Akademis.ai juga bisa dipilih untuk kondisi motor jika menjual layanan yang sesuai. Jurnal pembelian mencatat toko dan alasan pemilihan.

CLI lokal server dapat memilih akun dari ID menu Telegram. Hentikan worker akun dahulu sebelum inspect/reconcile. Shell server adalah akses operator tepercaya; gunakan Telegram untuk start dengan pengawasan kuota global.

```sh
docker compose exec -u app app python main.py --account ACCOUNT_ID profit
docker compose exec -u app app python main.py --account ACCOUNT_ID profit --date 2026-01-02
docker compose exec -u app app python main.py --account ACCOUNT_ID history
docker compose exec -u app app python main.py --account ACCOUNT_ID inspect --shop data
docker compose exec -u app app python main.py --account ACCOUNT_ID reconcile
```

Tanpa `--account`, CLI membaca direktori akun lama. `reconcile` hanya membaca game dan menyelesaikan ledger bila bukti cukup; tidak mengirim ulang pembelian/order/klaim. Aksi `pending`/`uncertain` tetap memblokir start baru. Klaim memerlukan receipt/rute/waktu/payout cocok, bukan perubahan history saja. Pencarian lama memakai dua snapshot stabil; state idle dapat ditutup tanpa replay, atau order saat ini diserahkan ke worker berikutnya tanpa mengklaim ongkos saat rekonsiliasi. Saldo naik yang tidak berasal dari payout hanya dicatat sebagai selisih tanpa atribusi. Bila bukti ambigu, tetap STOP; jangan hapus database atau paksa status transaksi.

Backup konsisten seluruh runtime, termasuk registry dan semua akun:

```sh
umask 077
docker compose stop app
docker compose run --rm --no-deps -T --entrypoint tar app -C /data -czf - runtime > state-backup.tar.gz
docker compose start app
```

Arsip memuat sesi akun; simpan privat. Restore saat aplikasi berhenti, pertahankan UID1000, jangan menjalankan akun sama di dua server. `docker compose down` mempertahankan volume; **`down -v` menghapus data**.

## Pengembangan

```sh
uv sync --frozen
uv run ruff check .
uv run ruff format --check .
uv run python scripts/test.py --prepare
uv run python scripts/test.py
docker build --target test -t ojol-kampung:test .
```

`.env.testing` wajib lokal dan diabaikan Git, termasuk dummy. Runner memuatnya eksplisit, membuang override shell, mengisolasi HOME/tmp/cache/SQLite, dan memblokir jaringan; tidak membaca `.env`. Test stage Docker menyiapkan file testing sendiri tanpa secret/volume akun.

[Arsitektur dan keputusan worker](docs/architecture.md) · [Endpoint HTTP](docs/http-endpoints.md) · [Telegram Bot API](https://core.telegram.org/bots/api)
