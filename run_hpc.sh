#!/bin/bash
# Run Flask behind Alberto's HPC1 NGINX:
#   location /ab-sayed { proxy_pass http://127.0.0.1:5000; ... }
# Public URL: https://hpc1.csub.edu/ab-sayed/
set -euo pipefail
cd "$(dirname "$0")"

export CSUBOT_PREFIX=/ab-sayed
export CSUBOT_BIND=127.0.0.1
export CSUBOT_PORT=5000
export CSUBOT_COOKIE_SECURE=1

if [[ ! -x .venv/bin/gunicorn ]]; then
  echo "Create .venv and pip install -r requirements.txt first." >&2
  exit 1
fi

exec .venv/bin/gunicorn \
  --bind 127.0.0.1:5000 \
  --timeout 120 \
  --worker-class gthread \
  --workers 1 \
  --threads 8 \
  app:app
