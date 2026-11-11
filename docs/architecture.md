# Arsitektur HTTP multi-account

Keputusan 11 November 2026 WIB: **satu akun terdaftar memiliki maksimal satu subprocess worker aktif; satu container aplikasi menampung control service, worker akun, MCP dan satu cloudflared**. Chrome/Browser Harness dan seluruh fallback dihapus. Error HTTP terminal menghentikan akun; tidak pindah backend.

## Alur

```text
Telegram private chat
  -> satu getUpdates poller + whitelist/admin + akun terpilih
    -> akun A: ControlService -> subprocess ADK -> stdio HTTP MCP -> game
    -> akun B: ControlService -> subprocess ADK -> stdio HTTP MCP -> game
HTTPS import /a/<ID>/...
  -> whitelist pemilik + tiket sekali pakai + sesi/CSRF akun
    -> verifikasi HTTP MCP -> cookie file akun diganti atomik
```

`accounts.sqlite3` memuat user yang diizinkan, pemilik akun, akun terpilih, kuota dan override admin. Admin adalah `OJOL_TELEGRAM_CHAT_ID` dari env induk; settings akun memakai Telegram ID pemilik untuk notifikasi. Penggantian env worker hanya mengubah runtime, penerima dan label akun, bukan otoritas admin registry.

Registry memakai query parameter dan transaksi `BEGIN IMMEDIATE` saat tambah/pulihkan akun. Batas default3akun/user dan3worker aktif global dapat diubah1–100. Lock management menserialisasi pemilihan/start/arsip/revokasi/import; jumlah worker memperhitungkan child yang sudah di-spawn sebelum mengambil file lock. Lock per akun mencegah worker ganda; lock control-server mencegah dua poller untuk volume sama. Tidak ada auto-resume gameplay setelah restart.

Akun baru: `runtime/accounts/<UUID>/`. Akun lama didaftarkan sebagai **Utama** dengan direktori asli supaya ledger/pending action/cookie tetap sama. Arsip membebaskan kuota tetapi menyimpan semua data. Revoke whitelist berlaku sebelum menunggu shutdown, menolak request baru, mencabut tiket/sesi import dan membatalkan delivery pending. User tidak dapat memilih akun user lain, termasuk dengan memalsukan callback. Callback laporan membawa ID akun agar tombol lama tidak berubah tujuan saat pilihan akun berubah.

Navigasi Telegram memakai reply keyboard dan inline button. Management meminta ID hanya ketika menambah user; user yang sudah ada dipilih dari daftar. Nama/kuota/tanggal memakai state input per Telegram ID, dengan validasi sebelum state dihapus dan tombol Batal. Callback akun tetap memeriksa ownership; callback admin dan input admin memeriksa ID admin. Arsip/pencabutan memerlukan konfirmasi yang terikat target dan state saat ini. Daftar berhalaman8item agar menu tetap ringkas. Perintah teks management lama tidak lagi menjalankan aksi; tombol Start bawaan Telegram hanya membuka menu.

Sesi form dibatasi path akun, HttpOnly, SameSite dan Secure pada HTTPS. CSRF berasal dari sesi yang sama. Registry dan import berserial sehingga pencabutan akses tidak bersaing dengan pemasangan cookie. Cookie sama dicegah terpasang ke slot akun lain dengan SHA256, tanpa menyimpan cookie di registry. **Batas:** dua cookie sesi berbeda dari akun game sama belum dapat dideduplikasi tanpa ID pemain stabil dari API. Jangan menjalankan akun game sama melalui beberapa sesi/server.

## Alasan subprocess, bukan container per akun

[Python asyncio menyediakan proses asynchronous](https://docs.python.org/3.12/library/asyncio-subprocess.html) yang dapat dipantau bersamaan. Proyek sudah memiliki lifecycle subprocess dan journal per direktori; model itu memenuhi kebutuhan akun HTTP terpisah tanpa scheduler/container API baru.

[Docker memakai namespaces untuk isolasi proses/network dan cgroups untuk resource](https://docs.docker.com/engine/security/). Container per akun berguna jika membutuhkan batas CPU/RAM dan isolasi OS per user. Saat ini setiap worker menjalankan kode aplikasi tepercaya, pengguna hanya memasukkan cookie, dan tidak ada browser/rendering. Membuat container per akun menambah lifecycle volume/secret/network dan pengelolaan Docker daemon. Bot tidak diberi Docker socket.

| Model | Kelebihan | Batas | Keputusan |
|---|---|---|---|
| Coroutine dalam satu proses | Proses lebih sedikit | Crash/cancel dan global state lebih saling terikat | Tidak dipilih |
| Subprocess per akun | Reuse worker/lock saat ini; sesi/journal/error per akun | UID, filesystem, batas CPU/RAM container masih bersama | Dipakai |
| Container per akun | Isolasi OS dan batas resource per akun | Perlu orchestrator, provisioning secret/volume dan pemantauan container | Tunda sampai diperlukan |

Default3worker adalah pembatas operasional awal, bukan hasil pengukuran. Container Compose dibatasi2CPU/2GiB; total RAM juga mencakup interpreter ADK dan MCP per akun. [Batas resource Docker harus dikonfigurasi eksplisit](https://docs.docker.com/engine/containers/resource_constraints/). Ukur RSS/CPU/latensi dan kegagalan429 pada server sebelum menaikkan kuota. Jika jumlah akun besar, kebutuhan isolasi OS muncul, atau resource per user harus dijamin, pindahkan worker ke service/container terkelola dengan volume akun terpisah.

## HTTP dan transaksi

Empat tool MCP: snapshot, preview toko, beli satu item, aksi Ojol. Adapter hanya mengizinkan origin/path/metode game yang diperiksa. Snapshot membaca wallet/Ojol/kebutuhan/waktu server; milli-koin memakai Decimal, arrival memakai waktu server. Preview toko tidak mengirim POST perjalanan. Efek item berasal dari data bundle client tanpa mengeksekusi JavaScript, cache mengikuti `configVersion`.

GET sementara gagal dicoba3kali dengan backoff1/2detik. Auth/redirect ditolak. POST satu percobaan; timeout write tidak menyebabkan retry. Batas request server MCP30detik, transport MCP35detik dan tunggu worker40detik. Stop diperiksa selama menunggu tool dan countdown.

Journal menulis aksi pending sebelum write, memverifikasi saldo/resource/receipt sesudahnya, lalu membukukan keuangan. Aksi ambigu tetap pending/uncertain dan memblokir start. Rekonsiliasi membaca bukti sekarang, tanpa replay. Saldo minimum production20, threshold/cadangan resource, produk tanpa overflow dan batas belanja/trip/durasi tetap berlaku per akun.

Error terminal menulis STOP/outbox akun dan dikirim hanya ke pemilik; kegagalan control global menghentikan semua worker. Outage Telegram menyimpan satu error per episode. Cloudflared exit menghentikan semua worker dan memberi tahu admin. Shutdown mencoba membersihkan seluruh worker dan tunnel sekalipun salah satu gagal; gameplay tidak diulang otomatis.

## Batas deployment dan pengujian

Satu replica control service per volume/bot. Filesystem akun adalah pemisahan aplikasi, bukan sandbox OS: proses aplikasi tepercaya memakai UID sama. Resource container adalah batas bersama. File cookie/registry privat, tidak masuk image/Git/log. Domain production mengalahkan override public-url lokal lama. TLS publik ditangani Cloudflare; port6080 hanya loopback host, metrics2000 hanya loopback container.

Test menggunakan runner `.env.testing` khusus dengan env shell dibuang dan network diblokir. Cakupan: whitelist/admin, ownership/callback/link, kuota paralel, batas worker, revoke/arsip/restore, sesi/CSRF, env child, HTTP MCP stdio, ledger dan rekonsiliasi tanpa replay. Pengujian offline tidak membuktikan kapasitas server atau kondisi endpoint game/Telegram live.
