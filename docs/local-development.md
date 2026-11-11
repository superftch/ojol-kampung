# Development lokal dengan Docker

Pakai Docker Desktop untuk menguji perubahan di Mac sebelum build dipasang di production. [Compose lokal](../compose.local.yaml) memakai Dockerfile yang sama, project `kampung-ojol-dev`, volume `dev-state`, dan secret dari `.env.local`. Control service dapat dibuka di `http://127.0.0.1:6081` dari Mac yang menjalankan Docker.

Nginx, domain, dan Cloudflare Tunnel tidak diperlukan untuk pengujian ini. Bot membuat koneksi keluar ke Telegram menggunakan [long polling `getUpdates`](https://core.telegram.org/bots/api#getupdates). URL lokal dipakai untuk form impor sesi. Jika link dibuka di ponsel, `127.0.0.1` menunjuk ke ponsel itu sendiri. Salin link utuh ke browser di Mac.

## Jalankan dan periksa container

Nyalakan Docker Desktop. Dari direktori repo, buat konfigurasi lokal sekali saja. File ini boleh tetap kosong pada dua pengaturan Telegram untuk smoke test container.

```sh
test -f .env.local || install -m 600 .env.local.example .env.local
docker compose --env-file .env.local -f compose.local.yaml up -d --build --wait
curl -fsS http://127.0.0.1:6081/health
```

Respons yang diharapkan adalah `service: ok`, `core: http`, dan kedua field tunnel `false`. Ini memastikan control service dan port lokal berfungsi. Untuk log dan shutdown, gunakan project lokal yang sama.

```sh
docker compose --env-file .env.local -f compose.local.yaml logs --tail 50 app
docker compose --env-file .env.local -f compose.local.yaml down
```

`down` mempertahankan volume development. `down -v` menghapus akun lokal, sesi, dan ledger.

## Uji bot Telegram sendiri

1. Buat bot khusus development melalui [BotFather](https://t.me/BotFather). Isi `OJOL_TELEGRAM_BOT_TOKEN` dan `OJOL_TELEGRAM_CHAT_ID` di `.env.local`. Chat ID admin adalah ID numerik akun Telegram pribadi Anda. Pakai token yang berbeda dari bot production. Simpan nilainya di file lokal.
2. Terapkan konfigurasi dengan `docker compose --env-file .env.local -f compose.local.yaml up -d --force-recreate --wait`. Buka chat pribadi dengan bot development dan tekan **Start**. Periksa menu, **Status**, dan **Laba Bersih** sebelum mengimpor sesi game.
3. Tekan **Import Cookie**. Buka link sekali pakai di browser Mac dan pastikan nama akun pada form benar. Untuk menguji integrasi API baca, impor sesi akun uji melalui form tersebut. Impor memverifikasi snapshot lewat HTTP MCP. Pengaturan bawaan `OJOL_OPERATOR_AUTHORIZED=false` memblokir **Jalankan Ojol**.
4. Setelah sesi berhasil diimpor, cek pembacaan snapshot dan kandidat toko. Perintah berikut memakai akun **Utama**. Untuk akun lain, tambahkan `--account ID_AKUN` sebelum `inspect`.

   ```sh
   docker compose --env-file .env.local -f compose.local.yaml exec -u app app python main.py inspect --shop data
   ```

5. Untuk smoke test transaksi, gunakan akun uji yang punya izin operator dan tidak aktif di worker lain. Ubah `OJOL_OPERATOR_AUTHORIZED=true` di `.env.local`, recreate container, lalu mulai dari Telegram. Contoh lokal membatasi sesi pada dua trip, 10 menit, dan lima koin. Setelah uji, cek **Status**, **Laba Bersih**, dan riwayat. Kembalikan pengaturan ke `false` dan recreate.

Jika bot diam, cek kedua nilai Telegram, pastikan Anda sudah membuka chat pribadi dan menekan **Start**, lalu cek log. Satu token sebaiknya dipakai satu poller. Bot dengan webhook aktif tidak bisa menerima update lewat polling. [Dokumentasi Telegram](https://core.telegram.org/bots/api#getupdates)

## Alur setiap perubahan

Jalankan suite yang sama dengan CI melalui Docker. Suite memakai fixture dan memblokir akses jaringan dari pengujian.

```sh
docker build --target test -t ojol-kampung:test .
```

Jalankan ulang build Compose lokal untuk perubahan kode, lalu cek `/health`, alur Telegram yang terkena perubahan, dan `inspect` jika perubahan menyangkut API game. Fitur yang melakukan transaksi diuji dulu dengan fixture, lalu dengan smoke test terbatas di akun uji. Setelah lolos, gunakan commit yang sama untuk build di server production. Pengujian URL publik dan tunnel menjadi bagian terpisah dari pemeriksaan production.
