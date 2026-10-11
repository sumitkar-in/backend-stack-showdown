#!/bin/bash
# Caches are built here (not at image build) because env() values are baked in by config:cache.
set -e
cd /app
php artisan config:cache >/dev/null
php artisan route:cache >/dev/null
exec php artisan octane:start --server=swoole --host=0.0.0.0 --port=8080 \
  --workers="${OCTANE_WORKERS:-4}" --task-workers=0 --max-requests="${OCTANE_MAX_REQUESTS:-100000}" \
  --log-level=error
