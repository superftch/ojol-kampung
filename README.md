# Ojol KampungSebelah

Automation Ojol multi-account dengan **HTTP MCP + Google ADK**. Satu bot Telegram melayani beberapa user dalam whitelist; setiap user bisa memiliki beberapa akun game. `OJOL_TELEGRAM_CHAT_ID` menjadi admin. Chrome, Browser Harness, fallback browser, dan migrasi profil browser dihapus.

- Default **3 akun per user**, **3 worker aktif global**; admin dapat mengubahnya tanpa restart.
- **1 akun = 1 subprocess worker**, dengan MCP, cookie, SQLite ledger, status dan pengaturan notifikasi sendiri. Semua berjalan dalam satu container aplikasi.
- Tanpa batas trip/durasi default; saldo utama production minimal **20 koin**.
- Default `OJOL_AUTO_START=true`: semua akun aktif dengan cookie tersimpan dicoba start pada setiap boot/deploy, mengikuti whitelist dan batas worker global.
- Pembacaan HTTP sementara gagal dicoba maksimal 3 kali (backoff 1/2 detik). Transaksi dikirim sekali; hasil ambigu menghentikan akun dan memblokir replay.
- Laporan laba harian WIB dan tombol navigasi tanggal terikat ke akun asal. Notifikasi diberi nama akun dan hanya dikirim ke pemiliknya.

Gunakan dengan izin operator game. Satu akun game jangan dijalankan bersamaan di server/aplikasi lain. Fingerprint cookie menolak cookie sama pada dua slot akun, termasuk arsip; dua sesi berbeda milik akun game sama belum bisa diidentifikasi tanpa ID pemain stabil dari API.

## Management Telegram

Admin pertama adalah ID pribadi dalam `OJOL_TELEGRAM_CHAT_ID`; ID ini selalu boleh masuk dan tidak bisa dicabut lewat bot. User lain belum bisa memakai fitur akun sampai admin menyetujui pengajuan atau menambahkan ID numeriknya. Kontrol hanya menerima private chat dengan `chat.id == from.id`; grup dan callback milik user lain ditolak.

Saat user ditambahkan atau diaktifkan ulang, bot mengirim menu utama ke chat pribadi user. Jika user belum pernah membuka bot, minta user menekan **Start** dahulu; [Telegram melarang bot memulai percakapan pribadi](https://core.telegram.org/bots#how-are-bots-different-from-users). Jika tombol belum terlihat, admin bisa memilih **Kirim Menu**, atau user mengirim pesan **menu** ke bot. Setelah menu muncul: **Tambah Akun → ketik nama → Import Cookie**.

User belum terdaftar bisa menekan **Start** atau mengirim **`/start` → Ajukan Akses**. Bot menyimpan **nama dari profil Telegram, username (jika ada), dan Telegram ID** pemohon, lalu mengirim notifikasi ke admin dengan tombol **Setujui / Tolak**. Daftar persisten tersedia lewat **Management → Pengajuan Akses**, termasuk setelah bot restart. Pengajuan berulang saat menunggu tidak menambah notifikasi admin. Persetujuan memasukkan user ke whitelist dan mengirim menu utama; penolakan tetap menutup akses, dan aktivasi ulang harus dilakukan admin melalui Daftar User. Pengajuan tidak otomatis membuat akun game atau menjalankan worker.

Semua operasi bot memakai tombol. Ketik hanya nilai yang diminta: ID Telegram, nama akun, batas angka, atau tanggal. Tidak perlu mengetik perintah. Tombol **Batal** selalu bisa membatalkan input; **Menu Utama** mengembalikan tombol utama.

| Aksi admin | Alur tombol |
|---|---|
| Tinjau pengajuan beserta nama pemohon | **Management → Pengajuan Akses → pilih pemohon → Setujui / Tolak** |
| Lihat whitelist, kuota dan worker aktif | **Management → Daftar User** |
| Tambah user | **Management → Tambah User**, lalu ketik ID Telegram |
| Aktifkan ulang user | **Daftar User → pilih user → Aktifkan Akses** |
| Kirim ulang tombol utama user | **Daftar User → pilih user → Kirim Menu** |
| Cabut akses dan hentikan seluruh akun user | **Daftar User → pilih user → Cabut Akses → Ya, Cabut Akses** |
| Default akun per user | **Management → Batas Akun Default**, lalu ketik angka |
| Override akun user tertentu | **Daftar User → pilih user → Ubah Batas Akun**, lalu ketik angka |
| Batas worker aktif global | **Management → Batas Worker**, lalu ketik angka |
| Jadwal maintenance game | **Management → Maintenance → Atur Jadwal**, lalu ketik waktu mulai dan selesai (WIB) |

Batas valid 1–100. Override management disimpan di `accounts.sqlite3` dan mengalahkan default env setelah restart. Menurunkan batas tidak menghapus akun atau memutus worker yang sudah aktif; batas berlaku pada tambah/pulihkan/start berikutnya. Override user yang sudah dibuat tetap mengalahkan default global. Pencabutan whitelist menghentikan worker user, mencabut tiket/sesi import, dan membatalkan notifikasi pending; data/history tetap disimpan. Aktivasi ulang tidak otomatis menjalankan game.

Contoh jadwal maintenance `2026-11-12 00:30 / 2026-11-12 01:30`. Jadwal berlaku untuk semua akun dan tersimpan setelah restart. Dua menit sebelum mulai, worker menahan aksi baru agar transaksi yang sedang berjalan bisa selesai. Selama jeda, tombol **Jalankan Ojol**, **Import Cookie**, dan **Cari Rumah Kotor** menampilkan waktu selesai. Worker melanjutkan dari status game terbaru setelah waktu selesai, dan antrean auto-start kembali diproses. Admin bisa mengubah jadwal atau memilih **Hapus / Akhiri** jika game dibuka lebih awal.

| Aksi user | Alur tombol |
|---|---|
| Daftar dan pilih akun | **Akun Saya → Pilih nama akun** |
| Tambah akun | **Tambah Akun**, lalu ketik nama |
| Ubah nama | **Akun Saya → Pilih akun → Ubah Nama**, lalu ketik nama baru |
| Arsipkan akun | **Akun Saya → Pilih akun → Arsipkan Akun → Ya, Arsipkan** |
| Pulihkan arsip | **Akun Saya → Pulihkan nama akun** |
| Login akun terpilih | **Import Cookie** |
| Mulai/hentikan akun terpilih | **Jalankan Ojol** / **Hentikan Ojol** |
| Pilih fitur yang dijalankan worker | **Auto**, lalu tekan tombol fitur untuk ubah ON/OFF |
| Resource, kebutuhan, saldo, countdown, riwayat game, sesi dan pengaturan Auto | **Status** |
| Laporan harian WIB | **Laba Bersih**, tombol hari atau **Pilih tanggal**, lalu ketik tanggal |
| Pilih satu kandidat rumah kotor secara acak di sekitar rumah akun | **Cari Rumah Kotor** |
| Cari satu rumah yang menerima tamu sekarang dan belum dikunjungi hari ini | **Cari Rumah Mampir** |
| Event rutin | **Notifikasi ON / OFF** |

Pesan Telegram memakai judul singkat, baris terpisah untuk angka penting, dan petunjuk tindakan berikutnya. Notifikasi ON mengirim hasil trip, pembelian yang sudah terverifikasi, serta jeda maintenance. Bot tetap mengirim pesan jika perlu tindakan saat notifikasi rutin OFF. Antrean lama juga disesuaikan saat dikirim ulang. Rujukan penulisan memakai [Telegram Bot Guidelines](https://core.telegram.org/bots/guidelines) dan [Material Communication Principles](https://codelabs.developers.google.com/codelabs/material-communication-guidance).

**Status** menampilkan snapshot terbaru yang dibaca worker atau rekonsiliasi, lengkap dengan waktu update WIB. Ringkasan trip dan pendapatan mengikuti penghitung game pada hari snapshot; lima receipt terbaru berasal dari riwayat yang disediakan game. Angka sesi bot ditampilkan terpisah. Menu juga menampilkan rumah/desa, trip dan perkiraan tiba, seluruh kebutuhan, ON/OFF tiap fitur, batas sesi, jadwal maintenance, serta metadata kedaluwarsa cookie bila tersedia. Membuka menu tidak mengirim transaksi ke game atau menampilkan nilai cookie.

Akun baru atau akun yang dipulihkan langsung terpilih. Ganti pilihan tidak menghentikan akun lain. Arsip menghentikan worker dan mencabut akses import, membebaskan kuota akun, tanpa menghapus ledger/cookie. Daftar akun dan user memiliki tombol halaman berikutnya/sebelumnya; tidak perlu menyalin ID akun. Form input yang belum selesai dibatalkan saat bot restart. Konfirmasi arsip/cabut akses yang sudah dibatalkan tidak berlaku lagi.

Pengaturan **Auto** tersimpan per akun dan berlaku pada worker yang sedang berjalan. Default seluruh fitur ON. **Auto Ojol** satu paket untuk trip, bensin, kondisi mesin, dan kuota. Saat dimatikan, worker menyelesaikan trip yang sedang dipantau dan berhenti mengambil order baru atau mengisi resource Ojol. **Makan**, **Kesehatan**, **Fisik**, **Rekreasi**, **Penampilan**, dan **Kondisi rumah** bisa dimatikan satu per satu. Jika semua fitur OFF, worker menunggu perubahan pengaturan.

**Cari Rumah Mampir** membaca rumah warga di blok rumah akun dan delapan blok tetangga yang tersedia. Rumah sendiri, plot kosong dan rumah yang tidak aktif dikecualikan. Kandidat diacak, lalu harus lolos dua pemeriksaan API: `visitedToday: false` dan akses lihat rumah diterima server saat ini. Rumah tutup atau yang menolak akses tamu dilewati. Jam menerima tamu mengikuti keputusan server untuk rumah tersebut, tanpa mengasumsikan semua rumah buka 06.00–21.00 WIB. Hasil menampilkan nama warga, ID rumah, koordinat, dan status menerima tamu saat diperiksa. Kriteria belum dikunjungi mengikuti hari game, bukan seluruh riwayat akun. Pencarian tidak mengirim kunjungan, tidak memulai worker atau tunnel, dan diblokir saat maintenance. Jika belum selesai dalam 12 detik, bot meminta pencarian diulang tanpa menganggap semua rumah sudah dikunjungi atau tutup.

Import hanya menerima cookie sesi `__Secure-better-auth.session_token` milik `www.kampungsebelah.com`, sebagai nilai atau JSON cookie. Cookie tidak dikirim melalui Telegram/argv/log. Link HTTPS sekali pakai berlaku 15 menit, memakai cookie HttpOnly dengan path akun dan CSRF terikat sesi. Kandidat sesi diverifikasi lewat HTTP MCP lalu dipasang atomik; kegagalan tidak mengganti sesi lama. Nama akun ditampilkan pada form supaya tujuan import jelas.

Jika JSON cookie menyertakan waktu kedaluwarsa, bot memeriksanya sebelum mulai dan sebelum request berikutnya. Nilai cookie tanpa metadata diperiksa lewat respons server. Jika sesi ditolak atau kedaluwarsa, akun berhenti dan Telegram meminta login ulang, dengan tombol **Login ulang ke game** dan **Import Cookie** untuk akun yang bermasalah. Login di game, impor cookie baru lewat formulir, lalu tekan **Jalankan Ojol**.

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
| `OJOL_AUTO_START` | `true` default: start semua akun saat boot; `false`: seluruh start manual |
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

Setelah mengganti konfigurasi/secret atau image, recreate aplikasi. **`OJOL_AUTO_START=true` menjadi default**, termasuk ketika variabel belum ditulis di `.env`. Setiap boot/deploy menyiapkan semua akun nonarsip milik user whitelist yang memiliki cookie tersimpan, termasuk akun yang sebelumnya dihentikan. Tidak perlu menekan Jalankan dulu pada update pertama. Akun menunggu slot jika batas worker global penuh. Status akun menampilkan **Auto-start saat boot: ON/OFF**, ditambah keterangan menunggu slot bila perlu.

Set `OJOL_AUTO_START=false` di `.env` lalu recreate untuk mematikan seluruh auto-start. Hentikan Ojol, Import Cookie, arsip, cabut akses, atau error menghentikan akun dan membatalkan antrean startup **selama aplikasi berjalan**; boot berikutnya dengan env `true` kembali mencoba semua akun yang memenuhi syarat. Akun baru/cookie baru setelah boot tetap dijalankan melalui tombol Jalankan Ojol. Error tidak memicu restart loop dalam sesi aplikasi yang sama.

Startup tetap memeriksa izin operator, whitelist, cookie dan kapasitas. Worker mencocokkan riwayat game dan menyelesaikan ledger pending/uncertain otomatis sebelum membuka sesi baru. Hasil yang belum pasti diperiksa ulang setiap 10 detik tanpa meminta admin dan tanpa mengirim ulang transaksi. **Setiap boot membuka sesi baru setelah rekonsiliasi:** batas belanja/trip/durasi dari env dihitung ulang per sesi, sedangkan saldo minimum production20 tetap berlaku. Marker `worker-restart.json` dari versi lama tidak lagi dipakai.

Telegram memberi tahu pemilik akun saat worker aktif dihentikan oleh shutdown normal, termasuk saat rebuild. Jika pengiriman tertunda, antrean lokal dilanjutkan setelah boot. Notifikasi auto-start berhasil dikirim setelah worker membaca status game dan bisa lanjut. Bot memberi kabar saat perlu menunggu rekonsiliasi dan saat sudah bisa melanjutkan. Jika perlu tindakan karena sesi habis atau bot dihentikan, pesan menyebut **Import Cookie** atau **Jalankan Ojol**. Notifikasi ini tetap aktif saat notifikasi rutin OFF.

Jika connector keluar, seluruh worker dihentikan dan admin diberi laporan `tunnel.process_exit`; tombol Import Cookie/Jalankan Ojol mencoba memulai connector lagi. `/health` membuktikan control service hidup, bukan keberhasilan game atau koneksi edge. Readiness connector:

```sh
docker compose exec -u app app python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:2000/ready',timeout=3).status)"
```

## Data dan pemulihan

Volume `state`: `runtime/accounts.sqlite3` menyimpan whitelist/kuota/ownership; akun baru berada di `runtime/accounts/<ID>/`; **Utama** memakai `runtime/`. Setiap direktori akun memiliki cookie0600, ledger SQLite WAL, status, lock worker dan outbox notifikasi. Delivery `.sent`/`.muted` kedaluwarsa setelah7hari; event/ledger dan notifikasi pending tetap tersimpan.

Pendapatan berasal dari receipt payout, bukan seluruh kenaikan dompet. Belanja manual di luar worker tidak otomatis menjadi biaya automation. Karakter tidur menghentikan worker sebelum order/belanja; bangunkan lewat game.

Worker memakai daftar toko tetap per desa dan resource di `ojol/shop_locations.py`. Jika beberapa toko Akademis.ai satu tipe punya produk yang layak dibeli, worker memilih toko yang paling lama belum menerima pembelian terverifikasi dari akun tersebut. Riwayat di jurnal mempertahankan giliran setelah restart. Toko lain menjadi cadangan saat pilihan Akademis.ai tidak memenuhi syarat. Worker membaca katalog untuk mengecek harga, stok, dan kepemilikan. Pembelian tetap mengikuti target isi ulang, kapasitas, anggaran, dan saldo minimum.

**Auto kebutuhan** berjalan di worker yang sama lewat **Jalankan Ojol**. Saat idle, worker menyelesaikan isi ulang Ojol dulu, lalu mengecek makan, kesehatan, fisik, rekreasi, penampilan, dan kondisi rumah di bawah `OJOL_THRESHOLD` (default 60). Untuk setiap kebutuhan, giliran jatuh ke toko Akademis.ai yang paling lama belum menerima pembelian terverifikasi dari akun itu, selama ada item dalam anggaran. Di toko tersebut, worker mengutamakan item yang mencapai ambang kebutuhan utama, membantu lebih banyak kebutuhan sekaligus, dan memberi manfaat sepadan dengan harga. Worker memilih toko cadangan hanya jika semua toko Akademis.ai terdaftar untuk kebutuhan itu melaporkan semua item relevan habis. Worker mengecek lagi sebelum membeli. Toko tutup, katalog kosong, atau pembacaan gagal membuat status stok belum pasti. Untuk fisik, worker memakai fasilitas gratis yang ditawarkan game dan siap dipakai. Jika kebutuhan belum bisa diisi, worker lanjut Ojol dan mencoba lagi setelah lima menit.

CLI lokal server dapat memilih akun dari ID menu Telegram. Hentikan worker akun dahulu sebelum inspect/reconcile. Shell server adalah akses operator tepercaya; gunakan Telegram untuk start dengan pengawasan kuota global.

```sh
docker compose exec -u app app python main.py --account ACCOUNT_ID profit
docker compose exec -u app app python main.py --account ACCOUNT_ID profit --date 2026-01-02
docker compose exec -u app app python main.py --account ACCOUNT_ID history
docker compose exec -u app app python main.py --account ACCOUNT_ID inspect --shop data
docker compose exec -u app app python main.py --account ACCOUNT_ID reconcile
```

Tanpa `--account`, CLI membaca direktori akun lama. `reconcile` melakukan satu pemeriksaan read-only; menjalankannya manual bersifat opsional. Worker otomatis menjalankan pemeriksaan yang sama sebelum start dan setelah timeout aksi Ojol. Ledger belum pasti menahan transaksi baru, bukan menghentikan pemeriksaan: bot menunggu dan membaca ulang setiap 10 detik, tetap bisa dihentikan lewat tombol Hentikan Ojol. Gangguan transport saat rekonsiliasi dicoba ulang; sesi kedaluwarsa tetap meminta Import Cookie.

Receipt yang ID trip dan waktunya cocok membuktikan klaim; jurnal lama tanpa ID memakai bukti rute/waktu/payout. Dua snapshot konsisten dapat menyerahkan pencarian atau klaim lama ke status game sekarang jika trip lama sudah tidak aktif. Status `handed_off` mempertahankan hasil lama sebagai belum pasti tanpa membukukan pendapatan. Trip lama yang masih sama tidak diklaim ulang. Riwayat game disimpan di `game-sync.json` terpisah dari ledger: sinkronisasi tidak mengarang pendapatan bot atau menggandakan payout. Cakupannya mengikuti riwayat yang dikembalikan API, bukan seluruh riwayat sepanjang masa. Jangan hapus database atau paksa status transaksi.

Backup konsisten seluruh runtime, termasuk registry dan semua akun:

```sh
umask 077
docker compose stop app
docker compose run --rm --no-deps -T --entrypoint tar app -C /data -czf - runtime > state-backup.tar.gz
docker compose start app
```

Arsip memuat sesi akun; simpan privat. Dengan env auto-start aktif, akun hasil restore juga dicoba saat boot. Restore saat aplikasi berhenti, pertahankan UID1000, dan hentikan server asal sebelum menjalankan hasil restore/migrasi supaya akun tidak berjalan di dua server. `docker compose down` mempertahankan volume; **`down -v` menghapus data**.

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
