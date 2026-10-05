#!/usr/bin/env bash
# One-time setup: Python venv + packages, frontend packages, AI model checkpoint.
#   ./setup.sh            full setup including the PyTorch transcription engine
#   ./setup.sh --no-ml    skip PyTorch (tempo/key/chords/sections still work)
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
WITH_ML=1
[[ "${1:-}" == "--no-ml" ]] && WITH_ML=0

PY="${PYTHON:-python3}"
"$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' || {
  echo "Python 3.11+ required (found $("$PY" --version))"; exit 1; }

echo "→ Backend: creating virtualenv and installing packages"
cd backend
[[ -d .venv ]] || "$PY" -m venv .venv
.venv/bin/python -m pip install -q --upgrade pip
.venv/bin/python -m pip install -q -r requirements.txt -r requirements-dev.txt
if [[ $WITH_ML == 1 ]]; then
  echo "→ Installing the AI transcription engine (PyTorch + ByteDance piano model, ~1 GB)"
  .venv/bin/python -m pip install -q -r requirements-ml.txt
  echo "→ Downloading the model checkpoint (~165 MB)"
  .venv/bin/python -m app.cli download-models
fi
[[ -f .env ]] || cp .env.example .env
cd ..

echo "→ Frontend: installing packages"
(cd frontend && npm install --no-audit --no-fund)
[[ -f frontend/.env.local ]] || cp frontend/.env.example frontend/.env.local

echo
(cd backend && .venv/bin/python -m app.cli doctor) || true
echo
echo "Done. Start the app with: ./dev.sh"
