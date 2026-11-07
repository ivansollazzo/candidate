#!/bin/sh
# Starts Caddy with the plain HTTP configuration, then keeps it in line with Settings › HTTPS: every few
# seconds it tells the backend which configuration is in use and gets the name of the wanted one. A new one is
# downloaded (Caddyfile and certificates) and loaded with a reload; if Caddy refuses it, the configuration in
# use stays (plain HTTP after a start), the error goes to the backend and that configuration isn't tried again
# until the settings change.

API=${API_URL:-http://backend:8000}/api/internal/https
PLAIN=/etc/caddy/Caddyfile
BUNDLES=/etc/caddy/https
INTERVAL=${HTTPS_SYNC_SECONDS:-5}

applied=off   # configuration in use: "off" (plain HTTP) or the name of an HTTPS one
failed=""     # configuration Caddy refused
: > /tmp/https-error

caddy run --config "$PLAIN" --adapter caddyfile &
caddy=$!
trap 'kill -TERM "$caddy" 2>/dev/null; wait "$caddy"; exit 0' TERM INT

load() { # Caddyfile
  caddy reload --config "$1" --adapter caddyfile --force > /tmp/https-reload.log 2>&1
}

while kill -0 "$caddy" 2>/dev/null; do
  sleep "$INTERVAL" &
  wait $!
  wanted=$(wget -qO- -T 5 --post-data "$(cat /tmp/https-error)" "$API/sync?applied=$applied&failed=$failed" 2>/dev/null) || continue
  case "$wanted" in
    off|[0-9a-f]*) ;;
    *) continue ;;
  esac
  [ "$wanted" = "$applied" ] || [ "$wanted" = "$failed" ] && continue

  if [ "$wanted" = off ]; then
    config=$PLAIN
  else
    dir=$BUNDLES/$wanted
    rm -rf "$dir" && mkdir -p "$dir"
    if ! wget -qO- -T 10 "$API/bundle/$wanted" 2>/dev/null | tar xzf - -C "$dir" 2>/dev/null || [ ! -s "$dir/Caddyfile" ]; then
      rm -rf "$dir"
      continue  # settings changed meanwhile, or the backend is restarting: next round
    fi
    config=$dir/Caddyfile
  fi

  if load "$config"; then
    echo "https: configuration $wanted in use"
    applied=$wanted
    failed=""
    : > /tmp/https-error
    # Older configurations are no longer needed
    for old in "$BUNDLES"/*; do
      [ -d "$old" ] && [ "$old" != "$BUNDLES/$applied" ] && rm -rf "$old"
    done
  else
    echo "https: configuration $wanted refused, $applied stays in use"
    cat /tmp/https-reload.log
    failed=$wanted
    tail -n 30 /tmp/https-reload.log > /tmp/https-error
    [ "$wanted" = off ] || rm -rf "$BUNDLES/$wanted"
  fi
done
