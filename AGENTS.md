# Panduan repo

Untuk perubahan yang memakai API KampungSebelah, mulai dari [inventaris API client](docs/http-endpoints.md). Periksa tanggal dan sumber bukti sebelum mengandalkan metode, path, payload, atau bentuk respons. Jika detail yang diperlukan belum terbukti, telusuri bundle client atau bukti yang diberikan, lalu perbarui inventaris sebelum memakainya di worker. Tandai temuan statis dan observasi historis sesuai sumbernya. Simpan artefak mentah di direktori lokal yang diabaikan Git.

## Wajib Header Browser pada Semua API Request

Semua request ke API atau endpoint web KampungSebelah **WAJIB** menyertakan set header peramban/browser lengkap yang sudah disediakan (`OjolHttpApi.browser_headers(...)` atau identitas browser di `.local/browser-identity.json`).

- **Dilarang keras** melakukan request HTTP mentah (seperti plain `curl`, `httpx`, `fetch`, atau `requests` tanpa header browser lengkap).
- Request tanpa header browser lengkap akan otomatis ditolak oleh proteksi WAF/anti-script server dengan kode error `SCRIPT`:
  `"Peramban ini tidak dikenali. Perbarui aplikasi Kampung Sebelah atau pakai Chrome, Safari, atau Firefox terbaru."`
- Setiap pembuatan modul worker, skrip penelusuran, atau pengujian live wajib memanfaatkan `OjolHttpApi` atau memanggil generator header resmi `browser_headers(path=...)`.

