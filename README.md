# Ojol KampungSebelah

Automation Ojol multi-account dengan **adapter HTTP langsung (tanpa ADK/MCP)** dan **Fully Web Dashboard**. Antarmuka dikendalikan penuh melalui browser di port `6080` (`/` dan `/login`), dengan sistem autentikasi mandiri, feed notifikasi in-app, kontrol worker, serta manajemen user multi-akun.

- Default **3 akun per user**, **3 worker aktif global**; admin dapat mengubahnya melalui panel web tanpa restart.
- **1 akun = 1 subprocess worker** di container `worker` terpisah dari web app. Keduanya berbagi volume state; update app tidak me-restart container worker.
- Tanpa batas trip/durasi default; saldo utama minimal **5 koin**.
- Default `OJOL_AUTO_START=true`: semua akun aktif dengan cookie tersimpan dicoba start pada setiap boot container worker, mengikuti whitelist dan batas worker global.
- Pembacaan HTTP sementara gagal dicoba maksimal 3 kali (backoff 1/2 detik). Transaksi dikirim sekali; hasil ambigu menghentikan akun dan memblokir replay.
- Feed notifikasi dan laporan laba harian WIB terikat ke akun asal langsung di dashboard web.

Gunakan dengan izin operator game. Satu akun game jangan dijalankan bersamaan di server/aplikasi lain. Fingerprint cookie menolak cookie sama pada dua slot akun, termasuk arsip; dua sesi berbeda milik akun game sama belum bisa diidentifikasi tanpa ID pemain stabil dari API.

## Management Web Dashboard

Pengguna pertama yang mendaftar melalui halaman `/register` secara otomatis memperoleh hak akses **Administrator** (`approved` dan `admin`). User pendaftar berikutnya berstatus *pending* dan dapat disetujui atau ditolak oleh admin melalui tab **Admin Panel** di dashboard web.

Semua operasi kontrol akun dan otomasi dilakukan langsung melalui antarmuka web yang responsif:

| Aksi User di Web | Alur Antarmuka |
|---|---|
| Masuk ke dashboard | Buka `/login`, masukkan username & password |
| Daftar akun baru | Buka `/register`, lengkapi form pendaftaran |
| Tambah slot akun game | Tekan tombol **+ Akun** di header dashboard |
| Impor cookie sesi game | Pilih akun → Tab **Dashboard** → **Impor Cookie** |
| Mulai / Hentikan Otomasi | Tombol **Jalankan Ojol** / **Hentikan Ojol** |
| Konfigurasi Fitur Auto | Tab **Auto & Kebutuhan** → Toggle fitur on/off (Makan, SPPG, Fisik, dll.) |
| Pantau Notifikasi & Error | Tab **Notifikasi** → Riwayat pekerjaan, pembelian, dan error ID |
| Laporan & Riwayat | Tab **Akun Saya** / **Dashboard** → Snapshot, saldo, dan log |

| Aksi Admin di Web | Alur Antarmuka |
|---|---|
| Tinjau pendaftaran user | Tab **Admin Panel** → Bagian Pengajuan Tertunda → Tekan **Setujui / Tolak** |
| Kelola user & kuota | Tab **Admin Panel** → Daftar User Terdaftar |
| Batas worker aktif global | Tab **Admin Panel** → Pengaturan Limit Sistem |

Batas valid 1–100. Override management disimpan di `accounts.sqlite3` dan mengalahkan default env setelah restart. Menurunkan batas tidak menghapus akun atau memutus worker yang sudah aktif; batas berlaku pada tambah/pulihkan/start berikutnya. Override user yang sudah dibuat tetap mengalahkan default global. Pencabutan whitelist menghentikan worker user, mencabut tiket/sesi import, dan membatalkan notifikasi pending; data/history tetap disimpan. Aktivasi ulang tidak otomatis menjalankan game.

Contoh jadwal maintenance `2026-11-12 00:30 / 2026-11-12 01:30`. Jadwal berlaku untuk semua akun dan tersimpan setelah restart. Dua menit sebelum mulai, worker menahan aksi baru agar transaksi yang sedang berjalan bisa selesai. Selama jeda, tombol **Jalankan Ojol**, **Import Cookie**, dan **Cari Rumah Kotor** menampilkan waktu selesai. Worker melanjutkan dari status game terbaru setelah waktu selesai, dan antrean auto-start kembali diproses. Admin bisa mengubah jadwal atau memilih **Hapus / Akhiri** jika game dibuka lebih awal.

| Aksi user | Alur tombol |
|---|---|
| Daftar dan pilih akun | **Akun Saya → Pilih nama akun** |
| Tambah akun | **Tambah Akun → formulir impor cookie**; nama otomatis dari nickname game |
| Perbarui nama | **Akun Saya** mengambil ulang profil; worker juga menyinkronkan nickname dari GET game |
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

Tambah Akun langsung menyiapkan link impor cookie, tanpa meminta nama. Slot yang belum selesai diimpor dipakai ulang saat menekan Tambah Akun lagi. Setelah cookie terverifikasi, nama diambil dari `profile.nickname` pada GET profil yang sama dengan pemeriksaan saldo. Akun lama diperbarui dari cache profil worker atau GET ulang saat membuka Akun Saya. Jika game tidak bisa dibaca, nama terakhir terverifikasi dipertahankan. Nama manual tidak lagi ditawarkan; perubahan nickname di game mengikuti profil terbaru yang terverifikasi. Cookie tetap privat dan tidak masuk registry.

Tab **Notifikasi** menampilkan pembelian terverifikasi, hasil trip, maintenance, dan error per akun. Admin dapat membuka feed seluruh akun.

**Status** menampilkan snapshot terbaru yang dibaca worker atau rekonsiliasi, lengkap dengan waktu update WIB. Ringkasan trip dan pendapatan mengikuti penghitung game pada hari snapshot; lima receipt terbaru berasal dari riwayat yang disediakan game. Angka sesi bot ditampilkan terpisah. Menu juga menampilkan rumah/desa, trip dan perkiraan tiba, seluruh kebutuhan, ON/OFF tiap fitur, batas sesi, jadwal maintenance, serta metadata kedaluwarsa cookie bila tersedia. Membuka menu tidak mengirim transaksi ke game atau menampilkan nilai cookie.

Akun baru atau akun yang dipulihkan langsung terpilih. Ganti pilihan tidak menghentikan akun lain. Arsip menghentikan worker dan mencabut akses import, membebaskan kuota akun, tanpa menghapus ledger/cookie. Daftar akun dan user memiliki tombol halaman berikutnya/sebelumnya; tidak perlu menyalin ID akun. Form input yang belum selesai dibatalkan saat bot restart. Konfirmasi arsip/cabut akses yang sudah dibatalkan tidak berlaku lagi.

Pengaturan **Auto** tersimpan per akun dan berlaku pada worker yang sedang berjalan. Default Ojol dan kebutuhan ON; **Auto Perpus (gratis)** dan **Auto Kuliah (bayar)** default OFF, termasuk pada akun lama. **Auto Ojol** satu paket untuk trip, bensin, kondisi mesin, dan kuota. Saat dimatikan, worker menyelesaikan trip yang sedang dipantau dan berhenti mengambil order baru atau mengisi resource Ojol. **Makan**, **Kesehatan**, **Fisik**, **Rekreasi**, **Penampilan**, dan **Kondisi rumah** bisa dimatikan satu per satu. Jika semua fitur OFF, worker menunggu perubahan pengaturan.

Setiap perubahan tombol Auto dikonfirmasi dalam teks pesan dengan nama fitur, ON/OFF, dan dampaknya. Status menampilkan kebutuhan dalam satu baris, misalnya `Makan • OFF • 55%`. Notifikasi pembelian/pemakaian fasilitas terverifikasi memuat kebutuhan sebelum–sesudah, status Auto saat pembaruan, produk/fasilitas, biaya sebenarnya, serta saldo tersisa. Pemulihan transaksi yang terverifikasi mengirim pembaruan yang sama; hasil yang tetap belum pasti tidak disebut berhasil. Notifikasi pembaruan ini mengikuti Notifikasi ON/OFF.

Untuk belajar, buka **Auto → Bidang Perpus / Bidang Kuliah**, pilih bidang masing-masing, lalu aktifkan ON. Memilih bidang tidak otomatis mengaktifkan pembayaran. Setiap akun menyimpan dua pilihan terpisah. Worker belajar saat idle setelah kebutuhan, membaca bacaan kuis selama enam detik, lalu menjawab satu kuis kunjungan dengan opsi dari server dan bank bacaan client. Soal yang tidak dikenali tidak ditebak. Bidang yang sedang dipelajari, sudah maksimum, atau memerlukan kursus lanjutan ditunda. Kuliah mengikuti anggaran sesi dan saldo minimum 20 koin; harga dicek ulang sebelum POST.

Kunjungan belajar mempunyai cooldown lokal minimal satu hari, ditambah `nextAt` server bila lebih lama. Pilihan dan riwayat di ledger bertahan setelah restart; kuis kunjungan yang belum selesai dapat dilanjutkan tanpa membeli sesi baru. Perpus dan kuliah mempunyai kuota terpisah. Setiap POST kunjungan/kuis hanya dicoba sekali; hasil transport yang belum pasti direkonsiliasi. Receipt atau bukti kunjungan dan saldo membuktikan biaya kuliah; biaya yang belum terbukti tidak dibukukan.

**Cari Rumah Mampir** membaca rumah warga di blok rumah akun dan delapan blok tetangga yang tersedia. Rumah sendiri, plot kosong dan rumah yang tidak aktif dikecualikan. Kandidat diacak, lalu harus lolos dua pemeriksaan API: `visitedToday: false` dan akses lihat rumah diterima server saat ini. Rumah tutup atau yang menolak akses tamu dilewati. Jam menerima tamu mengikuti keputusan server untuk rumah tersebut, tanpa mengasumsikan semua rumah buka 06.00–21.00 WIB. Hasil menampilkan nama warga, ID rumah, koordinat, dan status menerima tamu saat diperiksa. Kriteria belum dikunjungi mengikuti hari game, bukan seluruh riwayat akun. Pencarian tidak mengirim kunjungan, tidak memulai worker atau tunnel, dan diblokir saat maintenance. Jika belum selesai dalam 12 detik, bot meminta pencarian diulang tanpa menganggap semua rumah sudah dikunjungi atau tutup.

Import hanya menerima cookie sesi `__Secure-better-auth.session_token` milik `www.kampungsebelah.com`, sebagai nilai atau JSON cookie. Cookie hanya disimpan di runtime akun dan disamarkan di log. Link HTTPS sekali pakai berlaku 15 menit, memakai cookie HttpOnly dengan path akun dan CSRF terikat sesi. Kandidat sesi diverifikasi lewat adapter HTTP lalu dipasang atomik; kegagalan tidak mengganti sesi lama. Nama akun ditampilkan pada form supaya tujuan import jelas.

Jika JSON cookie menyertakan waktu kedaluwarsa, bot memeriksanya sebelum mulai dan sebelum request berikutnya. Nilai cookie tanpa metadata diperiksa lewat respons server. Jika sesi ditolak atau kedaluwarsa, worker berhenti dan dashboard menampilkan petunjuk login ulang dan impor cookie untuk akun yang bermasalah. Login di game, impor cookie baru lewat formulir, lalu tekan **Jalankan Ojol**.

Pengguna masuk dengan username dan password. Akun web pertama menjadi admin pada instalasi kosong. Admin dapat meninjau pendaftaran, mencabut akses, mengatur batas akun, dan menjadwalkan maintenance dari tab **Admin**. Laporan per tanggal dan pencarian rumah tersedia pada akun yang dipilih.

Untuk user lama yang sebelumnya hanya masuk lewat bot, operator server dapat memulihkan password web dengan `python -m ojol.control set-web-password USERNAME`. Perintah meminta password lewat prompt dan mencabut sesi sebelumnya. ID kepemilikan lama tetap dipakai untuk akun yang sudah tertaut ke pengguna web.

### Auto Jaga Usaha

Pilih akun dan buka **Dashboard → Auto Jaga Usaha → Pengaturan jaga**. Tekan **Jalankan** untuk memulai. Hentikan Auto Ojol agar sesi jaga dapat dimulai setelah aktivitas game selesai. Pilih **Terbaik** untuk estimasi tambahan pembeli, **Rotasi** untuk mendahulukan usaha yang sudah lama belum dijaga, atau **Manual** untuk memilih usaha satu per satu setelah daftar terbaca.

Anggaran harian membatasi durasi sesi worker. Target per usaha mengikuti menit yang dilaporkan game. Status menampilkan jumlah usaha yang sudah diperiksa, progres target dari game, dan alasan menunggu. Jika game meminta verifikasi, selesaikan di game sebelum menekan **Hentikan**, lalu **Jalankan** kembali di dashboard. Status penutupan yang belum pasti ditampilkan sampai server mengonfirmasi sesi berakhir. Bukti dan keterbatasan API dicatat di [inventaris HTTP](docs/http-endpoints.md#bukti-jaga-usaha-28-november-2026-update-249).

Membuka dashboard hanya membaca status. Sebelum membuka panel Jaga untuk usaha yang sedang dijaga di game, tekan **Hentikan** dan tunggu sesi berakhir. Browser game dapat ikut mengirim detak, dan menutup panel Jaga dapat mengakhiri sesi worker.

## Development lokal

Gunakan [panduan Docker lokal](docs/local-development.md) untuk pengujian sebelum deploy. Compose lokal memakai port 6081 dan volume development sendiri.

## Deploy dan upgrade

Prasyarat: Linux amd64/arm64, Docker Engine + Compose, `/dev/net/tun`, Cloudflare Zero Trust, koneksi game, dan domain Cloudflare. Production memakai Cloudflare Mesh pada Free plan untuk merutekan egress container melalui Cloudflare. Host dengan sedikitnya 4 vCPU dan 4 GiB RAM direkomendasikan Cloudflare untuk Mesh; container app tetap dibatasi 2 CPU / 2 GiB RAM.

```sh
git clone git@github.com:superftch/ojol-kampung.git
cd ojol-kampung
cp .env.example .env
chmod 600 .env
mkdir -p .secrets
chmod 700 .secrets
```

Di Cloudflare Zero Trust → **Networking → Mesh → Add node**, buat node Docker Compose dan simpan token-nya sebagai `.secrets/cloudflare-mesh-token` dengan mode `0600`. Cloudflare Mesh tersedia di Free plan (beta). Container app berbagi network namespace dengan node WARP; semua egress dari app, termasuk API game dan cloudflared, lewat Cloudflare. Egress default berbagi pool IP Cloudflare; ini **tidak memberi IP publik unik per akun**. [Panduan Mesh Docker](https://developers.cloudflare.com/mesh/guides/run-mesh-in-containers/) · [Free plan](https://developers.cloudflare.com/mesh/platform/).

Isi `.env` di server; jangan commit:

| Variabel | Nilai |
|---|---|
| `OJOL_ENV` | `production` |
| `OJOL_OPERATOR_AUTHORIZED` | `true` setelah izin operator tersedia |
| `OJOL_CORE` | `http`; nilai lain ditolak |
| `OJOL_AUTO_START` | `true` default: start semua akun saat boot; `false`: seluruh start manual |
| `OJOL_MAX_ACCOUNTS_PER_USER` | `3` default sebelum override management |
| `OJOL_MAX_ACTIVE_WORKERS` | `3` default sebelum override management |
| `OJOL_LOGIN_PUBLIC_URL` | Origin HTTPS form, misalnya `https://ojolkampung.sftch.web.id` |
| `OJOL_TUNNEL_ENABLED` | `true` untuk connector dalam container |
| `OJOL_MIN_BALANCE` | `5` atau lebih |
| `OJOL_THRESHOLD` | `60` default target isi ulang |
| `OJOL_SMART_THRESHOLDS` | `true` default: gunakan threshold optimal dinamis per kebutuhan |
| `OJOL_MAX_JOBS`, `OJOL_MAX_MINUTES`, `OJOL_MAX_SPEND` | Kosong untuk tanpa batas |

Simpan token connector pada `.secrets/cloudflared-token`, mode0600. Cloudflared terpasang dalam image dengan versi/digest tetap. Di dashboard Cloudflare, Published application route untuk domain harus menuju **HTTP `http://localhost:6080`**. Token dibaca lewat file privat, bukan argv/env. Port aplikasi diterbitkan lewat node Mesh hanya ke loopback6080; metrics connector loopback2000.

```sh
./deploy.sh app
curl -fsS http://127.0.0.1:6080/health
docker compose logs --tail 50 app
```

`./deploy.sh app` hanya membangun dan mengganti app; container worker dan WARP tidak di-recreate. Untuk menerapkan kode worker, jalankan `./deploy.sh worker`. `./deploy.sh all` memperbarui semua service dan dapat menghentikan worker.

Reset database lokal: `scripts/reset-db.sh --local`. Reset server dari checkout ini: siapkan Docker context yang menunjuk server, lalu jalankan `scripts/reset-db.sh --context <nama-context>`. Skrip meminta konfirmasi, menghapus volume database/state akun, mempertahankan volume identitas WARP, lalu membuat ulang app dan worker.

Production menolak origin tanpa HTTPS dan saldo minimum di bawah 5. Proses berjalan sebagai UID1000. Docker mengelola rotasi log3file×10MiB. Tidak memasang Docker socket atau memberi bot kewenangan membuat container.

Saat upgrade dari versi satu akun, **Utama** milik admin otomatis menunjuk direktori runtime lama. Ledger, cookie HTTP, dan pengaturan tidak dipindah/dihapus. Profil Chrome lama dibiarkan sebagai arsip tetapi tidak dibaca; jika hanya profil Chrome yang tersedia, lakukan **Import Cookie** baru. Hapus variabel lama `OJOL_MANAGED_BROWSER`, `OJOL_CDP_URL`, dan `OJOL_BROWSER_FALLBACK` dari konfigurasi; pastikan `OJOL_CORE=http`.

Setelah mengganti konfigurasi/secret, recreate service yang memakai perubahan tersebut. **`OJOL_AUTO_START=true` menjadi default**, termasuk ketika variabel belum ditulis di `.env`. Setiap boot container worker menyiapkan semua akun nonarsip milik user whitelist yang memiliki cookie tersimpan, termasuk akun yang sebelumnya dihentikan. Update app tidak me-restart worker. Akun menunggu slot jika batas worker global penuh. Status akun menampilkan **Auto-start saat boot: ON/OFF**, ditambah keterangan menunggu slot bila perlu.

Set `OJOL_AUTO_START=false` di `.env` lalu recreate untuk mematikan seluruh auto-start. Hentikan Ojol, Import Cookie, arsip, cabut akses, atau error menghentikan akun dan membatalkan antrean startup **selama aplikasi berjalan**; boot berikutnya dengan env `true` kembali mencoba semua akun yang memenuhi syarat. Akun baru/cookie baru setelah boot tetap dijalankan melalui tombol Jalankan Ojol. Error tidak memicu restart loop dalam sesi aplikasi yang sama.

Startup tetap memeriksa izin operator, whitelist, cookie dan kapasitas. Worker mencocokkan riwayat game dan menyelesaikan ledger pending/uncertain otomatis sebelum membuka sesi baru. Hasil yang belum pasti diperiksa otomatis maksimal 3 kali per proses rekonsiliasi, dengan jeda 10 detik dan tanpa mengirim ulang transaksi. Jika percobaan ketiga belum berhasil, worker dihentikan sebagai gagal dan pemilik akun menerima notifikasi, termasuk saat notifikasi rutin OFF. Hasil transaksi tetap tersimpan sebagai belum pasti, tanpa pembukuan biaya/pendapatan yang belum terbukti. **Setiap boot membuka sesi baru setelah rekonsiliasi:** batas belanja/trip/durasi dari env dihitung ulang per sesi, sedangkan saldo minimum production20 tetap berlaku. Marker `worker-restart.json` dari versi lama tidak lagi dipakai.

Dashboard mencatat startup worker, jeda rekonsiliasi, hasil pemulihan, dan sesi game yang perlu diperbarui di tab **Notifikasi**.

Jika connector keluar, seluruh worker dihentikan dan admin diberi laporan `tunnel.process_exit`; tombol Import Cookie/Jalankan Ojol mencoba memulai connector lagi. `/health` membuktikan control service hidup, bukan keberhasilan game atau koneksi edge. Readiness connector:

```sh
docker compose exec -u app app python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:2000/ready',timeout=3).status)"
```

## Data dan pemulihan

Volume `state`: `runtime/accounts.sqlite3` menyimpan whitelist/kuota/ownership; akun baru berada di `runtime/accounts/<ID>/`; **Utama** memakai `runtime/`. Setiap direktori akun memiliki cookie0600, ledger SQLite WAL, status, lock worker dan outbox notifikasi. Delivery `.sent`/`.muted` kedaluwarsa setelah7hari; event/ledger dan notifikasi pending tetap tersimpan.

Notifikasi error memuat penyebab yang disamarkan, langkah pemulihan, dan ID `OJL-...`. ID yang sama tersedia di log JSON, `last-error.json`, dan feed notifikasi akun.

**Notifikasi OFF hanya mematikan kabar rutin trip dan pembelian.** Maintenance mulai/selesai, aplikasi ditutup/kembali aktif saat startup atau restart Docker, serta karakter tidur/bangun tetap dikirim. Kabar tidur dikirim sekali saat memasuki tidur, bukan pada setiap pemeriksaan berkala. Notifikasi aplikasi kembali aktif menandai proses persiapan; bot baru mengabarkan siap kembali setelah sesi dan status game terverifikasi.

Pendapatan berasal dari receipt payout, bukan seluruh kenaikan dompet. Belanja manual di luar worker tidak otomatis menjadi biaya automation.

Saat status game menunjukkan karakter tidur, seluruh fitur Auto dijeda: tidak ada order, klaim, belanja atau pemakaian fasilitas. Worker hanya membaca status berkala dan tetap bisa dihentikan. Timer durasi sesi, pencarian, perjalanan dan jeda kebutuhan dibekukan selama tidur. Setelah karakter bangun di game, worker melanjutkan dari status terbaru sesuai pengaturan Auto tanpa perlu dijalankan ulang. Aksi yang sudah terkirim sebelum tidur tetap harus terverifikasi sebelum aktivitas berikutnya.

Jam tidur mengikuti pengaturan **per akun** dari game, dalam WIB; **Status** menampilkan ON/OFF serta jam tidur dan bangun yang terbaca. Worker menghitung batas jadwal memakai waktu server, termasuk jadwal melewati tengah malam, lalu membaca ulang status di batas tersebut. Selama tidur, status diperiksa setiap `OJOL_IDLE_POLL_SECONDS` (default 10 detik), atau lebih cepat jika batas jadwal bangun lebih dekat. Tidur manual juga menjeda Auto; bangun manual dihormati meskipun masih dalam rentang jadwal tidur. Lihat [bukti jadwal tidur](docs/http-endpoints.md#bukti-jadwal-tidur).

Untuk resource Ojol, worker memakai daftar toko tetap per desa dan resource di `app/integrations/kampung/shop_locations.py`. Jika beberapa toko Akademis.ai satu tipe punya produk yang layak dibeli, worker memilih toko yang paling lama belum menerima pembelian terverifikasi dari akun tersebut. Riwayat di jurnal mempertahankan giliran setelah restart. Toko lain menjadi cadangan saat pilihan Akademis.ai tidak memenuhi syarat. Jika toko tetap untuk kuota HP atau kondisi kendaraan tidak tersedia, worker memeriksa direktori game untuk mencari konter atau bengkel di desa akun. Worker membaca katalog untuk mengecek harga, stok, dan kepemilikan. Pembelian tetap mengikuti target isi ulang, kapasitas, anggaran, dan saldo minimum.

Jika katalog berhasil dibaca tetapi tidak ada pembelian Ojol yang layak, worker menunda isi ulang selama resource masih di atas `OJOL_RESOURCE_RESERVE_PERCENT` (default 20), lalu memeriksa resource lain dan melanjutkan order. Isi ulang dicoba lagi pada observasi idle berikutnya. Saat resource mencapai atau di bawah batas cadangan dan pembelian tetap tidak tersedia, worker berhenti. Kegagalan HTTP tetap mengikuti penanganan error yang berlaku.

**Auto kebutuhan** berjalan di worker yang sama lewat **Jalankan Ojol**. Saat idle, worker menyelesaikan isi ulang Ojol dulu, lalu mengecek makan, kesehatan, fisik, rekreasi, penampilan, dan kondisi rumah di bawah target threshold. Worker mengutamakan toko Akademis.ai dan memilih biaya terendah per poin manfaat yang masih muat sampai 100 pada seluruh kebutuhan terbaca. Efek makanan mengikuti selera akun dari katalog bila tersedia. Rotasi toko berlaku saat nilai, kecukupan dan biaya setara. Kondisi rumah diisi dengan membeli bahan di toko bangunan; bahan langsung dipakai oleh game. Jika rasio manfaat setara, worker mengutamakan item yang mencapai ambang kebutuhan utama, lalu total belanja lebih kecil. Produk hemat boleh memerlukan beberapa pembelian; setiap pembelian tetap membaca ulang kondisi dan katalog. Worker memilih toko cadangan terdekat secara dinamis jika semua toko Akademis.ai terdaftar untuk kebutuhan itu melaporkan semua item relevan habis atau tidak dapat dijangkau. Worker mengecek lagi sebelum membeli. Untuk fisik, worker memprioritaskan minigame gratis Angkat beban 3x sehari, lalu fallback ke Gym Desa berbayar hanya jika kuota habis dan fisik berada di bawah batas aman. Anggaran dan saldo minimum tetap berlaku. Jika kebutuhan belum bisa diisi, worker mencatat alasan penundaan, lanjut Ojol dan mencoba lagi setelah lima menit.

## Pilihan Produk & Smart Dynamic Thresholds

Bot dilengkapi optimasi seleksi produk dan **Smart Dynamic Thresholds** (`OJOL_SMART_THRESHOLDS=true`) untuk mencegah pemborosan koin dan efek yang terbuang sia-sia akibat overflow kapasitas bar (100). Setiap produk dievaluasi berdasarkan rasio biaya per poin efektif (`cost / points`), prioritas fasilitas gratis/minigame, dan threshold pemicu otomatis yang ideal.

### Batas Threshold Dinamis (`OPTIMAL_THRESHOLDS`)

| Kategori | Threshold Optimal | Alasan & Efisiensi Kapasitas |
|---|---|---|
| **Fisik (`fisik`)** | **45%** | Minigame Angkat beban (3x main $= +45$) langsung menaikkan fisik ke 90%. Jika jatah minigame habis dan fisik $\le 45\%$, fasilitas Gym berbayar ($+55$) mengisi tepat ke 100% tanpa ada poin/koin terbuang (0% overflow) dan tanpa memicu cooldown 12 jam terlalu dini. |
| **Bensin (`fuel`)** | **30%** | Memanfaatkan kapasitas penuh pengisian SPKLU ($+70$) dari $\le 30\%$ langsung ke 100%. |
| **Kondisi (`condition`)** | **40%** | Memanfaatkan kapasitas Servis motor/mobil ($+60$) dari $\le 40\%$ langsung ke 100%. |
| **Data (`data`)** | **40%** | Memanfaatkan Paket data ($+60$) dari $\le 40\%$ langsung ke 100%. |
| **Kebutuhan Lainnya (`makan`, `kesehatan`, `rekreasi`, `penampilan`, `rumah`)** | **50%** | Porsi pemulihan makanan, obat toko, dan layanan fasum rata-rata bernilai $+35$ hingga $+50$. Mengisi di ambang $\le 50\%$ menjaga kebutuhan tetap aman tanpa risiko kelaparan ($< 30\%$) dan tanpa overflow. |

Jika `OJOL_SMART_THRESHOLDS=false`, bot menggunakan nilai global tunggal `OJOL_THRESHOLD` (default 60%). Threshold spesifik juga dapat dioverride manual via JSON `OJOL_NEED_THRESHOLDS='{"fuel": 30, "fisik": 45, ...}'`.

### Inventaris Produk Paling Optimal (Hasil Audit Live 19 Nov 2026)

Setiap produk dievaluasi berdasarkan rasio biaya per poin efektif (`cost / points`), prioritas fasilitas gratis/minigame, serta kemampuan pembelian berulang (*multiple purchase*) tanpa harus terbatas pada 1x transaksi:

| Kategori | Produk Terpilih | Biaya | Efek (Gain) | Efisiensi | Keunggulan & Strategi (*Multiple Purchase*) |
|---|---|---|---|---|---|
| **Kondisi** | **Tambal ban (Bengkel)** | **0.50 koin** | **$+25$ kondisi** | **0.0200 koin/poin** | **JUARA 1 (Paling Murah & Efisien)**. Lebih hemat 20% dibanding Servis motor (0.0250). Beli **3x = 1.50 koin** menghasilkan **$+75$ kondisi** (unggul $+15$ poin dibanding 1x Servis motor yang hanya $+60$ pada harga sama). |
| **Kuota** | **Isi pulsa (Konter)** | **0.50 koin** | **$+40$ kuota** | **0.0125 koin/poin** | **JUARA 1 (Paling Murah & Efisien)**. Lebih hemat 25% dibanding Paket data (0.0167). Beli **2x = 1.00 koin** menghasilkan **$+80$ kuota** (unggul $+20$ poin dibanding 1x Paket data yang hanya $+60$ pada harga sama). |
| **Bensin** | **Isi daya SPKLU (mobil listrik)** | **0.80 koin** | **$+70$ bensin** | **0.0114 koin/poin** | **Paling Murah & Efisien**. Berlaku untuk motor maupun mobil. Lebih hemat 31.7% dibanding Pertalite (1.0 koin / $+60$) dan 24% dibanding Pertamax (1.5 koin / $+100$). |
| **Fisik** | **Angkat beban (Gym desa)** | **Gratis (0 koin)** | $+15$ fisik per game ($+45$ sehari) | $\le 0$ *(Cuan)* | **Prioritas Mutlak #1**. Dijalankan langsung 3x sehari saat idle. Menghasilkan tambahan uang kas desa hingga $+3$ koin sehari. Gym berbayar ($+55$, 1.5 koin) hanya dipakai sebagai emergency fallback jika kuota harian habis dan fisik $\le 45\%$. |
| **Kesehatan** | **Puskesmas / RS (BPJS)** | **Gratis (0 koin)** | $+15$ s/d $+40$ kesehatan | 0.0000 | **Prioritas Mutlak #1**. Memanfaatkan minigame tensi/detak gratis BPJS sebelum apotek berbayar. Fallback: obat apotek (0.8 koin / $+20$, rasio 0.0400). |
| **Makan** | **SPPG (dapur Makan Bergizi Gratis)** / **Mi instan (Sembako)** / **Nasi Goreng / Soto (Restoran)** | **Gratis (0 koin)** (SPPG) / 0.40 koin (sembako) / 1.50 koin (restoran) | $+60$ makan $+5$ kesehatan (SPPG) / $+24$ makan (sembako) / $+63$ makan $+5$ rekreasi (restoran) | **0.0000** (SPPG) / 0.0167 (sembako) / 0.0221 (restoran) | **Prioritas Mutlak #1: SPPG MBG Gratis**. Sekali sehari (cooldown 24 jam) dengan minigame nampan gizi seimbang (+10 makan, +5 kesehatan, bonus upah +3%). **Fallback berbayar**: Mi instan untuk hemat ekstrem atau Nasi goreng/Soto restoran porsi besar, dengan rotasi max 3x streak. |
| **Penampilan** | **Cukur jenggot / Potong rambut** | 0.50 koin (cukur) / 1.00 koin (potong) | $+30$ (cukur) / $+60$ (potong) | 0.0167 koin/poin | Rasio koin per poin terbaik di barbershop Akademis.ai. Beli 2x Cukur jenggot setara 1x Potong rambut. |
| **Kondisi Rumah** | **Pipa paralon (Toko bangunan)** | 0.80 koin | $+20$ kondisi rumah | 0.0400 koin/poin | Bahan perbaikan paling murah per poin pemulihan dibanding Cat tembok (2.0 koin / $+40 = 0.0500$) dan Paku & Semen (1.5 koin / $+25 = 0.0600$). Beli 2x = 1.60 koin $\rightarrow +40$ rumah. |
| **Rekreasi** | **Alun-alun / Taman Desa** / **Main warnet 1 jam (iCafe)** | **Gratis (0 koin)** (Fasum) / 0.50 koin (iCafe) | $+30$ rekreasi $+10$ fisik (Alun-alun) / $+20$ rekreasi (Taman) / $+25$ rekreasi (iCafe) | **0.0000** (Fasum) / 0.0200 (iCafe) | **Prioritas Mutlak #1: Fasum Rekreasi Gratis**. Alun-alun (1x sehari, upah +3%) dan Taman Desa (cooldown 1 jam) dengan minigame foto kenangan (+10 rekreasi). **Fallback berbayar**: Main warnet 1 jam di iCafe (0.5 koin / $+25$) jika seluruh fasum gratis sedang cooldown. |
| **Belajar** | **Perpustakaan Desa (Perpus)** | **Gratis (0 koin)** | Kuis 3/3 benar, XP skill naik | 0.0000 | 100% Gratis. Otomatis mendeteksi dan memblokir bidang belajar yang sudah mencapai level maksimal `(Maks)`. Opsi berbayar: Kuliah (4 koin). |
| **Kebun & Kolam** | **Panen, Rawat, Tanam Sayur** | Modal bibit 0.30 koin | Hasil panen sayur/ikan | Profitabel | Memprioritaskan panen tanaman siap panen $\rightarrow$ rawat/siram $\rightarrow$ tanam bibit sayur termurah. |

> [!NOTE]
> - **Pembelian Berulang (*Multiple Transactions*)**: Seluruh pembelian produk di game dieksekusi per satuan unit transaksi (`/api/shops/{id}/buy`). Worker bot secara otomatis menghitung jumlah unit yang diperlukan (`quantity`) dan melakukan pembelian berulang hingga target terpenuhi tanpa risiko overflow. Produk Ojol (Tambal ban, Isi pulsa, SPKLU) serta kebutuhan umum lainnya bebas dari penalti dan aman dibeli berulang kali secara maksimal.
> - **Prioritas Utama & Minigame Makan Gratis SPPG (MBG)**: Untuk kebutuhan makan (`makan`), bot mengutamakan fasilitas umum **SPPG (dapur Makan Bergizi Gratis)** sebagai **prioritas mutlak #1**. Program ini 100% **gratis (0 koin)** dengan cooldown **1x sehari (24 jam)** pada jam operasional 06:00–14:00. Bot otomatis memainkan minigame **Isi nampan gizi (`nampan`)** dengan menyusun 5 kelompok gizi lengkap (makanan pokok, lauk, sayur, buah, susu) tanpa junk food untuk memperoleh poin sempurna (+60 makan, +5 kesehatan, bonus minigame +10 makan, +5 kesehatan, dan upah kerja +3% selama 24 jam).
> - **Prioritas Utama & Minigame Rekreasi Fasum Gratis (Alun-alun & Taman Desa)**: Untuk kebutuhan rekreasi (`rekreasi`), bot mengutamakan fasum gratis di desa (**Alun-alun** dan **Taman Desa**) sebagai **prioritas mutlak #1**. Alun-alun (cooldown 24 jam, bonus upah +3%, $+30$ rekreasi, $+10$ fisik) dan Taman Desa (cooldown hanya 1 jam, $+20$ rekreasi) dilengkapi minigame **Ambil foto (`foto`)**. Bot otomatis menyimulasikan jepretan kamera tepat di tengah bingkai ($p = 0.50$, sempurna 100%) untuk menghasilkan kartu foto kenangan dan bonus tambahan **$+10$ rekreasi**. Jika fasum gratis sedang cooldown, bot otomatis fallback ke warnet iCafe berbayar (0.5 koin / $+25$).
> - **Aturan Rotasi Cerdas Makanan Berbayar (Max 3x Beli)**: Saat jatah harian SPPG sedang cooldown, bot beralih ke toko makanan berbayar (warung/sembako/restoran). Game menerapkan mekanik kebosanan rasa (*diminishing returns*) jika mengonsumsi menu berbayar yang sama lebih dari 3 kali berturut-turut. Planner bot secara otomatis melacak streak pembelian di database dan status `rasa.bosan`. Setelah maksimal 3 kali pembelian menu yang sama, bot otomatis **merotasi** ke menu makanan alternatif berikutnya yang paling *worth it* (misal: Mi instan $\rightarrow$ Nasi goreng / Soto $\rightarrow$ Nasi pecel). Langkah ini mereset streak kebosanan sehingga efek pemulihan makanan selalu optimal 100%.

### Manajemen Saldo Minimum Bertingkat (Tiered Balance Management)

Konfigurasi `OJOL_MIN_BALANCE=5` (default 5 koin) menerapkan mekanisme proteksi modal darurat bertingkat:

1. **Zona Darurat Ojol & Bertahan Hidup ($5 \le \text{Saldo} < 20$ koin)**:
   - **Prioritas Utama**: Seluruh saldo dialokasikan khusus untuk kelancaran kerja Ojol dan bertahan hidup.
   - **Aktivitas yang Diizinkan**:
     - **Paket Darurat Ojol**: Isi daya SPKLU (0.8 koin), Tambal ban (0.5 koin), dan Isi pulsa (0.5 koin).
     - **Kebutuhan Primer**: Makan nasi bungkus / mi instan / warung (0.4 - 0.7 koin).
     - **Fasilitas & Minigame Gratis**: Angkat beban gym desa (0 koin), Puskesmas / RS BPJS gratis (0 koin), Perpustakaan belajar gratis (0 koin).
   - **Aktivitas yang Ditunda (Hold)**: Belanja kebutuhan sekunder/tersier berbayar (potong rambut/salon penampilan, bioskop/warnet rekreasi, material bangunan rumah, gym berbayar, obat apotek berbayar, kuliah berbayar, dan tanam bibit kebun) otomatis **DITUNDA** agar modal kerja Ojol tidak terkuras.

2. **Zona Bebas ($\text{Saldo} \ge 20$ koin)**:
   - Seluruh kebutuhan sekunder (rekreasi, salon penampilan, renovasi rumah), kuliah berbayar, dan tanam bibit kebun **BEBAS DIJALANKAN**, selama sisa saldo setelah pembelian tidak menggerus batas cadangan darurat Ojol ($\ge 20$ koin) dan batas absolut saldo ($\ge 5$ koin).

3. **Lantai Saldo Absolut ($< 5$ koin)**:
   - Seluruh transaksi berbayar diblokir untuk melindungi akun dari risiko kehabisan uang total (*insolvency*).



Gunakan `list-accounts` untuk melihat nama dan ID akun yang belum diarsipkan. Salin ID ke `--account` untuk memilih akun di CLI. Hentikan worker akun dahulu sebelum inspect/reconcile. Shell server adalah akses operator tepercaya; mulai worker dari dashboard supaya batas worker global diterapkan.

Penolakan lock atau kegagalan perintah CLI di luar sesi `run --live` tidak memasang `STOP`. Notifikasi tetap memuat ID error dan akun dari `--account`; konteks aksi hanya diambil dari status milik proses CLI yang sama, agar tidak mengaitkan error inspeksi ke transaksi worker lain.

```sh
docker compose exec -u app app python main.py list-accounts
docker compose exec -u app app python main.py --account ACCOUNT_ID profit
docker compose exec -u app app python main.py --account ACCOUNT_ID profit --date 2026-01-02
docker compose exec -u app app python main.py --account ACCOUNT_ID history
docker compose exec -u app app python main.py --account ACCOUNT_ID inspect --shop data
docker compose exec -u app app python main.py --account ACCOUNT_ID reconcile
docker compose exec -u app app python main.py --account ACCOUNT_ID reconcile --error-id OJL-012345ABCDEF
docker compose exec -u app app python main.py --account ACCOUNT_ID reconcile --action-id 3095
docker compose exec -u app app python main.py --account ACCOUNT_ID reconcile --action-id 3095 --skip
```

Tanpa `--account`, CLI membaca direktori akun lama. `reconcile` melakukan satu pemeriksaan read-only; menjalankannya manual bersifat opsional. Worker otomatis menjalankan pemeriksaan yang sama sebelum start dan setelah timeout verifikasi atau gangguan transport pada aksi Ojol maupun pembelian isi ulang/kebutuhan. Pembelian tidak dikirim ulang selama hasil belum pasti. Ledger belum pasti menahan transaksi baru. Bot memeriksa maksimal 3 kali per proses rekonsiliasi dengan jeda 10 detik; pembacaan gagal karena transport juga dihitung sebagai satu percobaan. Kegagalan ketiga menghentikan worker dan memberi notifikasi gagal, tanpa menganggap transaksi game pasti batal. Tombol Hentikan Ojol tetap dapat memutus penantian; sesi kedaluwarsa langsung meminta Import Cookie. Perintah reconcile manual tetap tersedia untuk memeriksa bukti berikutnya.

`reconcile --error-id OJL-...` memeriksa aksi ledger yang dirujuk catatan error pada akun pilihan. Output memuat ID aksi/run, jenis dan payload aksi, status sebelum/sesudah, alasan dan bukti, saldo/resource sebelum/sesudah beserta selisihnya, serta pembukuan terkait dan yang baru ditambahkan. Error tanpa referensi aksi menampilkan penjelasan. Aksi yang sudah selesai menampilkan catatan tersimpan. Total aksi belum pasti tetap dilaporkan untuk seluruh akun. Pembacaan game memakai GET; hasil verifikasi memperbarui ledger lokal.

Angka `#3095` di log adalah ID aksi ledger. Gunakan `--action-id 3095` untuk memeriksa satu aksi langsung; pilih salah satu `--action-id` atau `--error-id`. Log menyertakan akun, nama aksi/produk/toko, perubahan status, dan alasan. Selama menunggu otomatis, Status menampilkan aksi tertahan, waktu aksi, alasan, dan saldo sebelum/sesudah. Detail pemeriksaan terbaru tersimpan di `game-sync.json`.

Untuk melewati hasil aksi lama atas keputusan operator, hentikan worker akun dan tunggu berhenti, lalu gunakan `reconcile --action-id 3095 --skip`. Opsi ini hanya mengubah aksi `pending`/`uncertain` yang dipilih menjadi `skipped` dan mencatat audit `aksi_dilewati_operator`, tanpa request ke game. Bukti asli dipertahankan, hasil transaksi lama tetap belum terverifikasi, serta payout/biaya tidak ditambahkan ke ledger. Menjalankan skip lagi untuk aksi yang sama aman. Opsi ini memerlukan `--action-id`. Setelah selesai, tekan Jalankan Ojol; worker mengikuti kondisi game terbaru, termasuk klaim bila trip masih siap menerima ongkos.

Pembelian dan penerimaan order yang melewati jendela verifikasi lima menit dapat berstatus `handed_off` setelah dua snapshot baru berurutan membuktikan kondisi game stabil. Fase mencari atau tidak dikenal tetap menunggu. Countdown perjalanan harus berkurang, sedangkan saldo, resource, kebutuhan, trip, dan riwayat tetap sama di antara kedua snapshot. Bot melanjutkan dari kondisi terbaru dan menyimpan hasil aksi lama sebagai belum pasti, tanpa menambahkan biaya/pendapatan untuk aksi tersebut. Harga pembelian yang masuk pemulihan dalam sesi berjalan tetap dicadangkan terhadap batas belanja sesi, termasuk bila hasilnya `handed_off`. Laporan laba ledger dapat kehilangan biaya pembelian lama yang hasilnya belum terbukti.

Error baru disimpan privat per ID di `errors/`. ID lama bisa dibaca selama masih tersedia di `last-error.json` atau antrean/arsip notifikasi akun. Arsip notifikasi terkirim kedaluwarsa setelah tujuh hari. ID yang sudah hilang perlu ditelusuri dari log operator. Catatan lama tanpa referensi aksi memerlukan pemeriksaan `history` dan `reconcile` seluruh akun.

Receipt yang ID trip dan waktunya cocok membuktikan klaim; jurnal lama tanpa ID memakai bukti rute/waktu/payout. Dua snapshot baru yang konsisten dan menunjukkan tidak ada order aktif dapat menutup pencarian lama sebagai `closed_idle`, meski saldo, resource, atau riwayat berubah sejak aksi. Hasil asli tetap dicatat sebagai belum pasti dan selisih saldo tidak masuk pembukuan bot. Untuk melanjutkan order aktif dari pencarian yang belum pasti, saldo dan riwayat harus tetap cocok dengan snapshot sebelum pencarian. Status `handed_off` mempertahankan hasil lama sebagai belum pasti tanpa membukukan pendapatan. Rekonsiliasi otomatis tidak mengklaim ulang trip lama yang masih sama; operator dapat melewati aksi lama memakai `--skip`. Riwayat game disimpan di `game-sync.json` terpisah dari ledger: sinkronisasi tidak mengarang pendapatan bot atau menggandakan payout. Cakupannya mengikuti riwayat yang dikembalikan API, bukan seluruh riwayat sepanjang masa. Pertahankan database dan gunakan perintah operator yang mencatat audit untuk melewati aksi.

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
uv run python scripts/test.py           # Cakupan fitur web cepat (~3.5 detik, 264 pengujian)
uv run python scripts/test.py --all     # Seluruh test suite (771 pengujian)
docker build --target test -t ojol-kampung:test .
```

`.env.testing` wajib lokal dan diabaikan Git, termasuk dummy. Runner memuatnya eksplisit, membuang override shell, mengisolasi HOME/tmp/cache/SQLite, dan memblokir jaringan; tidak membaca `.env`. Test stage Docker menyiapkan file testing sendiri tanpa secret/volume akun.

[Arsitektur dan keputusan worker](docs/architecture.md) · [Endpoint HTTP](docs/http-endpoints.md)
