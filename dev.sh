#!/usr/bin/env bash
# Start PianoScribe AI locally: API, background worker and web UI.
# Ctrl-C stops everything. Ports can be changed with API_PORT / WEB_PORT.
# Per-request API logs are off to keep the output readable (worker progress still shows).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
API_PORT="${API_PORT:-8484}"
WEB_PORT="${WEB_PORT:-3456}"
export WEB_PORT
export NEXT_PUBLIC_API_URL="${NEXT_PUBLIC_API_URL:-http://localhost:$API_PORT}"
export PIANOSCRIBE_CORS_ORIGINS="[\"http://localhost:$WEB_PORT\",\"http://127.0.0.1:$WEB_PORT\"]"

if [[ ! -x backend/.venv/bin/python ]]; then
  echo "Backend not set up yet – running ./setup.sh first…"
  ./setup.sh
fi
[[ -d frontend/node_modules ]] || (cd frontend && npm install)

for port in "$API_PORT" "$WEB_PORT"; do
  if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "Port $port is already in use. Pick another, e.g.: API_PORT=8585 WEB_PORT=3737 ./dev.sh"
    exit 1
  fi
done

trap 'trap - EXIT; kill 0' INT TERM EXIT

echo "▶ API      http://localhost:$API_PORT  (interactive docs: /docs)"
(cd backend && exec .venv/bin/python -m uvicorn app.main:app --port "$API_PORT" --reload --reload-dir app --no-access-log 2>&1 | sed -u 's/^/[api]    /') &
echo "▶ Worker   transcription queue (restarts when backend code changes)"
(cd backend && exec .venv/bin/python -m watchfiles --filter python --sigint-timeout 10 \
  "'$ROOT/backend/.venv/bin/python' -m app.worker" app 2>&1 | sed -u 's/^/[worker] /') &
echo "▶ Web UI   http://localhost:$WEB_PORT"
(cd frontend && exec npm run dev 2>&1 | sed -u 's/^/[web]    /') &

wait
