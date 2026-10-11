#!/bin/bash
# Runs nginx and PHP-FPM side by side; the container exits when either dies.
set -e
cd /app
# Caches are built here (not at image build) because env() values are baked in by config:cache.
php artisan config:cache >/dev/null
php artisan route:cache >/dev/null

mkdir -p /tmp/nginx-body /tmp/nginx-proxy /tmp/nginx-fastcgi /tmp/nginx-uwsgi /tmp/nginx-scgi
php-fpm -F &
FPM=$!
nginx -c /etc/nginx/bench.conf -g 'daemon off;' &
NGINX=$!

trap 'kill -TERM "$NGINX" "$FPM" 2>/dev/null; wait; exit 0' TERM INT
wait -n "$FPM" "$NGINX"
echo "a server process exited unexpectedly" >&2
kill -TERM "$NGINX" "$FPM" 2>/dev/null || true
exit 1
