#!/bin/sh
# Keeps Candidate up to date from its Git repository. The project folder is mounted at /project
# and must be a Git clone. Talks to the backend through files in /updates:
#   state.json    written here: checked-out branch, branches on the remote with their version, progress
#   request.json  written by the backend: {"action": "check"} or {"action": "install", "branch": "..."}
# An install checks out the branch, rebuilds the backend and frontend with docker compose (the old
# containers keep running until the new ones are ready) and removes the old images.
# This service is never rebuilt by itself: when an update changes the compose file, llm/ or updater/,
# the state asks for a manual "docker compose up --build -d".
set -u

REPO=/project
STATE=/updates/state.json
REQUEST=/updates/request.json
CHECK_SECONDS=$(( ${UPDATE_CHECK_HOURS:-6} * 3600 ))

SELF=$(hostname)
label() { docker inspect -f "{{index .Config.Labels \"com.docker.compose.$1\"}}" "$SELF" 2>/dev/null; }
PROJECT=$(label project)
# Run compose from the same path as on the host, so it computes the same configuration
HOST_DIR=$(label project.working_dir)
case $HOST_DIR in
  /*) [ -e "$HOST_DIR" ] || { mkdir -p "$(dirname "$HOST_DIR")" && ln -s "$REPO" "$HOST_DIR"; } ;;
  *) HOST_DIR=$REPO ;;
esac
# Files created here belong to the owner of the project folder
OWNER=$(stat -c %u:%g "$REPO")

STATUS=idle STEP="" BRANCHES="" CHECKED_AT="" LAST=""

log() { echo "[updater] $*"; }
now() { date -u +%Y-%m-%dT%H:%M:%SZ; }
json() { printf '%s' "$1" | tr -d '\000-\011\013-\037' | sed 's/\\/\\\\/g; s/"/\\"/g' | awk 'NR > 1 { printf "\\n" } { printf "%s", $0 }'; }
git() { command git -C "$REPO" "$@"; }
compose() { docker compose --project-directory "$HOST_DIR" -p "$PROJECT" "$@"; }

write_state() {
  head_branch=$(git symbolic-ref --short -q HEAD)
  head_commit=$(git rev-parse --short HEAD 2>/dev/null)
  printf '{"status": "%s", "step": "%s", "branch": "%s", "commit": "%s", "checked_at": "%s", "branches": [%s], "last": %s}\n' \
    "$STATUS" "$STEP" "$(json "$head_branch")" "$head_commit" "$CHECKED_AT" "$BRANCHES" "${LAST:-null}" > "$STATE.tmp" \
    && mv "$STATE.tmp" "$STATE"
}

set_step() { STATUS=$1 STEP=$2; write_state; }

finish() { # result error detail restart_required
  LAST=$(printf '{"result": "%s", "error": "%s", "detail": "%s", "restart_required": %s, "finished_at": "%s"}' \
    "$1" "$2" "$(json "$3")" "$4" "$(now)")
  STATUS=idle STEP=""
  write_state
}

fix_owner() {
  [ "$OWNER" = 0:0 ] || find "$REPO" -xdev -user 0 -exec chown -h "$OWNER" {} + 2>/dev/null
}

# Version and build of a branch, read from backend/app/__init__.py
version_of() { # ref field
  git show "$1:backend/app/__init__.py" 2>/dev/null | sed -n "s/^__$2__ *= *\"\([^\"]*\)\".*/\1/p" | head -n 1
}

list_branches() {
  BRANCHES=""
  for name in $(git for-each-ref --format='%(refname:strip=3)' refs/remotes/origin); do
    [ "$name" = HEAD ] && continue
    ref="refs/remotes/origin/$name"
    entry=$(printf '{"name": "%s", "version": "%s", "build": "%s", "commit": "%s"}' "$(json "$name")" \
      "$(json "$(version_of "$ref" version)")" "$(json "$(version_of "$ref" build)")" "$(git rev-parse --short "$ref")")
    BRANCHES="${BRANCHES:+$BRANCHES, }$entry"
  done
}

fetch() {
  output=$(git fetch --prune origin 2>&1)
  status=$?
  fix_owner
  [ $status -eq 0 ] || { log "$output"; FETCH_ERROR=$output; return 1; }
}

check() {
  set_step checking fetch
  if fetch; then
    list_branches
    CHECKED_AT=$(now)
    log "controllo completato"
  else
    LAST=$(printf '{"result": "failed", "error": "fetch", "detail": "%s", "restart_required": false, "finished_at": "%s"}' \
      "$(json "$FETCH_ERROR")" "$(now)")
  fi
  STATUS=idle STEP=""
  write_state
}

# Back to the commit that was running (the old containers are still up)
rollback() {
  if [ -n "$previous_branch" ] && [ "$(git symbolic-ref --short -q HEAD)" = "$previous_branch" ]; then
    git reset -q --hard "$previous"
  else
    git checkout -q "${previous_branch:-$previous}"
  fi
  fix_owner
}

install() { # branch
  target=$1
  log "aggiornamento al branch $target"
  set_step updating fetch
  fetch || { finish failed fetch "$FETCH_ERROR" false; return; }
  git show-ref --verify -q "refs/remotes/origin/$target" || { finish failed branch "$target" false; return; }
  changes=$(git status --porcelain --untracked-files=no)
  [ -z "$changes" ] || { finish failed local_changes "$changes" false; return; }

  previous=$(git rev-parse HEAD)
  previous_branch=$(git symbolic-ref --short -q HEAD)
  output=$( { git checkout -q "$target" && git merge -q --ff-only "origin/$target"; } 2>&1)
  status=$?
  fix_owner
  if [ $status -ne 0 ]; then
    rollback
    finish failed checkout "$output" false
    return
  fi
  list_branches

  # The compose file, the llm service and this service are only applied by a manual restart
  restart=false
  git diff --quiet "$previous" HEAD -- docker-compose.yml llm updater || restart=true

  set_step updating build
  # In the background so a docker compose stop doesn't wait for the build
  compose up -d --build --no-deps backend frontend > /tmp/build.log 2>&1 &
  if ! wait $!; then
    log "build non riuscita"
    cat /tmp/build.log
    rollback
    list_branches
    finish failed build "$(tail -n 20 /tmp/build.log)" false
    return
  fi

  set_step updating cleanup
  docker image prune -f --filter "label=com.docker.compose.project=$PROJECT" >/dev/null 2>&1
  log "aggiornamento completato: $(git rev-parse --short HEAD)"
  finish ok "" "" "$restart"
}

trap 'exit 0' TERM INT

mkdir -p /updates
rm -f "$REQUEST"
# The project folder belongs to the host user, not to root
command git config --global safe.directory '*'
if [ "$(git rev-parse --is-inside-work-tree 2>/dev/null)" != true ]; then
  log "la cartella del progetto non è un repository Git: aggiornamenti non disponibili"
  STATUS=unavailable
  write_state
  while :; do sleep 3600 & wait $!; done
fi

check
next_check=$(( $(date +%s) + CHECK_SECONDS ))
while :; do
  if [ -f "$REQUEST" ]; then
    action=$(sed -n 's/.*"action": *"\([a-z]*\)".*/\1/p' "$REQUEST")
    branch=$(sed -n 's/.*"branch": *"\([^"]*\)".*/\1/p' "$REQUEST")
    rm -f "$REQUEST"
    case $action in
      check) check ;;
      install) git check-ref-format --branch "$branch" >/dev/null 2>&1 && install "$branch" ;;
    esac
    next_check=$(( $(date +%s) + CHECK_SECONDS ))
  elif [ "$(date +%s)" -ge "$next_check" ]; then
    check
    next_check=$(( $(date +%s) + CHECK_SECONDS ))
  fi
  sleep 2 &
  wait $!
done
