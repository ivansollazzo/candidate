#!/bin/sh
# Detects usable hardware stacks, starts Ollama with the chosen one and writes to /runtime:
#   hardware.json  detected stacks (available, unavailable, failed), shown in the app settings
#   llm.json       model and accelerator in use, read by the backend
# User choices (LLM on/off, accelerator) come from the backend in /runtime/settings.json.
# With accelerator "auto" it tries, in order: NVIDIA (CUDA), AMD (ROCm), Intel/AMD (Vulkan), CPU.
# The Ollama container is created through the Docker socket and removed when this service stops
# (docker compose down / stop / Ctrl+C) or when the LLM is disabled.
set -u

MODEL="${LLM_MODEL:-qwen3:4b}"
# Dev only: publish Ollama on 127.0.0.1:$OLLAMA_PORT for a backend running outside Docker
PUBLISH="${OLLAMA_PORT:+-p 127.0.0.1:$OLLAMA_PORT:11434}"
NAME="${OLLAMA_CONTAINER:-candidate-ollama}"
OUT=/runtime/llm.json
SETTINGS=/runtime/settings.json
HARDWARE=/runtime/hardware.json

SELF=$(hostname)
SELF_IMAGE=$(docker inspect -f '{{.Config.Image}}' "$SELF")
PROJECT=$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project"}}' "$SELF")
NETWORK=$(docker inspect -f '{{range $name, $_ := .NetworkSettings.Networks}}{{$name}} {{end}}' "$SELF" | awk '{print $1}')
VOLUME="${PROJECT:-candidate}_ollama"

CUDA=unavailable ROCM=unavailable VULKAN=unavailable
ACCELERATOR="" STARTED_WITH=""

log() { echo "[llm] $*"; }

running() { [ "$(docker inspect -f '{{.State.Running}}' "$NAME" 2>/dev/null)" = true ]; }
# Without the file (first run, before the backend starts) defaults apply
enabled() { ! grep -q '"llm_enabled": *false' "$SETTINGS" 2>/dev/null; }
preference() {
  value=$(sed -n 's/.*"llm_accelerator": *"\([a-z]*\)".*/\1/p' "$SETTINGS" 2>/dev/null)
  echo "${value:-auto}"
}

status_of() {
  case $1 in cuda) echo "$CUDA" ;; rocm) echo "$ROCM" ;; vulkan) echo "$VULKAN" ;; cpu) echo available ;; esac
}
set_status() { # accelerator status
  case $1 in cuda) CUDA=$2 ;; rocm) ROCM=$2 ;; vulkan) VULKAN=$2 ;; esac
  write_hardware
}
write_hardware() {
  printf '{"cuda": "%s", "rocm": "%s", "vulkan": "%s", "cpu": "available"}\n' "$CUDA" "$ROCM" "$VULKAN" \
    > "$HARDWARE.tmp" && mv "$HARDWARE.tmp" "$HARDWARE"
}

# Try attaching the GPU to a throwaway container (this service's image, already pulled)
probe() { docker run --rm --entrypoint true "$@" "$SELF_IMAGE" >/dev/null 2>&1; }
detect_hardware() {
  probe --gpus all && CUDA=available
  probe --device /dev/kfd --device /dev/dri && ROCM=available
  probe --device /dev/dri && VULKAN=available
  write_hardware
  log "rilevati: cuda=$CUDA rocm=$ROCM vulkan=$VULKAN cpu=available"
}

write_choice() { # model accelerator
  printf '{"base_url": "http://ollama:11434", "model": "%s", "accelerator": "%s"}\n' "$1" "$2" > "$OUT.tmp" \
    && mv "$OUT.tmp" "$OUT"
  log "in uso: $2 ($1)"
}

stop_llm() {
  rm -f "$OUT"
  docker rm -f "$NAME" >/dev/null 2>&1
}

cleanup() {
  stop_llm
  exit 0
}
trap cleanup TERM INT

# Start Ollama with the requested accelerator; fails if Docker can't attach the GPU
# or Ollama reports it is running on CPU only.
start_ollama() { # accelerator
  accelerator=$1
  case $accelerator in
    cuda) image=ollama/ollama:latest; set -- --gpus all ;;
    rocm) image=ollama/ollama:rocm; set -- --device /dev/kfd --device /dev/dri ;;
    # OLLAMA_IGPU_ENABLE lets Vulkan use integrated GPUs too
    vulkan) image=ollama/ollama:latest; set -- --device /dev/dri -e OLLAMA_VULKAN=1 -e OLLAMA_IGPU_ENABLE=1 ;;
    *) image=ollama/ollama:latest; set -- ;;
  esac
  docker rm -f "$NAME" >/dev/null 2>&1
  log "provo $accelerator"
  docker run -d --name "$NAME" --network "$NETWORK" --network-alias ollama \
    --label com.candidate.managed=true -v "$VOLUME:/root/.ollama" -e OLLAMA_KEEP_ALIVE=24h $PUBLISH \
    "$@" "$image" >/dev/null 2>&1 || { log "$accelerator non disponibile"; return 1; }

  library=""
  i=0
  while [ $i -lt 30 ]; do
    running || break
    library=$(docker logs "$NAME" 2>&1 | grep 'inference compute' | sed -n 's/.*library=\([A-Za-z0-9]*\).*/\1/p' | head -n 1)
    [ -n "$library" ] && break
    sleep 1
    i=$((i + 1))
  done
  if ! running; then
    log "$accelerator: il container si è fermato"
    docker rm -f "$NAME" >/dev/null 2>&1
    return 1
  fi
  if [ "$accelerator" != cpu ] && [ "$(echo "$library" | tr 'A-Z' 'a-z')" = cpu ]; then
    log "$accelerator: Ollama non vede la GPU"
    docker rm -f "$NAME" >/dev/null 2>&1
    return 1
  fi
  ACCELERATOR=$accelerator
}

# With "auto" try the detected stacks in order, skipping ones that already failed;
# with a specific stack try that one and fall back to CPU if it fails.
start_container() { # preference
  if [ "$1" = auto ]; then
    candidates="cuda rocm vulkan cpu"
  else
    candidates="$1 cpu"
  fi
  for candidate in $candidates; do
    [ "$(status_of "$candidate")" = available ] || continue
    start_ollama "$candidate" && return 0
    [ "$candidate" = cpu ] || set_status "$candidate" failed
  done
  return 1
}

start_llm() { # preference
  start_container "$1" || { log "impossibile avviare Ollama"; return 1; }
  until docker exec "$NAME" ollama list >/dev/null 2>&1; do
    running || return 1
    sleep 1
  done
  log "controllo il modello $MODEL (il download avviene solo la prima volta)"
  # In the background so Ctrl+C stops even a long download right away
  docker exec "$NAME" ollama pull "$MODEL" &
  wait $! || { log "download del modello non riuscito"; return 1; }
  write_choice "$MODEL" "$ACCELERATOR"
}

rm -f "$OUT"
detect_hardware
while :; do
  wanted=$(preference)
  if enabled; then
    if running && [ "$wanted" != "$STARTED_WITH" ]; then
      log "acceleratore cambiato nelle impostazioni ($STARTED_WITH -> $wanted): riavvio Ollama"
      stop_llm
    fi
    if ! running; then
      [ -f "$OUT" ] && log "il container di Ollama si è fermato, lo riavvio"
      stop_llm
      STARTED_WITH=$wanted
      if ! start_llm "$wanted"; then
        stop_llm
        log "nuovo tentativo tra un minuto"
        sleep 60 &
        wait $!
      fi
    fi
  elif running || [ -f "$OUT" ]; then
    log "LLM disattivato dalle impostazioni: fermo Ollama"
    stop_llm
  fi
  sleep 5 &
  wait $!
done
