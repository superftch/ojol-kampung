#!/bin/sh
set -eu

token_file=/run/secrets/mesh_node_token
test -s "$token_file" || { echo 'Cloudflare Mesh token belum tersedia.' >&2; exit 1; }
MESH_NODE_TOKEN=$(cat "$token_file")
export MESH_NODE_TOKEN
exec /entrypoint "$@"
