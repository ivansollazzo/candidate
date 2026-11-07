#!/bin/sh
# Keeps Candidate up to date with the images that .github/workflows/images.yml publishes on GHCR for every
# commit (tag sha-<commit>). Talks to the backend through files in /updates:
#   state.json    written here: status, step and progress of an install, branches with their release,
#                 result of the last install and error of the last check
#   request.json  written by the backend: {"action": "check"} or {"action": "install", "branch": "stable"}
#   settings.json written by the backend: {"check_hours": 6}, hours between checks (0 = only on request)
# The admin follows a branch of the repository: its latest commit can be installed once the images of that
# commit are published.
# An install asks the backup service for a backup (database and files), writes the docker-compose.yml of that
# commit and CANDIDATE_TAG in .env, pulls the images and recreates the services, then waits for the app to answer
# with the new build: if it doesn't, compose file and .env go back, the backup is restored and the previous
# version starts again.
# Last, the updater replaces its own container when its image changed.
set -u

REPOSITORY=${CANDIDATE_REPOSITORY:-ivansollazzo/candidate}
# The UPDATER_* variables point elsewhere, for tests or mirrors
GIT_URL=${UPDATER_GIT_URL:-https://github.com/$REPOSITORY.git}
RAW_URL=${UPDATER_RAW_URL:-https://raw.githubusercontent.com/$REPOSITORY}
REGISTRY=${UPDATER_REGISTRY:-ghcr.io/$(echo "$REPOSITORY" | tr '[:upper:]' '[:lower:]')}
IMAGES="backend frontend llm updater backup"

DIR=/project
STATE=/updates/state.json
REQUEST=/updates/request.json
SETTINGS=/updates/settings.json
LAST_FILE=/updates/last.json
CHECKED_FILE=/updates/checked_at
# The backup service (backup/backup.py): saves database and files before an update, restores them when one fails
BACKUP_URL=${UPDATER_BACKUP_URL:-http://backup:8080}
# Release and image availability of the commits already looked up
CACHE=/updates/commits
BRANCHES=/updates/branches.tsv

# A repository that doesn't answer must not block the updater
NETWORK_TIMEOUT=60
# After a failed check, try again sooner than the check interval
RETRY_SECONDS=900
# How long the new backend has to answer with its build, database migrations included
START_SECONDS=${UPDATER_START_SECONDS:-300}
# When the repository's host name stops resolving (stale DNS servers in this container), restart this
# container, at most once in this many seconds
RESTART_SECONDS=900
RESTARTED_FILE=/updates/restarted_at

SELF=$(hostname)
label() { docker inspect -f "{{index .Config.Labels \"com.docker.compose.$1\"}}" "$SELF" 2>/dev/null; }
PROJECT=$(label project)
# Compose runs from the same path as on the host, so relative paths in the compose files resolve the same
HOST_DIR=$(label project.working_dir)
case $HOST_DIR in
  /*) [ -e "$HOST_DIR" ] || { mkdir -p "$(dirname "$HOST_DIR")" && ln -s "$DIR" "$HOST_DIR"; } ;;
  *) HOST_DIR="" ;;
esac
# Files written here belong to the owner of the project folder
OWNER=$(stat -c %u:%g "$DIR" 2>/dev/null)

STATUS=idle STEP="" PROGRESS=0 CHECK_ERROR="" CHECK_DETAIL=""
LAST=$(cat "$LAST_FILE" 2>/dev/null)
CHECKED_AT=$(cat "$CHECKED_FILE" 2>/dev/null)

log() { echo "[updater] $*"; }
now() { date -u +%Y-%m-%dT%H:%M:%SZ; }
json() { printf '%s' "$1" | tr -d '\000-\011\013-\037' | sed 's/\\/\\\\/g; s/"/\\"/g' | awk 'NR > 1 { printf "\\n" } { printf "%s", $0 }'; }
compose() { docker compose --project-directory "$HOST_DIR" -p "$PROJECT" "$@"; }
fetch() { timeout "$NETWORK_TIMEOUT" wget -qO- "$1"; }
short() { echo "$1" | cut -c1-7; }
check_hours() {
  value=$(sed -n 's/.*"check_hours": *\([0-9]*\).*/\1/p' "$SETTINGS" 2>/dev/null)
  echo "${value:-6}"
}

branches_json() {
  [ -s "$BRANCHES" ] || return 0
  while IFS='	' read -r name commit version build published; do
    printf '{"name": "%s", "commit": "%s", "version": "%s", "build": "%s", "published": %s}\n' \
      "$(json "$name")" "$commit" "$(json "$version")" "$(json "$build")" "$published"
  done < "$BRANCHES" | awk 'NR > 1 { printf ", " } { printf "%s", $0 }'
}

write_state() {
  printf '{"status": "%s", "step": "%s", "progress": %s, "checked_at": "%s", "branches": [%s], "last": %s, "check_error": %s}\n' \
    "$STATUS" "$STEP" "$PROGRESS" "$CHECKED_AT" "$(branches_json)" "${LAST:-null}" "${CHECK_ERROR:-null}" > "$STATE.tmp" \
    && mv "$STATE.tmp" "$STATE"
}

set_step() { STATUS=$1 STEP=$2 PROGRESS=${3:-0}; write_state; }

finish() { # result error detail
  LAST=$(printf '{"result": "%s", "error": "%s", "detail": "%s", "finished_at": "%s"}' "$1" "$2" "$(json "$3")" "$(now)")
  echo "$LAST" > "$LAST_FILE"
  set_step idle ""
}

fix_owner() { # files
  [ -n "$OWNER" ] && [ "$OWNER" != 0:0 ] && chown "$OWNER" "$@" 2>/dev/null
  return 0
}

# Release of a commit and whether all its images are published: "version<TAB>build<TAB>true|false".
# Only commits with their images are cached: the others are looked up again until the images arrive
lookup() { # commit
  case $(cat "$CACHE/$1" 2>/dev/null) in *true) cat "$CACHE/$1"; return 0 ;; esac
  version_file=$(fetch "$RAW_URL/$1/backend/app/__init__.py") || return 1
  version=$(echo "$version_file" | sed -n 's/^__version__ *= *"\([^"]*\)".*/\1/p' | head -n 1)
  build=$(echo "$version_file" | sed -n 's/^__build__ *= *"\([^"]*\)".*/\1/p' | head -n 1)
  published=true
  for image in $IMAGES; do
    docker manifest inspect "$REGISTRY-$image:sha-$(short "$1")" >/dev/null 2>&1 || { published=false; break; }
  done
  mkdir -p "$CACHE"
  printf '%s\t%s\t%s\n' "$version" "$build" "$published" | tee "$CACHE/$1"
}

# Branches of the repository with their release. Returns 1 with CHECK_DETAIL on failure
check() {
  if ! refs=$(GIT_TERMINAL_PROMPT=0 timeout "$NETWORK_TIMEOUT" git ls-remote --heads "$GIT_URL" 2>&1); then
    CHECK_DETAIL=${refs:-"no answer from the repository within $NETWORK_TIMEOUT seconds"}
    return 1
  fi
  # "<commit><TAB>refs/heads/<branch>"
  echo "$refs" | sed -n 's|^\([0-9a-f]*\)	refs/heads/\(.*\)|\2\t\1|p' | sort > /tmp/heads
  : > "$BRANCHES.new"
  while IFS='	' read -r name commit; do
    if ! release=$(lookup "$commit"); then
      CHECK_DETAIL="couldn't read the release of $name from $RAW_URL"
      return 1
    fi
    printf '%s\t%s\t%s\n' "$name" "$commit" "$release" >> "$BRANCHES.new"
  done < /tmp/heads
  mv "$BRANCHES.new" "$BRANCHES"
}

# Docker gives a container its DNS servers when it starts: if the host's change later (new DHCP lease,
# VPN...), names stop resolving here until the container restarts
restart_self() {
  restarted=$(cat "$RESTARTED_FILE" 2>/dev/null)
  [ $(($(date +%s) - ${restarted:-0})) -ge "$RESTART_SECONDS" ] || return
  date +%s > "$RESTARTED_FILE"
  log "the repository host name doesn't resolve: restarting the updater container"
  docker restart "$SELF" >/dev/null
}

# The error of a failed check is shown until a check succeeds; the branches of the last good one stay
run_check() {
  set_step checking ""
  if check; then
    CHECKED_AT=$(now) CHECK_ERROR=""
    echo "$CHECKED_AT" > "$CHECKED_FILE"
    log "check completed"
  else
    log "check failed: $CHECK_DETAIL"
    CHECK_ERROR=$(printf '{"detail": "%s", "failed_at": "%s"}' "$(json "$CHECK_DETAIL")" "$(now)")
  fi
  set_step idle ""
  case $CHECK_DETAIL in *"Could not resolve host"*) restart_self ;; esac
  CHECK_DETAIL=""
}

set_env() { # name value: changes or adds one line of .env, the rest stays as it is
  touch "$DIR/.env"
  if grep -q "^$1=" "$DIR/.env"; then
    sed -i "s|^$1=.*|$1=$2|" "$DIR/.env"
  else
    [ -s "$DIR/.env" ] && [ -n "$(tail -c 1 "$DIR/.env")" ] && echo >> "$DIR/.env"
    echo "$1=$2" >> "$DIR/.env"
  fi
  fix_owner "$DIR/.env"
}

restore_files() {
  cp /tmp/previous/docker-compose.yml "$DIR/docker-compose.yml"
  if [ -f /tmp/previous/.env ]; then cp /tmp/previous/.env "$DIR/.env"; else rm -f "$DIR/.env"; fi
}

backup_request() { # path json: POST to the backup service, waits until the operation is over
  timeout 3600 wget -qO- -T 3600 --header 'Content-Type: application/json' --post-data "$2" "$BACKUP_URL/$1" 2>/dev/null
}

# Build answering through the web app: the page and the API forwarded to the backend must both work. Port 8080
# is plain HTTP also when the app is served over HTTPS (Settings › HTTPS); versions before it only have 5173
app_build() {
  web=http://frontend:8080
  timeout 5 wget -qO /dev/null $web/ 2>/dev/null || web=http://frontend:5173
  timeout 5 wget -qO /dev/null $web/ 2>/dev/null || return 0
  timeout 5 wget -qO- $web/api/health 2>/dev/null | sed -n 's/.*"build": *"\([^"]*\)".*/\1/p'
}

# The new version didn't start: previous compose file, .env, database and containers
roll_back() { # services
  log "the new version didn't start: rolling back"
  detail=$(compose logs --no-color --tail 40 backend frontend 2>&1)
  failed_images=$(compose config --images 2>/dev/null)
  restore_files
  compose stop backend >/dev/null 2>&1
  # The backup service of the new version restores, then the previous one is started again with the others
  if ! backup_request "backups/$BACKUP/restore" '{"safety": false}' > /dev/null; then
    detail="$detail
Restoring database and files failed: the backup $BACKUP is in the backups folder.
$(compose logs --no-color --tail 20 backup 2>&1)"
  fi
  compose up -d $1 > /tmp/up.log 2>&1 || detail="$detail
$(cat /tmp/up.log)"
  docker image rm $failed_images >/dev/null 2>&1
  finish failed start "$detail"
}

install() { # branch
  entry=$(awk -F '\t' -v b="$1" '$1 == b' "$BRANCHES" 2>/dev/null)
  [ -n "$entry" ] || { finish failed branch "$1"; return; }
  commit=$(echo "$entry" | cut -f2)
  build=$(echo "$entry" | cut -f4)
  [ "$(echo "$entry" | cut -f5)" = true ] || { finish failed image "$1"; return; }
  tag=sha-$(short "$commit")
  log "updating to $1 ($tag)"

  set_step updating backup 5
  rm -rf /tmp/previous && mkdir -p /tmp/previous
  cp "$DIR/docker-compose.yml" /tmp/previous/
  [ -f "$DIR/.env" ] && cp "$DIR/.env" /tmp/previous/
  previous_images=$(compose config --images 2>/dev/null)
  # No update without a backup. A scheduled backup may be running: it is waited for, up to five minutes
  tries=0
  until answer=$(backup_request backups "{\"kind\": \"update\", \"note\": \"$(json "$1") $(short "$commit")\"}"); do
    tries=$((tries + 1))
    if [ "$tries" -ge 30 ]; then
      finish failed backup "$(compose logs --no-color --tail 20 backup 2>&1)"
      return
    fi
    sleep 10
  done
  BACKUP=$(echo "$answer" | sed -n 's/.*"name": *"\([^"]*\)".*/\1/p')

  set_step updating download 10
  if ! fetch "$RAW_URL/$commit/docker-compose.yml" > /tmp/docker-compose.yml || [ ! -s /tmp/docker-compose.yml ]; then
    finish failed download "couldn't download docker-compose.yml of $commit from $RAW_URL"
    return
  fi
  cp /tmp/docker-compose.yml "$DIR/docker-compose.yml"
  fix_owner "$DIR/docker-compose.yml"
  set_env CANDIDATE_TAG "$tag"
  services=$(compose config --services | grep -vx updater | tr '\n' ' ')
  total=$(echo "$services" | wc -w)
  compose pull $services > /tmp/pull.log 2>&1 &
  pull=$!
  while kill -0 "$pull" 2>/dev/null; do
    progress=$((10 + $(grep -c ' Pulled' /tmp/pull.log) * 70 / (total > 0 ? total : 1)))
    [ "$progress" -gt "$PROGRESS" ] && { PROGRESS=$progress; write_state; }
    sleep 1
  done
  if ! wait "$pull"; then
    restore_files
    finish failed download "$(tail -n 20 /tmp/pull.log)"
    return
  fi

  set_step updating restart 85
  if ! compose up -d $services > /tmp/up.log 2>&1; then
    cat /tmp/up.log
    roll_back "$services"
    return
  fi

  set_step updating verify 92
  waited=0
  until [ "$(app_build)" = "$build" ]; do
    [ "$waited" -ge "$START_SECONDS" ] && { roll_back "$services"; return; }
    sleep 3
    waited=$((waited + 3))
  done

  # The images of the previous version, unless still in use (by the updater itself, for one)
  docker image rm $previous_images >/dev/null 2>&1
  log "update completed: $1 ($tag)"
  finish ok "" ""
  replace_self
}

# This container can't recreate itself with compose: a short-lived container of the new image does it
replace_self() {
  image=$(compose config --images updater 2>/dev/null)
  [ -n "$image" ] || return 0
  docker pull -q "$image" >/dev/null 2>&1 || return 0
  [ "$(docker inspect -f '{{.Image}}' "$SELF")" = "$(docker image inspect -f '{{.Id}}' "$image")" ] && return 0
  log "replacing the updater container with $image"
  old=$(docker inspect -f '{{.Image}}' "$SELF")
  docker run -d --rm -v /var/run/docker.sock:/var/run/docker.sock -v "$HOST_DIR:$HOST_DIR" -w "$HOST_DIR" \
    --entrypoint sh "$image" -c "sleep 2; docker compose -p '$PROJECT' up -d --no-deps updater && docker image rm $old" >/dev/null
}

trap 'exit 0' TERM INT

mkdir -p /updates
# sources.tsv: list of the previous format, with release tags
rm -f "$REQUEST" /updates/sources.tsv
if [ -z "$PROJECT" ] || [ -z "$HOST_DIR" ] || [ ! -f "$DIR/docker-compose.yml" ]; then
  log "not started by docker compose with the project folder in /project: updates unavailable"
  STATUS=unavailable
  write_state
  while :; do sleep 3600 & wait $!; done
fi

next_check() {
  [ -n "$CHECK_ERROR" ] && [ $((hours * 3600)) -gt "$RETRY_SECONDS" ] && echo "$RETRY_SECONDS" || echo $((hours * 3600))
}

run_check
last_check=$(date +%s)
while :; do
  hours=$(check_hours)
  if [ -f "$REQUEST" ]; then
    action=$(sed -n 's/.*"action": *"\([a-z]*\)".*/\1/p' "$REQUEST")
    branch=$(sed -n 's/.*"branch": *"\([^"]*\)".*/\1/p' "$REQUEST")
    rm -f "$REQUEST"
    case $action in
      check) run_check ;;
      install) install "$branch" ;;
    esac
    last_check=$(date +%s)
  elif [ "$hours" -gt 0 ] && [ "$(date +%s)" -ge $((last_check + $(next_check))) ]; then
    run_check
    last_check=$(date +%s)
  fi
  sleep 2 &
  wait $!
done
