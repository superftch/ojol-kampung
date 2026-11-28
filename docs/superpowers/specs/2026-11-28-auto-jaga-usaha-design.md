# Auto Jaga Usaha: design

Status: DISETUJUI pengguna (28 November 2026). Rencana: `docs/superpowers/plans/2026-11-28-auto-jaga-usaha.md`.
Tanggal: 28 November 2026 (WIB).

## Tujuan

Auto di background yang menjaga usaha milik akun (contoh: 18 usaha) supaya tiap usaha yang layak mendapat bonus pembeli besok (bobot x1,2) dan isi kebutuhan +25% hari ini. Perilakunya harus terlihat seperti manusia.

## Bukan tujuan

- Tidak berinteraksi dengan Auto Ojol (keputusan pengguna: fokus ke jaga saja).
- Tidak menjaga lebih dari 60 sampai 75 menit per usaha per hari. Bonus besok berhenti naik di 60 menit.
- Tidak membuat pengaturan lintas akun. Satu file pengaturan per akun.

## Anti-tujuan (gagal walau tes lulus)

- Detak berpola tetap (persis tiap 60 detik selama berjam-jam).
- Jaga tanpa henti sepanjang hari atau malam.
- Jaga tersisa aktif setelah auto berhenti atau crash.

## Bukti yang dipakai

Lihat `docs/http-endpoints.md`, bagian "Bukti Jaga Usaha" dan "Observasi manual pengguna".

- Statis: endpoint, config server (`detak_detik` 60, `hidup_menit` 3, `maks_menit_per_hari` 240, `min_menit_bonus` 60).
- Observasi manual: `mulai` mengembalikan `menit: 1`, satu `detak` mengembalikan `menit: 2`, ada field `pilihanPersen: 20`.
- Laporan pengguna: hanya satu usaha aktif. `mulai` di usaha ke-2 mematikan usaha ke-1.
- Belum terbukti: `menit` per detak atau per waktu nyata, pesan galat konflik kontrak kerja, kemungkinan `428 CEK_MANUSIA`.

## Pendekatan

| | A. Rencana harian | B. Reaktif per sesi | C. Daftar manual saja |
|---|---|---|---|
| Cara | Sekali per hari WIB: skor semua usaha, undi jadwal, simpan | Tiap sesi selesai, skor ulang, pilih berikutnya | Pengguna tentukan urutan dan menit |
| Plus | Mudah dites, pola harian terlihat manusia, tahan restart | Mengikuti data terbaru | Paling sederhana |
| Minus | Data bisa basi di siang hari | Pola sulit diprediksi dan dites | Tidak "paling worth it" otomatis |

**Pilihan (usulan saya, belum disetujui): A**, ditambah satu skor ulang ringan di antara sesi untuk membuang usaha yang tutup atau bahannya habis. Pola sama dengan `ojol-jitter.json`.

## Pengaturan (per akun, `jaga-usaha-settings.json`, default mati)

Semua nilai di bawah adalah **usulan saya**, bukan dari sumber data.

| Pengaturan | Default | Catatan |
|---|---|---|
| `enabled` | false | |
| `mode` | `terbaik` | `terbaik`, `rotasi`, `manual` |
| Anggaran harian | 6 jam | Preset: Hemat 4 jam, Seimbang 6 jam, Agresif 8 jam. Bisa isi jam sendiri, maksimal 10 |
| Target per usaha | 60 sampai 75 menit, diacak per usaha per hari | Tidak melebihi `maksMenit` dari server |
| Override per usaha | kosong | `aktif`, `prioritas`, `target_menit_min/max`, `maks_menit_hari` |
| Jam aktif | 06:00 sampai 23:00 | Jam tenang digeser acak ±30 menit per hari |
| Pindah otomatis saat target tercapai | true | |
| Batas skor minimum | diatur otomatis ke persentil, bisa diganti angka | |
| Minimal pelanggan kemarin | 20 | |
| Hari malas | peluang 10 sampai 15%, anggaran dipotong separuh | |

Saran penggunaan anggaran: 18 usaha x 60 menit = 18 jam, tidak muat. Dengan 6 jam, muat sekitar 5 usaha penuh per hari. Jadi pilih yang skornya tertinggi, dan usaha tanpa pesaing sejenis dilewati.

## Skor "worth it"

Perkiraan untuk mengurutkan, bukan angka terbukti.

- Tambahan pelanggan = `customersYesterday x 0,2R / (R + 1,2)`. R = `today.rivals`.
- Skor = tambahan pelanggan x laba per pelanggan. Laba per pelanggan = `kas7.masuk / (7 x customersYesterday)`.
- Lolos bila: buka, bahan tidak habis, R ≥ 1, pelanggan kemarin ≥ batas.
- Undian berbobot dari kandidat teratas. Usaha yang baru dijaga kena penalti.
- Evaluasi: bandingkan `customersYesterday` sebelum dan sesudah jaga, simpan di jurnal.

## Alur satu hari

1. Buat rencana harian (usaha, menit target, jam mulai kasar). Simpan.
2. Sesi 25 sampai 70 menit. Satu usaha boleh dua sesi, karena `menit` kumulatif per hari.
3. Jeda antar sesi 4 sampai 25 menit. Setelah 150 sampai 180 menit beruntun, istirahat 15 sampai 45 menit.
4. Sekitar 15% sesi pindah ke usaha lain sebelum target tercapai, lalu kembali nanti.
5. Berhenti per usaha saat `menit` dari server mencapai target.

## Humanize

- Interval detak = `detakDetik` + acak 0,5 sampai 8 detik. Tidak pernah lebih cepat dari `detakDetik`. Tidak lebih dari 150 detik.
- Jeda 5 sampai 45 detik sebelum `mulai`. Gunakan `human_pause` yang sudah ada.
- Sebelum pindah usaha: `selesai`, jeda acak, baru `mulai` usaha lain.

## Pengaman

- Kirim `selesai` saat stop, cancel, shutdown. Setelah restart: baca `GET /jaga`, lanjut atau tutup.
- Berhenti bila: `jaga` false dari server, 3 detak gagal, `428` tak terpecahkan, usaha tutup, karakter tidur, kebutuhan di bawah batas, atau jam kerja kontrak.
- Jurnal tiap sesi: menit server vs menit lokal. Selisih janggal = berhenti.
- Semua request lewat `OjolHttpApi` dengan header browser lengkap.
- Hanya satu usaha aktif sekaligus (terbukti oleh laporan pengguna).

## Titik sentuh kode

- `app/modules/worker/settings.py`: flag `jaga`.
- `app/integrations/kampung/http_api.py`: izin path baru. Kategori galat baru, karena `request()` membuang isi galat POST yang ditolak.
- `app/modules/gameplay/jaga_usaha.py` (baru): `run_jaga(c)`, dipanggil setelah `run_kerja`.
- `app/modules/worker/jaga_planner.py` (baru): skor dan rencana harian, fungsi murni.
- Dashboard: kartu "Auto Jaga Usaha" dan jurnal sesi.

## Rencana verifikasi (live, bertahap)

1. A. Baca saja untuk akun Yumika: `semua`, `shops`, `jaga`, `report`, jeda acak.
2. B. Satu sesi pendek di satu usaha: `mulai`, beberapa `detak`, `selesai`. Catat `menit` tiap detak.
3. C. Uji pindah: `mulai` di usaha kedua, lalu `GET` usaha pertama, lalu `selesai`.

B dan C mengubah state akun, bisa ditutup dengan `selesai`. Tes unit untuk planner dan skor tidak membuktikan perilaku server.

## Diserahkan ke pembangun

Angka jeda, persentil batas skor, bentuk kartu dashboard, nama field jurnal.
