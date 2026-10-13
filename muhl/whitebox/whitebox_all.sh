#!/usr/bin/env bash
# host/whitebox_all.sh — drive the white-box operator spectrometer across the model library.
#
# For each model: start the streaming server (mmap, one resident at a time = the capability-stack rung-2
# headroom-safe pattern), wait for it to bind, run whitebox_sweep.py (accumulating into the shared JSON
# matrix), then stop the server and move on. RAM is a knob: each model mmap-streams from the SSD, so size
# is storage-bounded — but throughput falls as the model grows, so we sequence small→large and report as
# we go. NEVER --no-mmap / --mlock (run_server.sh refuses them anyway).
#
# Usage:  bash host/whitebox_all.sh [model.gguf ...]     # default = the diverse-family set, small→large
set -u
REPO="$(cd "$(dirname "$0")/.." && pwd)"
MODELS_DIR="/c/llm/models"
PY="/c/Users/lucys/AppData/Local/Programs/Python/Python312/python.exe"
RESULTS="/c/llm/bin/whitebox_matrix.json"
CTX=2048

# default order: architectural diversity, small→large (Phi already measured separately)
if [ "$#" -gt 0 ]; then
  LIST=("$@")
else
  LIST=(
    "mistralai_Mistral-Small-3.2-24B-Instruct-2506-Q4_K_M.gguf"  # Mistral (France), dense 24B
    "gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf"           # Gemma 4 MoE (~4B active) — phone family, fast
    "google_gemma-3-27b-it-Q4_K_M.gguf"                # Gemma 3 dense 27B — phone family
    "mixtral-8x7b-instruct-v0.1.Q4_K_M.gguf"           # Mixtral MoE (~13B active)
    "gemma-4-31B-it-qat-UD-Q4_K_XL.gguf"               # biggest Gemma 4
    "Llama-3.3-70B-Instruct-Q4_K_M.gguf"               # Llama 70B — the slow one, last
  )
fi

stop_server() { powershell -NoProfile -Command "Stop-Process -Name llama-server -Force -ErrorAction SilentlyContinue" >/dev/null 2>&1; sleep 2; }

for m in "${LIST[@]}"; do
  MPATH="$MODELS_DIR/$m"
  if [ ! -f "$MPATH" ]; then echo "[all] SKIP (missing): $m"; continue; fi
  LOG="/c/llm/bin/server_$(echo "$m" | tr -c 'A-Za-z0-9' '_').log"
  echo "============================================================"
  echo "[all] $m  ($(du -m "$MPATH" | cut -f1) MB) — starting server"
  stop_server
  LLAMA_MODEL="$MPATH" LLAMA_CTX="$CTX" bash "$REPO/host/run_server.sh" > "$LOG" 2>&1 &
  # wait up to 20 min for the cold mmap load + bind (big models page a lot on 8 GB)
  ok=0
  for i in $(seq 1 400); do
    if grep -qiE "server is listening|listening on http" "$LOG" 2>/dev/null; then ok=1; break; fi
    if grep -qiE "terminate called|std::bad_alloc|error loading model|failed to load|REFUSED|not found at" "$LOG" 2>/dev/null; then
      echo "[all] LOAD FAILED for $m:"; tail -6 "$LOG"; break
    fi
    # grace period: give run_server.sh time to exec llama-server before trusting a process-gone verdict
    if [ "$i" -gt 8 ] && ! powershell -NoProfile -Command "if(Get-Process llama-server -ErrorAction SilentlyContinue){exit 0}else{exit 1}" >/dev/null 2>&1; then
      echo "[all] server process gone for $m (after grace):"; tail -6 "$LOG"; break
    fi
    sleep 3
  done
  if [ "$ok" -ne 1 ]; then echo "[all] $m did not bind — moving on"; stop_server; continue; fi
  echo "[all] $m bound — running spectrometer"
  WB_RESULTS="$RESULTS" LLM_URL="http://127.0.0.1:8080" "$PY" "$REPO/host/whitebox_sweep.py"
  stop_server
done
echo "[all] DONE. Matrix at $RESULTS"
