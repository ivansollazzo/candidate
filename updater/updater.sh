#!/bin/sh
# Keeps Candidate up to date with the images that .github/workflows/images.yml publishes on GHCR for every
# commit (tag sha-<commit>). Talks to the backend through files in /updates:
#   state.json    written here: status, step and progress of an install, sources with their release,
#                 result of the last install and error of the last check
#   request.json  written by the backend: {"action": "check"} or {"action": "install", "ref": "refs/heads/main"}
#   settings.json written by the backend: {"check_hours": 6}, hours between checks (0 = only on request)
# The sources are the branches and the release tags (v2.1, v2.1-beta.1...) of the repository: the backend
# turns the tags into the stable and beta channels. A source can be installed once the images of its commit
# are published.
# An install dumps the database, writes the docker-compose.yml of that commit and CANDIDATE_TAG in .env,
# pulls the images and recreates the services, then waits for the backend to answer with the new build:
# if it doesn't, compose file, .env and database go back and the previous version starts again.
# Last, the updater replaces its own container when its image changed.
set -u

REPOSITORY=${CANDIDATE_REPOSITORY:-ivansollazzo/candidate}
# The UPDATER_* variables point elsewhere, for tests or mirrors
GIT_URL=${UPDATER_GIT_URL:-https://github.com/$REPOSITORY.git}
RAW_URL=${UPDATER_RAW_URL:-https://raw.githubusercontent.com/$REPOSITORY}
REGISTRY=${UPDATER_REGISTRY:-ghcr.io/$(echo "$REPOSITORY" | tr '[:upper:]' '[:lower:]')}
IMAGES="backend frontend llm updater"

DIR=/project
STATE=/updates/state.json
REQUEST=/updates/request.json
SETTINGS=/updates/settings.json
LAST_FILE=/updates/last.json
CHECKED_FILE=/updates/checked_at
DUMP=/updates/database-before-update.sql
# Release and image availability of the commits already looked up
CACHE=/updates/commits
SOURCES=/updates/sources.tsv

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

sources_json() {
  [ -s "$SOURCES" ] || return 0
  while IFS='	' read -r name kind ref commit version build published; do
    printf '{"name": "%s", "kind": "%s", "ref": "%s", "commit": "%s", "version": "%s", "build": "%s", "published": %s}\n' \
      "$(json "$name")" "$kind" "$(json "$ref")" "$commit" "$(json "$version")" "$(json "$build")" "$published"
  done < "$SOURCES" | awk 'NR > 1 { printf ", " } { printf "%s", $0 }'
}

write_state() {
  printf '{"status": "%s", "step": "%s", "progress": %s, "checked_at": "%s", "sources": [%s], "last": %s, "check_error": %s}\n' \
    "$STATUS" "$STEP" "$PROGRESS" "$CHECKED_AT" "$(sources_json)" "${LAST:-null}" "${CHECK_ERROR:-null}" > "$STATE.tmp" \
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

# Branches and release tags of the repository with their release. Returns 1 with CHECK_DETAIL on failure
check() {
  if ! refs=$(GIT_TERMINAL_PROMPT=0 timeout "$NETWORK_TIMEOUT" git ls-remote --heads --tags "$GIT_URL" 2>&1); then
    CHECK_DETAIL=${refs:-"no answer from the repository within $NETWORK_TIMEOUT seconds"}
    return 1
  fi
  # "<commit><TAB><ref>"; for annotated tags the commit is on the peeled line (refs/tags/v2.1^{})
  refs=$(echo "$refs" | awk '{ ref = $2; sub(/\^\{\}$/, "", ref); if (!(ref in commit) || $2 != ref) commit[ref] = $1 }
    END { for (ref in commit) print commit[ref] "\t" ref }')
  echo "$refs" | sed -n 's|.*	refs/heads/\(.*\)|\1\tbranch\trefs/heads/\1|p; s|.*	refs/tags/\(v[0-9].*\)|\1\ttag\trefs/tags/\1|p' \
    | sort > /tmp/wanted
  : > "$SOURCES.new"
  while IFS='	' read -r name kind path; do
    commit=$(echo "$refs" | awk -F '\t' -v p="$path" '$2 == p { print $1 }')
    if ! release=$(lookup "$commit"); then
      CHECK_DETAIL="couldn't read the release of $name from $RAW_URL"
      return 1
    fi
    printf '%s\t%s\t%s\t%s\t%s\n' "$name" "$kind" "$path" "$commit" "$release" >> "$SOURCES.new"
  done < /tmp/wanted
  mv "$SOURCES.new" "$SOURCES"
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

# The error of a failed check is shown until a check succeeds; the sources of the last good one stay
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

backend_build() {
  timeout 5 wget -qO- http://backend:8000/api/health 2>/dev/null | sed -n 's/.*"build": *"\([^"]*\)".*/\1/p'
}

# The new version didn't start: previous compose file, .env, database and containers
roll_back() { # services
  log "the new version didn't start: rolling back"
  detail=$(compose logs --no-color --tail 40 backend 2>&1)
  failed_images=$(compose config --images 2>/dev/null)
  restore_files
  compose stop backend >/dev/null 2>&1
  if ! compose exec -T db sh -c 'psql -q -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;" \
      && psql -q -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < "$DUMP" > /tmp/restore.log 2>&1; then
    detail="$detail
Database restore failed, the dump is $DUMP in the updates volume:
$(cat /tmp/restore.log)"
  fi
  compose up -d $1 > /tmp/up.log 2>&1 || detail="$detail
$(cat /tmp/up.log)"
  docker image rm $failed_images >/dev/null 2>&1
  finish failed start "$detail"
}

install() { # ref
  entry=$(awk -F '\t' -v r="$1" '$3 == r' "$SOURCES" 2>/dev/null)
  [ -n "$entry" ] || { finish failed source "$1"; return; }
  commit=$(echo "$entry" | cut -f4)
  build=$(echo "$entry" | cut -f6)
  [ "$(echo "$entry" | cut -f7)" = true ] || { finish failed image "$1"; return; }
  tag=sha-$(short "$commit")
  log "updating to $1 ($tag)"

  set_step updating backup 5
  rm -rf /tmp/previous && mkdir -p /tmp/previous
  cp "$DIR/docker-compose.yml" /tmp/previous/
  [ -f "$DIR/.env" ] && cp "$DIR/.env" /tmp/previous/
  previous_images=$(compose config --images 2>/dev/null)
  if ! compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB"' > "$DUMP.tmp" 2> /tmp/dump.log; then
    finish failed backup "$(cat /tmp/dump.log)"
    return
  fi
  mv "$DUMP.tmp" "$DUMP"

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
  until [ "$(backend_build)" = "$build" ]; do
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
rm -f "$REQUEST"
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
    ref=$(sed -n 's/.*"ref": *"\([^"]*\)".*/\1/p' "$REQUEST")
    rm -f "$REQUEST"
    case $action in
      check) run_check ;;
      install) install "$ref" ;;
    esac
    last_check=$(date +%s)
  elif [ "$hours" -gt 0 ] && [ "$(date +%s)" -ge $((last_check + $(next_check))) ]; then
    run_check
    last_check=$(date +%s)
  fi
  sleep 2 &
  wait $!
done
