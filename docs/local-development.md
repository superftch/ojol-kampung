# Development lokal dengan Docker

Pakai Docker Desktop untuk menguji perubahan di Mac sebelum build dipasang di production. [Compose lokal](../compose.local.yaml) memakai Dockerfile yang sama, project `kampung-ojol-dev`, volume `dev-state`, dan secret dari `.env.local`. Control service dapat dibuka di `http://127.0.0.1:6081` dari Mac yang menjalankan Docker.

Nginx, domain, dan Cloudflare Tunnel tidak diperlukan untuk pengujian ini. URL lokal dipakai untuk form impor sesi. Jika link dibuka di ponsel, `127.0.0.1` menunjuk ke ponsel itu sendiri. Salin link utuh ke browser di Mac.

## Jalankan dan periksa container

Nyalakan Docker Desktop. Dari direktori repo, buat konfigurasi lokal sekali saja.

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

## Alur web

Buka `http://127.0.0.1:6081/register`, daftar sebagai pengguna pertama pada volume development kosong, dan masuk lewat `/login`. Dari dashboard, buat akun, periksa notifikasi dan daftar akun, lalu buka tab **Admin** untuk batas akun dan maintenance. Form **Cookie akun** menerima cookie untuk akun yang dipilih.

Untuk smoke test lokal terisolasi, jalankan aplikasi dengan `.env.testing` dan direktori runtime baru. Operator live, tunnel, kredensial game, dan database development tidak diperlukan untuk memeriksa login, dashboard, dan IPC worker.

## Alur setiap perubahan

Jalankan suite yang sama dengan CI melalui Docker. Suite memakai fixture dan memblokir akses jaringan dari pengujian.

```sh
docker build --target test -t ojol-kampung:test .
```

Pemeriksaan lokal untuk aplikasi, CLI, dan tes:

```sh
uv run ruff check app ojol main.py scripts/test.py tests
uv run ruff format --check app ojol main.py scripts/test.py tests
uv run ty check --python .venv/bin/python app ojol main.py scripts tests
```

Konfigurasi mypy strict tersedia untuk audit tipe lanjutan melalui `uvx mypy --python-executable .venv/bin/python app`. Jalankan suite penuh lewat `uv run python scripts/test.py --all` setelah memeriksa isolasi `.env.testing`.
