# Inventaris API client KampungSebelah

Inventaris request gameplay lengkap ada di [katalog API client](http-gameplay-catalog.md). Panduan development tersedia di [development lokal](local-development.md).

Inspeksi 11 November 2026 WIB: bundle client dibaca sebagai teks, lalu GET dan POST terpilih diverifikasi melalui sesi pemilik akun. Source/capture awal berada di `.local/http-discovery`, diabaikan Git dan direktori mode0700. Salinan cookie inspeksi dihapus setelah verifikasi. Analisis REA bersifat statis dan graph semantik parsial; bukan bukti eksekusi seluruh route.

Bundle awal `0wwcgg-bq-sxa.js` SHA256: `29798a21c5b7a06ea883e76e804e9629f30f07bca625ded74d8356e13352d74e`. Runtime tidak mem-pin nama bundle; halaman dan configVersion aktif menentukan konfigurasi yang dibaca.

## Request KampungSebelah

Tabel ini mencakup seluruh request yang dipanggil adapter Ojol ke `https://www.kampungsebelah.com`. Kolom bukti membedakan hasil probe live sebelumnya dari pemeriksaan kode adapter saat ini.

### Mimikri Header Browser (Browser Header Mimicry)
Setiap request ke `https://www.kampungsebelah.com` kini menyertakan header browser lengkap untuk menghindari deteksi otomasi dan WAF:
1. **Identitas Browser Statis Per-Akun (`browser-identity.json`)**:
   - Setiap akun wajib memiliki 1 identitas browser (`User-Agent`, `sec-ch-ua`, `sec-ch-ua-platform`, `sec-ch-ua-mobile`) yang disimpan secara persisten di `<runtime_dir>/browser-identity.json`.
   - Header identitas ini bersifat statis permanen untuk akun tersebut dan tidak pernah berubah antar request, meniru satu instalasi browser desktop yang konsisten.
   - Pilihan profil diambil secara deterministik dari kumpulan browser desktop modern (Chrome/Edge pada Windows dan macOS) atau profil kustom yang telah ditentukan pengguna.
2. **Variasi Header Acak Per-Request**:
   - Header request yang dinamis di-generate secara acak realistis pada setiap pemanggilan API:
     - `Accept`: variasi realistis (`application/json, text/plain, */*`, `*/*`, dsb., serta `text/html` untuk halaman `/kampung` dan script untuk file `_next/static`).
     - `Accept-Language`: variasi bobot bahasa pengguna Indonesia (`id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7`, dsb.).
     - `Priority`: `u=1, i`, `u=1`.
     - `Cache-Control`: `no-cache`, `max-age=0`, dsb.
     - `Sec-Fetch-*`: `Sec-Fetch-Site: same-origin`, `Sec-Fetch-Mode`, dan `Sec-Fetch-Dest` sesuai jenis resource.
     - `Origin` dan `Referer`: `https://www.kampungsebelah.com`.

| Endpoint | Pemakaian | Bukti |
|---|---|---|
| GET `/api/ojol` | `vehicle` default, `vehicles` tersedia, `bars` dan `pakai` bersama, mitra, trip, tarif, payout/history, sisa jam narik harian (maksimal 14 jam per hari) | HTTP200 13 November 2026 dengan `vehicle: "mobil"`, `vehicles: ["motor", "mobil"]`. Update #15 tanggal 19 November 2026: batas narik maksimal 8 jam/hari. Update #16 tanggal 20 November 2026: batas narik maksimal 12 jam/hari (`narikMaksMenit: 720`). Update #17 tanggal 21-22 November 2026 (bundle `14kftr3gt-5o6.js`): batas narik harian naik menjadi 14 jam/hari (`narik_harian_menit: 840`), istirahat wajib dipersingkat 15 -> 10 menit (`istirahat_menit: 10`), batas jalan terus-menerus 3 jam (`narik_maks_menit: 180`). Konsumsi bensin dasar `bensin: 6` (rumus jarak: `2 + jarak/10`, maks 6), `kendaraan: 2`, `kuota: 4`. Aturan anti-bot `cek_kilat` (terima ongkos < 2.5 detik memicu verifikasi di setiap order). Mode kendara kini `ikut_batas_harian: true` (terhitung ke kuota 14 jam, tapi tetap bebas jeda istirahat wajib). |
| GET `/api/kendaraan` | `items[]`, termasuk `family`, `listrik`, dan `name` | Bundle `3tkrjjmq3rsag.js` dan HTTP200 13 November 2026 dengan Motor bebek dan Mobil listrik |
| GET `/api/game/me` | `balanceMilli`, `configVersion`, rumah/desa, `profile.nickname`, `profile.resting`, `profile.sleep` | HTTP200 historis; nickname dan saldo teramati lagi saat validasi Browser Harness 19 November 2026; field tidur dicocokkan dengan bundle client tersimpan pada 12 November 2026 |
| GET `/api/kebutuhan` | `asleep`, status kebutuhan aktif (`makan`, `kesehatan`, `fisik`, `rekreasi`, `kebersihan`, `wc`, `penampilan`, `bensin`, `kendaraan`, `kuota`, `rumah`), status `kondisi` (`bau`, `kebelet`, `upahPotongBps`), kuota harian `bersih` (`mandi`, `sikat`, `mandiMaks`, `sikatMaks`), dan kandidat tempat | HTTP 200 untuk status kebutuhan. Live verifikasi 23 November 2026 membuktikan `kebersihan` dan `wc`: kondisi `bau: true` dan `kebelet: true` memotong upah ojol 10% (`upahPotongBps: 1000`). Kuota mandi maks 2x dan sikat gigi maks 3x per hari. |
| GET `/api/rumah/interior` | Data interior rumah akun: `plotId`, `mandi` (level fasilitas kamar mandi), `rak` (persediaan sabun, pasta, dll.) | Bundle client `14kftr3gt-5o6.js` dan GET live terotorisasi 23 November 2026. |
| POST `/api/rumah/kamar-mandi` | Aksi kamar mandi rumah: `{"aksi": "wc"}` (buang air, mengisi wc ke 100, gratis, menghilangkan status kebelet); `{"aksi": "mandi"}` (mandi, kebersihan +65 pakai sabun / +20 tanpa sabun, maks 2x/hari, menghilangkan bau); `{"aksi": "sikat"}` (sikat gigi, kebersihan +35 pakai pasta / +10 tanpa pasta, maks 3x/hari); `{"aksi": "cuci"}` (cuci tangan, kebersihan +5); `{"beli": "sabun"|"pasta", "requestId"}` (beli persediaan rak: sabun 1 koin/10x, pasta 1 koin/15x) | Bundle client `14kftr3gt-5o6.js` dan POST live terotorisasi 23 November 2026. |
| GET `/api/time` | waktu server untuk arrival/countdown | HTTP200 |
| GET `/api/daily/house?plotId={plotId}` | Baca status kunjungan akun ke rumah kandidat; harus `visitedToday: false` | Bundle client dan HTTP200 pada 12 November 2026 |
| GET `/api/rumah/interior/lihat?plotId={plotId}` | Pastikan server mengizinkan akses rumah sekarang sebelum menawarkan kandidat mampir | Bundle client terbaru dan GET terotorisasi pada 12 November 2026: HTTP403 `FORBIDDEN` ketika tutup; HTTP200 dengan `bentuk` string dan `layout` array pada akses yang diizinkan |
| GET `/api/shops/{businessId}` | menu, item ID, priceMilli, open, mine | HTTP200 untuk SPBU/bengkel/konter |
| GET `/api/tujuan` | `usaha[]` berisi plot, koordinat, kategori, dan nama usaha yang ditampilkan di peta | GET HTTP200 dan bundle client 24 November 2026. Direktori menjadi daftar kandidat; tidak membuktikan stok atau desa. |
| GET `/api/world/plots/{plotId}?t={timestamp}` | Cocokkan ID usaha, kategori, dan desa sebelum membeli dari kandidat direktori | Bundle client dan GET HTTP200 24 November 2026. |
| GET `/kampung` | baca HTML halaman untuk menemukan bundle yang dirujuk | kode `OjolHttpApi.effects` |
| GET `/_next/static/{path}.js` | baca efek item dari bundle yang dirujuk halaman | kode `OjolHttpApi.effects` |
| POST `/api/shops/{businessId}/buy` | `{item, requestId}` | Historis: Pertalite, Tambal ban, Isi pulsa. Update #170 memindahkan pengisian tangki ke layanan SPBU; lihat catatan di bawah. |
| POST `/api/ojol` | `{action:"tawar", vehicle:"motor"|"mobil", mode:"kendara"}` | Mode kendara: meminta 3 tawaran order (`pilihan[]`) dengan `id`, `fareMilli`, `from`, `to`, `distance`. Live terverifikasi 20 November 2026. |
| POST `/api/ojol` | `{action:"ambil", vehicle:"motor"|"mobil", mode?:"kendara", pilih?:string}` | Mode otomatis: ambil order acak (`{action:"ambil", vehicle}`). Mode kendara: ambil order pilihan (`{action:"ambil", mode:"kendara", pilih: chosen_id, vehicle}`). Bot memprioritaskan tarif (`fareMilli`) paling tinggi. Live terverifikasi 20 November 2026. |
| POST `/api/ojol` | `{action:"lacak", x: float, y: float}` | Mode kendara: memperbarui posisi koordinat GPS mitra menuju titik jemput atau titik tujuan (maks laju 1.8 petak/detik). Live terverifikasi 20 November 2026. |
| POST `/api/ojol` | `{action:"jemput"}` | Mode kendara: menjemput penumpang setelah tiba dalam radius `dekat_petak` (3.5 petak) dari titik jemput (`jemput: true`). Live terverifikasi 20 November 2026. |
| POST `/api/ojol` | `{action:"selesai", kode?}` | Menyelesaikan order dan mencairkan ongkos setelah sampai di tujuan. Mode kendara mengirim `lacak` koordinat tujuan akhir sebelum `selesai`. Field `cek` trip adalah boolean (live 20 November 2026: `false` pada order biasa; `true` berarti verifikasi aktif); bila string, nilainya dipakai langsung sebagai `kode`. Bila `cek` aktif, client menampilkan gambar dari endpoint GET di bawah dan mengirim 2 angka sebagai `kode`. `selesai` tanpa verifikasi live terverifikasi 20 November 2026. |
| GET `/api/ojol/cek?t={trip.id}&a={trip.arriveAt}&m={n}` | Gambar cek pengemudi (SVG) saat `cek` trip aktif; `m` adalah nomor muat ulang gambar dari bundle client live. Dipecahkan otomatis oleh `ojol/svg_captcha_solver.py` (port MIT dari [AmireNoori/SVG-Captcha-Solver](https://github.com/AmireNoori/SVG-Captcha-Solver)); hasil bukan 2 angka atau pola tidak dikenal gagal aman tanpa mengirim `kode` salah. Bentuk respons gambar belum diamati live karena order sampel tidak memicu `cek`. |
| GET `/api/facilities/{id}` | Status, layanan, tarif, cooldown, serta bidang belajar | Browser Harness dan GET terotorisasi 19 November 2026; lihat validasi kebutuhan/belajar di bawah |
| POST `/api/facilities/{id}/use` | `{requestId}` untuk fisik; `{requestId, track}` untuk perpus/kuliah | POST live terotorisasi 19 November 2026: gym, perpus, universitas |
| GET `/api/facilities/{id}/kuis` | `available`, `visitId`, `track`, `bacaan`, `soal[].{q,options}`, `need`; selesai: `reason: selesai`, `track`, `bonus` | Browser Harness dan GET live 19 November 2026 |
| POST `/api/facilities/{id}/kuis` | `{visitId, answers: [index, ...]}` | POST live 19 November 2026: perpus 3/3 dan kuliah 5/5 benar; indeks mengikuti urutan opsi dari GET, bukan urutan bank soal |
| GET `/api/bpjs` | `rules`, `kartu` (`noKartu`, `aktif`, `sisaHari`), `gratisSisa`, `walletMilli` | GET live terotorisasi 19 November 2026 |
| POST `/api/bpjs/bayar` | `{projectId, requestId}` dengan header `Origin: https://www.kampungsebelah.com` | POST live terotorisasi 19 November 2026: kartu diterbitkan 30 hari, gratisSisa 1 |
| GET `/api/facilities/{id}/kegiatan` | `available`, `visitId`, `kind` (`tensi` \| `detak`), `plan` | GET live dan bundle client tersimpan 19 November 2026 |
| POST `/api/facilities/{id}/kegiatan` | `{visitId, stops: [...]}` untuk tensi; `{visitId, taps: [...]}` untuk detak | Bundle client modul kegiatan fasum 19 November 2026 |
| GET `/api/minigame?projectId={id}&game=gym` | `game`, `name`, `icon`, `playsLeft`, `playsPerDay`, `maxRewardMilli`, `kebutuhan: {fisik: 15}`, papan juara | Bundle client `05bjqrf9rphsk.js` (modul 751355) dan tangkapan layar antarmuka pengguna 19 November 2026 |
| POST `/api/minigame` | `{"action": "start", "projectId", "requestId", "game": "gym"}` mengembalikan `playId` dan `plan`; `{"action": "finish", "playId", "holds": [...]}` menyelesaikan latihan gym dengan efek `fisik: 15` dan hadiah kas desa. Bot menjalankan minigame ini langsung 3x sehari saat idle. | Bundle client `05bjqrf9rphsk.js`, modul kalkulasi skor `910615`, aturan kebutuhan `899117`, dan uji live 19 November 2026 |
| GET `/api/daily/garden` | Status kebun dan kolam: `now`, `gardens[]` (`id`, `kind`, `state`, `readyAt`, `cared`, `seedMilli`, dll.), `perlengkapan`, `letak`, `ukuran`, `tas` | Bundle client `0wwcgg-bq-sxa.js`, `3g13rrtpxw-ld.js`, dan GET live terotorisasi 19 November 2026 |
| POST `/api/daily/garden/{id}` | Aksi kebun/kolam: `{"action": "panen" \| "rawat" \| "tanam"}` | Bundle client `0wwcgg-bq-sxa.js` (komponen `#ks-kebun`, fungsi `a6`) dan bundle `3g13rrtpxw-ld.js` (modul 649755) |
| GET `/api/realtime/token` | Token koneksi realtime / presence client | Bundle client `0wwcgg-bq-sxa.js`, `087o49eachamv.js`, dan katalog API. Mengembalikan `{url}` token realtime; dipanggil bersama `/api/game/me` dan `/api/time` untuk menjaga status akun tetap online |
| GET `/api/diving` | Status diving Pulau Seberang: `nama`, `aktif`, `tiketMilli` (10.000 m-koin), `tabungMenit` (30 menit oksigen), `rekreasi: 30`, `mutiara` (`perHari`, `ketemu`, `dipegang`, `hargaMilli`, `langka`), `diPulau`, `bisaBeli`, `sesi` (`id`, `mulai`, `hangus`, `buka[]`) | Chunk `1j_v3n6k6p7js.js`, rules `2p8n67a_wffd0.js`, dan GET live terotorisasi 23 November 2026. |
| POST `/api/diving` | Aksi diving: `{"aksi": "masuk"}` (beli tiket 10 koin / lanjut tabung); `{"aksi": "kerang", "id", "kerang": int}` (buka kerang 0-47); `{"aksi": "jual"}` (jual mutiara ke desa, 100 koin biasa / 300 koin langka); `{"aksi": "selesai", "id"}` (selesai menyelam, +30 rekreasi); `{"aksi": "hiu", "id"}` (terkena hiu) | Chunk `1j_v3n6k6p7js.js`, rules `2p8n67a_wffd0.js`, dan GET/POST live terotorisasi 23 November 2026. |
| GET `/api/diving/realtime` | Endpoint URL realtime websocket posisi penyelam lain di perairan | Chunk `1j_v3n6k6p7js.js` |

Capture historis `/api/ojol` dalam `.local/http-discovery/ojol.json` memuat `todayCount` dan receipt `history[]` dengan `id`, `doneAt`, `kind`, `from.label`, `to.label`, serta `netMilli`. Trip aktif memuat `id` dan `arriveAt`. Adapter memakai ID receipt dan waktu server untuk rekonsiliasi, serta `netMilli` untuk ongkos diterima. Snapshot menyimpan penghitung dan riwayat yang tersedia pada respons, bukan seluruh riwayat akun. Tidak ada endpoint baru atau asumsi idempotensi POST untuk fitur ini.

Sebelum update #170, panel Ojol memakai `vehicle` sebagai default UI dan pembacaan dua katalog SPBU Utara pada 13 November 2026 menemukan `isi-daya` seharga 800 mili-koin. Temuan ini historis. Bundle lama `0xxms-_bv3y9s.js` mendefinisikan `servis-mobil` dengan efek `kendaraan: 60` dan `isi-daya` dengan efek `bensin: 70`.

### Update SPBU #170, 24 November 2026

- **GET live, tanpa transaksi:** `/api/shops/{businessId}` di SPBU Kampung Sebelah, Utara 1, Utara 2, dan Pulau Seberang 2 memberikan `spbu.plotId`; menu berisi isi angin dan minuman dingin. Pertalite, Pertamax, dan isi daya tidak muncul pada katalog tersebut.
- **GET live** `/api/spbu/{plotId}` memberi `title`, `hadir`, `tutup`, `harga`, `namaBbm`, dan `nominal`. Contoh `K36-U04` (SPBU Dusun Barat Atas) dan `Q07-U04` (SPBU Timur 2) memberi `hadir: false`, `tutup: null`, `harga: {bensin: 20, listrik: 20}` dalam mili-koin per poin, serta nominal 500, 1.000, dan 1.500 mili-koin. `GET /api/tujuan` memberi plot dan koordinat SPBU; untuk lokasi rumah akun yang diperiksa, Timur 2 paling dekat menurut jarak lurus.
- **Bukti client**, bundle `3emxdqymd4rla.js` dan `3cph-w4-q3-3f.js`: client mengambil posisi berkendara saat masuk SPBU dan memanggil layanan kedatangan sebelum isi. Konfigurasi client menyebut jarak maksimum empat petak dari tapak SPBU. Harga dihitung dari poin yang benar-benar terisi. Bensin motor dan mobil terpisah. Kode kendaraan `mobil-listrik` memakai SPKLU; kendaraan lain memakai bensin. Akun pemeriksaan memiliki Motor matic dengan `listrik: false`.
- **Bukti transaksi live (terverifikasi 24 November 2026):**
  Endpoint `POST /api/spbu/{plotId}` melayani 3 aksi:
  1. `{"aksi": "datang", "kode": string, "dorong": bool, "x": float, "y": float}`: Kedatangan di SPBU. Mengembalikan status SPBU, meter tangki saat ini, dan `hadir: true`.
  2. `{"aksi": "isi", "jumlah": "penuh" | int, "x": float, "y": float, "requestId": string}`: Eksekusi pengisian bensin. Live terverifikasi pada akun Kuki di SPBU Desa Timur 2 (`P29-U01`), mengisi 96 poin bensin dari 4% ke 100% dengan biaya 1.920 mili-koin (1,92 koin). Respons: `{"replayed":false,"item":"isi-bensin-motor","nama":"Isi bensin motor","family":"motor","bbm":"bensin","poin":96,"priceMilli":1920,"sebelum":4,"sesudah":100,"mulai":"...","selesai":"..."}`.
  3. `{"aksi": "pamit"}`: Meninggalkan SPBU (HTTP 200).
- Worker dan ekstensi dapat mengeksekusi pengisian resmi ini secara otomatis tanpa memerlukan interaksi UI manual jika koordinat SPBU terdekat valid dan kendaraan Ojol aktif teridentifikasi.
- Ekstensi juga tetap mempertahankan tombol resmi **Penuh** dan **Isi** (`panel-isi`, `jumlah-penuh`, `isi-bensin`) ketika dialog dibuka manual oleh pengguna.

Pada tanggal yang sama, katalog Bengkel motor Gotei menawarkan **Servis motor** 1.500 mili-koin dan **Servis mobil** 2.500 mili-koin. Efek client keduanya `kendaraan: 60`, sesuai bar Kondisi mesin bersama pada respons Ojol. **Konfirmasi pengguna pada 19 November 2026: Servis motor dapat dipakai untuk mobil.** Adapter tetap memasukkan item perawatan motor saat mobil aktif; planner membandingkan biaya per poin dan total biaya, lalu memverifikasi kenaikan bar setelah pembelian. Dengan efek sama +60 dan harga 1,5 vs 2,5 koin, Servis motor dipilih. Tes HTTP terisolasi `test_car_condition_prefers_lower_cost_for_same_recovery` mencakup pemilihan dan satu POST `servis-motor` saat kendaraan mobil. Konfirmasi pengguna dan tes simulasi ini dibedakan dari observasi POST live oleh agen, yang belum dilakukan untuk kasus tersebut. Batas anggaran, saldo minimum, kapasitas resource, dan pemeriksaan perubahan kendaraan tetap berlaku.

## Bukti dan Alur Mode Berkendara / Kendarai Sendiri (Update 20-22 November 2026)

Inspeksi client bundle `3txiswhto39cq.js` dan bundle terbaru `14kftr3gt-5o6.js` (audit Eka 21-22 November 2026) membuktikan perkembangan aturan **Kendarai Sendiri** (`mode: "kendara"`):
1. **Konfigurasi Server/Client (`config.kendara`)**:
   - `enabled: true`
   - `laju_maks: 1.8` (kecepatan perpindahan koordinat maksimal 1.8 petak per detik)
   - `dekat_petak: 3.5` (radius maksimal penjemputan dan penurunan dari target)
   - `naik_detik: 8`, `turun_detik: 8`
   - `lacak_detik: 5`, `lacak_basi_detik: 45`
   - `tanpa_batas: true`: **Penting** — order mode kendara **bebas dari aturan istirahat wajib 10 menit** (`istirahat_menit: 10`).
   - `ikut_batas_harian: true` (Update 21-22 Nov 2026): Order mode kendara kini ikut dihitung ke batas kuota narik harian **14 jam per hari** (`narik_harian_menit: 840`, reset 00.00 WIB); durasi order yang dihitung adalah dari ambil sampai selesai (maksimal `hitung_maks_menit: 15` per order).
   - `jemput_asal_menit: 30`: Penumpang paling cepat naik setelah jarak lurus dari posisi awal (lokasi order sebelumnya bila selesai < 30 menit lalu, selain itu rumah) dibagi `laju_maks`.
   - `pesanan_maks_menit: 10`: Pesanan warga wajib diselesaikan dalam 10 menit sejak diambil agar tidak dialihkan ke Mitra Ojek Desa.
   - `gerak_petak: 0.5`, `luar_jalan_maks: 0.2`: Server mengecek jejak jalan koordinat (minimal gerak 0.5 petak per laporan dan di luar jalan maksimal 20%).
2. **Aturan Anti-Bot `cek_kilat` (Update 21-22 Nov 2026)**:
   - `cek_kilat_detik: 2.5`, `cek_kilat_dari: 6`, `cek_kilat_min: 5`.
   - Bila pengemudi menerima ongkos kurang dari 2.5 detik setelah sampai pada $\ge 5$ dari 6 order terakhir, server menandai akun dan memicu cek verifikasi (Turnstile / SVG 2 angka) pada **SETIAP ORDER**.
   - Mitigasi: Bot/ekstensi wajib menerapkan human jitter dan menunda klaim ongkos minimal $\ge 2.8$ detik setelah tiba (`arrived`).
3. **Siklus Pemanggilan API**:
   - `POST /api/ojol {"action": "tawar", "vehicle": "mobil", "mode": "kendara"}`: Server merespons `pilihan[]` berisi 3 order dengan rincian `id`, `fareMilli`, `warga`, `from`, `to`, dan `distance`. Bot memprioritaskan order dengan `fareMilli` tertinggi.
   - `POST /api/ojol {"action": "ambil", "mode": "kendara", "pilih": "<chosen_order_id>", "vehicle": "mobil"}`: Server merespons status `trip` dengan `mode: "kendara"` dan `jemput: false`.
   - `POST /api/ojol {"action": "lacak", "x": from.x, "y": from.y}`: Memperbarui posisi koordinat mitra ke titik penjemputan.
   - `POST /api/ojol {"action": "jemput"}`: Menjemput penumpang; server merespons `jemput: true` dan menghitung waktu kedatangan `arriveAt`.
   - `POST /api/ojol {"action": "lacak", "x": to.x, "y": to.y}`: Memperbarui posisi koordinat mitra ke titik tujuan.
   - `POST /api/ojol {"action": "selesai"}`: Dipanggil setelah server `arriveAt` tercapai (ditambah jeda aman $> 2.5$ detik anti cek kilat) untuk mencairkan ongkos (`netMilli`) ke dompet koin dan menambah `todayCount`. Bila `cek` trip aktif, `selesai` mengirim `kode` 2 angka hasil pemecahan otomatis gambar SVG cek.
4. **Konfigurasi Akun & Default**:
   - `Settings.ojol_mode`: pilihan `"kendara"` (default) atau `"otomatis"`.
   - Jika `ojol_mode == "kendara"`, otomatisasi melakukan siklus penawaran (memilih tarif tertinggi) dan penjemputan/pengantaran.
   - Jika mode kendara menghasilkan daftar penawaran kosong atau fallback diperlukan, sistem beralih ke mode otomatis reguler.

## Bukti jadwal tidur

Pemeriksaan statis 12 November 2026 pada bundle tersimpan `1xhiowffvsf0w.js` (SHA256 `68d239f92244dcce98cafdb2adc431866082dbab780005a55f0d7370cd266f3e`) menemukan form `ks-sleep-from` / `ks-sleep-to` dan label **Jam tidur (WIB)** / **Jam bangun (WIB)**. Client membaca `me.profile.sleep.{auto,from,to,inSchedule}`; `from` dan `to` adalah menit sejak tengah malam. Nilai awal form 1320 / 300 setara 22.00 / 05.00 dan bukan bukti jadwal aktif setiap akun. Client memakai `me.profile.resting` untuk status tidur aktual dan menawarkan tombol Bangun/Tidur kapan saja. `inSchedule` dapat tetap true saat karakter sudah dibangunkan manual.

Capture historis `.local/http-discovery/me.json` memuat bentuk yang sama: `resting: false` dan `sleep: {auto: false, from: 1320, to: 300, inSchedule: false}`. Capture ini tidak membuktikan konfigurasi akun saat ini.

Verifikasi live read-only 12 November 2026 pukul 02.51–02.53 WIB memakai sesi yang diberikan pengguna. Tiga pembacaan terpisah mengonfirmasi `sleep: {auto: true, from: 120, to: 300, inSchedule: true}`, yaitu **02.00–05.00 WIB** untuk akun yang diperiksa. `profile.resting` dan `kebutuhan.asleep` sama-sama true; parser worker menghasilkan `phase: sleeping` dan batas berikutnya 05.00 WIB. Satu siklus controller dengan dua snapshot live, terpisah sekitar 10 detik, tetap di `stage: sleeping` / `event: tidur` dan tidak membuat aksi ledger. Seluruh verifikasi berisi 20 GET dan nol POST. Cookie sementara dihapus; laporan tanpa cookie disimpan privat di `.local/sleep-inspection/live-verification.json`, diabaikan Git. Pergantian status pada 05.00 belum diamati langsung; batas waktu dan kelanjutan setelah bangun diuji dengan simulasi terisolasi.

Worker membaca jadwal akun pada setiap snapshot dan menghitung batas berikutnya dengan `GET /api/time.now` dalam `Asia/Jakarta`, termasuk lintas tengah malam. Waktu sejak snapshot diterima dihitung dengan jam monotonic agar waktu tunggu tidak melewati batas jadwal yang sudah diketahui. Di batas itu worker membaca ulang status, dan selama tidur memeriksa berkala sesuai `idle_poll_seconds`. Status tidur dari salah satu `kebutuhan.asleep` atau `profile.resting` menahan semua transaksi; jam jadwal sendiri tidak menimpa status bangun manual. Perubahan tepat di antara GET terakhir dan POST tetap tunduk pada keputusan server, dan hasil transaksi belum pasti tetap memerlukan bukti sebelum dilanjutkan.

Tombol mata memanggil onLook → centerOn + pembukaan panel. Panel membaca detail plot lalu katalog. Tombol Pergi memakai POST `/api/tujuan`; core HTTP tidak mengirim endpoint tersebut. Adapter membaca katalog berdasarkan ID toko tetap di `ojol/shop_locations.py`. Pembelian service sendiri dapat mempunyai efek tampil di toko yang ditentukan server, sama seperti Beli dari preview browser.

Auto Kebutuhan memeriksa cabang Akademis.ai terdaftar dan kandidat bermerek dalam direktori untuk desa akun. Rotasi mendahulukan cabang yang paling lama tidak memiliki pembelian terverifikasi, selama produknya memenuhi anggaran dan kebutuhan. Cadangan baru dicari jika pemeriksaan berhasil dan tidak ada produk Akademis.ai yang tersedia. Cadangan berada di desa yang sama dan maksimal 60 petak dari rumah berdasarkan jarak lurus. Katalog cadangan diperiksa bertahap mulai dari yang terdekat. Adapter memeriksa ulang prioritas dan produk sebelum POST.

Efek resource Ojol dibaca dari konfigurasi JSON dalam bundle, misalnya `pulsa` untuk kuota. Untuk kebutuhan, adapter memakai `menu[].rasa.isi` bila tersedia dan konfigurasi `barang` sebagai fallback; efek tambahan fasilitas dibaca dari `fasum`. Pembelian kebutuhan memakai katalog toko Akademis.ai terdaftar dan menyaring layanan atau barang yang langsung dipakai menurut client. Cache diikat ke configVersion dan versi skema parser kebutuhan. Sebelum validasi 19 November di bawah, pembelian kebutuhan dan pemakaian fasilitas baru diverifikasi di simulasi HTTP; GET live saat itu mengembalikan HTTP 503.

Client helper memakai JSON body, sesi cookie same-origin dan tidak menambahkan token CSRF khusus pada request game yang teramati. Form import aplikasi tetap memakai CSRF sendiri. HTTP adapter mengirim Origin/Referer game, memvalidasi sesi lewat GET, menolak redirect serta error auth; tidak mencoba melewati login atau challenge.

Keterbatasan: endpoint internal bisa berubah, tidak membuktikan kontrak API publik. Tidak menyimpulkan idempotensi endpoint Ojol dari adanya requestId pada pembelian; semua POST tetap satu kali. Perubahan harga/efek/resource dan error auth tetap menahan transaksi; hasil belum pasti direkonsiliasi tanpa mengulang POST. Runtime kini hanya adapter HTTP; kegagalan terminal menghentikan akun tanpa fallback browser.

## Validasi kebutuhan dan belajar 19 November 2026

Pemeriksaan nilai kebutuhan read-only **19 November 2026, 10.20 WIB** memakai GET katalog, detail fasilitas, detail plot dan konfigurasi client aktif; **nol POST**. Capture privat: `.local/needs-value-audit-20261119/`. Katalog makanan menyediakan `menu[].rasa.isi`, yaitu efek sesuai selera akun/dapur; gunakan nilai ini bila tersedia, dengan validasi integer 0–100 untuk kebutuhan yang dikenal, dan konfigurasi `barang` sebagai fallback saat field tidak tersedia. Contoh akun pemeriksaan: Mi instan Sembako 400 mili memberi makan +24, sedangkan Mi instan Warung Jajan 400 mili memberi makan +36 dan rekreasi +5. Efek ini bisa berbeda antar akun dan waktu.

GET plot dan katalog mengonfirmasi dua pemasok makan tambahan Desa Utara (juga diperiksa untuk rekreasi bersama Restaurant, karena efek makanan mencakup rekreasi): **Akademis.ai Warung Jajan**, `K22-U10`, `kios`, ID `e42f8d13-2911-4d21-b499-e608f43dedaf`; **Akademis.ai Pecel Lele & Ayam**, `O39-U01`, `lamongan`, ID `88b0c25a-1297-4c41-88b1-4c7df5e887e0`. Keduanya buka dan bukan milik akun pemeriksaan. Kepemilikan, nama, buka, stok, harga dan efek tetap dibaca ulang sebelum pembelian.

Konfigurasi `fasum` di bundle aktif `3jnzibg21c0eb.js` memuat Gym desa: fisik +55/kesehatan +15; Kolam renang: fisik +50/rekreasi +15. GET detail keduanya menawarkan tarif 2.000 mili. Kandidat fisik tetap menentukan efek primer; efek sekunder hanya dipakai jika item fasilitas dan kenaikan primer cocok dengan konfigurasi. Gym sedang cooldown pada pemeriksaan ini. Ranking membandingkan biaya per jumlah kenaikan yang benar-benar muat sampai 100 pada seluruh kebutuhan terbaca, setelah penyaringan Akademis.ai dan anggaran. Efek durasi, bonus upah, dan optimasi rangkaian belanja tidak diberi nilai koin.

Pengguna mengizinkan Browser Harness dengan cookie sementara, kemudian secara eksplisit mengizinkan pembelian live. Cookie dipisahkan dalam konteks browser sementara; sesi bot tersimpan tidak diganti. Capture privat di `.local/needs-learning-inspection/`, diabaikan Git.

Pembelian **Pipa paralon** di Akademis.ai Bangunan (`K40-U01`) seharga 800 mili-koin berhasil: rumah 40 → 60, saldo turun tepat 800. Respons POST memuat `eaten: true` dan `kebutuhan.gains.rumah: 20`, walaupun katalog memberi `service: false`. Efek bahan juga terbukti pada bundle `3jnzibg21c0eb.js`: paku-semen +25, cat-tembok +40, pasir +15, bata +20, pipa +20. Pemeriksaan preview source lokal berhasil membaca kelima produk tersebut; kegagalan rumah pada deployment sebelumnya belum direproduksi.

**Gym desa 2** (`296dc278-b765-4caf-9349-469385d6fc03`) berharga 2.000 mili-koin, bukan gratis. Satu POST menaikkan fisik 31 → 86 dan kesehatan 67 → 82; receipt menyertakan `id`, `projectId`, `requestId`, `priceMilli`, `startedAt`, `visitUntil`, `ledgerTxId`, dan `kebutuhan.gains`. GET menawarkan `nextAt` untuk cooldown 12 jam. Fasilitas dipilih dari kandidat `places` kebutuhan fisik dan tarif harus cocok lagi sebelum transaksi.

**Perpustakaan desa** (`90ae44da-6d71-495d-83f7-5b0b69400504`, varian `perpustakaan-desa-t6`) gratis; **Universitas** (`0fb7ae51-34da-434e-a04f-050b0dd82f9b`) berharga 4.000 mili-koin. Keduanya memakai `track: administrasi` dalam validasi live. Perpus menghasilkan kunjungan dan kuis 3/3 benar, universitas 5/5 benar. Administrasi naik 2 → 3 → 4. `studySessions` positif menandai layanan belajar; `studyTracks` dapat membatasi bidang. Bidang harus mempunyai `next`, tanpa `pending`, dan `next.library` bukan false, sesuai guard UI. Keduanya dapat dipakai sekali sehari secara terpisah. GET setelah kunjungan mengembalikan `nextAt: 2026-11-20T00:00:00.000Z`; gunakan waktu server tersebut, jangan mengasumsikan reset tengah malam WIB dari teks UI.

Bundle aktif `087o49eachamv.js` memuat bank bacaan/soal/opsi benar di konfigurasi JSON `facilities` dan `tracks`. Komponen lazy `26kxp4sri85ut.js` (SHA256 `9cbdb73b09dffbd1fbbcfcb0277059d71ecfdce408ab1c611fae52f213537155`) membaca endpoint kuis, menampilkan bacaan selama enam detik, lalu mengirim satu array indeks jawaban bersama `visitId`. GET kuis tersedia mengikat soal ke kunjungan tersebut; setelah submit, GET memberi `available: false`, `reason: selesai`, bidang dan bonus. Kuis diperlakukan sebagai satu kesempatan per kunjungan; POST tidak diputar ulang setelah timeout. Harga, sesi, dan kuis yang diamati adalah bukti akun/waktu tersebut, bukan kontrak tetap untuk seluruh fasilitas.

Probe transaksi lokal dilakukan setelah pengguna menghentikan worker production, melalui worker → adapter HTTP tanpa Chromium. Lima aksi (klaim, tiga pembelian, ambil) tercatat verified pada ledger lokal, tanpa pending/uncertain. Sesuai instruksi pengguna, probe sementara melewati planner threshold dan mengizinkan efek pembelian terpotong di100%, dengan anggaran maksimal2koin dan saldo minimum20. Pengecualian hanya pada proses probe sementara; guard source production tidak diubah. Script bypass dan salinan cookie dihapus setelah proses berhenti. Bukti finansial/account tetap privat di `.local/live-verification/report.json` dan ledger lokal, tidak dikomit.

## Bukti BPJS dan pemeriksaan kesehatan gratis (Puskesmas / Rumah Sakit)

Verifikasi live terotorisasi 19 November 2026:
- **Pengecekan dan Pembelian BPJS**: `GET /api/bpjs` mengembalikan konfigurasi iuran (`iuranMilli: 5000` / 5 koin), masa aktif (`masaHari: 30`), kuota gratis periksa (`gratisPerHari: 1`), sisa gratis hari ini (`gratisSisa`), dan kartu aktif (`kartu`). Jika kartu belum ada atau tidak aktif, pembelian dilakukan via `POST /api/bpjs/bayar` dengan `{projectId, requestId}` ke Kantor BPJS terdekat di desa akun (misal `5149bd70-4b0b-4b4e-be2e-839b7099f8dc` untuk Desa Utara). Header `Origin: https://www.kampungsebelah.com` wajib disertakan untuk lolos proteksi CSRF. Verifikasi live menghasilkan kartu `0001197727537` dengan `aktif: true`, `sisaHari: 30`, dan `gratisSisa: 1`.
- **Prioritas Pemeriksaan Kesehatan Gratis**: Jika BPJS aktif dan `gratisSisa > 0`, bot memprioritaskan pemeriksaan 1x gratis di fasilitas kesehatan (Puskesmas atau Rumah Sakit) yang telah berstatus `DONE` dan tidak sedang cooldown (`nextAt` kosong). Pemanggilan `POST /api/facilities/{id}/use` mengonsumsi kuota gratis (`priceMilli: 0`).
- **Minigame Fasilitas Kesehatan**: Setelah `/use`, endpoint `GET /api/facilities/{id}/kegiatan` mengembalikan minigame interaktif. Modul client `13458` (`0wwcgg-bq-sxa.js` modul `895979`) mengonfirmasi format payload:
  - **Puskesmas (`kind: "tensi"`)**: Mengirim array `{visitId, stops: [...]}` di mana setiap elemen bernilai `round(lead_ms + period * 0.25)` untuk menghasilkan rasio ideal 0.5 (tekanan darah normal 120/80 pada zona hijau tensimeter).
  - **Rumah Sakit (`kind: "detak"`)**: Mengirim array `{visitId, taps: [...]}` dengan timestamps ketukan yang mencocokkan timestamps target `beats` dari GET `/kegiatan`.
  - Penyelesaian minigame memberikan bonus peningkatan kesehatan (`bonusGains.kesehatan`).
- **Fallback Toko Obat**: Jika kuota periksa gratis harian sudah habis (`gratisSisa: 0`) atau fasilitas sedang cooldown, tetapi nilai kesehatan masih di bawah ambang batas (`threshold`), bot otomatis melanjutkan pembelian obat ke toko obat (Akademis Farma atau cadangan toko obat).

## Bukti minigame fasilitas angkat beban (Gym desa / Gym mini desa)

Verifikasi statis bundle client dan tangkapan layar antarmuka pengguna 19 November 2026:
- **Ketersediaan dan Kuota**: `GET /api/minigame?projectId={id}&game=gym` mengembalikan status minigame angkat beban (`game: "gym"`, `name: "Angkat beban"`, `playsLeft: 0..3`, `playsPerDay: 3`, `maxRewardMilli: 1000`, `kebutuhan: {fisik: 15}`).
- **Bypass Cooldown Layanan**: Minigame angkat beban tetap aktif (`Main sekarang (sisa 3x)`) dan dapat dimainkan meskipun layanan utama gym sedang mengalami cooldown (`nextAt` aktif).
- **Gratis dan Efek Kebutuhan**: Minigame tidak memungut biaya koin (`priceMilli: 0`) dan memberikan pemenuhan fisik +15 serta potensi hadiah koin dari kas desa.
- **Mekanisme Permainan dan Observasi Live 19 November 2026**:
  - `POST /api/minigame` dengan `{"action": "start", "projectId", "requestId", "game": "gym"}` mengembalikan `playId` dan objek `plan: {"reps": [...]}` (8 repetisi dengan properti `fill`, `center`, `half`).
  - Berdasarkan modul scoring `910615`, waktu tahan ideal tiap repetisi adalah `hold = round(fill * center)` untuk menghasilkan hasil angkatan `sempurna` (2 poin/rep, total 16 poin max score).
  - Jeda simulasi waktu fisik per repetisi dijalankan sebelum mengirimkan hasil untuk menghindari penolakan backend `Permainan tidak sah (terlalu cepat)`.
  - `POST /api/minigame` dengan `{"action": "finish", "playId", "holds": [...]}` diverifikasi live berhasil 100% sempurna (skor 16, reward 960 milli-koin, pemenuhan fisik +15).
  - Fasilitas gym terdaftar permanen dalam `GYM_FACILITIES_BY_VILLAGE` agar selalu dievaluasi pada kebutuhan fisik tanpa bergantung batas radius 3 tempat terdekat dari `/api/kebutuhan`.
  - Prioritas auto kebutuhan fisik: Minigame "Angkat beban" > Fasilitas Gym berbayar > Fasum olahraga lainnya.
  - Prioritas auto kebutuhan kesehatan: Pemeriksaan BPJS Puskesmas/Rumah Sakit (minigame tensi/detak) > Toko Obat.
  - Prioritas auto kebutuhan makan: SPPG Makan Bergizi Gratis (minigame nampan) > Warung / Restoran berbayar.
  - Prioritas auto kebutuhan rekreasi: Fasum Rekreasi Gratis (Alun-alun & Taman Desa minigame foto) > iCafe / Kafe berbayar.

## Bukti SPPG (Dapur Makan Bergizi Gratis) & Minigame Nampan

Verifikasi bundle client `0wwcgg-bq-sxa.js` (modul `895979`), `087o49eachamv.js`, dan katalog fasilitas 19 November 2026:
- **Karakteristik Layanan**:
  - Fasilitas SPPG terdaftar per desa dalam `SPPG_FACILITIES_BY_VILLAGE` (Desa Utara: `04f36c8b-f2a6-4d24-945c-a0b62540cb56`, `a8d496e4-9d2d-46b8-860a-a54ea73d253d`; Kampung Sebelah: `c30281d2-de01-4fdc-a7a2-20aa039112a0`, `e21259ea-3a4e-4d16-8287-dbb1d989e6bf`, `f4b29614-e075-4af6-9962-f37853e71958`; Pulau Seberang: `a2c2d43b-d560-4a0d-a393-aa6ae71877b9`).
  - Biaya: **Gratis (`price_milli: 0`)**.
  - Jam Operasional: `06:00-14:00`.
  - Cooldown: **24 jam (1x sehari)** via field `nextAt` dan `myVisitUntil`.
  - Efek Layanan: `{"makan": 60, "kesehatan": 5}` dan bonus upah kerja +3% (`wage_bonus_bps: 300`) selama 24 jam.
- **Alur Penggunaan**:
  - `POST /api/facilities/{id}/use` dengan `{"requestId": request_id}` untuk memulai kunjungan makan bergizi.
  - `GET /api/facilities/{id}/kegiatan` mengembalikan minigame `kind: "nampan"` dengan daftar makanan `plan.items`.
  - `POST /api/facilities/{id}/kegiatan` mengirimkan payload `{"visitId": visit_id, "picks": [...]}` berisi 5 makanan bergizi seimbang dari 5 kelompok (pokok, lauk, sayur, buah, susu) tanpa junk food (mi instan, gorengan, es sirup, permen).
  - Skor sempurna memberikan tambahan bonus kebutuhan: `{"makan": 10, "kesehatan": 5}`.

## Bukti Fasum Rekreasi (Alun-alun, Taman Desa) & Minigame Foto

Verifikasi bundle client `0wwcgg-bq-sxa.js` (modul `895979`), `kegiatan_fasum.js` (modul `13458`), dan `world-full.json` 19 November 2026:
- **Karakteristik Layanan Rekreasi Gratis**:
  - Fasilitas terdaftar per desa dalam `RECREATION_FACILITIES_BY_VILLAGE`:
    - **Alun-alun**: `price_milli: 0` (gratis), efek `{"rekreasi": 30, "fisik": 10}`, bonus upah kerja +3% selama 24 jam, cooldown 24 jam (1x sehari), jam buka 05:00–23:00.
    - **Taman Desa**: `price_milli: 0` (gratis), efek `{"rekreasi": 20}` (tier 0) s/d `{"rekreasi": 20}` + bonus upah tier 1–6, cooldown hanya 1 jam (`cooldown_hours: 1`).
- **Alur & Solver Minigame Foto (`kind: "foto"`)**:
  - Setelah `POST /api/facilities/{id}/use`, endpoint `GET /api/facilities/{id}/kegiatan` mengembalikan minigame `kind: "foto"` dengan `plan.periods: [...]` (array 3 periode dalam ms) dan `plan.scene`.
  - Objek bergerak bolak-balik melintasi bingkai kamera dengan formula posisi gelombang segitiga:
    $$\text{posisi } p = 2i \quad (\text{bila } i < 0.5) \quad \text{atau} \quad 2 - 2i \quad (\text{bila } i \ge 0.5)$$
    di mana $t = (\text{shot} - \text{lead\_ms}) / \text{period}$ dan $i = t - \lfloor t \rfloor$.
  - Objek tepat di tengah ($p = 0.50$, deviasi 0.0) saat waktu jepretan:
    $$\text{shot} = \text{lead\_ms} + \text{round}(0.25 \times \text{period})$$
    dengan `lead_ms = 600`.
  - `POST /api/facilities/{id}/kegiatan` dengan payload `{"visitId": visit_id, "shots": [...]}` menghasilkan skor sempurna 6/6 dan bonus kartu foto kenangan serta tambahan **$+10$ rekreasi**.

## Bukti status dan presence online

Verifikasi client bundle `0gw8r7_0xl80t.js`, `2suhvd2g415c_.js` (modul `309513`), dan `087o49eachamv.js` (modul `129929`):
- **Parameter Presence Client**:
  - `presenceWriteSec: 45`
  - `onlineWindowSec: 120`
- **Mekanisme Penentuan Online**:
  - Client menentukan status "Online" bila selisih waktu sekarang dengan aktivitas terakhir (`lastOnlineAt`) tidak melebihi `onlineWindowSec` (120 detik). Jika lebih, status turun menjadi "Aktif X mnt lalu" atau "Lama tidak online".
  - Status online warga di peta direpresentasikan oleh flag boolean `t.w.o` (online) pada plot kavling (`/api/world/plots`).
- **Strategi Pemeliharaan Presence Online**:
  - Endpoint `GET /api/game/me` dan `GET /api/time` (didampingi `GET /api/realtime/token`) memperbarui timestamp aktivitas akun pada server.
  - Adapter `OjolHttpApi.fetch_online_status()` dipanggil secara berkala ($\le 35$ detik) baik oleh worker aktif (termasuk saat menunggu trip countdown/tidur/idle) maupun oleh supervisor multi-akun `MultiAccountService` untuk semua akun terdaftar, sehingga setiap akun selalu berada dalam status presence online tanpa terputus.




## Bukti laporan harian

Pada 11 November 2026 WIB, pembacaan lokal terotorisasi untuk dua halaman `GET /api/me/koin` berhasil. Respons berisi `items` dan cursor `next`. Query `after` menerima cursor dari halaman sebelumnya. Baris memiliki `id`, `at` dengan zona waktu, `amountMilli` bertanda, `type`, `label`, dan `detail`. Dua halaman yang diperiksa berurutan dari terbaru ke terlama.

Payout Ojol memiliki `type: OJOL_ONGKOS`. Pembelian yang terlihat memakai `SHOP_PURCHASE` dan tidak memberi penanda yang cukup untuk mengaitkan biaya manual ke Ojol. Bot menghitung pendapatan dari penanda payout dan mengestimasi laba dengan mengurangi belanja yang nama produknya cocok persis dengan daftar produk worker setelah normalisasi kapital dan spasi. Estimasi menganggap semua pembelian produk yang cocok sebagai biaya Ojol. Jurnal tetap menyediakan biaya worker terverifikasi. Lihat [rujukan client riwayat koin](http-gameplay-catalog.md#profil-perbankan-dan-pembayaran).

## Inventaris Akademis.ai

Pemeriksaan ulang read-only **19 November 2026, 09.58 WIB** melalui `GET /api/tujuan` (HTTP200) menemukan **26 usaha bernama Akademis.ai dari 1.146 usaha** yang terlihat oleh sesi, mencakup **22 jenis usaha**. Pencocokan memakai substring `akademis.ai` tanpa membedakan kapital. Nama, plot, jenis, dan pemilik pada tabel berasal dari direktori saat pemeriksaan; stok/harga tidak diperiksa ulang dalam inventaris ini.

Katalog pembanding adalah **39 jenis usaha aktif** (`category: usaha`, `mechanic: business`, `status: active`) dari bundle client `0q9be105b3nja.js`, diambil ulang pada pemeriksaan ini. GET `/api/game/me` mengembalikan `configVersion: file-1.0` dan 38 jenis pada `catalog.business` untuk akun pemeriksaan. Capture direktori, katalog, SHA256 sumber, dan hasil perbandingan tersimpan privat di `.local/akademis-inventory-20261119/`, diabaikan Git. Cookie tidak disimpan pada artefak.

Catatan 11 November memuat 19 kecocokan dari 782 usaha. Ada **tujuh lokasi tambahan** terhadap catatan tersebut: Venture, Marine, Pecel Lele & Ayam, Rumah Makan, Warung Jajan, Hutan Pohon Kayu B, dan Motor di `F35-U01`. Ini tambahan pada hasil inventaris; waktu pembangunannya tidak disimpulkan dari perbandingan. Nama di `C75-B4-1` sekarang **Akademis.ai Sawah**, sebelumnya tercatat Akademis.ai Sabe.

| Nama di direktori | Plot | Kategori | Pemilik di direktori |
|---|---|---|---|
| Akademis.ai - Kebun Ziraf | `Q42-B2-1` | `kebun-kopi` | Ziraf |
| Akademis.ai - Motor | `F35-U01` | `bengkel-motor` | Williamw1293 |
| Akademis.ai - Ziraf Kopisop | `H35-U03` | `kedai-kopi` | Ziraf |
| Akademis.ai Bangunan | `K40-U01` | `toko-bangunan` | Williamw1293 |
| Akademis.ai Barbershop | `K40-U07` | `barbershop` | Yumika |
| Akademis.ai Coffee | `K40-U09` | `coffee-shop` | yakis |
| Akademis.ai Coffee Farm | `C75-B3-1` | `kebun-kopi` | Williamw1293 |
| Akademis.ai Farm | `C80-B4-1` | `sapi-perah` | Pokonyang |
| Akademis.ai Farma | `K40-U06` | `toko-obat` | Yumika |
| Akademis.ai GamingHouse | `B37-U07` | `warnet` | jeta |
| Akademis.ai Hutan Pohon Kayu B | `B73-B4-1` | `hutan-produksi` | Yumika |
| Akademis.ai iCafe | `K39-U04` | `warnet` | jeta |
| Akademis.ai Konter | `O38-U06` | `konter-pulsa` | Yumika |
| Akademis.ai Marine | `P17-D17` | `kapal-nelayan` | Williamw1293 |
| Akademis.ai Motor | `K40-U03` | `bengkel-motor` | Williamw1293 |
| Akademis.ai MyAnabul | `C08-U07` | `pet-shop` | jeta |
| Akademis.ai Pecel Lele & Ayam | `O39-U01` | `lamongan` | Yumika |
| Akademis.ai Restaurant | `K40-U04` | `restoran` | Williamw1293 |
| Akademis.ai Sawah | `C75-B4-1` | `sawah` | anunyakamu |
| Akademis.ai Sembako | `K40-U08` | `cek ` | anunyakamu |
| Akademis.ai Tahu Tempe | `O37-U09` | `pabrik-tahu` | Yumika |
| Akademis.ai Venture | `P17-D04` | `kapal-nelayan` | Yumika |
| Akademis.ai Warung Jajan | `K22-U10` | `kios` | Yumika |
| Bidan Akademis.ai | `Q36-U09` | `praktik-bidan` | Pokonyang |
| PT Akademis.ai Sawit | `H77-B4-1` | `kebun-kelapa` | yakis |
| Rumah Makan - Akademis.ai | `G05-U07` | `rumah-makan` | Williamw1293 |

### Jenis usaha yang ditawarkan untuk dibeli dan belum terdeteksi dimiliki Akademis.ai

Dengan filter hanya jenis yang **ditawarkan pada `catalog.business` akun pemeriksaan**, ada **16 dari 38 jenis** yang belum tercakup pada usaha bernama Akademis.ai. Pemeriksaan tambahan terhadap seluruh usaha milik tujuh nickname pemilik pada tabel (jeta, Yumika, Ziraf, yakis, anunyakamu, Williamw1293, Pokonyang) juga tidak menemukan jenis yang kosong ini dengan nama usaha lain. Cakupan kepemilikan mengikuti pemilik yang terlihat pada direktori; akun tim lainnya dan usaha yang belum muncul di direktori belum terverifikasi. Katalog membuktikan jenis yang ditawarkan; kelayakan lahan, kuota, saldo, dan persyaratan pembelian tiap akun tidak diuji dengan transaksi.

| Jenis usaha | ID katalog | Jumlah terlihat di direktori |
|---|---|---:|
| Kebun rempah | `kebun-rempah` | 5 |
| Kebun tebu | `kebun-tebu` | 3 |
| Kebun sayur | `ladang-sayur` | 4 |
| Minimarket | `minimarket` | 23 |
| Pabrik batako | `pabrik-batako` | 6 |
| Pabrik es | `pabrik-es` | 8 |
| Pabrik pakan ternak | `pabrik-pakan` | 17 |
| Pabrik tepung & mi | `pabrik-tepung` | 31 |
| Percetakan | `percetakan` | 11 |
| Peternakan ayam | `peternakan-ayam` | 21 |
| Peternakan lele | `peternakan-lele` | 9 |
| Spa | `spa` | 11 |
| Tambang pasir & batu | `tambang-pasir` | 4 |
| Toko pakaian | `toko-pakaian` | 19 |
| Toko perabot | `toko-perabot` | 30 |
| Warung | `warung` | 19 |

SPBU Pertamina dikeluarkan dari daftar pembelian di atas karena tidak muncul pada `catalog.business` akun pemeriksaan. Jenis ini tetap ada pada bundle client dan 14 entri direktori, seluruhnya tanpa kecocokan nama/pemilik Akademis.ai pada pemeriksaan ini; syarat untuk membukanya belum diverifikasi. Semua jenis pada tabel di atas ada di `catalog.business` saat pemeriksaan. Jumlah direktori mencatat usaha yang terlihat, bukan bukti stok, profitabilitas, atau izin mendirikan usaha baru.

## Aksi adapter Ojol

Worker memanggil [`ojol/http_api.py`](../ojol/http_api.py) langsung melalui adapter [`ojol/ui.py`](../ojol/ui.py); tidak ada lagi stdio MCP di antara worker dan API. Nama aksi pada tabel berikut dipertahankan sebagai label seam pengujian `HttpUI.call_tool`.

| Tool | Parameter | Hasil atau aksi |
|---|---|---|
| `ojol_snapshot` | Tanpa parameter | Baca saldo, resource, trip, dan riwayat |
| `ojol_preview_shop` | `resource` (`fuel`, `condition`, `data`, `makan`, `kesehatan`, `fisik`, `rekreasi`, `penampilan`, atau `rumah`) | Baca katalog toko tetap untuk desa dan resource akun, atau fasilitas gratis untuk fisik |
| `ojol_purchase` | `product`, `expected_wallet`, `expected_resource`, `min_balance`, `request_id` | Validasi katalog dan snapshot terbaru, lalu beli satu item |
| `ojol_job_action` | `kind` (`search` atau `complete`) | Ambil order atau klaim trip yang sudah tiba |
| `ojol_study_status` | `mode` (`perpus` atau `kuliah`) | Baca fasilitas terdaftar untuk desa akun, bidang, cooldown dan kuis kunjungan |
| `ojol_study_start` | `mode`, `track`, `expected_price`, `expected_wallet`, `min_balance`, `request_id` | Satu kunjungan setelah opt-in dan validasi ulang bidang/harga/saldo; mengembalikan receipt server |
| `ojol_study_quiz` | `mode`, `visit_id`, `track` | Baca ulang kuis kunjungan, cocokkan soal/opsi dengan bank bacaan client, submit satu kali |

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

## Kebun & kolam

Inspeksi statis bundle `0wwcgg-bq-sxa.js` (komponen UI `#ks-kebun`, fungsi `a6`) dan `3g13rrtpxw-ld.js` (modul 649755) serta GET live 19 November 2026:
- `GET /api/daily/garden` menghasilkan objek `{now, gardens: [...], perlengkapan, letak, ukuran, tas}`.
- Elemen dalam `gardens` mencakup `id`, `kind` (`"kebun-sayur"` | `"kolam-ikan"`), `label`, `icon`, `state`, `seedMilli`, `growHours`, `readyAt`, `cared`, `careLabel`, `plantLabel`, `item`, `yield`, dan `caredYield`.
- Siklus state kebun:
  1. `"siap"`: Hasil kebun/kolam sudah matang dan siap dipanen. Request `POST /api/daily/garden/{id}` dengan body `{"action": "panen"}` memanen item ke tas. Jumlah hasil panen adalah `cared ? caredYield : yield`.
  2. `"tumbuh"`: Tanaman/ikan sedang bertumbuh sampai timestamp `readyAt`. Bila `cared: false`, dapat dirawat/disiram satu kali lewat `POST /api/daily/garden/{id}` dengan body `{"action": "rawat"}` untuk meningkatkan hasil panen. Bila sudah dirawat (`cared: true`), kebun menunggu hingga waktu `readyAt` tiba (beralih ke state `"siap"`).

## Kebutuhan Kebersihan, Buang Air (WC), dan Penampilan (23 November 2026)

Inspeksi bundle aktif `14kftr3gt-5o6.js`, `026npiqik_trk.js`, dan uji live terotorisasi 23 November 2026:
1. **Status Kebutuhan dan Dampak Upah**:
   - `/api/kebutuhan` memuat kebutuhan `kebersihan` dan `wc`.
   - `kondisi` memuat `bau: true` saat kebersihan 0 dan `kebelet: true` saat wc 0.
   - Status bau atau kebelet menyebabkan penalti upah Ojol sebesar 10% (`upahPotongBps: 1000`).
2. **Kamar Mandi Rumah (`POST /api/rumah/kamar-mandi`)**:
   - `{"aksi": "wc"}`: Buang air di kloset kamar mandi rumah sendiri. Mengembalikan `{"isi": 100, "wc": 100, "cuciSampai": ..., "detik": 5}`. Mengisi penuh kebutuhan buang air (100) dan menghapus status kebelet. Gratis.
   - `{"aksi": "mandi"}`: Mandi di kamar mandi. Menghapus status bau. Efek +65 (dengan sabun) atau +20 (tanpa sabun). Kuota maks 2x sehari (`bersih.mandi < bersih.mandiMaks`).
   - `{"aksi": "sikat"}`: Sikat gigi di wastafel kamar mandi. Efek +35 (dengan pasta) atau +10 (tanpa pasta). Kuota maks 3x sehari (`bersih.sikat < bersih.sikatMaks`).
   - `{"aksi": "cuci"}`: Cuci tangan. Efek +5.
   - `{"beli": "sabun"|"pasta", "requestId"}`: Beli persediaan sabun batang (1 koin / 10x) atau pasta gigi (1 koin / 15x) ke rak kamar mandi.
3. **Penampilan (Barbershop)**:
   - Di desa `kampung-sebelah`, barbershop fallback tersedia di plot `S09-U09` ("Cukur Sisi Jalan", id usaha `57458327-df64-483f-8904-0ec40bfc28fe`).
   - Layanan: `potong-rambut` (+60 penampilan, 1 koin), `cukur-jenggot` (+30, 0.5 koin), `keramas` (+25, 0.5 koin), `semir-rambut` (+40, 1.5 koin).
   - Pembelian melalui `POST /api/shops/{businessId}/buy` dengan body `{"item": "potong-rambut", "requestId": ...}` terbukti live menaikkan penampilan dari 0 ke 60.

  3. `"kosong"`: Lahan belum ditanami. Request `POST /api/daily/garden/{id}` dengan body `{"action": "tanam"}` menanam bibit baru dengan biaya `seedMilli` jika saldo koin mencukupi.
- Manajemen cooldown: Saat ada kebun/kolam dalam kondisi `"tumbuh"` dan sudah dirawat (`cared: true`), cooldown worker dijadwalkan berdasarkan nilai terkecil dari `readyAt` yang akan datang sehingga worker tidak melakukan polling berulang sebelum panen siap.
