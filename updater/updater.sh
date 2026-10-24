#!/bin/sh
# Keeps Candidate up to date from its Git repository. The project folder is mounted at /project
# and must be a Git clone. Talks to the backend through files in /updates:
#   state.json    written here: checked-out branch, branches on the remote with their version, progress
#                 (step and an estimated percentage, from the build steps docker compose reports),
#                 result of the last install and error of the last check, if it failed
#   request.json  written by the backend: {"action": "check"} or {"action": "install", "branch": "..."}
#   settings.json written by the backend: {"check_hours": 6}, hours between checks (0 = only on request)
# An install moves the folder to the branch on the remote (local changes go to a stash), rebuilds and
# recreates every service but this one with docker compose (the old containers keep running until the new
# images are built), applying the new compose file too, and removes the old images.
# The image runs this script from the project folder, so after an install the updater restarts itself
# with the new script. Its own container can't be replaced from inside it: only when an update changes
# its image (updater/Dockerfile) or its service in the compose file, the state asks for a manual
# "docker compose up --build -d".
set -u

REPO=/project
STATE=/updates/state.json
REQUEST=/updates/request.json
SETTINGS=/updates/settings.json
# A repository that doesn't answer must not block the updater: give up after this many seconds
FETCH_TIMEOUT=120
# After a failed check, try again sooner than the check interval
RETRY_SECONDS=900
# A Git lock file older than this is left over by a git killed halfway (e.g. a container stopped
# during a fetch): it would make every following fetch fail
STALE_LOCK_MINUTES=10
# When the last check succeeded, kept across restarts of the updater
CHECKED_FILE=/updates/checked_at

SCRIPT=$REPO/updater/updater.sh
# The script now running: an install that changes it restarts the updater with the new one
RUNNING_SCRIPT=$(md5sum < "$0")

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

# LAST (result of the last install) is handed over when the updater restarts itself with a new script
STATUS=idle STEP="" PROGRESS=0 BRANCHES="" CHECK_ERROR="" LAST=${LAST:-}
CHECKED_AT=$(cat "$CHECKED_FILE" 2>/dev/null)

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
  printf '{"status": "%s", "step": "%s", "progress": %s, "branch": "%s", "checked_at": "%s", "branches": [%s], "last": %s, "check_error": %s}\n' \
    "$STATUS" "$STEP" "$PROGRESS" "$(json "$head_branch")" "$CHECKED_AT" "$BRANCHES" "${LAST:-null}" "${CHECK_ERROR:-null}" > "$STATE.tmp" \
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
    entry=$(printf '{"name": "%s", "version": "%s", "build": "%s"}' "$(json "$name")" \
      "$(json "$(version_of "$ref" version)")" "$(json "$(version_of "$ref" build)")")
    BRANCHES="${BRANCHES:+$BRANCHES, }$entry"
  done
}

remove_stale_locks() {
  find "$REPO/.git" -name '*.lock' -mmin +"$STALE_LOCK_MINUTES" 2>/dev/null | while read -r lock; do
    log "removing stale Git lock $lock"
    rm -f "$lock"
  done
}

# Every fetch that works, also the one of an install, counts as a successful check
fetch() {
  remove_stale_locks
  # No credential prompts, and no waiting forever on a server that doesn't answer
  output=$(GIT_TERMINAL_PROMPT=0 timeout "$FETCH_TIMEOUT" git -C "$REPO" fetch --prune origin 2>&1)
  status=$?
  fix_owner
  if [ $status -eq 0 ]; then
    CHECKED_AT=$(now)
    CHECK_ERROR=""
    echo "$CHECKED_AT" > "$CHECKED_FILE"
    return 0
  fi
  [ -n "$output" ] || output="no answer from the repository within $FETCH_TIMEOUT seconds"
  log "fetch failed: $output"
  FETCH_ERROR=$output
  return 1
}

# The error of a failed check is shown until a fetch succeeds; it is kept apart from the result of the
# last install, so a notice like "restart required" is not lost
check() {
  set_step checking fetch
  if fetch; then
    log "check completed"
  else
    CHECK_ERROR=$(printf '{"detail": "%s", "failed_at": "%s"}' "$(json "$FETCH_ERROR")" "$(now)")
  fi
  # Without the repository, the branches are those of the last fetch that worked
  list_branches
  STATUS=idle STEP="" PROGRESS=0
  write_state
}

# Fingerprint of what only a manual restart applies: the image of this service (not this script, which is
# reloaded by itself) and its definition in the compose file
restart_files() {
  { (cd "$REPO" && find updater -type f ! -name updater.sh | sort | xargs md5sum); compose config updater; } 2>/dev/null | md5sum
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
  services=$(compose config --services | grep -vx updater)
  # Unquoted: one argument per service
  { compose up -d --build $services > /tmp/build.log 2>&1; echo $? > /tmp/build.status.tmp; mv /tmp/build.status.tmp /tmp/build.status; } &
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
  # A new version of this script takes over right away, keeping the result of the install
  if [ -f "$SCRIPT" ] && [ "$(md5sum < "$SCRIPT")" != "$RUNNING_SCRIPT" ]; then
    log "restarting with the new updater script"
    export LAST
    exec sh "$SCRIPT"
  fi
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

# Seconds until the next automatic check: the interval, or sooner after a failed check
next_check() {
  [ -n "$CHECK_ERROR" ] && [ $((hours * 3600)) -gt "$RETRY_SECONDS" ] && echo "$RETRY_SECONDS" || echo $((hours * 3600))
}

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
  elif [ "$hours" -gt 0 ] && [ "$(date +%s)" -ge $((last_check + $(next_check))) ]; then
    check
    last_check=$(date +%s)
  fi
  sleep 2 &
  wait $!
done
