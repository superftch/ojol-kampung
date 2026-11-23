# Catatan kelemahan klien-tepercaya (KampungSebelah)

Inspeksi 23 November 2026 WIB oleh `scripts/probe_vuln.py` terhadap akun **Eskobar**
(desa uji, saldo ±46 koin) plus pembacaan bundle client tersimpan di
`.local/http-discovery`. Status: **observasi live**, bukan audit penuh. Semua
temuan bisa diulang dari sesi yang sama.

Aturan main: server menolak hal yang tidak masuk akal (menu toko, replay kuis,
`petak` negatif), jadi bukan "tanpa validasi". Yang bocor adalah nilai yang
memang dihitung di client lalu dipercaya apa adanya.

## 1. Skor minigame dari `holds` client (bisa dimanipulasi)

`POST /api/minigame {"action":"finish","playId","holds":[...]}` — `holds` adalah
daftar lama tahan per repetisi. Server mencocokkan indeks ke `plan.reps`, tetapi
**kelebihan entri tidak dipotong**.

Bukti (gym, `plan.reps` = 8):

| kiriman | skor | hadiah |
|---|---|---|
| 8 holds pas di tengah (benar) | 8 | ±0.5 koin |
| 56 holds pas di tengah | **16** | **960 milli** (cap 1000) |

Jadi skor bisa 2× lipat melewati batas main manusia hanya dengan mengulang pola
`round(fill * center)`. Batas harian 3 main/game dan cap harian 3000 milli tetap
berlaku server-side, jadi ini menggandakan hasil per jatah, bukan menambah jatah.

## 2. Bensin 100% dilaporkan client (`petak`)

`POST /api/kebutuhan/bensin {"ride","petak"}` — server hanya mengalikan
`petak × 0.02` (motor), tanpa mencocokkan dengan jumlah `lacak` yang dikirim.

- `petak: 0` → **tidak ada pengurangan sama sekali** (bar tetap 100).
- `petak: 99999` → tetap dipotong 12 (cap `maks_per_kirim` 600 petak).
- `petak: -50` → 400 "Data perjalanan tidak valid".

Artefak bot ini (`ojol/`) belum pernah memanggil endpoint tersebut, jadi
kendaraan bot saat ini sudah jalan tanpa biaya bensin. Kalau mau hemat kuota
laporan, kirim `petak` hanya saat bar mendekati 0.

## 3. `lacak` menerima lompatan koordinat besar

Satu `POST /api/ojol {"action":"lacak","x","y"}` diterima untuk lompatan 41
petak (dari titik jemput langsung ke tujuan), tanpa penolakan "terlalu cepat".
**Tetapi** `arriveAt` sudah dipatok saat `ambil` (`detik` di penawaran, mis. 306
detik untuk 41 petak), dan `arrived` baru `true` setelah jam itu lewat.

Kesimpulan: teleport tidak mempercepat jam tiba; yang hilang hanya kerja
menyetir, jumlah laporan, dan risiko mogok di jalan. Tetap berguna untuk bot
karena 1 laporan menggantikan puluhan.

Konsekuensi praktis: urutan aman tetap `lacak(from) → jemput → lacak(to)`,
lalu tunggu `arriveAt` lewat, baru `selesai`. `jemput` wajib (409 "Jemput dulu
di tempat jemput").

## 4. Cek pengemudi (captcha) — perilaku yang perlu diketahui

- Gambar hanya ada di jendela sempit dan hanya bila `t` = id trip dan `a` =
  `arriveAt` **saat itu**; di luar itu 404 "Tidak ada cek".
- Salah kode → 400 + kunci 60 detik, dan `arriveAt` ikut bergeser (trip jadi
  harus dilacak ulang ke tujuan). Brute force 100 kemungkinan tidak murah.
- Saat `cek` bernilai `false` pada trip, `selesai` tetap minta cek lolos pada
  percobaan pertama setelah tiba, lalu 200 tanpa `kode` setelah kunci lewat.

Pemecah SVG repo (`ojol/svg_captcha_solver.py`) belum teruji pada sampel live
karena trip sampel tidak pernah membuka cek saat diuji.

## 5. Yang ternyata aman (sudah diuji)

- `POST /api/shops/{id}/buy`: item luar menu 400; `priceMilli` dan `quantity`
  diabaikan (selalu 1 unit, harga dari server).
- `POST /api/facilities/{id}/kuis`: replay `visitId` sama → 409.
- `POST /api/facilities/{id}/use`: idempoten per `requestId`; batas harian per
  fasilitas ditegakkan (409 dengan jam buka berikutnya).
- `POST /api/topups`: hanya 5 paket tetap (50/100/250/500/1000 poin, cap
  Rp100.000/bulan). `simulate` **403 "Simulasi hanya untuk mode uji"** di
  produksi, jadi tidak ada koin gratis dari topup; harus bayar QR.

## Cara mengulang

```bash
.venv/bin/python scripts/probe_vuln.py --only minigame
.venv/bin/python scripts/probe_vuln.py --only ojol
.venv/bin/python scripts/probe_vuln.py --only topup   # kuis, garden juga ada
```

Id fasilitas gym/perpus dipatok di skrip dari capture lama; ganti bila desa
berganti bangunan. Skrip memakai sesi di `.local/http-session.json`.

## 6. Permukaan admin (`/api/admin/*`) — tidak terbuka untuk warga

Tidak ada di bundle client publik (hanya `kades-chat` dan `keamanan` yang
dipakai UI), jadi ditemukan lewat enumerasi. Yang ada, semua `403
{"code":"FORBIDDEN","message":"Khusus kepala desa."}` untuk sesi warga:

`GET stats`, `GET kas`, `GET report`, `GET rt`, `GET facilities`, `GET toa`,
`GET topups` (+`/topups/export`), `POST keamanan`, `POST|GET rewards`
(GET 405, perlu body), `GET kades-chat` (200 — satu-satunya yang sengaja
dibuka untuk warga).

Urutan lapisan benar: tanpa cookie `401 UNAUTHENTICATED`, sesi
pending/ditolak ditahan di gerbang akun, warga `403`. Semua penolakan datang
dari lookup peran di DB, bukan dari input request.

Bypass yang dicoba dan gagal: `?desaId=`/`?desa=` (diabaikan), header
`X-Role`/`X-Peran`/`X-User-Role`/`X-Forwarded-User`/`X-Desa-Id`,
`X-HTTP-Method-Override`, serta varian method PUT/DELETE/PATCH (405). Tidak
ada route anak tanpa guard.

Kebocoran kecil yang nyata: `GET /api/admin/kades-chat` untuk warga
mengembalikan `userId`, `seenAt`, dan `online` milik kades + camat desa
(warga desa lain tidak terlihat). Cookie sesi `__Secure-better-auth` opaque
dan server-side, jadi tidak bisa ditempah.

Jalur naik peran: calon RT `POST /api/rt {"action":"daftar","promise"}` (janji
10–200 karakter, divalidasi) → menang pemilihan RT → baru bisa daftar calon
kades lewat `/api/pilkades`, dengan syarat top up total Rp25.000. Jadi admin
desa praktis butuh bayar, bukan celah.

Percobaan eskalasi izin (23 Nov, akun Eskobar): `electionId` karangan dan
tanpa `electionId` sama-sama `404 Pemilihan tidak ditemukan` (validasi id
duluan, gate syarat belum tercapai); `?desa=` pada `/api/pilkades` dan
`/api/balai` diterima 200 tapi desa lain tidak membuka daftar pemilu; sebagai
calon RT tetap `403` di `/api/admin/*`. Tidak ada eskalasi lewat bug — peran
hanya berpindah lewat pemilu terjadwal.

Enumerasi ulang: `.local/probe_admin.py` dan `.local/probe_admin2.py`
(memakai sesi yang sama, hasil 403/404 dibedakan).

## Belum diperiksa

- Isi dan kontrak `/api/admin/{stats,kas,topups,rewards,report,rt,toa,facilities}`
  belum bisa diuji karena akun sampel bukan kades — perlu akun kades (top up
  Rp25k + menang pilkades, atau pinjam sesi kades) untuk mengecek IDOR
  `desaId` antar desa, batas `rewards`/`topups`, dan idempotensi `kas`.
- Minigame lain (mancing, penalti, badminton, lari, renang, basket) — pola
  `holds`/`casts`/`strikes` kemungkinan sama, belum diuji.
- Kebun/kolam (`/api/daily/garden`): akun ini belum punya kebun, jadi `panen`
  ganda belum bisa diuji.
- Kegiatan fasum (`tensi`, `detak`, `nampan`) — `stops`/`taps` juga kiriman
  client.
- Balapan `selesai` paralel (double payout) belum dicoba.
