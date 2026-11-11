# Inventaris API client KampungSebelah

Inventaris request gameplay lengkap ada di [katalog API client](http-gameplay-catalog.md). Panduan development tersedia di [development lokal](local-development.md).

Inspeksi 11 November 2026 WIB: bundle client dibaca sebagai teks, lalu GET dan POST terpilih diverifikasi melalui sesi pemilik akun. Source/capture awal berada di `.local/http-discovery`, diabaikan Git dan direktori mode0700. Salinan cookie inspeksi dihapus setelah verifikasi. Analisis REA bersifat statis dan graph semantik parsial; bukan bukti eksekusi seluruh route.

Bundle awal `0wwcgg-bq-sxa.js` SHA256: `29798a21c5b7a06ea883e76e804e9629f30f07bca625ded74d8356e13352d74e`. Runtime tidak mem-pin nama bundle; halaman dan configVersion aktif menentukan konfigurasi yang dibaca.

## Request KampungSebelah

Tabel ini mencakup seluruh request yang dipanggil adapter Ojol ke `https://www.kampungsebelah.com`. Kolom bukti membedakan hasil probe live sebelumnya dari pemeriksaan kode adapter saat ini.

| Endpoint | Pemakaian | Bukti |
|---|---|---|
| GET `/api/ojol` | mitra, kendaraan, resource, trip, tarif, payout/history | HTTP200 dan konsumsi client |
| GET `/api/game/me` | `balanceMilli`, `configVersion`, rumah/desa, `profile.resting`, `profile.sleep` | HTTP200 historis; field tidur dicocokkan dengan bundle client tersimpan pada 12 November 2026 |
| GET `/api/kebutuhan` | `asleep`, status kebutuhan aktif, nilai per kebutuhan, dan kandidat tempat fisik | HTTP 200 untuk status kebutuhan. Bentuk kandidat fasilitas berasal dari bundle client. |
| GET `/api/time` | waktu server untuk arrival/countdown | HTTP200 |
| GET `/api/daily/house?plotId={plotId}` | Baca status kunjungan akun ke rumah kandidat; harus `visitedToday: false` | Bundle client dan HTTP200 pada 12 November 2026 |
| GET `/api/rumah/interior/lihat?plotId={plotId}` | Pastikan server mengizinkan akses rumah sekarang sebelum menawarkan kandidat mampir | Bundle client terbaru dan GET terotorisasi pada 12 November 2026: HTTP403 `FORBIDDEN` ketika tutup; HTTP200 dengan `bentuk` string dan `layout` array pada akses yang diizinkan |
| GET `/api/shops/{businessId}` | menu, item ID, priceMilli, open, mine | HTTP200 untuk SPBU/bengkel/konter |
| GET `/api/world/plots/{plotId}?t={timestamp}` | Cocokkan ID usaha, kategori, dan desa untuk plot cadangan auto kebutuhan | Bundle client dan capture detail plot historis. Plot cadangan berasal dari inventaris tujuan historis. Pemeriksaan live lanjutan mendapat HTTP 503. |
| GET `/kampung` | baca HTML halaman untuk menemukan bundle yang dirujuk | kode `OjolHttpApi.effects` |
| GET `/_next/static/{path}.js` | baca efek item dari bundle yang dirujuk halaman | kode `OjolHttpApi.effects` |
| POST `/api/shops/{businessId}/buy` | `{item, requestId}` | live: Pertalite, Tambal ban, Isi pulsa; perubahan saldo/resource terverifikasi |
| POST `/api/ojol` | `{action:"ambil", vehicle:"motor"}` | live: trip baru dengan countdown terverifikasi |
| POST `/api/ojol` | `{action:"selesai"}` | live: receipt payout baru terverifikasi setelah arrival server |
| GET `/api/facilities/{id}` | Cek status, layanan, tarif, dan cooldown fasilitas fisik yang ditawarkan game | Bundle client; alur adapter diuji dengan mock |
| POST `/api/facilities/{id}/use` | `{requestId}` untuk fasilitas fisik gratis yang lolos pemeriksaan | Bundle client; belum dieksekusi live oleh adapter |

Capture historis `/api/ojol` dalam `.local/http-discovery/ojol.json` memuat `todayCount` dan receipt `history[]` dengan `id`, `doneAt`, `kind`, `from.label`, `to.label`, serta `netMilli`. Trip aktif memuat `id` dan `arriveAt`. Adapter memakai ID receipt dan waktu server untuk rekonsiliasi, serta `netMilli` untuk ongkos diterima. Snapshot menyimpan penghitung dan riwayat yang tersedia pada respons, bukan seluruh riwayat akun. Tidak ada endpoint baru atau asumsi idempotensi POST untuk fitur ini.

## Bukti jadwal tidur

Pemeriksaan statis 12 November 2026 pada bundle tersimpan `1xhiowffvsf0w.js` (SHA256 `68d239f92244dcce98cafdb2adc431866082dbab780005a55f0d7370cd266f3e`) menemukan form `ks-sleep-from` / `ks-sleep-to` dan label **Jam tidur (WIB)** / **Jam bangun (WIB)**. Client membaca `me.profile.sleep.{auto,from,to,inSchedule}`; `from` dan `to` adalah menit sejak tengah malam. Nilai awal form 1320 / 300 setara 22.00 / 05.00 dan bukan bukti jadwal aktif setiap akun. Client memakai `me.profile.resting` untuk status tidur aktual dan menawarkan tombol Bangun/Tidur kapan saja. `inSchedule` dapat tetap true saat karakter sudah dibangunkan manual.

Capture historis `.local/http-discovery/me.json` memuat bentuk yang sama: `resting: false` dan `sleep: {auto: false, from: 1320, to: 300, inSchedule: false}`. Capture ini tidak membuktikan konfigurasi akun saat ini.

Verifikasi live read-only 12 November 2026 pukul 02.51–02.53 WIB memakai sesi yang diberikan pengguna. Tiga pembacaan terpisah mengonfirmasi `sleep: {auto: true, from: 120, to: 300, inSchedule: true}`, yaitu **02.00–05.00 WIB** untuk akun yang diperiksa. `profile.resting` dan `kebutuhan.asleep` sama-sama true; parser worker menghasilkan `phase: sleeping` dan batas berikutnya 05.00 WIB. Satu siklus controller dengan dua snapshot live, terpisah sekitar 10 detik, tetap di `stage: sleeping` / `event: tidur` dan tidak membuat aksi ledger. Seluruh verifikasi berisi 20 GET dan nol POST. Cookie sementara dihapus; laporan tanpa cookie disimpan privat di `.local/sleep-inspection/live-verification.json`, diabaikan Git. Pergantian status pada 05.00 belum diamati langsung; batas waktu dan kelanjutan setelah bangun diuji dengan simulasi terisolasi.

Worker membaca jadwal akun pada setiap snapshot dan menghitung batas berikutnya dengan `GET /api/time.now` dalam `Asia/Jakarta`, termasuk lintas tengah malam. Waktu sejak snapshot diterima dihitung dengan jam monotonic agar waktu tunggu tidak melewati batas jadwal yang sudah diketahui. Di batas itu worker membaca ulang status, dan selama tidur memeriksa berkala sesuai `idle_poll_seconds`. Status tidur dari salah satu `kebutuhan.asleep` atau `profile.resting` menahan semua transaksi; jam jadwal sendiri tidak menimpa status bangun manual. Perubahan tepat di antara GET terakhir dan POST tetap tunduk pada keputusan server, dan hasil transaksi belum pasti tetap memerlukan bukti sebelum dilanjutkan.

Tombol mata memanggil onLook → centerOn + pembukaan panel. Panel membaca detail plot lalu katalog. Tombol Pergi memakai POST `/api/tujuan`; core HTTP tidak mengirim endpoint tersebut. Adapter membaca katalog berdasarkan ID toko tetap di `ojol/shop_locations.py`. Pembelian service sendiri dapat mempunyai efek tampil di toko yang ditentukan server, sama seperti Beli dari preview browser.

Auto kebutuhan memeriksa semua katalog Akademis.ai yang terdaftar untuk desa dan kebutuhan akun. Cadangan hanya tersedia jika setiap katalog yang cocok berisi produk relevan dan semuanya ditandai habis oleh game. Adapter memeriksa lagi status ini dan detail usaha cadangan sebelum POST. Pergantian stok sebelum POST diuji lewat simulasi HTTP.

Efek resource tidak ada di response katalog. Client memakai konfigurasi JSON dalam bundle, misalnya `pulsa` untuk kuota dan `nasi-goreng` untuk makan. Adapter membaca efek barang kebutuhan dari konfigurasi `barang`. Pembelian kebutuhan memakai katalog toko Akademis.ai terdaftar dan menyaring layanan atau barang yang langsung dipakai menurut client. Cache diikat ke configVersion. Pembelian kebutuhan dan pemakaian fasilitas baru diverifikasi di simulasi HTTP. GET live pada pemeriksaan lanjutan mengembalikan HTTP 503, sehingga konfirmasi live fasilitas masih tertunda.

Client helper memakai JSON body, sesi cookie same-origin dan tidak menambahkan token CSRF khusus pada request game yang teramati. Form import aplikasi tetap memakai CSRF sendiri. HTTP adapter mengirim Origin/Referer game, memvalidasi sesi lewat GET, menolak redirect serta error auth; tidak mencoba melewati login atau challenge.

Keterbatasan: endpoint internal bisa berubah, tidak membuktikan kontrak API publik. Tidak menyimpulkan idempotensi endpoint Ojol dari adanya requestId pada pembelian; semua POST tetap satu kali. Perubahan harga/efek/resource, error auth, dan hasil transaksi yang belum pasti tetap dapat menghentikan worker. Runtime kini hanya HTTP MCP; kegagalan terminal menghentikan akun tanpa fallback browser.

Probe transaksi lokal dilakukan setelah pengguna menghentikan worker production, melalui ADK → stdio MCP → HTTP tanpa Chromium. Lima aksi (klaim, tiga pembelian, ambil) tercatat verified pada ledger lokal, tanpa pending/uncertain. Sesuai instruksi pengguna, probe sementara melewati planner threshold dan mengizinkan efek pembelian terpotong di100%, dengan anggaran maksimal2koin dan saldo minimum20. Pengecualian hanya pada proses probe sementara; guard source production tidak diubah. Script bypass dan salinan cookie dihapus setelah proses berhenti. Bukti finansial/account tetap privat di `.local/live-verification/report.json` dan ledger lokal, tidak dikomit.

## Bukti laporan harian

Pada 11 November 2026 WIB, pembacaan lokal terotorisasi untuk dua halaman `GET /api/me/koin` berhasil. Respons berisi `items` dan cursor `next`. Query `after` menerima cursor dari halaman sebelumnya. Baris memiliki `id`, `at` dengan zona waktu, `amountMilli` bertanda, `type`, `label`, dan `detail`. Dua halaman yang diperiksa berurutan dari terbaru ke terlama.

Payout Ojol memiliki `type: OJOL_ONGKOS`. Pembelian yang terlihat memakai `SHOP_PURCHASE` dan tidak memberi penanda yang cukup untuk mengaitkan biaya manual ke Ojol. Bot menghitung pendapatan dari penanda payout dan mengestimasi laba dengan mengurangi belanja yang nama produknya cocok persis dengan daftar produk worker setelah normalisasi kapital dan spasi. Estimasi menganggap semua pembelian produk yang cocok sebagai biaya Ojol. Jurnal tetap menyediakan biaya worker terverifikasi. Lihat [rujukan client riwayat koin](http-gameplay-catalog.md#profil-perbankan-dan-pembayaran).

## Inventaris Akademis.ai

Inspeksi read-only lewat CDP pada 11 November 2026 mencocokkan nama tanpa membedakan kapital di respons `GET /api/tujuan`. Ada **19 kecocokan dari 782 usaha** yang terlihat oleh sesi. Detail plot dan katalog mengonfirmasi **Akademis.ai Motor** dan **Akademis.ai Konter** di Desa Utara. Pemeriksaan 13 katalog SPBU yang terdaftar tidak menemukan nama Akademis.ai.

| Nama di direktori | Plot | Kategori |
|---|---|---|
| Akademis.ai - Kebun Ziraf | `Q42-B2-1` | `kebun-kopi` |
| Akademis.ai - Ziraf Kopisop | `H35-U03` | `kedai-kopi` |
| Akademis.ai Bangunan | `K40-U01` | `toko-bangunan` |
| Akademis.ai Barbershop | `K40-U07` | `barbershop` |
| Akademis.ai Coffee | `K40-U09` | `coffee-shop` |
| Akademis.ai Coffee Farm | `C75-B3-1` | `kebun-kopi` |
| Akademis.ai Farm | `C80-B4-1` | `sapi-perah` |
| Akademis.ai Farma | `K40-U06` | `toko-obat` |
| Akademis.ai GamingHouse | `B37-U07` | `warnet` |
| Akademis.ai iCafe | `K39-U04` | `warnet` |
| Akademis.ai Konter | `O38-U06` | `konter-pulsa` |
| Akademis.ai Motor | `K40-U03` | `bengkel-motor` |
| Akademis.ai MyAnabul | `C08-U07` | `pet-shop` |
| Akademis.ai Restaurant | `K40-U04` | `restoran` |
| Akademis.ai Sabe | `C75-B4-1` | `sawah` |
| Akademis.ai Sembako | `K40-U08` | `warung-sembako` |
| Akademis.ai Tahu Tempe | `O37-U09` | `pabrik-tahu` |
| Bidan Akademis.ai | `Q36-U09` | `praktik-bidan` |
| PT Akademis.ai Sawit | `H77-B4-1` | `kebun-kelapa` |

## Tool MCP Ojol

Adapter tersedia melalui stdio MCP dengan tool yang dideklarasikan di [`ojol/http_server.py`](../ojol/http_server.py).

| Tool | Parameter | Hasil atau aksi |
|---|---|---|
| `ojol_snapshot` | Tanpa parameter | Baca saldo, resource, trip, dan riwayat |
| `ojol_preview_shop` | `resource` (`fuel`, `condition`, `data`, `makan`, `kesehatan`, `fisik`, `rekreasi`, `penampilan`, atau `rumah`) | Baca katalog toko tetap untuk desa dan resource akun, atau fasilitas gratis untuk fisik |
| `ojol_purchase` | `product`, `expected_wallet`, `expected_resource`, `min_balance`, `request_id` | Validasi katalog dan snapshot terbaru, lalu beli satu item |
| `ojol_job_action` | `kind` (`search` atau `complete`) | Ambil order atau klaim trip yang sudah tiba |

## HTTP service aplikasi

Route berikut dideklarasikan di [`ojol/control.py`](../ojol/control.py) dan berjalan di host aplikasi Ojol.

| Route | Pemakaian |
|---|---|
| GET `/health` | Baca status service, core, dan proses tunnel |
| GET `/access/{ticket}` atau `/a/{account_id}/access/{ticket}` | Tukarkan tiket sekali pakai dengan sesi import dan redirect ke formulir |
| GET `/import-cookie` atau `/a/{account_id}/import-cookie` | Tampilkan formulir untuk sesi import aktif |
| POST `/import-cookie` atau `/a/{account_id}/import-cookie` | Terima formulir import dengan sesi aktif dan validasi CSRF |

## Bantu bersih

| Endpoint | Pemakaian | Bukti |
|---|---|---|
| GET `/api/world/plots?v={v}&blocks={blocks}` | Baca plot untuk blok yang diminta tab. JSON berisi `plots[]`, dengan `id`, koordinat `x`/`y`, penanda kotor `kt`, dan data warga `w` pada kandidat rumah kotor. | HTTP 200 dari satu GET dengan URL yang dipakai tab aktif. Respons berisi 260 plot, termasuk 39 kandidat sebelum pengecualian UI. |

Bundle aktif `1ko4eop1xo-dv.js` membuat marker **Bantu bersih** dari data plot. Filter dasarnya `k == "R"`, `s == "O"`, `e` tidak aktif, dan `kt` bernilai truthy. UI juga mengecualikan rumah sendiri dan plot yang sudah tersaring di state UI. Jumlah kandidat di satu respons mengikuti cakupan `blocks` dan bisa berbeda dari jumlah marker di HUD.

Verifikasi tab dan bundle memakai REA lewat CDP WebSocket di `127.0.0.1:9222`. Discovery HTTP pada port tersebut masih merespons 404. Alur penyelesaian pekerjaan lewat API belum diverifikasi.

### Workflow API untuk target 10 rumah

1. Ambil `GET /api/game/me` untuk mengenali plot rumah sendiri dan koordinat awal. Ambil `GET /api/world/plots` dengan `v` dan `blocks` dari request peta yang teramati.
2. Terapkan filter kandidat di atas, keluarkan rumah sendiri, dan deduplikasi berdasarkan `id`. Urutkan berdasarkan blok saat tersedia dan jarak dari rumah sendiri. Pilih maksimal 10 kandidat pertama dan simpan sisanya sebagai cadangan.
3. Sebelum memulai tiap kandidat, baca ulang plotnya. Jika status kotor hilang, ambil cadangan. Jalankan pekerjaan hanya setelah API yang mendukung alur normal dan konfirmasi keberhasilannya terverifikasi. Catat progres berdasarkan konfirmasi server untuk akun, karena `kt` bisa berubah setelah rumah dibersihkan pemain lain.
4. Akhiri sesi saat progres terverifikasi mencapai 10 atau saat kandidat habis. Jika hasil transaksi belum pasti, baca statusnya sebelum mempertimbangkan pengulangan.

Bagian pemetaan sudah diuji lewat GET. Workflow berhenti setelah menghasilkan daftar kandidat sampai kontrak API untuk mengerjakan dan mengonfirmasi pekerjaan tersedia.

Command lokal `cleanup-scan` memakai sesi HTTP akun yang sudah diimpor. Default-nya membaca blok rumah sendiri dan mengeluarkan satu kandidat terdekat sebagai JSON. Gunakan `--blocks` untuk memilih area dan `--limit` untuk mengatur jumlah kandidat.

```sh
python main.py cleanup-scan --blocks K39 L39 --limit 1
```

## Cari rumah untuk mampir

Inspeksi statis 12 November 2026 memakai capture bundle `0wwcgg-bq-sxa.js` dari 11 November dan REA Evidence `ev_023e4ab77fb30c59c2aae651f186a1310584965590f54b8e31adc3bd2a6ca0eb`. Analisis semantik REA parsial; pembacaan langsung fungsi `V` pada bundle memperlihatkan GET `/api/daily/house?plotId=...` dan properti `visitedToday`. Tombol Mampir memakai POST `/api/daily/visit` hanya bila belum dikunjungi; bila sudah, client menampilkan Sudah mampir atau Masuk lagi. Bukti ini menetapkan arti status pada client, bukan keberhasilan request live.

Fitur Telegram **Cari Rumah Mampir** memakai GET saja. Filter peta memakai `k == "R"`, `s == "O"`, `e` tidak aktif, dan data warga `w`; rumah sendiri dikeluarkan berdasarkan ID dan koordinat. Penanda kotor `kt` tidak diperlukan. Status kunjungan dibaca dengan sesi akun terpilih dan harus boolean eksplisit. Field hilang atau respons gagal tidak dianggap belum dikunjungi. Kandidat dengan `visitedToday: false` harus juga berhasil dibaca lewat GET `/api/rumah/interior/lihat?plotId=...`, dengan respons interior valid. Fitur tidak memanggil POST kunjungan dan tidak mencatat kunjungan hanya karena rumah ditampilkan.

Debug HTTP terotorisasi 12 November 2026 membuktikan rumah `K39-R08` memiliki `visitedToday: false`, tetapi GET lihat interior mengembalikan HTTP403 `FORBIDDEN` dengan pesan rumah hanya menerima tamu 06.00–21.00 WIB. Jadi `visitedToday` tidak membuktikan rumah sedang buka. Bundle terbaru `1xhiowffvsf0w.js` memanggil route lihat interior untuk akses tamu; bundle `3culysozx9orn.js` mencantumkan beberapa pilihan jam tamu termasuk 24 jam. Adapter mengikuti penolakan server, tanpa hardcode jam global. Hanya HTTP403 dengan kode `FORBIDDEN` pada route lihat rumah ini yang menjadi `HouseUnavailable` dan dilewati; HTTP401 `UNAUTHENTICATED` serta error auth pada route lain tetap meminta login ulang. Respons sukses harus memuat `bentuk` string dan `layout` array. Status masih dapat berubah setelah pemeriksaan.

Pemindaian read-only pada sesi debug memeriksa 38 kandidat di area rumah dan blok tetangga. Tiga sudah dikunjungi; 35 lainnya ditolak akses interior sehingga tidak ada kandidat yang ditawarkan. Ini hasil sesaat untuk area tersebut, bukan bukti seluruh desa tutup. Capture debug berada di `.local/visit-hours-inspection`, diabaikan Git; cookie hanya dipakai dalam memori proses dan tidak mengganti sesi bot tersimpan.
