#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# Skrip Reset Database & State Kampung Ojol
# ==============================================================================

echo "⚠️  PERINGATAN: Skrip ini akan menghapus database, sesi, dan volume data!"
echo "Semua akun game yang tersimpan akan di-reset ke kondisi awal."
echo ""

# Pastikan berada di root directory repository
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

# 1. Hentikan container dan HAPUS Docker Volumes (-v adalah kunci utama reset Docker)
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    echo "🛑 Menghentikan container Docker dan MENGHAPUS volume data (docker compose down -v)..."
    docker compose down -v --remove-orphans || true

    # Hapus volume docker manual jika masih tersisa
    docker volume rm kampung-ojol_state kampung-ojol-dev_dev-state 2>/dev/null || true
fi

# 2. Hentikan proses python lokal jika ada yang berjalan di host
echo "🛑 Menghentikan proses Python lokal..."
pkill -f "ojol.control" 2>/dev/null || true
pkill -f "python -m ojol" 2>/dev/null || true
pkill -f "python.*main.py" 2>/dev/null || true

# 3. Bersihkan file database dan session di direktori lokal host
echo "🧹 Membersihkan file database dan runtime lokal (.local/)..."
rm -f .local/accounts.sqlite3*
rm -f .local/status.json .local/game-sync.json .local/online-status.json .local/STOP
rm -rf .local/accounts/*
rm -rf .local/runtime/*

echo ""
echo "✅ Reset database & volume BERHASIL SELESAI!"
echo "Sekarang Anda dapat menjalankan ./deploy.sh untuk memulai dari database bersih yang baru."
