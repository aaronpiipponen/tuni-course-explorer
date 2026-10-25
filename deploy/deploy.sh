#!/usr/bin/bash
# Build both frontends, restart the two serving units, and prove their loopback listeners and
# their HTTP answers.
# Usage: deploy/deploy.sh <tested-commit>
# <tested-commit> is the full commit SHA the caller admitted and prints as deployed.
# The units and ports come from serving.conf beside this script.
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: deploy/deploy.sh <tested-commit>" >&2
  exit 2
fi
tested_commit="$1"

source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/serving.conf"

npm --prefix web run build
npm --prefix admin-web run build
sudo -n /usr/bin/systemctl restart "$DEPLOY_WEB_UNIT"
systemctl --user restart "$DEPLOY_ADMIN_UNIT"

# Return 0 when the process owns 127.0.0.1:port, 2 when it listens on another address of that
# port, and 1 when it holds no listener on the port.
listener_state() {
  local pid="$1" port="$2" state=0
  ss -H -ltnp "sport = :$port" | awk -v pid="$pid" -v port="$port" '
    $1 == "LISTEN" && index($0, "pid=" pid ",") > 0 {
      if ($4 == "127.0.0.1:" port) found = 1
      else wrong = 1
    }
    END {
      if (wrong) exit 2
      if (found) exit 0
      exit 1
    }
  ' || state=$?
  return "$state"
}

# Poll one unit, its active state and its listener for up to 30 seconds. The unit and port come
# first, and a trailing --user selects the user manager.
wait_serving() {
  local unit="$1" port="$2" pid state
  shift 2
  local deadline=$((SECONDS + 30))
  while (( SECONDS < deadline )); do
    if systemctl "$@" is-active --quiet "$unit"; then
      pid="$(systemctl "$@" show "$unit" -p MainPID --value)"
      if [[ "$pid" =~ ^[1-9][0-9]*$ ]]; then
        state=0
        listener_state "$pid" "$port" || state=$?
        if (( state == 0 )); then
          return 0
        fi
        if (( state == 2 )); then
          printf 'deployment failed: %s listens on an address other than 127.0.0.1:%s\n' \
            "$unit" "$port" >&2
          return 1
        fi
      fi
    fi
    sleep 1
  done
  printf 'deployment failed: %s is not active with a 127.0.0.1:%s listener\n' \
    "$unit" "$port" >&2
  return 1
}

# Poll one application over HTTP until it answers. The console refuses a request whose Host is not
# its configured origin, so its probe accepts any response, while `--fail` requires a successful
# status for the application that serves the shell.
wait_http() {
  local url="$1"
  shift
  local deadline=$((SECONDS + 15))
  while (( SECONDS < deadline )); do
    if curl --silent --max-time 5 --output /dev/null "$@" "$url"; then
      return 0
    fi
    sleep 1
  done
  printf 'deployment failed: %s answers no HTTP request\n' "$url" >&2
  return 1
}

wait_serving "$DEPLOY_WEB_UNIT" "$DEPLOY_WEB_PORT"
wait_serving "$DEPLOY_ADMIN_UNIT" "$DEPLOY_ADMIN_PORT" --user
wait_http "http://127.0.0.1:$DEPLOY_WEB_PORT/" --fail
wait_http "http://127.0.0.1:$DEPLOY_ADMIN_PORT/"

printf 'deployed %s\n' "$tested_commit"
