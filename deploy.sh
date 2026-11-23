#!/usr/bin/env bash
set -euo pipefail

# Skrip Deployment Otomatis Kampung Ojol
echo "🚀 Memulai deployment Kampung Ojol..."

# 1. Pindah ke direktori repository
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

# 2. Update kode dari git
echo "📥 Menarik perubahan terbaru dari Git..."
git pull --ff-only origin main || {
    echo "⚠️ Git pull --ff-only gagal, mencoba git pull origin main..."
    git pull origin main
}

# 3. Cek apakah Docker Compose digunakan
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    echo "🐳 Membangun dan memperbarui container Docker..."
    docker compose build app warp
    docker compose up -d

    echo "⏳ Menunggu container siap dan memeriksa status..."
    sleep 5
    docker compose ps

    # Uji health check lokal jika curl tersedia
    if command -v curl >/dev/null 2>&1; then
        echo "🔍 Memeriksa status health endpoint..."
        for i in {1..15}; do
            if curl -fsS http://127.0.0.1:6080/health >/dev/null 2>&1; then
                echo "✅ Health check berhasil (http://127.0.0.1:6080/health OK)!"
                break
            fi
            echo "Menunggu endpoint health... ($i/15)"
            sleep 2
        done
    fi

    echo "📋 30 baris log aplikasi terbaru:"
    docker compose logs --tail 30 app
else
    echo "⚠️ Docker Compose tidak ditemukan. Menggunakan environment Python/uv..."
    if command -v uv >/dev/null 2>&1; then
        echo "📦 Menyelaraskan dependensi dengan uv sync..."
        uv sync
    fi

    if command -v systemctl >/dev/null 2>&1 && systemctl is-active --quiet kampung-ojol 2>/dev/null; then
        echo "🔄 Me-restart service systemd kampung-ojol..."
        sudo systemctl restart kampung-ojol
        sudo systemctl status kampung-ojol --no-pager
    fi
fi

echo "✨ Deployment berhasil selesai!"
