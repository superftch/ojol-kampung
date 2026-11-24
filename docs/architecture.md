# Arsitektur HTTP multi-account

Keputusan 23 November 2026 WIB: **control service web dan pengelola subprocess akun berjalan di container `app`; daemon worker akun berjalan di container `worker` terpisah; keduanya berbagi volume state dan berkomunikasi lewat Unix socket**. Keduanya memakai network namespace Cloudflare Mesh/WARP. Update app tidak me-recreate worker atau WARP; update WARP/full deploy tetap dapat memutus worker. Semua akun memakai egress bersama, bukan IP publik unik per akun. Chrome/Browser Harness dan seluruh fallback dihapus. Error HTTP terminal menghentikan akun; tidak pindah backend.

## Alur

Browser memakai dashboard FastAPI dan sesi HttpOnly untuk login, memilih akun, serta mengatur worker. Router akun dan kontrol memeriksa kepemilikan. Tindakan administrator memerlukan peran admin. Pendaftaran pertama pada database kosong menjadi admin dan pendaftaran berikutnya menunggu persetujuan.

`accounts.sqlite3` menyimpan kredensial web ter-hash, sesi, akun game, pemilik, pilihan akun, kuota, dan pengaturan server. Kolom kepemilikan lama dipertahankan agar akun, riwayat, dan sesi yang sudah tersimpan tetap dapat dipetakan. Pencabutan akses membatalkan sesi web dan tiket impor, lalu menghentikan worker milik pengguna terkait.

Dashboard membaca ringkasan dan ledger SQLite melalui koneksi read-only. Backfill ledger lama berjalan saat startup. Log akun masuk ke feed notifikasi, dengan akses seluruh akun di tab Admin.

## Proses akun dan container worker

[Python asyncio menyediakan proses asynchronous](https://docs.python.org/3.12/library/asyncio-subprocess.html) yang dapat dipantau bersamaan. Proyek memakai container worker khusus untuk menjaga subprocess akun tetap hidup saat container app diperbarui; satu akun tetap satu subprocess dengan journal per direktori.

[Docker memakai namespaces untuk isolasi proses/network dan cgroups untuk resource](https://docs.docker.com/engine/security/). Container per akun berguna jika membutuhkan batas CPU/RAM dan isolasi OS per user. Saat ini setiap worker menjalankan kode aplikasi tepercaya, pengguna hanya memasukkan cookie, dan tidak ada browser/rendering. Membuat container per akun menambah lifecycle volume/secret/network dan pengelolaan Docker daemon. Bot tidak diberi Docker socket.

| Model | Kelebihan | Batas | Keputusan |
|---|---|---|---|
| Coroutine dalam satu proses | Proses lebih sedikit | Crash/cancel dan global state lebih saling terikat | Tidak dipilih |
| Subprocess per akun dalam container worker | Reuse lock; sesi/journal/error per akun; app dapat diperbarui mandiri | UID, filesystem, batas CPU/RAM worker masih bersama | Dipakai |
| Container per akun | Isolasi OS dan batas resource per akun | Perlu orchestrator, provisioning secret/volume dan pemantauan container | Tunda sampai diperlukan |

Default3worker adalah pembatas operasional awal, bukan hasil pengukuran. Container Compose dibatasi2CPU/2GiB; total RAM juga mencakup interpreter Python dan klien HTTP per akun. [Batas resource Docker harus dikonfigurasi eksplisit](https://docs.docker.com/engine/containers/resource_constraints/). Ukur RSS/CPU/latensi dan kegagalan429 pada server sebelum menaikkan kuota. Jika jumlah akun besar, kebutuhan isolasi OS muncul, atau resource per user harus dijamin, pindahkan worker ke service/container terkelola dengan volume akun terpisah.

## HTTP dan transaksi

Lima aksi adapter: snapshot, katalog toko tetap, beli satu item, aksi Ojol dan aktivitas pendukung. Adapter hanya mengizinkan origin/path/metode game yang diperiksa. Snapshot membaca wallet/Ojol/kebutuhan/waktu server; milli-koin memakai Decimal, arrival memakai waktu server. Daftar toko berasal dari `ojol/shop_locations.py` berdasarkan desa dan resource. Planner menyaring rencana isi ulang yang layak berdasarkan katalog terkini. Rotasi menurut jurnal akun berlaku antar toko Akademis.ai satu tipe. Toko cadangan dipilih berdasarkan biaya jika tak ada rencana Akademis.ai yang layak. Pembelian memeriksa ulang desa, fase, saldo, resource, dan katalog sebelum POST. Efek item berasal dari data bundle client tanpa mengeksekusi JavaScript, cache mengikuti `configVersion`.

GET sementara gagal dicoba3kali dengan backoff1/2detik. Auth/redirect ditolak. POST satu percobaan; timeout write tidak menyebabkan retry. Batas request API30detik dan tunggu worker40detik. Stop diperiksa selama menunggu aksi dan countdown.

Journal menulis aksi pending sebelum write, memverifikasi saldo/resource/receipt sesudahnya, lalu membukukan keuangan. Rekonsiliasi bersama dijalankan sebelum sesi live baru dan setelah timeout/hasil ambigu aksi Ojol. Ledger pending/uncertain menahan transaksi baru sambil worker memeriksa ulang setiap 10 detik, tanpa admin atau replay POST. Receipt ID trip membuktikan klaim; snapshot jurnal lama tanpa ID memakai rute/waktu/payout. Dua observasi stabil dapat menyerahkan klaim lama ke trip/status sekarang sebagai handed_off tanpa atribusi ongkos. Trip lama yang masih sama tetap menunggu. Gangguan transport saat rekonsiliasi boleh dicoba ulang; auth, Stop, dan maintenance tetap dihormati. Saldo minimum production20 dan batas sesi tetap berlaku.

Snapshot menyimpan receipt terstruktur dari game, ID trip aktif, penghitung harian, waktu tiba, serta rumah/desa. `game-sync.json` menyimpan snapshot terakhir dan hasil pemeriksaan, terpisah dari cashflows. Menyalin riwayat game tidak membukukan pendapatan baru. Status dashboard memakai snapshot terbaru dari worker atau sinkronisasi, menandai waktu data, dan memisahkan penghitung game dari sesi bot. Data cookie yang ditampilkan hanya metadata kedaluwarsa.

Error terminal menulis STOP/outbox akun dan tampil di dashboard pemilik; kegagalan control global menghentikan semua worker. Cloudflared exit menghentikan semua worker dan memberi tahu admin. Shutdown mencoba membersihkan seluruh worker dan tunnel sekalipun salah satu gagal. Antrean auto-start berupa flag per ControlService yang dibuat sekali saat boot dari env `OJOL_AUTO_START` (defaulttrue). Tidak memerlukan marker dari versi lama atau start manual pertama. Saat boot envtrue sengaja membersihkan STOP lama untuk kandidat akun; pending/uncertain diselesaikan worker sebelum sesi baru. Stop manual/Import Cookie/shutdown membatalkan flag antrean untuk sesi aplikasi saat ini. Error startup menghapus flag sebelum melaporkan kegagalan sehingga tidak ada restart loop. Boot berikutnya kembali mencoba semua akun eligible, termasuk akun yang sebelumnya berhenti/error.

Startup memeriksa izin operator, cookie, whitelist dan kapasitas. Akun lain tetap bisa dimulai bila satu akun diblokir. Kandidat yang tertahan kapasitas menunggu slot di supervisor. Tiap start memakai file lock akun dan lock management sehingga startup/poll tidak menggandakan worker. HTTP membaca state game terbaru; pembelian/order/klaim lama tidak diputar ulang. Setelah rekonsiliasi, setiap boot membuka sesi baru dengan batas belanja/trip/durasi per sesi dari env; saldo minimum production20 tetap wajib. `OJOL_AUTO_START=false` mencegah auto-start meskipun ada marker resume lama.


## Batas deployment dan pengujian

Satu replica control service dan satu replica worker per volume/bot. Perintah `./deploy.sh app` membangun dan mengganti hanya app, sambil memastikan worker/WARP ada tanpa me-recreate yang sudah berjalan. `./deploy.sh worker` hanya mengganti worker; `./deploy.sh all` dapat menghentikan worker dan mengganggu koneksi saat WARP dibuat ulang. Filesystem akun adalah pemisahan aplikasi, bukan sandbox OS: proses tepercaya memakai UID sama. File cookie/registry privat, tidak masuk image/Git/log. Domain production mengalahkan override public-url lokal lama. TLS publik ditangani Cloudflare; port6080 hanya loopback host, metrics2000 hanya loopback container.

Test menggunakan runner `.env.testing` khusus dengan env shell dibuang dan network diblokir. Cakupan: whitelist/admin, kepemilikan dan tiket impor, kuota paralel, batas worker, revoke/arsip/restore, sesi/CSRF, env child, adapter HTTP, ledger dan rekonsiliasi tanpa replay. Pengujian offline tidak membuktikan kapasitas server atau kondisi endpoint game live.
