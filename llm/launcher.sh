#!/bin/sh
# Detects usable hardware stacks, starts Ollama with the chosen one and writes to /runtime:
#   hardware.json  detected stacks (available, unavailable, failed), shown in the app settings
#   llm.json       model and accelerator in use, read by the backend
#   pull.json      model being downloaded and its progress, while it lasts
# User choices (LLM on/off, accelerator, model) come from the backend in /runtime/settings.json.
# Only the chosen model is kept in the Ollama volume: changing it downloads the new one and removes the old.
# With accelerator "auto" it tries, in order: NVIDIA (CUDA), AMD (ROCm), Intel/AMD (Vulkan), CPU.
# The Ollama container is created through the Docker socket and removed when this service stops
# (docker compose down / stop / Ctrl+C) or when the LLM is disabled.
set -u

# Before the backend publishes the settings
DEFAULT_MODEL=gemma4:e2b
# Dev only: publish Ollama on 127.0.0.1:$OLLAMA_PORT for a backend running outside Docker
PUBLISH="${OLLAMA_PORT:+-p 127.0.0.1:$OLLAMA_PORT:11434}"
NAME="${OLLAMA_CONTAINER:-candidate-ollama}"
OUT=/runtime/llm.json
PULL=/runtime/pull.json
SETTINGS=/runtime/settings.json
HARDWARE=/runtime/hardware.json

SELF=$(hostname)
SELF_IMAGE=$(docker inspect -f '{{.Config.Image}}' "$SELF")
PROJECT=$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project"}}' "$SELF")
NETWORK=$(docker inspect -f '{{range $name, $_ := .NetworkSettings.Networks}}{{$name}} {{end}}' "$SELF" | awk '{print $1}')
VOLUME="${PROJECT:-candidate}_ollama"

CUDA=unavailable ROCM=unavailable VULKAN=unavailable
ACCELERATOR="" STARTED_WITH="" MODEL=""

log() { echo "[llm] $*"; }

running() { [ "$(docker inspect -f '{{.State.Running}}' "$NAME" 2>/dev/null)" = true ]; }
# Without the file (first run, before the backend starts) defaults apply
enabled() { ! grep -q '"llm_enabled": *false' "$SETTINGS" 2>/dev/null; }
preference() {
  value=$(sed -n 's/.*"llm_accelerator": *"\([a-z]*\)".*/\1/p' "$SETTINGS" 2>/dev/null)
  echo "${value:-auto}"
}
wanted_model() {
  value=$(sed -n 's/.*"llm_model": *"\([^"]*\)".*/\1/p' "$SETTINGS" 2>/dev/null)
  echo "${value:-$DEFAULT_MODEL}"
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
  log "detected: cuda=$CUDA rocm=$ROCM vulkan=$VULKAN cpu=available"
}

write_choice() { # model accelerator
  printf '{"base_url": "http://ollama:11434", "model": "%s", "accelerator": "%s"}\n' "$1" "$2" > "$OUT.tmp" \
    && mv "$OUT.tmp" "$OUT"
  log "in use: $2 ($1)"
}

stop_llm() {
  rm -f "$OUT" "$PULL"
  MODEL=""
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
  log "trying $accelerator"
  docker run -d --name "$NAME" --network "$NETWORK" --network-alias ollama \
    --label com.candidate.managed=true -v "$VOLUME:/root/.ollama" -e OLLAMA_KEEP_ALIVE=24h $PUBLISH \
    "$@" "$image" >/dev/null 2>&1 || { log "$accelerator not available"; return 1; }

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
    log "$accelerator: the container stopped"
    docker rm -f "$NAME" >/dev/null 2>&1
    return 1
  fi
  if [ "$accelerator" != cpu ] && [ "$(echo "$library" | tr 'A-Z' 'a-z')" = cpu ]; then
    log "$accelerator: Ollama does not see the GPU"
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
  start_container "$1" || { log "unable to start Ollama"; return 1; }
  until docker exec "$NAME" ollama list >/dev/null 2>&1; do
    running || return 1
    sleep 1
  done
  use_model "$(wanted_model)"
}

# Download the model if needed (pull.json reports the progress), then remove the other models
use_model() { # model
  log "checking model $1 (downloaded only the first time)"
  # In the background so Ctrl+C stops even a long download right away
  docker exec "$NAME" ollama pull "$1" > /tmp/pull.log 2>&1 &
  pull=$!
  while kill -0 "$pull" 2>/dev/null; do
    progress=$(tr '\r' '\n' < /tmp/pull.log | grep -o '[0-9]*%' | tail -n 1 | tr -d %)
    printf '{"model": "%s", "progress": %s}\n' "$1" "${progress:-0}" > "$PULL.tmp" && mv "$PULL.tmp" "$PULL"
    sleep 1 &
    wait $!
  done
  wait "$pull"
  status=$?
  rm -f "$PULL"
  if [ $status -ne 0 ]; then
    log "download of $1 failed: $(tr '\r' '\n' < /tmp/pull.log | grep -i error | tail -n 1)"
    return 1
  fi
  for other in $(docker exec "$NAME" ollama list | awk 'NR > 1 { print $1 }'); do
    [ "$other" = "$1" ] || [ "$other" = "$1:latest" ] && continue
    log "removing model $other"
    docker exec "$NAME" ollama rm "$other" >/dev/null 2>&1
  done
  MODEL=$1
  write_choice "$MODEL" "$ACCELERATOR"
}

rm -f "$OUT"
detect_hardware
while :; do
  wanted=$(preference)
  if enabled; then
    if running && [ "$wanted" != "$STARTED_WITH" ]; then
      log "accelerator changed in the settings ($STARTED_WITH -> $wanted): restarting Ollama"
      stop_llm
    fi
    if ! running; then
      [ -f "$OUT" ] && log "the Ollama container stopped, restarting it"
      stop_llm
      STARTED_WITH=$wanted
      if ! start_llm "$wanted"; then
        stop_llm
        log "retrying in a minute"
        sleep 60 &
        wait $!
      fi
    elif [ "$(wanted_model)" != "$MODEL" ]; then
      wanted=$(wanted_model)
      log "model changed in the settings (${MODEL:-none} -> $wanted)"
      previous=$MODEL
      rm -f "$OUT"
      if ! use_model "$wanted"; then
        # The previous model stays in use; the download is tried again in a minute
        [ -n "$previous" ] && MODEL=$previous && write_choice "$MODEL" "$ACCELERATOR"
        sleep 60 &
        wait $!
      fi
    fi
  elif running || [ -f "$OUT" ]; then
    log "LLM disabled in the settings: stopping Ollama"
    stop_llm
  fi
  sleep 5 &
  wait $!
done
