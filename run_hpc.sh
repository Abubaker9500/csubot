#!/bin/bash
# Flask + Ollama on HPC1. Odin public_html proxies here.
# 0.0.0.0 lets Odin reach port 5000; Alberto's 127.0.0.1 nginx still works too.
set -euo pipefail
cd "$(dirname "$0")"

export CSUBOT_PREFIX=/ab-sayed
export CSUBOT_BIND=0.0.0.0
export CSUBOT_PORT=5000
export CSUBOT_COOKIE_SECURE=1
export CSUBOT_MODEL=qwen3:8b

if [[ -z "${CSUBOT_SECRET:-}" ]]; then
  if [[ ! -f .csubot_secret ]]; then
    python3 -c 'import secrets; print(secrets.token_hex(32))' > .csubot_secret
    chmod 600 .csubot_secret
    echo "Wrote a new CSUBOT_SECRET to .csubot_secret (gitignored)."
  fi
  CSUBOT_SECRET="$(cat .csubot_secret)"
  export CSUBOT_SECRET
fi

if [[ ! -x .venv/bin/gunicorn ]]; then
  echo "Create .venv and pip install -r requirements.txt first." >&2
  exit 1
fi

exec .venv/bin/gunicorn \
  --bind 0.0.0.0:5000 \
  --timeout 120 \
  --worker-class gthread \
  --workers 1 \
  --threads 8 \
  app:app
