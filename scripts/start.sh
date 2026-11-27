#!/bin/zsh
set -e
cd "$(dirname "$0")/.."
if [[ ! -x .venv/bin/python ]]; then
  python3 -m venv .venv
  .venv/bin/python -m pip install -r requirements-dev.txt
fi
if [[ ! -d frontend/node_modules ]]; then
  npm --prefix frontend install
fi
npm --prefix frontend run build
if [[ ! -f storage/dentalis.db && -z "$DENTALIS_ADMIN_PASSWORD" ]]; then
  read -rs 'DENTALIS_ADMIN_PASSWORD?Contraseña inicial de admin (mínimo 12 caracteres): '
  echo
  export DENTALIS_ADMIN_PASSWORD
fi
export DENTALIS_DEMO="${DENTALIS_DEMO:-1}"
exec .venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
