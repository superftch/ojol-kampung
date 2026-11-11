# Inventaris API client KampungSebelah

**Status parsial.** Ada **273 kombinasi metode dan pola path** dari bukti historis, bundle publik, dan bundle halaman game. [Katalog gameplay](http-gameplay-catalog.md) memuat 269 kombinasi dari kode client yang dimuat Chrome. Sembilan kombinasi dipakai worker. Varian aksi pada metode dan path yang sama dihitung sekali.

Cakupan adalah origin `https://www.kampungsebelah.com` dan artefak yang disebut di bawah. Endpoint control service `ojol-kampung`, Telegram, aset Next.js, dan penyedia OAuth eksternal berada di luar inventaris API game ini.

## Akses dan autentikasi

| Metode dan path | Tujuan | Request yang terlihat | Respons yang terlihat | Worker | Bukti |
| --- | --- | --- | --- | --- | --- |
| POST `/api/intent` | Menyimpan pilihan masuk atau daftar sebelum client memulai login Google | JSON `{intent}`. Pilihan UI `masuk` atau `daftar`. | Kode pemanggil tidak membaca respons. | Tidak | Pemanggilan langsung di `1fw2_wjft05dg.js:3:6916`. |
| POST `/api/auth/sign-in/social` | Memulai alur login Google | JSON dengan `provider: "google"`, `callbackURL: "/lanjut"`, dan `errorCallbackURL: "/masuk-gagal"`. | Pemanggil menangani `error`. Helper SDK dapat memakai `url` dan `redirect` dari data respons. | Tidak | Pemanggilan `signIn.social` di `1fw2_wjft05dg.js:3:7044`. Base path, konversi nama, dan pembentukan metode/path ditelusuri di `1-z3-19vwe2f1.js:1:23827`, `:1:22281`, dan `:1:34349`. Redirect helper di `:1:7910`. |
| GET `/api/auth/get-session` | Memuat sesi melalui SDK yang dibundel | Helper meneruskan query opsional. Nama parameternya belum teridentifikasi. | SDK memeriksa `needsRefresh` dan menangani status 401. Skema sesi lengkap belum diketahui. | Tidak | Pemanggilan di SDK `1-z3-19vwe2f1.js:1:28692`. Pemakaian oleh halaman publik belum terbukti. |
| POST `/api/auth/get-session` | Memuat ulang sesi ketika respons GET memiliki `needsRefresh` | SDK memanggilnya tanpa body eksplisit. | Hasil dipakai sebagai data sesi. Skema lengkap belum diketahui. | Tidak | Cabang kondisional di SDK `1-z3-19vwe2f1.js:1:28848`. Pemakaian oleh halaman publik belum terbukti. |

Bukti di bagian ini bersifat statis. Nama operasi lain di peta metode atau pesan error SDK belum membuktikan adanya pemanggilan dari aplikasi atau tersedianya endpoint di server.

## Gameplay dan Ojol

Sumber historis bertanggal **11 November 2026 WIB**. Bundle gameplay yang dicatat saat itu adalah `0wwcgg-bq-sxa.js` dengan SHA-256 `29798a21c5b7a06ea883e76e804e9629f30f07bca625ded74d8356e13352d74e`. File tersebut tidak tersedia di checkout ini. Lokasi kode di tabel merujuk pada adapter di commit `07cf767`, dan hasil live merujuk pada catatan historis di commit tersebut.

| Metode dan path | Tujuan | Request yang terlihat | Respons yang dipakai atau hasil yang diamati | Worker | Bukti |
| --- | --- | --- | --- | --- | --- |
| GET `/api/ojol` | Status mitra, kendaraan, resource, dan trip | GET tanpa query di adapter. | `enabled`, `mitra`, `vehicle`, `trip`, `problem`, `bars` (bensin, kendaraan, kuota), `earnedTodayMilli`, dan `history`. Trip memakai `arriveAt`, `kind`, `distance`, `fareMilli`, serta label asal dan tujuan. Receipt riwayat memakai `doneAt`, `kind`, label asal dan tujuan, serta `netMilli`. | Ya | HTTP 200 historis. [Snapshot](../ojol/http_api.py#L236) dan [parser](../ojol/http_api.py#L67). |
| POST `/api/ojol` | Ambil order atau selesaikan trip | `{"action":"ambil","vehicle":"motor"}` saat idle. `{"action":"selesai"}` setelah waktu tiba menurut server. | Bundle gameplay juga menunjukkan `action: "daftar"` dan `action: "berhenti"`. Worker hanya memakai `ambil` dan `selesai`. Untuk `ambil`, trip baru dengan hitung mundur teramati. Untuk `selesai`, receipt payout baru teramati. Client membaca `netMilli` dan `warga` dari respons `selesai`. Skema lengkap belum diketahui. | Ya | `ambil` dan `selesai` diverifikasi live pada inspeksi historis. Bundle saat ini menunjukkan varian tambahan di [katalog gameplay](http-gameplay-catalog.md#ojol-kerja-dan-kegiatan-harian). [Aksi Ojol](../ojol/http_api.py#L419). |
| GET `/api/game/me` | Saldo dan konteks akun | GET tanpa query di adapter. | `balanceMilli`, `configVersion`, dan `home` dengan `desa`, `x`, serta `y`. | Ya | HTTP 200 historis. [Snapshot](../ojol/http_api.py#L236) dan [pemilihan toko](../ojol/http_api.py#L305). |
| GET `/api/kebutuhan` | Cek apakah karakter tidur | GET tanpa query di adapter. | `asleep` boolean. | Ya | HTTP 200 historis. [Snapshot](../ojol/http_api.py#L236) dan [parser](../ojol/http_api.py#L67). |
| GET `/api/time` | Waktu server untuk menentukan waktu tiba | GET tanpa query di adapter. | `now`, dibaca sebagai timestamp. | Ya | HTTP 200 historis. [Snapshot](../ojol/http_api.py#L236). |
| GET `/api/tujuan` | Daftar tujuan untuk pencarian toko | GET tanpa query di adapter. | `usaha[]` dengan `plotId`, `item` (kategori), `x`, dan `y`. | Ya | HTTP 200 historis. [Preview](../ojol/http_api.py#L329) dan [pemilihan toko](../ojol/http_api.py#L305). |
| POST `/api/tujuan` | Aksi **Pergi** dari daftar tujuan | Bundle gameplay saat ini mengirim JSON `{place}`. | Belum diketahui. | Tidak | Pemanggilan client historis dan `0locg-pigz8wv.js:1:123472`. |
| GET `/api/world/plots/{plotId}` | Detail kavling dan identitas usaha | `plotId` dari daftar tujuan, dalam format seperti `K22-U07` yang diterima adapter. | `business` dapat bernilai null. Jika ada, worker membaca `id`, `catalogId`, `name`, dan `desa`. | Ya | HTTP 200 dan loader panel pada inspeksi historis. [Detail toko](../ojol/http_api.py#L305). |
| GET `/api/shops/{businessId}` | Katalog toko, status buka, dan kepemilikan | `businessId` berupa UUID dari detail kavling. | `open`, `mine`, `plang`, dan `menu[]` dengan `item`, `name`, `priceMilli`, serta `habis` bila ada. | Ya | HTTP 200 untuk SPBU, bengkel, dan konter pada inspeksi historis. [Katalog](../ojol/http_api.py#L279) dan [nama toko](../ojol/http_api.py#L320). |
| POST `/api/shops/{businessId}/buy` | Membeli satu item dari katalog | `businessId` berupa UUID. JSON `{item, requestId}`. Adapter mengambil ID item dari menu dan mengirim UUID sebagai `requestId`. | Perubahan saldo dan resource diverifikasi dari snapshot berikutnya. Skema body respons POST belum diketahui. | Ya | Pertalite, Tambal ban, dan Isi pulsa diverifikasi live pada inspeksi historis. [Pembelian](../ojol/http_api.py#L381). |

## Bukti laporan harian

Pada 11 November 2026 WIB, pembacaan lokal terotorisasi untuk dua halaman `GET /api/me/koin` berhasil. Respons berisi `items` dan cursor `next`. Query `after` menerima cursor dari halaman sebelumnya. Baris memiliki `id`, `at` dengan zona waktu, `amountMilli` bertanda, `type`, `label`, dan `detail`. Dua halaman yang diperiksa berurutan dari terbaru ke terlama.

Payout Ojol memiliki `type: OJOL_ONGKOS`. Pembelian yang terlihat memakai `SHOP_PURCHASE` dan tidak memberi penanda yang cukup untuk mengaitkan biaya manual ke Ojol. Bot menghitung pendapatan dari penanda payout dan mengestimasi laba dengan mengurangi belanja yang nama produknya cocok persis dengan daftar produk worker setelah normalisasi kapital dan spasi. Estimasi menganggap semua pembelian produk yang cocok sebagai biaya Ojol. Jurnal tetap menyediakan biaya worker terverifikasi. Lihat [rujukan client riwayat koin](http-gameplay-catalog.md#profil-perbankan-dan-pembayaran).

## Catatan worker

Pada pemeriksaan 11 November 2026 WIB, katalog toko tutup mengembalikan HTTP 409 dengan `error.code = REQUIREMENT_NOT_MET` dan `error.message = Usaha ini belum buka.`. Preview melewati toko hanya jika kedua nilai cocok pada endpoint katalog. Konflik lain tetap menghentikan preview.

Preview toko membaca detail kavling lalu katalog. Tombol **Pergi** di client memakai `POST /api/tujuan`. Worker cukup memakai GET untuk preview. Efek item diambil dari konfigurasi di bundle client, misalnya `pulsa` menambah `kuota`. Worker membaca halaman `/kampung` dan aset JavaScript yang dirujuknya untuk mengekstrak efek. Cache mengikuti `configVersion`. Aset tersebut tidak dihitung sebagai endpoint API di tabel.

Catatan verifikasi historis mencatat lima aksi yang diverifikasi, yaitu satu klaim, tiga pembelian, dan satu ambil order. Probe saat itu memakai pengecualian sementara terhadap threshold dan overflow dalam proses lokal. Ini menjelaskan cakupan uji historis. Runtime saat ini tetap memeriksa fase, saldo, resource, harga, dan kapasitas sebelum pembelian. `requestId` sendiri belum membuktikan idempotensi server. Hasil POST yang ambigu ditangani melalui jurnal dan rekonsiliasi.

## Artefak inspeksi publik

Bundle diambil pada **11 November 2026 sekitar 15.20–15.21 WIB** dari halaman `/`, `/privasi`, dan `/syarat`. Referensi skrip di HTML dan data halaman Next.js diperiksa, termasuk referensi chunk yang dapat diresolusikan. Halaman `/kampung` dan `/masuk-gagal` mengembalikan HTTP 307 ke `/` tanpa sesi. Bundle dari tab Chrome yang sudah login dicatat terpisah di [katalog gameplay](http-gameplay-catalog.md).

Alat analisis adalah REA CLI `6.8.0` dengan Node.js `24.22.1`. Metode mengikuti [panduan analisis statis REA](https://github.com/morluto/rea/blob/main/docs/guides/javascript/javascript-artifact-reconstruction.md). Artefak mentah, manifest, dan keluaran REA disimpan di `.local/http-discovery/`. Nomor kolom pada rujukan JavaScript dihitung dari 1 pada bundle asli yang diminifikasi.

Sebelas bundle berhasil diunduh dan lolos `node --check`. REA menyelesaikan 10 bundle tanpa kegagalan parsing dalam analisis terarah (`rea-scoped-evidence`). Analisis penuh berhenti saat `41bx3p8jpx9qa.js` mencapai batas 300 detik per sumber (`provider_timeout`, tercatat di `rea-summary.json`). Bundle itu tetap diperiksa melalui pencarian referensi request pada teks. Grafik semantiknya belum tersedia. Pemeriksaan menemukan rujukan runtime Next.js, tanpa path API game yang dapat ditelusuri dari file itu.

Grafik semantik REA mencatat pemanggilan langsung `POST /api/intent`. Rute autentikasi dinamis ditelusuri dari kode aplikasi dan helper SDK karena inventaris rute otomatis REA belum memulihkannya. Temuan dari bundle publik tidak memverifikasi kontrak runtime.

Semua nama file di bawah relatif terhadap `/_next/static/immutable/chunks/`.

| Bundle | Halaman yang merujuk | SHA-256 |
| --- | --- | --- |
| `01msv9ym379u0.js` | `/`, `/privasi`, `/syarat` | `d5232bd1fb8d9df648d66072f9c815a1b96c04f0c7408553591be1273dd7cb31` |
| `0c0hxoamwjsbw.js` | `/`, `/privasi`, `/syarat` | `0973c1d64c88adc8e3c950410cb58b288f72118d5965b78049438deb8f2f9683` |
| `0w7baq3zknu_f.js` | `/privasi`, `/syarat` | `d9a4c74323cde6c121e89f2eb40d654728d413a4e392e5cb71eb2ac0d366c012` |
| `1-z3-19vwe2f1.js` | `/` | `5220272202cdcfaba1fd7b106319f754ef6699807d21dc474b0561bba36d46b1` |
| `1fw2_wjft05dg.js` | `/` | `f2651a16935a7469141973090bf27e2d904feb1bfa08531664a0457a47178915` |
| `254-kj64ajyl9.js` | `/` | `b9917338d593abf652f9716d95a0ab77a8b8a249f54ba4abb56eaba5410b637e` |
| `2g4c2hdw1i1x_.js` | `/`, `/privasi`, `/syarat` | `73b8b644f6821cc35fa90e7aeac577096ecc3b9bdb7b93368672d33ad815ef27` |
| `2g_6k205jx9fz.js` | `/`, `/privasi`, `/syarat` | `92ead3ffa1d91c45386d251a00466e889a705bc014e2f74ce33f2d731348ae73` |
| `41bx3p8jpx9qa.js` | `/`, `/privasi`, `/syarat` | `a42724de40fee0d08575a9410a38a6e9dd4dec6729c08277e6c8efb1e559a41b` |
| `44b6i8chqw4y5.js` | `/`, `/privasi`, `/syarat` | `fbb6cee32d669bf810b9ffdb61fa672f748f903e3506d1ec8fe03748a43d8d0d` |
| `turbopack-1byz1flvc-bu1.js` | `/`, `/privasi`, `/syarat` | `b5f9b5199b99ab6c141f4540f0b7d0fe803c4ecf6956849ecb6e59d3d439272e` |

## Saat menambah fitur automation

Telusuri metode, path, dan payload hingga ke sumber yang mendukung. Perbarui tabel dengan rujukan kode dan tingkat buktinya, lalu uji parsing dan alur worker menggunakan respons tiruan. Bundle baru bisa mengubah kontrak yang terlihat. Cek ulang versi dan perilaku terkait saat mengandalkan temuan historis.

Katalog gameplay mencakup bundle yang dimuat tab `/kampung` saat inspeksi. Chunk yang baru dimuat setelah membuka fitur lain, rute dinamis yang belum terurai, dan endpoint yang hanya ada di server masih bisa berada di luar cakupan.
