#!/bin/bash
# Our own Ollama on HPC1, limited to GPUs 1-3 because GPU 0 keeps faulting.
# Runs beside the shared Ollama (11434) on port 11435 and survives SSH logout.
#
#   ./ollama_hpc.sh start    start it and pull the model if missing
#   ./ollama_hpc.sh stop
#   ./ollama_hpc.sh status
#   ./ollama_hpc.sh log
set -euo pipefail
cd "$(dirname "$0")"

PORT=11435
MODEL="${CSUBOT_MODEL:-qwen3:8b}"
PID_FILE=.ollama_hpc.pid
LOG_FILE=ollama_hpc.log

# Numbers must match nvidia-smi, so order CUDA devices by PCI bus like nvidia-smi does.
export CUDA_DEVICE_ORDER=PCI_BUS_ID
export CUDA_VISIBLE_DEVICES="${CSUBOT_GPUS:-1,2,3}"
export OLLAMA_HOST="127.0.0.1:$PORT"
export OLLAMA_MODELS="${OLLAMA_MODELS:-$HOME/.ollama/models}"
export OLLAMA_KEEP_ALIVE=2h

running() {
  [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null
}

healthy() {
  curl -fsS -m 3 "http://$OLLAMA_HOST/" >/dev/null 2>&1
}

case "${1:-status}" in
  start)
    if running && healthy; then
      echo "Already running (pid $(cat "$PID_FILE")) on $OLLAMA_HOST, GPUs $CUDA_VISIBLE_DEVICES"
      exit 0
    fi
    mkdir -p "$OLLAMA_MODELS"
    nohup ollama serve >>"$LOG_FILE" 2>&1 &
    echo $! >"$PID_FILE"
    for _ in $(seq 1 30); do
      healthy && break
      sleep 1
    done
    if ! healthy; then
      echo "Ollama did not start. Last log lines:" >&2
      tail -n 20 "$LOG_FILE" >&2
      exit 1
    fi
    echo "Ollama running (pid $(cat "$PID_FILE")) on $OLLAMA_HOST, GPUs $CUDA_VISIBLE_DEVICES"
    if ! ollama list | awk 'NR>1 {print $1}' | grep -qx "$MODEL"; then
      echo "Pulling $MODEL into $OLLAMA_MODELS (one time, about 5 GB) ..."
      ollama pull "$MODEL"
    fi
    echo "Loading $MODEL onto the GPU ..."
    ollama run "$MODEL" "Reply with OK." >/dev/null
    ollama ps
    ;;
  stop)
    if running; then
      kill "$(cat "$PID_FILE")"
      echo "Stopped Ollama (pid $(cat "$PID_FILE"))"
    else
      echo "Not running"
    fi
    rm -f "$PID_FILE"
    ;;
  status)
    if running && healthy; then
      echo "Running (pid $(cat "$PID_FILE")) on $OLLAMA_HOST, GPUs $CUDA_VISIBLE_DEVICES"
      ollama ps
    else
      echo "Not running"
      exit 1
    fi
    ;;
  log)
    tail -n 50 "$LOG_FILE"
    ;;
  *)
    echo "Usage: $0 {start|stop|status|log}" >&2
    exit 2
    ;;
esac
