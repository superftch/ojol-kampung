#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

usage() {
    cat <<'EOF'
Reset database and account state.

Usage:
  scripts/reset-db.sh --local
  scripts/reset-db.sh --context DOCKER_CONTEXT

Remote reset needs a Docker context configured for the server. The script
recreates app and worker while preserving the WARP identity volume.
EOF
}

case "${1:-}" in
    --help|-h)
        usage
        exit 0
        ;;
    --local)
        active_context=$(docker context show)
        docker_host=$(docker context inspect "$active_context" --format '{{.Endpoints.docker.Host}}')
        case "$docker_host" in
            unix://*|npipe://*) ;;
            *)
                echo "Docker context aktif bukan daemon lokal; gunakan --context secara eksplisit." >&2
                exit 2
                ;;
        esac
        docker_cmd=(docker --context "$active_context")
        target_name="local ($active_context)"
        local_reset=true
        ;;
    --context)
        if [[ -z "${2:-}" || -n "${3:-}" ]]; then
            usage >&2
            exit 2
        fi
        docker_cmd=(docker --context "$2")
        target_name="$2"
        local_reset=false
        ;;
    *)
        usage >&2
        exit 2
        ;;
esac

if ! "${docker_cmd[@]}" compose version >/dev/null 2>&1; then
    echo "Docker Compose tidak tersedia untuk target ini." >&2
    exit 1
fi

echo "⚠️ Reset database dan seluruh state akun pada target terpilih."
echo "   Target: $target_name"
echo "   Volume identitas WARP tetap dipertahankan."
read -r -p "Ketik RESET untuk melanjutkan: " confirmation
if [[ "$confirmation" != "RESET" ]]; then
    echo "Reset dibatalkan."
    exit 1
fi

state_volume=$(
    "${docker_cmd[@]}" compose config --format json |
        python3 -c 'import json,sys; print(json.load(sys.stdin)["volumes"]["state"]["name"])'
)

echo "🛑 Menghentikan stack; volume lain tetap disimpan..."
"${docker_cmd[@]}" compose down --remove-orphans
if "${docker_cmd[@]}" volume inspect "$state_volume" >/dev/null 2>&1; then
    echo "🧹 Menghapus volume $state_volume..."
    "${docker_cmd[@]}" volume rm "$state_volume"
else
    echo "Volume $state_volume tidak ditemukan; tidak ada DB Docker untuk dihapus."
fi

if [[ "$local_reset" == true ]]; then
    echo "🛑 Menghentikan proses Python lokal..."
    pkill -f "ojol.control" 2>/dev/null || true
    pkill -f "python -m ojol" 2>/dev/null || true
    pkill -f "python.*main.py" 2>/dev/null || true

    echo "🧹 Membersihkan runtime lokal (.local/)..."
    rm -f .local/accounts.sqlite3*
    rm -f .local/status.json .local/game-sync.json .local/online-status.json .local/STOP
    rm -rf .local/accounts/* .local/runtime/*
fi

echo "🚀 Membuat ulang app dan worker dengan DB kosong..."
"${docker_cmd[@]}" compose up -d --no-recreate warp app worker
"${docker_cmd[@]}" compose ps app worker
echo "✅ Reset database selesai pada target terpilih."
