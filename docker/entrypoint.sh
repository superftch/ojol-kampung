#!/bin/sh
set -eu
umask 077
mkdir -p /data/runtime
chown app:app /data /data/runtime
test -r /run/secrets/ojol_env || { echo 'Konfigurasi runtime tidak tersedia: pasang secret ojol_env.' >&2; exit 1; }
install -o app -g app -m 600 /run/secrets/ojol_env /data/config.env.tmp
mv -f /data/config.env.tmp /data/config.env
exec gosu app "$@"
