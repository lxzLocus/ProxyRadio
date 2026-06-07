#!/bin/sh
# docker-entrypoint.sh
# コンテナ起動時に BACKEND_URL を env-config.js に書き出す

ENV_CONFIG="/usr/share/nginx/html/env-config.js"

echo "// Auto-generated at container startup — do not edit" > "$ENV_CONFIG"
echo "window.__RADIKO_BACKEND_URL = \"${BACKEND_URL:-}\";" >> "$ENV_CONFIG"

echo "[entrypoint] BACKEND_URL = '${BACKEND_URL:-<same-origin>}'"
echo "[entrypoint] Generated $ENV_CONFIG"

exec "$@"
