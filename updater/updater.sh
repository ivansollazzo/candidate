#!/bin/sh
# Keeps Candidate up to date from its Git repository. The project folder is mounted at /project
# and must be a Git clone. Talks to the backend through files in /updates:
#   state.json    written here: checked-out branch, branches on the remote with their version, progress
#                 (step and an estimated percentage, from the build steps docker compose reports)
#   request.json  written by the backend: {"action": "check"} or {"action": "install", "branch": "..."}
#   settings.json written by the backend: {"check_hours": 6}, hours between checks (0 = only on request)
# An install moves the folder to the branch on the remote (local changes go to a stash), rebuilds the
# backend and frontend with docker compose (the old containers keep running until the new ones are ready)
# and removes the old images.
# This service is never rebuilt by itself: when an update changes the compose file, llm/ or updater/,
# the state asks for a manual "docker compose up --build -d".
set -u

REPO=/project
STATE=/updates/state.json
REQUEST=/updates/request.json
SETTINGS=/updates/settings.json

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

STATUS=idle STEP="" PROGRESS=0 BRANCHES="" CHECKED_AT="" LAST=""

log() { echo "[updater] $*"; }
# Without the file (before the backend starts) the default applies
check_hours() {
  value=$(sed -n 's/.*"check_hours": *\([0-9]*\).*/\1/p' "$SETTINGS" 2>/dev/null)
  echo "${value:-6}"
}
now() { date -u +%Y-%m-%dT%H:%M:%SZ; }
json() { printf '%s' "$1" | tr -d '\000-\011\013-\037' | sed 's/\\/\\\\/g; s/"/\\"/g' | awk 'NR > 1 { printf "\\n" } { printf "%s", $0 }'; }
git() { command git -C "$REPO" "$@"; }
compose() { docker compose --project-directory "$HOST_DIR" -p "$PROJECT" "$@"; }

write_state() {
  head_branch=$(git symbolic-ref --short -q HEAD)
  head_commit=$(git rev-parse --short HEAD 2>/dev/null)
  printf '{"status": "%s", "step": "%s", "progress": %s, "branch": "%s", "commit": "%s", "checked_at": "%s", "branches": [%s], "last": %s}\n' \
    "$STATUS" "$STEP" "$PROGRESS" "$(json "$head_branch")" "$head_commit" "$CHECKED_AT" "$BRANCHES" "${LAST:-null}" > "$STATE.tmp" \
    && mv "$STATE.tmp" "$STATE"
}

set_step() { STATUS=$1 STEP=$2 PROGRESS=${3:-0}; write_state; }

# Share of the build done, 0-100: the steps finished in each Dockerfile. Both BuildKit ("[backend 3/6]")
# and the classic builder ("Step 3/6") print a step when it starts, so step 3 means 2 finished
build_done() {
  service=$(grep -oE '\[(backend|frontend) [0-9]+/[0-9]+\]' /tmp/build.log | tr -d '[]' | tr / ' ' \
    | awk '{ f = ($2 - 1) / $3; if (f > done[$1]) done[$1] = f } END { print int((done["backend"] + done["frontend"]) * 50) }')
  classic=$(grep -oE '^Step [0-9]+/[0-9]+' /tmp/build.log | tr / ' ' \
    | awk '{ f = ($2 - 1) / $3; if (f > done) done = f } END { print int(done * 100) }')
  [ "${service:-0}" -gt "${classic:-0}" ] && echo "${service:-0}" || echo "${classic:-0}"
}

finish() { # result error detail restart_required [stashed]
  LAST=$(printf '{"result": "%s", "error": "%s", "detail": "%s", "restart_required": %s, "stashed": %s, "finished_at": "%s"}' \
    "$1" "$2" "$(json "$3")" "$4" "${5:-false}" "$(now)")
  STATUS=idle STEP="" PROGRESS=0
  write_state
  fix_owner
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
    log "check completed"
  else
    LAST=$(printf '{"result": "failed", "error": "fetch", "detail": "%s", "restart_required": false, "finished_at": "%s"}' \
      "$(json "$FETCH_ERROR")" "$(now)")
  fi
  STATUS=idle STEP="" PROGRESS=0
  write_state
}

# Fingerprint of the files only applied by a manual restart: the compose file, the llm service and this service
restart_files() {
  (cd "$REPO" && find docker-compose.yml llm updater -type f 2>/dev/null | sort | xargs md5sum 2>/dev/null | md5sum)
}

# Finder's .DS_Store files change on their own and are not worth keeping
NOT_DS_STORE=':(exclude,glob)**/.DS_Store'

# Whether the files match a recent version of the branch on the remote (e.g. copied there by hand):
# then the local changes are nothing to keep
published() { # branch
  for commit in $(git rev-list -n 50 "origin/$1"); do
    git diff --quiet "$commit" -- "$NOT_DS_STORE" && return 0
  done
  return 1
}

# Back to the commit that was running (the old containers are still up) and to the files as they were
rollback() {
  if [ -n "$previous_branch" ]; then
    git checkout -q -f -B "$previous_branch" "$previous"
  else
    git checkout -q -f "$previous"
  fi
  [ "$stashed" = true ] && git stash pop -q
  fix_owner
}

# The project folder is managed here: it follows the branch on the remote. Local changes to tracked files
# are kept in a stash (git stash list) rather than blocking the update; untracked files, such as
# docker-compose.override.yml and .env, are left alone.
install() { # branch
  target=$1
  log "updating to branch $target"
  set_step updating fetch
  fetch || { finish failed fetch "$FETCH_ERROR" false; return; }
  git show-ref --verify -q "refs/remotes/origin/$target" || { finish failed branch "$target" false; return; }

  previous=$(git rev-parse HEAD)
  previous_branch=$(git symbolic-ref --short -q HEAD)
  running_files=$(restart_files)
  stashed=false
  if ! git diff --quiet HEAD -- "$NOT_DS_STORE" && ! published "$target"; then
    git -c user.name=Candidate -c user.email=updater@candidate.local \
      stash push -q -m "Candidate: local changes before the update of $(now)" && stashed=true
  fi
  output=$(git checkout -q -f -B "$target" --track "origin/$target" 2>&1)
  status=$?
  fix_owner
  if [ $status -ne 0 ]; then
    rollback
    finish failed checkout "$output" false
    return
  fi
  list_branches
  set_step updating fetch 10

  restart=false
  [ "$(restart_files)" = "$running_files" ] || restart=true

  set_step updating build 10
  # In the background so a docker compose stop doesn't wait for the build; the build goes from 10% to 90%
  rm -f /tmp/build.status
  { compose up -d --build --no-deps backend frontend > /tmp/build.log 2>&1; echo $? > /tmp/build.status.tmp; mv /tmp/build.status.tmp /tmp/build.status; } &
  while [ ! -f /tmp/build.status ]; do
    progress=$((10 + $(build_done) * 80 / 100))
    [ "$progress" -gt "$PROGRESS" ] && { PROGRESS=$progress; write_state; }
    sleep 1 &
    wait $!
  done
  if [ "$(cat /tmp/build.status)" != 0 ]; then
    log "build failed"
    cat /tmp/build.log
    rollback
    list_branches
    finish failed build "$(tail -n 20 /tmp/build.log)" false
    return
  fi

  set_step updating cleanup 92
  docker image prune -f --filter "label=com.docker.compose.project=$PROJECT" >/dev/null 2>&1
  log "update completed: $(git rev-parse --short HEAD)"
  finish ok "" "" "$restart" "$stashed"
}

trap 'exit 0' TERM INT

mkdir -p /updates
rm -f "$REQUEST"
# The project folder belongs to the host user, not to root
command git config --global safe.directory '*'
if [ "$(git rev-parse --is-inside-work-tree 2>/dev/null)" != true ]; then
  log "the project folder is not a Git repository: updates unavailable"
  STATUS=unavailable
  write_state
  while :; do sleep 3600 & wait $!; done
fi

check
last_check=$(date +%s)
while :; do
  hours=$(check_hours)
  if [ -f "$REQUEST" ]; then
    action=$(sed -n 's/.*"action": *"\([a-z]*\)".*/\1/p' "$REQUEST")
    branch=$(sed -n 's/.*"branch": *"\([^"]*\)".*/\1/p' "$REQUEST")
    rm -f "$REQUEST"
    case $action in
      check) check ;;
      install) git check-ref-format --branch "$branch" >/dev/null 2>&1 && install "$branch" ;;
    esac
    last_check=$(date +%s)
  elif [ "$hours" -gt 0 ] && [ "$(date +%s)" -ge $((last_check + hours * 3600)) ]; then
    check
    last_check=$(date +%s)
  fi
  sleep 2 &
  wait $!
done
