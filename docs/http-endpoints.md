# Endpoint Ojol

Inspeksi 11 November 2026 WIB: bundle client terautentikasi dibaca sebagai teks, lalu endpoint GET diverifikasi melalui sesi pemilik akun. Tidak menjalankan POST live dalam inspeksi ini. Source/capture berada di `.local/http-discovery`, diabaikan Git dan direktori mode0700. Salinan cookie inspeksi dihapus setelah verifikasi. Analisis REA bersifat statis dan graph semantik parsial; bukan bukti eksekusi seluruh route.

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
| POST `/api/shops/{businessId}/buy` | `{item, requestId}` | handler Beli dalam source; write diuji dengan mock |
| POST `/api/ojol` | `{action:"ambil", vehicle:"motor"}` | handler Cari order dalam source; write diuji dengan mock |
| POST `/api/ojol` | `{action:"selesai"}` | handler Sampai dalam source; write diuji dengan mock |

Tombol mata memanggil onLook → centerOn + pembukaan panel. Panel membaca detail plot lalu katalog. Tombol Pergi memakai POST `/api/tujuan`; core HTTP tidak mengirim endpoint tersebut. Pembelian service sendiri dapat mempunyai efek tampil di toko yang ditentukan server, sama seperti Beli dari preview browser.

Efek resource tidak ada di response katalog: client menggunakan konfigurasi JSON dalam bundle (misalnya key `pulsa`→`kuota`). Adapter mengunduh bundle yang dirujuk halaman aktif, mengekstrak hanya item yang didukung dan memverifikasi nilai0–100 tanpa mengeksekusi JavaScript. Cache diikat ke configVersion; perubahan versi memuat ulang. Item solar/EV dan transaksi di luar Ojol motor dikecualikan.

Client helper memakai JSON body, sesi cookie same-origin dan tidak menambahkan token CSRF khusus pada request game yang teramati. Form import aplikasi tetap memakai CSRF sendiri. HTTP adapter mengirim Origin/Referer game, memvalidasi sesi lewat GET, menolak redirect serta error auth; tidak mencoba melewati login atau challenge.

Keterbatasan: endpoint internal bisa berubah, tidak membuktikan kontrak API publik. Tidak menyimpulkan idempotensi endpoint Ojol dari adanya requestId pada pembelian; semua POST tetap satu kali. Perubahan harga/efek/resource, error auth, dan hasil transaksi yang belum pasti tetap dapat menghentikan worker. Browser Harness lama tetap tersedia untuk fallback pembacaan dan mode manual.

Pengukuran lokal image runtime ARM64, batas2CPU/2GiB: tiga snapshot HTTP selama9,71detik setelah preview tiga kategori menghasilkan CPU1,28% (delta cgroup usage/waktu), memory.current173,86MiB dan0proses Chromium. Ini core read-only dengan MCP/ADK, tanpa bot/control/tunnel dan tanpa transaksi live; bukan angka beban production penuh atau perbandingan perangkat yang sama.
