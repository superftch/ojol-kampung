# Endpoint Ojol

Inspeksi 11 November 2026 WIB: bundle client dibaca sebagai teks, lalu GET dan POST terpilih diverifikasi melalui sesi pemilik akun. Source/capture awal berada di `.local/http-discovery`, diabaikan Git dan direktori mode0700. Salinan cookie inspeksi dihapus setelah verifikasi. Analisis REA bersifat statis dan graph semantik parsial; bukan bukti eksekusi seluruh route.

Bundle awal `0wwcgg-bq-sxa.js` SHA256: `29798a21c5b7a06ea883e76e804e9629f30f07bca625ded74d8356e13352d74e`. Runtime tidak mem-pin nama bundle; halaman dan configVersion aktif menentukan konfigurasi yang dibaca.

| Endpoint | Pemakaian | Bukti |
|---|---|---|
| GET `/api/ojol` | mitra, kendaraan, resource, trip, tarif, payout/history | HTTP200 dan konsumsi client |
| GET `/api/game/me` | `balanceMilli`, `configVersion`, rumah/desa | HTTP200 |
| GET `/api/kebutuhan` | `asleep` | HTTP200 |
| GET `/api/time` | waktu server untuk arrival/countdown | HTTP200 |
| GET `/api/tujuan` | daftar usaha, plot ID, kategori, koordinat | HTTP200 |
| GET `/api/world/plots/{plotId}` | business ID dan desa | HTTP200 dan loader panel client |
| GET `/api/shops/{businessId}` | menu, item ID, priceMilli, open, mine | HTTP200 untuk SPBU/bengkel/konter |
| POST `/api/shops/{businessId}/buy` | `{item, requestId}` | live: Pertalite, Tambal ban, Isi pulsa; perubahan saldo/resource terverifikasi |
| POST `/api/ojol` | `{action:"ambil", vehicle:"motor"}` | live: trip baru dengan countdown terverifikasi |
| POST `/api/ojol` | `{action:"selesai"}` | live: receipt payout baru terverifikasi setelah arrival server |

Tombol mata memanggil onLook → centerOn + pembukaan panel. Panel membaca detail plot lalu katalog. Tombol Pergi memakai POST `/api/tujuan`; core HTTP tidak mengirim endpoint tersebut. Pembelian service sendiri dapat mempunyai efek tampil di toko yang ditentukan server, sama seperti Beli dari preview browser.

Efek resource tidak ada di response katalog: client menggunakan konfigurasi JSON dalam bundle (misalnya key `pulsa`→`kuota`). Adapter mengunduh bundle yang dirujuk halaman aktif, mengekstrak hanya item yang didukung dan memverifikasi nilai0–100 tanpa mengeksekusi JavaScript. Cache diikat ke configVersion; perubahan versi memuat ulang. Item solar/EV dan transaksi di luar Ojol motor dikecualikan.

Client helper memakai JSON body, sesi cookie same-origin dan tidak menambahkan token CSRF khusus pada request game yang teramati. Form import aplikasi tetap memakai CSRF sendiri. HTTP adapter mengirim Origin/Referer game, memvalidasi sesi lewat GET, menolak redirect serta error auth; tidak mencoba melewati login atau challenge.

Keterbatasan: endpoint internal bisa berubah, tidak membuktikan kontrak API publik. Tidak menyimpulkan idempotensi endpoint Ojol dari adanya requestId pada pembelian; semua POST tetap satu kali. Perubahan harga/efek/resource, error auth, dan hasil transaksi yang belum pasti tetap dapat menghentikan worker. Browser Harness lama tetap tersedia untuk fallback pembacaan dan mode manual.

Probe transaksi lokal dilakukan setelah pengguna menghentikan worker production, melalui ADK → stdio MCP → HTTP tanpa Chromium. Lima aksi (klaim, tiga pembelian, ambil) tercatat verified pada ledger lokal, tanpa pending/uncertain. Sesuai instruksi pengguna, probe sementara melewati planner threshold dan mengizinkan efek pembelian terpotong di100%, dengan anggaran maksimal2koin dan saldo minimum20. Pengecualian hanya pada proses probe sementara; guard source production tidak diubah. Script bypass dan salinan cookie dihapus setelah proses berhenti. Bukti finansial/account tetap privat di `.local/live-verification/report.json` dan ledger lokal, tidak dikomit.
