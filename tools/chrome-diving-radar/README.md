# Chrome Extension: KampungSebelah Helper v2.4.0 (Diving, Mancing, Ojol, TPU & Berburu)

Ekstensi Chrome multi-fitur untuk minigame dan aktivitas di KampungSebelah:
1. **🎯 Berburu Radar & Sniper (`/berburu`)**: Radar satwa 3D + deteksi halangan pohon (LOS), auto-bidik balistik (kompensasi gravitasi + angin), auto-tembak aman, auto-ambil, proteksi seruduk babi, dan kalkulasi cuan.
2. **👻 TPU & Pusaka Mbah Rukmi Radar (Auto-Geledah)**: HUD Live Tracker Jam Angker (23.00 - 03.00 WIB), radar 12 koordinat perabot rumah & pekarangan, transparansi server RNG (1:200), serta auto-geledah rute optimal 12 perabot.
2. **🚗 Auto-Ojol Pro (Khusus Mode Kendarai)**: Otomatisasi ojol tanpa batas 12 jam harian, auto-pilih order tarif tertinggi (max omzet), solver SVG captcha cek 2-angka instan, proteksi retry 409 penumpang turun, dan loop otomatis.
3. **🤿 Diving Radar & Full Auto-Pilot**: HUD Live Compass 3D, filter potensi mutiara (300 koin & 100 koin), auto-pilot berenang navigasi 3D, auto-buka kerang, dan auto-chain loop ke kerang berikutnya di `/diving`.
4. **🎣 Auto-Mancing Pro**: Modul otomatisasi memancing lengkap di `/mancing`: auto celup kail (laut dalam), auto sentak instan (< 100ms), smart tension reel control (gulung pintar anti-putus & anti-kendur), dan auto simpan/jual tangkapan.

---

## 👻 Fitur Baru: TPU & Pusaka Mbah Rukmi Radar (`tpu.js`)

### 🔍 Apakah Lokasi Pusaka Bisa Diketahui Persis Duluan?
- **Fakta Teknis Kode Server & Client**:
  - **Lokasi Geografis 12 Perabot**: Koordinatnya **pasti dan presisi 100%**:
    - **7 di dalam Rumah Mbah Rukmi**: Dipan kayu, Lemari tua, Peti kayu, Tungku dapur, Gentong air, Meja kecil, dan Bale bambu.
    - **5 di Pekarangan Luar**: Tong kayu, Tumpukan kayu bakar, Kandang ayam, Lesung batu, dan Sumur tua.
  - **Keberadaan Pusaka**: **TIDAK BISA diketahui duluan di awal**.
    - Di kode resmi KampungSebelah (`tpu-rules.ts` & `0ne-rhmeq5g4d.js`), pusaka **tidak ditempatkan di objek tertentu di dalam 3D scene / client memory**.
    - Penentuan pusaka terjadi saat pemain menekan tombol **"Geledah"**, di mana browser mengirim `POST /api/tpu` (`{ aksi: "cari", tempat: "<benda_id>" }`). Server melakukan **undian RNG live berpeluang 1 : 200 (0.5%)** dan dibatasi kuota desa maksimal **1 pusaka per malam**.
  - **Solusi Paling Efektif**: Karena semua 12 benda memiliki peluang yang sama diundi oleh server, strategi terbaik adalah **menggeledah seluruh 12 perabot secepat mungkin (rute terpendek)** begitu jam 23.00 WIB tiba sebelum kuota malam diambil warga lain!

### ⚡ Kemampuan Auto-Geledah TPU:
- **⏰ Live Jam Angker Tracker**: Menghitung mundur dan mendeteksi waktu aktif jam angker (23.00 - 03.00 WIB).
- **📍 Radar Jarak & Arah Real-Time**: Menghitung jarak presisi pemain ke masing-masing dari 12 kotak interaksi perabot.
- **🏃 Auto-Pilot Rute Optimal**: Karakter otomatis berjalan teratur menelusuri 12 perabot dari pekarangan luar hingga perabot dapur/kamar dalam rumah Mbah Rukmi.
- **🔍 Auto-Geledah & Auto-Close**: Otomatis menekan geledah saat tiba di jarak $\le 1.1$m, menunggu animasi 5 detik, membaca loot pusaka, dan otomatis menutup dialog untuk lanjut ke perabot berikutnya sampai selesai!
- **✋ Draggable Floating Panel**: HUD melayang dengan checklist 12 benda dan tombol Start/Stop yang bisa digeser bebas ke mana saja.

---

## 🚗 Fitur Baru: Auto-Ojol Pro (Khusus Mode Kendarai)

- **⚡ Keunggulan Mutlak Mode Kendarai**:
  - **Tanpa Batas 12 Jam Harian (`tanpa_batas: true`)**: Berbeda dengan mode otomatis biasa yang dibatasi kuota 12 jam (`narikMaksMenit: 720`) dan aturan istirahat wajib 30 menit, order mode kendara dapat dijalankan nonstop tanpa terkena limit harian server!
  - **🧭 Checkpoint-Following Autopilot (Taat Marka Jalan & Anti-Tabrak Rumah)**:
    - Mengaitkan diri secara langsung ke instance renderer 3D desa (`window.__KS_VILLAGE_INSTANCE`) via prototype hooks & React Fiber scanner.
    - **Jalan Terdekat**: Mengikuti array checkpoint jalur terpendek BFS resmi dari jaringan jalan desa (`inst.nav.route.pts`).
    - **Ikuti Per Checkpoint (Sekuensial Murni)**: Mengikuti setiap titik checkpoint secara berurutan ($P_0 \to P_1 \to P_2 \dots$). Checkpoint hanya berganti ke tikungan berikutnya setelah motor benar-benar tiba di persimpangan (radius $\le 0.45$ petak), dilarang memotong serong diagonal.
    - **Terkunci di Tengah Jalur Jalan (Anti-Tabrak Rumah)**:
      - Pada jalan vertikal ($X = \text{tetap}$): posisi $X$ dikunci di garis tengah aspal ($|X - X_{\text{jalan}}| \le 0.28$), motor melaju murni pada sumbu $Y$.
      - Pada jalan horizontal ($Y = \text{tetap}$): posisi $Y$ dikunci di garis tengah aspal ($|Y - Y_{\text{jalan}}| \le 0.28$), motor melaju murni pada sumbu $X$.
      - Tidak akan pernah keluar aspal atau menabrak dinding rumah/pekarangan warga di tepi jalan.
    - **Anti-Stuck Nudge Searah Jalan**: Jika tertahan $> 300$ms di tikungan, dorongan *nudge* hanya bergerak sejajar sumbu aspal jalan (tidak pernah mendorong ke samping menuju rumah warga).
    - **Radius Tiba Resmi Game**: Auto-stop dan transisi saat tiba di radius jemput/antar $\le 1.4$ petak (sesuai threshold resmi game `t2.Y`).
  - **Smart Bid & Max-Omzet Engine**: Selalu memprioritaskan dan memilih order dengan tarif koin (`fareMilli`) paling tinggi di antara 3 tawaran yang masuk, dengan prioritas tambahan untuk pesanan warga (*warga*).
  - **Auto-Solver SVG Captcha Cek (2 Digit Instan)**: Menganalisis dan memecahkan gambar cek verifikasi SVG pengemudi secara lokal dalam hitungan milidetik menggunakan template bank bentuk geometri polyline, dan otomatis mengisi input form tanpa intervensi manual.
  - **Proteksi 409 "Penumpang Sedang Turun"**: Menangani jendela waktu turun penumpang (`turun_detik: 8`) secara otomatis dengan timer jeda aman (9 detik) sebelum mengulang klaim pencairan ongkos, mencegah kegagalan order.
  - **🛡️ Proteksi Anti-Bot Cek Kilat (>2.5 Detik)**: Menahan jeda minimal $\ge 2.8$ detik setelah tiba di tujuan sebelum mengklik klaim ongkos, menghindari hukuman deteksi script server yang memicu verifikasi captcha di setiap order.
  - **🎛️ Floating Glassmorphism Controller (Draggable / Free Move)**: Panel kontrol melayang di layar desa dengan tombol Mulai/Stop, counter total order selesai, total omzet koin harian, dan log riwayat aktivitas real-time. Posisinya dapat digeser bebas dan tersimpan otomatis di `localStorage`.

---

## 🎣 Fitur Baru: Auto-Mancing Pro (Natural & Zero-Loss) (`/mancing`)

- **🌿 Mode Gerakan Natural Manusiawi (Anti-Bot / Human Rhythm)**:
  - **Refleks Sambaran Manusia**: Jeda sentak kail diacak alami antara `220ms - 380ms` (bukan instan 0ms robot), tetap jauh di bawah batas waktu 10 detik game.
  - **Koordinat Pointer Acak**: Event klik mouse dikirim dengan koordinat $(x, y)$ acak di dalam tombol, bukan titik $(0,0)$ robotik.
  - **Jeda Celup Kail Alami**: Cooldown antar celupan diacak `2.2s - 3.8s`, menyerupai jeda manusia saat menurunkan kail lurus ke laut dalam dan memasang umpan.
  - **Jeda Inspeksi Tangkapan**: Jeda `1.4s - 2.5s` sebelum menekan Simpan/Jual, mensimulasikan pemain membaca kartu nama & berat ikan.

- **🛡️ Zero-Loss Engine (Pasti Untung & Anti-Rugi)**:
  - **🧭 Autopilot Navigasi Langsung ke Titik Paling Ramai**: Membaca koordinat spot gerombolan ikan (`titik`) dari game dan secara otomatis mengemudikan kapal (kemudi proporsional & throttle maju) langsung ke titik spot yang paling ramai (*kaya*) dan berkedalaman tinggi. Kapal berhenti tepat di tengah gerombolan ikan saat Sonar membaca **"Ramai" (5 Bar)**!
  - **⚡ Tindakan Cepat Alami (Tanpa Delay Kaku 1s, Tetap Human Jitter)**: Menghapus jeda kaku 1 detik antar aksi toko/alat dan menggantinya dengan refleks manusiawi dinamis `140ms - 280ms`.
  - **🛡️ Proteksi Anti-Kendur Mutlak (Anti-Lepas 100%)**: Memperbaiki kontrol gulungan tali dengan mendeteksi atribut `data-tahan` game langsung dan memproteksi `setPointerCapture`, mencegah situasi tali kendur ($< 4\%$) selama $> 3.2$s sehingga ikan tidak akan pernah lepas!
  - **Anti-Putus Tali**: Otomatis melepas tarikan pada tegangan dinamis `78% - 82%` atau segera bila status bahaya `data-merah` muncul (game putus jika $> 85\%$ selama $> 0.6$s).
  - **Anti-Lepas Ikan**: Otomatis menarik kail saat tegangan turun ke `58% - 63%` (game lepas jika $< 8\%$ selama $> 3.2$s).
  - **Smart Bag Fallback (Tas Penuh $\rightarrow$ Auto Jual)**: Jika tas ikan penuh sehingga tombol simpan tidak aktif, sistem otomatis beralih menjual tangkapan menjadi koin desa agar tidak ada ikan yang hangus atau terbuang.
  - **Anti-Sampah**: Otomatis menjual tangkapan sampah (seperti Sandal Jepit) untuk mengosongkan slot tas demi ikan bernilai tinggi.
  - **Auto-Beli Umpan Paling Worth It (Zero Downtime)**: Otomatis mendeteksi saat umpan habis, membuka toko umpan, membeli paket umpan cumi (atau udang jika modal tipis), memilihnya, dan kembali mencelupkan kail tanpa intervensi manual!
  - **Auto-Upgrade Joran & Peralatan (High-ROI Engine)**: Otomatis memeriksa dan membeli upgrade joran (Tonda / Samudra) saat saldo koin mencukupi.

- **📊 Kalkulasi Matematis: Umpan & Upgrade Paling Worth It**:
  - **Tabel Umpan (Batas BUMDes: 20 Ekor / Hari)**:
    | Jenis Umpan | Harga Beli | Target Ikan | Omzet per 20 Ekor | Modal (20 Ekor) | **Net Profit Bersih** | **Peringkat ROI** |
    | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
    | **Umpan Cumi** | 0.5 koin | Besar & Raksasa (2kg - 32kg+) | 45.0 - 70.0+ koin | 10.0 koin | **+35.0 - 60.0+ koin** | 🥇 **Juara 1 (Paling Cuan)** |
    | **Umpan Udang**| 0.3 koin | Sedang & Besar (300g - 5kg) | 22.0 - 32.0 koin | 6.0 koin | **+16.0 - 26.0 koin** | 🥈 **Juara 2 (Hemat Modal)** |
    | **Umpan Cacing**| 0.2 koin | Kecil (100g - 300g) | 8.0 - 9.2 koin | 4.0 koin | **+4.0 - 5.2 koin** | ❌ **Rugi Kuota Harian** |

  - **Tabel Upgrade Joran (Permanen Milik Selamanya)**:
    | Nama Joran | Biaya Koin | Efek Spesial | Manfaat Profit & BEP |
    | :--- | :--- | :--- | :--- |
    | **Joran Bambu** | 0 koin (Gratis) | Normal | Joran standar awal. |
    | **Joran Tonda** | 60 koin | 1.8× sambaran ikan cepat + **Tarik Ringan (`mudah: 1`)** | **Sangat Direkomendasikan!** Menarik ikan jauh lebih cepat dan anti-lepas. Balik modal hanya dalam 1.5 hari mancing cumi. |
    | **Joran Samudra** | 120 koin | 2.0× sambaran ikan raksasa + **Tarik Ringan (`mudah: 1`)** | **Best Late-Game!** Khusus pemancing laut lepas pemburu kuwe, tuna, layaran, dan marlin. |
    | **Joran Karang** | 30 koin | 1.8× sambaran ikan karang | Pilihan awal jika koin belum cukup untuk Tonda. |

- **🎛️ Floating Glassmorphism Controller (Free Move / Draggable)**: Panel kontrol melayang di halaman `/mancing` dengan indikator status fase real-time, saklar proteksi, dan riwayat tangkapan. Dapat digeser bebas (drag & drop) ke posisi mana saja di layar, posisi tersimpan otomatis di localStorage, dan dapat di-reset dengan double-click pada header.

---

## 🤿 Fitur Diving Radar & Auto-Pilot (`/diving`)

1. **✨ Status Kerang Potensi Tersedia (Real-time Live Tracker)**:
   - Menampilkan jumlah sisa kerang berpotensi mutiara yang **masih tersedia (belum dibuka)** di laut saat ini (Breakdown: 💎 300 koin dan 🟡 100 koin).
2. **💎 Filter Khusus "300 Koin" (Mutiara Langka)**:
   - Menyaring dan hanya memandu ke kerang palung gelap ($\ge 40$ meter) berisi mutiara langka senilai 300 koin.
3. **Auto Berenang Langsung ke Sasaran**:
   - Arah hadap karakter dan sudut kamera langsung tertuju ke kerang target dengan dorongan renang maju dan penyesuaian kedalaman vertikal.
   - **🪨 Anti-Nyangkut (Hindari Batu)** (`diving-avoid.js` + `inject.js`):
     - Temuan statis dari bundle `1j_v3n6k6p7js.js` (24 November 2026): game hanya menabrakkan pemain dengan `dunia.batuBesar` (bola `{x,y,z,r}`, batu skala ≥ 2), dorongan keluar `r + 0.45`. Berenang lurus ke pusat batu membuat dorongan sama dengan laju maju, jadi karakter diam.
     - Tiap 50ms perencana mensimulasikan 14 m ke depan untuk 13 sudut belokan dan 3 pilihan naik/turun. Jalur lurus dipakai bila bebas; jika tidak, dipilih belokan atau naik/turun paling kecil yang bebas dari batu (jarak aman +1 m), dengan hysteresis agar tidak bolak-balik.
     - Pengaman: bila posisi bergerak < 0.35 m dalam 700 ms, auto-pilot mundur, bergeser ke samping, lalu naik, bergantian sisi dan makin lama (maks. level 5). Nyangkut tidak pernah menghentikan auto-pilot; penghitung kembali 0 begitu bergerak ≥ 0.35 m. Jeda antar tick > 500 ms dianggap tab di latar belakang (timer ditahan Chrome dan game berhenti menggerakkan karakter), sehingga pengukuran diulang dan tidak dihitung nyangkut.
     - Satu-satunya henti otomatis adalah `no_progress`: 3 × 12 detik tanpa mendekat ≥ 1 m ke kerang. Pintasan dengan Cmd/Ctrl/Alt (mis. Cmd+Opt+Panah pindah tab) tidak lagi membatalkan auto-pilot.
     - Kerang tersembunyi di dalam/di balik batu: navigator mencari titik berdiri di luar zona batu yang masih dalam jangkauan buka (≤ 2,8 m), lalu menuju titik itu, bukan ke pusat kerang. Ini mencegah berputar-putar di atas batu. Bila tidak ada titik layak, jarak aman dilonggarkan bertahap, dan setelah 3 kali 9 detik tanpa mendekat ≥ 1 m auto-pilot berhenti dengan alasan `no_progress`.
     - Judul pill HUD berubah menjadi "🪨 Menghindari batu" atau "🛟 Lepas dari batu".
     - Belum diukur live: rasio laju naik/turun terhadap laju horizontal (diasumsikan 0.45). Dasar laut tidak memblokir pemain, hanya mengangkatnya.
   - **🧍 Mode Manusia** (`diving-human.js`, v2.3.0): supaya rantai auto-pilot tidak berpola mesin. Ini meniru pola, bukan jaminan lolos deteksi: apa yang diperiksa server belum terbukti. Posisi 48 kerang sama untuk semua pemain pada hari yang sama; urutan "terdekat dulu" hanya pilihan ekstensi.
     - **Pengaturan** (kotak centang "🧍 Mode Manusia" di panel radar, kunci `localStorage` `ks_diving_humanize`): default aktif = urutan acak (3 terdekat berbobot + 1-2 kerang dangkal per sesi), jeda acak, dan gerak ala manusia. Dimatikan = rantai otomatis selalu ke kerang terdekat berurutan seperti versi awal. Pilihan tersimpan dan ikut dikirim ke `inject.js` saat Auto Jalan dimulai.
     - **Pilihan kerang** (rantai otomatis saja; tombol "terdekat" di HUD tetap deterministik): acak di antara 3 kerang terdekat dengan peluang 60/25/15 %. Tiap sesi membuka 1-2 kerang dangkal (pasti kosong) terdekat, di posisi acak di antara kerang utama. Diam > 35 menit dianggap sesi baru. Tidak ada batas kerang per sesi atau per hari.
     - **Jeda**: 0,4-2,2 detik setelah tiba sebelum membuka kerang (sebelumnya tetap 300 ms), 2,5-7 detik antar kerang (sebelumnya tetap 4200 ms), dan jeda 0,6-2,2 detik di jalan tiap 8-25 detik sambil menoleh.
     - **Jalur**: arah bergoyang halus (maks. 0,1 rad) dan belok dibatasi 3 rad/detik. Semua ini hanya saat jalur tenang: tidak sedang menghindar atau pulih, tidak ada batu dalam 8 m, dan jarak ke kerang > 6 m. Saat menghindar batu, arah navigator dipakai apa adanya.
     - **Aman terhadap anti-nyangkut**: jeda memanggil `hold()` di navigator, jadi diam sengaja tidak dihitung nyangkut maupun tanpa kemajuan.
     - Batas: game tidak punya aturan hiu di ekstensi ini. Hiu berpatroli di kedalaman > 6 m dan kerang dangkal bisa berada di sana; tertangkap berarti rawat inap 12 jam.
   - **🔓 Buka kerang yang benar** (`diving-open.js`, v2.4.0): "tiba" diukur dengan rumus jarak game (`kerang.y + 0.3`, jangkauan 3,2 m), bukan jarak ekstensi. Klik tombol "Buka kerang" hanya bila tombol game ada. Kerang dianggap terbuka hanya bila game menandai `dibuka`. Klik yang diabaikan atau ditolak server dicoba ulang (maks. 3 kali, jeda bertambah). Bila tetap gagal, kerang dilewati dan rantai lanjut. Kontrol yang dikunci game (`kunci`, `tertangkap`) tidak dihitung nyangkut.
   - **🦈 Kabur dari hiu** (`diving-shark.js`, v2.5.0): saat auto-pilot aktif, hiu dalam radius 70 m, hiu memburu, atau indikator merah di HUD game menyala, karakter langsung naik penuh sambil menjauh dari hiu (batu tetap dihindari). Di kedalaman < 4,5 m ia berhenti dan menjaga kedalaman 3-5 m sampai hiu pergi atau lebih jauh dari 100 m, lalu lanjut setelah jeda 1,5-4 detik. Pembukaan kerang yang sedang berjalan dibatalkan dan diulang setelah aman.
     - Dasar dari bundle game: hiu hanya memburu bila kedalaman > 6 m dan jarak < 45 m, tidak bisa naik di atas 6 m, lajunya 2,5 m/s (4,4 m/s saat menyergap), sedangkan laju renang pemain turun sampai 0,55x di kedalaman. Hiu tidak bisa dikalahkan secara horizontal; satu-satunya jalan aman adalah naik.
     - Penjaga hiu tetap menyala selama jeda antar kerang (maks. 15 detik). Setelah STOP manual atau tombol keyboard, kendali kembali penuh ke pemain.
     - Batas: nilai `tangkap_m` dan lama sergap tidak terbaca dari konfigurasi, jadi simulasi di `test/test-diving-shark.test.mjs` memakai asumsi. Hiu yang sudah sangat dekat (< 20 m) di kedalaman besar tidak dijamin terlewati. Penjaga hanya aktif saat auto-pilot aktif atau jeda rantai.
   - **📋 Log diagnostik**: buffer 400 entri di `inject.js` (start, stop, nyangkut, tiba, klik, tiap 5 detik). Salin lewat tombol "Salin Log Diagnostik" di panel radar, atau `__KS_DIVING_DUMP()` di konsol.
   - **🔴 Tombol STOP**: tampilan dihitung dari status nyata dan disinkronkan tiap frame. Biru "Auto Jalan" = diam, merah berdenyut "STOP Auto Jalan" = berenang, kuning berdenyut "STOP (jeda)" = jeda menuju kerang berikutnya. Alasan berhenti tampil di judul HUD. Diuji di `test/test-diving-hud-ui.test.mjs`.
4. **Auto Buka Kerang & Auto-Chain Loop**:
   - Otomatis membuka kerang saat tiba ($\le 2,8$ meter), menandai sudah dibuka, lalu berlanjut ke kerang berpotensi terdekat berikutnya.
5. **Emergency Stop (Override)**:
   - Tekan tombol `W`, `A`, `S`, `D`, `Space` pada keyboard kapan saja, atau klik tombol merah `⏹ STOP`.
6. **🎯 Free Move / Draggable HUD (Nav Compass & Radar)**:
   - Panel Radar dan Kompas Arah kini dapat digeser bebas (free move / drag & drop) ke mana pun di layar sesuai kenyamanan pandangan.
   - Posisi tersimpan otomatis di browser (`localStorage`), aman dari batas layar saat resize, dan dapat di-reset ke posisi default cukup dengan melakukan double-click pada header / handle drag (`⠿`).

---

### 📊 Knowledge Base & Logika Server Mutiara Diving

Berdasarkan bedah source code game engine resmi (`src/lib/diving-rules.ts`, `src/lib/diving.ts`, dan chunk `1j_v3n6k6p7js.js`):

#### 1. Kuota Terbatas & Kolam Bersama (*Shared Global Pool*)
- **Total Kerang di Laut**: Ada **48 kerang fisik** di dasar laut (posisi 3D deterministik berdasarkan seed tanggal harian).
- **Kuota Mutiara Server**: **Hanya ada 7 mutiara per hari** untuk seluruh pemain di 1 server:
  - **5 Mutiara Biasa (100 koin)**: Bernilai Rp100.000 / 100 koin, dibeli langsung oleh kas desa Pulau Seberang.
  - **2 Mutiara Langka (300 koin)**: Bernilai Rp300.000 / 300 koin, berada di palung gelap berisiko hiu.
- **Kategori Kedalaman Laut**:
  - **Cetek ($< 18$m)**: 10 kerang $\to$ **100% PASTI KOSONG**. Dilarang oleh server berisi mutiara. Radar otomatis mengabaikan kerang cetek ini.
  - **Lereng ($18\text{m} - 39\text{m}$)**: 29 kerang $\to$ **Kandidat Mutiara Biasa (100 koin)**.
  - **Palung ($\ge 40$m)**: 9 kerang $\to$ **Kandidat Mutiara Langka (300 koin)**.

#### 2. 🕒 Tabel Jadwal & Probabilitas Kemunculan Mutiara (`muncul_jam`)
Server sengaja tidak menaruh semua mutiara di awal hari (jam 00:00) agar tidak diborong oleh satu pemain. Mutiara baru "diisi" ke dalam kerang pada menit acak di rentang jadwal berikut:

| Kategori Mutiara | Nilai Jual | Kuota / Hari | Jendela Waktu Server (`muncul_jam`) | Probabilitas & Golden Window |
| :--- | :---: | :---: | :--- | :--- |
| **Mutiara Langka Sesi 1** | **300 koin** | 1 butir | `07:00 – 14:00 WIB` (Siang) | **Golden Window**: `11:00 – 13:00 WIB` (Probabilitas spawn tinggi sebelum disapu warga lain). |
| **Mutiara Langka Sesi 2** | **300 koin** | 1 butir | `15:00 – 22:00 WIB` (Malam) | **Golden Window**: `19:30 – 21:00 WIB` (Probabilitas spawn tinggi di paruh akhir jendela). |
| **Mutiara Biasa #1** | 100 koin | 1 butir | `06:00 – 10:00 WIB` (Pagi) | Golden Window: `08:00 – 09:30 WIB` |
| **Mutiara Biasa #2** | 100 koin | 1 butir | `09:00 – 13:00 WIB` (Siang) | Golden Window: `11:00 – 12:30 WIB` |
| **Mutiara Biasa #3** | 100 koin | 1 butir | `12:00 – 16:00 WIB` (Sore) | Golden Window: `14:00 – 15:30 WIB` |
| **Mutiara Biasa #4** | 100 koin | 1 butir | `15:00 – 19:00 WIB` (Sore-Malam) | Golden Window: `17:00 – 18:30 WIB` |
| **Mutiara Biasa #5** | 100 koin | 1 butir | `18:00 – 22:00 WIB` (Malam) | Golden Window: `20:00 – 21:30 WIB` |

> [!NOTE]
> Jam dan menit pastinya diundi secara rahasia di sisi **SERVER**. Client browser tidak pernah dikirimi timestamp pasti untuk mencegah bot/script melakukan *sniping* pada detik tertentu.

#### 3. ❓ Mengapa Buka 9/9 Kerang Palung Bisa Tetap Kosong?
Banyak pemain bingung saat membuka semua 9 kerang palung ($\ge 40$m) tetapi muncul pesan *"Kerang ini kosong. Cari kerang lain."*:
1. **Radar Menandai "Kandidat Kedalaman", Bukan Kepastian Isi**: Di palung memang ada 9 kerang, tetapi kuota mutiara langka hanya 2 per hari. Minimal 7 kerang palung memang dijamin kosong.
2. **Jam Acak Sesi Belum Tercapai**: Jika Anda menyelam pukul 18:30 pada sesi malam (`15:00 - 22:00`), dan server mengundi jam spawn jatuh pada pukul 20:15, maka pada pukul 18:30 seluruh 9 kerang palung **memang belum diisi mutiara oleh server**.
3. **Sudah Diambil Penyelam Lain**: Karena sifatnya *shared pool*, jika ada penyelam lain yang membuka kerang tersebut 10 menit sebelum Anda, mutiara langka tersebut sudah diambil.

#### 4. 💡 Strategi Efisiensi Tiket (10 Koin) & Profit Maksimal
1. **Baca Counter Modal Sebelum Bayar Tiket**:
   - Selalu periksa baris dialog dermaga: *"Mutiara hari ini: X dari 7 belum ditemukan. Y di antaranya mutiara langka..."*
   - Jika tertulis **`0 mutiara langka`**: Jangan buang waktu dan oksigen berenang ke palung $\ge 40$m!
2. **Sapu Kerang Lereng (100 Koin) Saat Palung Kosong**:
   - Jika Anda sudah membuka kerang palung dan kosong, jangan sia-siakan sisa tabung oksigen (30 menit).
   - Segera klik filter **`🟡 100 & 300`** pada Radar: ada **29 kerang lereng (18m–39m)** yang jaraknya saling berdekatan. Peluang mendapatkan mutiara biasa (100 koin) jauh lebih besar (kuota 5 butir/hari).
3. **Waspada Hiu ($\ge 6$m)**:
   - Hiu berpatroli tiap 8 menit selama 70–100 detik di kedalaman $> 6$ meter. Jika sirene berbunyi atau sirip hiu mendekat, segera tekan tombol **Naik** ke kedalaman $< 6$m (zona aman hiu) agar tidak tertangkap dan dirawat 12 jam di rumah sakit.

#### 5. 🗺️ Panduan Akses Lokasi & Titik Koordinat
Diving hanya dapat dimulai jika akun Anda berada di **Pulau Seberang** (`diPulau: true`). Jika berada di daratan utama, tombol "Mulai menyelam" dikunci:
1. **Menyeberang ke Pulau Seberang**:
   - **Kapal Penyeberangan (2 koin)**: Datang ke Dermaga Pantai Sebelah (`X: 113, Y: -22`), naik kapal selama 30 detik ke Pelabuhan Pulau Seberang (`X: 1120, Y: 122`).
   - **Pesawat Desa (5 koin)**: Datang ke Bandara Kampung Sebelah (`X: 171, Y: 43`).
2. **Dermaga Diving Laut Seberang**:
   - Terletak di pantai utara Pulau Seberang.
   - Pintu masuk: `X: 1197, Y: 11`, Papan nama: `X: 1199, Y: 3`.
   - *Cara termudah*: Buka menu **"Mau ke mana"** pada peta, cari **`Diving`**, dan klik untuk panduan rute otomatis.

---

## 🚀 Cara Memasang & Memperbarui di Chrome

### Metode Default: Load Unpacked (`.ZIP`)

1. Unduh `.ZIP` dari dashboard (`/api/extension/download`), lalu ekstrak.
2. Buka tab baru: `chrome://extensions`, aktifkan **Developer mode** di pojok kanan atas.
3. Pilih **Load unpacked** -> pilih folder `kampungsebelah-extension` (atau klik **🔄 Reload** setelah mengganti file dengan ZIP terbaru).

### Opsi Auto-Update: Distribusi CRX via Enterprise Policy

Server dashboard juga menyediakan distribusi `.crx` beserta manifest `update.xml` dan file policy siap pakai (`/api/extension/policy/*`):

- **Windows**: Unduh `kampungsebelah-chrome-policy.reg` dari modal **Tutorial & Opsi CRX** di dashboard, klik dua kali, lalu restart Chrome.
- **macOS**: Unduh `kampungsebelah-chrome-policy.mobileconfig` (atau gunakan `defaults write com.google.Chrome ExtensionInstallForcelist -array-add "<EXT_ID>;<UPDATE_XML_URL>"`), lalu restart Chrome.
- **Linux**: Simpan `kampungsebelah-helper.json` ke `/etc/opt/chrome/policies/managed/`, lalu restart Chrome.

Setiap kali `version` di `manifest.json` dinaikkan di server, Chrome akan otomatis mengunduh versi terbaru tanpa perlu ekstrak atau *Load unpacked* ulang.

Setelah terpasang, buka halaman game untuk memunculkan panel kontrol:
- Untuk Auto-Ojol: `https://www.kampungsebelah.com/?narik=1` (atau buka desa langsung)
- Untuk Diving: `https://www.kampungsebelah.com/diving`
- Untuk Mancing: `https://www.kampungsebelah.com/mancing`
- Untuk Berburu: `https://www.kampungsebelah.com/berburu`
