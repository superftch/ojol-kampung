#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# Skrip Deployment Kampung Ojol - Dedicated Web Platform (ojol.jnck.pl)
# ==============================================================================

echo "🚀 Memulai deployment Kampung Ojol (Website Mode)..."

# 1. Pindah ke direktori repository
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

# 2. Update kode dari git
echo "📥 Menarik perubahan terbaru dari Git..."
git pull --ff-only origin main || {
    echo "⚠️ Git pull --ff-only gagal, mencoba git pull origin main..."
    git pull origin main || echo "⚠️ Git pull diabaikan jika tidak ada remote."
}

# 3. PASTIKAN SEMUA BOT TELEGRAM DIMATIKAN
echo "🛑 Memastikan bot Telegram dimatikan..."
if command -v docker >/dev/null 2>&1; then
    docker compose stop telegram-bot 2>/dev/null || true
    docker compose rm -f telegram-bot 2>/dev/null || true
    docker stop kampung-ojol-telegram-bot-1 2>/dev/null || true
    docker rm -f kampung-ojol-telegram-bot-1 2>/dev/null || true
fi

# Stop proses python telegram bot lokal jika ada
pkill -f "ojol.telegram_login_bot" 2>/dev/null || true
pkill -f "python -m ojol.telegram" 2>/dev/null || true

# Stop & disable service systemd telegram jika ada
if command -v systemctl >/dev/null 2>&1; then
    sudo systemctl stop kampung-ojol-telegram 2>/dev/null || true
    sudo systemctl disable kampung-ojol-telegram 2>/dev/null || true
fi
echo "✅ Bot Telegram dipastikan MATI (Semua kontrol pindah ke Website)."

# 4. Konfigurasi Binding Domain & URL
export OJOL_BIND_IP="${OJOL_BIND_IP:-0.0.0.0}"
export OJOL_PORT="${OJOL_PORT:-6080}"
export OJOL_LOGIN_PUBLIC_URL="${OJOL_LOGIN_PUBLIC_URL:-https://ojol.jnck.pl}"

echo "🌐 Domain Website: ${OJOL_LOGIN_PUBLIC_URL}"
echo "📡 Binding Port : ${OJOL_BIND_IP}:${OJOL_PORT}"

# 5. Jalankan Service Web via Docker Compose
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    TARGET="${1:-app}"
    if [ "$TARGET" = "app" ]; then
        echo "🐳 Membangun app; worker dan WARP tetap berjalan..."
        docker compose build app
        docker compose up -d --no-recreate warp worker
        docker compose up -d --no-deps app
    elif [ "$TARGET" = "worker" ]; then
        echo "🐳 Memperbarui worker tanpa me-restart app..."
        docker compose build worker
        docker compose up -d --no-recreate warp
        docker compose up -d --no-deps worker
    elif [ "$TARGET" = "all" ]; then
        echo "🐳 Membangun dan memperbarui semua container Docker..."
        docker compose build app warp worker
        docker compose up -d --remove-orphans app warp worker
    else
        echo "Target tidak dikenal: $TARGET (gunakan app, worker, atau all)" >&2
        exit 2
    fi

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

# 6. Informasi Setup Nginx untuk ojol.jnck.pl
echo ""
echo "=================================================================="
echo "✨ Deployment berhasil selesai!"
echo "🌐 Akses Website: ${OJOL_LOGIN_PUBLIC_URL}"
echo ""
echo "💡 Untuk setup Nginx Reverse Proxy (ojol.jnck.pl):"
echo "   sudo cp deploy/nginx-ojol.conf /etc/nginx/sites-available/ojol.jnck.pl"
echo "   sudo ln -sf /etc/nginx/sites-available/ojol.jnck.pl /etc/nginx/sites-enabled/"
echo "   sudo nginx -t && sudo systemctl reload nginx"
echo "   (Opsional SSL Certbot): sudo certbot --nginx -d ojol.jnck.pl"
echo "=================================================================="
