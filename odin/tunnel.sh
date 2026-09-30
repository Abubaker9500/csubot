#!/bin/bash
# Keep Odin -> HPC1 Flask reachable on 127.0.0.1:5000.
#
# Safe to run every few minutes from cron. It exits immediately when the
# tunnel is already healthy, and re-opens it when it is not.
#
# One-time setup (so it never asks for a password):
#   ssh-keygen -t ed25519 -N '' -f ~/.ssh/id_ed25519     # if you have no key
#   ssh-copy-id sayed@hpc1.csub.edu
#
# Cron (crontab -e on Odin):
#   */3 * * * * $HOME/bin/csubot-tunnel.sh >> $HOME/csubot-tunnel.log 2>&1

HPC_USER="${CSUBOT_HPC_USER:-sayed}"
HPC_HOST="${CSUBOT_HPC_HOST:-hpc1.csub.edu}"
LOCAL_PORT="${CSUBOT_LOCAL_PORT:-5000}"
REMOTE_PORT="${CSUBOT_REMOTE_PORT:-5000}"
PREFIX="${CSUBOT_PREFIX:-/ab-sayed}"

health_url="http://127.0.0.1:${LOCAL_PORT}${PREFIX}/health"

# If cron is not available, run "tunnel.sh --watch" inside tmux instead.
if [[ "${1:-}" == "--watch" ]]; then
    while true; do
        "$0"
        sleep 60
    done
fi

if curl -sS -m 5 "$health_url" | grep -q '"status"'; then
    exit 0
fi

echo "$(date '+%F %T') tunnel down, restarting"

# Drop any half-dead forwarder holding the port.
pkill -f "ssh -N.*-L ${LOCAL_PORT}:127.0.0.1:${REMOTE_PORT}" 2>/dev/null

ssh -f -N \
    -o BatchMode=yes \
    -o ExitOnForwardFailure=yes \
    -o ServerAliveInterval=30 \
    -o ServerAliveCountMax=3 \
    -L "${LOCAL_PORT}:127.0.0.1:${REMOTE_PORT}" \
    "${HPC_USER}@${HPC_HOST}"

sleep 2

if curl -sS -m 5 "$health_url" | grep -q '"status"'; then
    echo "$(date '+%F %T') tunnel up"
    exit 0
fi

echo "$(date '+%F %T') tunnel FAILED — is gunicorn running on ${HPC_HOST}?"
exit 1
