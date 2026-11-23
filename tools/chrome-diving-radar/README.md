# Chrome Extension: KampungSebelah Helper v2.2.0 (Diving, Mancing, Ojol & TPU Pusaka)

Ekstensi Chrome multi-fitur untuk minigame dan aktivitas di KampungSebelah:
1. **👻 TPU & Pusaka Mbah Rukmi Radar (Auto-Geledah)**: HUD Live Tracker Jam Angker (23.00 - 03.00 WIB), radar 12 koordinat perabot rumah & pekarangan, transparansi server RNG (1:200), serta auto-geledah rute optimal 12 perabot.
2. **🚗 Auto-Ojol Pro (Khusus Mode Kendarai)**: Otomatisasi ojol tanpa batas 12 jam harian, auto-pilih order tarif tertinggi (max omzet), solver SVG captcha cek 2-angka instan, proteksi retry 409 penumpang turun, dan loop otomatis.
3. **🤿 Diving Radar & Full Auto-Pilot**: HUD Live Compass 3D, filter potensi mutiara (300 koin & 100 koin), auto-pilot berenang navigasi 3D, auto-buka kerang, dan auto-chain loop ke kerang berikutnya di `/diving`.
4. **🎣 Auto-Mancing Pro**: Modul otomatisasi memancing lengkap di `/mancing`: auto lempar kail, auto sentak instan (< 100ms), smart tension reel control (gulung pintar anti-putus & anti-kendur), dan auto simpan/jual tangkapan.

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
  - **Jeda Lempar Kail Alami**: Cooldown antar lemparan diacak `2.2s - 3.8s`, menyerupai jeda manusia saat mengayunkan kail dan memasang umpan.
  - **Jeda Inspeksi Tangkapan**: Jeda `1.4s - 2.5s` sebelum menekan Simpan/Jual, mensimulasikan pemain membaca kartu nama & berat ikan.

- **🛡️ Zero-Loss Engine (Pasti Untung & Anti-Rugi)**:
  - **🧭 Autopilot Navigasi Langsung ke Titik Paling Ramai**: Membaca koordinat spot gerombolan ikan (`titik`) dari game dan secara otomatis mengemudikan kapal (kemudi proporsional & throttle maju) langsung ke titik spot yang paling ramai (*kaya*) dan berkedalaman tinggi. Kapal berhenti tepat di tengah gerombolan ikan saat Sonar membaca **"Ramai" (5 Bar)**!
  - **⚡ Tindakan Cepat Alami (Tanpa Delay Kaku 1s, Tetap Human Jitter)**: Menghapus jeda kaku 1 detik antar aksi toko/alat dan menggantinya dengan refleks manusiawi dinamis `140ms - 280ms`.
  - **🛡️ Proteksi Anti-Kendur Mutlak (Anti-Lepas 100%)**: Memperbaiki kontrol gulungan tali dengan mendeteksi atribut `data-tahan` game langsung dan memproteksi `setPointerCapture`, mencegah situasi tali kendur ($< 4\%$) selama $> 3.2$s sehingga ikan tidak akan pernah lepas!
  - **Anti-Putus Tali**: Otomatis melepas tarikan pada tegangan dinamis `78% - 82%` atau segera bila status bahaya `data-merah` muncul (game putus jika $> 85\%$ selama $> 0.6$s).
  - **Anti-Lepas Ikan**: Otomatis menarik kail saat tegangan turun ke `58% - 63%` (game lepas jika $< 8\%$ selama $> 3.2$s).
  - **Smart Bag Fallback (Tas Penuh $\rightarrow$ Auto Jual)**: Jika tas ikan penuh sehingga tombol simpan tidak aktif, sistem otomatis beralih menjual tangkapan menjadi koin desa agar tidak ada ikan yang hangus atau terbuang.
  - **Anti-Sampah**: Otomatis menjual tangkapan sampah (seperti Sandal Jepit) untuk mengosongkan slot tas demi ikan bernilai tinggi.
  - **Auto-Beli Umpan Paling Worth It (Zero Downtime)**: Otomatis mendeteksi saat umpan habis, membuka toko umpan, membeli paket umpan cumi (atau udang jika modal tipis), memilihnya, dan kembali melempar kail tanpa intervensi manual!
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
4. **Auto Buka Kerang & Auto-Chain Loop**:
   - Otomatis membuka kerang saat tiba ($\le 2,8$ meter), menandai sudah dibuka, lalu berlanjut ke kerang berpotensi terdekat berikutnya.
5. **Emergency Stop (Override)**:
   - Tekan tombol `W`, `A`, `S`, `D`, `Space` pada keyboard kapan saja, atau klik tombol merah `⏹ STOP`.
6. **🎯 Free Move / Draggable HUD (Nav Compass & Radar)**:
   - Panel Radar dan Kompas Arah kini dapat digeser bebas (free move / drag & drop) ke mana pun di layar sesuai kenyamanan pandangan.
   - Posisi tersimpan otomatis di browser (`localStorage`), aman dari batas layar saat resize, dan dapat di-reset ke posisi default cukup dengan melakukan double-click pada header / handle drag (`⠿`).

---

## 🚀 Cara Memperbarui di Chrome:

1. Buka tab baru: `chrome://extensions`.
2. Aktifkan **Developer mode** di pojok kanan atas.
3. Klik tombol **🔄 Reload (Perbarui)** pada kartu ekstensi **KampungSebelah Helper**.
4. Buka halaman game:
   - Untuk Auto-Ojol: `https://www.kampungsebelah.com/?narik=1` (atau buka desa langsung)
   - Untuk Diving: `https://www.kampungsebelah.com/diving`
   - Untuk Mancing: `https://www.kampungsebelah.com/mancing`
5. Panel kontrol otomatis muncul di layar game masing-masing!
