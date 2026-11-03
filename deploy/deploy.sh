#!/usr/bin/bash
# Build the extension database image and deploy one admitted commit to the serving checkout.
#
# Usage: deploy/deploy.sh <tested-commit>
# <tested-commit> is the full commit SHA the caller admitted and prints as deployed.
#
# The script recreates only the database service, builds the native serving libraries, enrolls the
# configured database when the state root is bootstrap, applies the role's guarded database
# migration, builds the served dataset's artifacts, builds both frontends, restarts the two serving
# units, proves their loopback listeners and HTTP answers, then prunes the superseded artifact
# builds. An enrolled site migrates Selected and builds its artifacts with serving-artifacts. A
# bootstrap site with the configured example database migrates that database and rebuilds its
# example artifacts with mock_data.py write-artifacts.
# The units and ports come from serving.conf beside this script. Enrollment of the configured
# database runs through datasets ensure-selected, and the script refuses before any build while a
# stage is running.
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: deploy/deploy.sh <tested-commit>" >&2
  exit 2
fi
tested_commit="$1"

source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/serving.conf"

python="./.venv/bin/python"
compose=("$python" -m course_explorer_admin.compose --non-interactive --)

fail_step() {
  printf 'deployment failed: %s\n' "$1" >&2
  exit 1
}

# A running stage owns a database or worker resource the deployment must not change underneath it.
"$python" -c 'from course_explorer_admin.datasets import require_stages_idle; require_stages_idle()' ||
  fail_step "a stage is running or not idle, stop it before deployment"

# The prepared image carries the exact semantic scan extension. Its named volume keeps the
# database, so only the container is recreated.
"${compose[@]}" build db || fail_step "database image build"
"${compose[@]}" up -d --wait --force-recreate --no-build --pull never db ||
  fail_step "database service recreate"

"$python" scripts/build_native.py --non-interactive || fail_step "native serving library build"

# Enrollment follows the configured example-database exception. Its mode decides the site's
# database mode, so an example bootstrap migrates and rebuilds its example artifacts while an
# enrolled site migrates Selected.
enrollment="$("$python" scripts/admin.py datasets ensure-selected)" || fail_step "dataset enrollment"
selected_dataset="$(
  printf '%s' "$enrollment" | "$python" -c 'import json, sys; print(1 if json.load(sys.stdin)["mode"] == "enrolled" else 0)'
)" || fail_step "dataset enrollment mode read"
if (( selected_dataset == 1 )); then
  "$python" scripts/admin.py migrate selected || fail_step "dataset migration"
  "$python" scripts/admin.py serving-artifacts || fail_step "serving artifact build"
else
  "$python" scripts/admin.py migrate database || fail_step "configured database migration"
  "$python" scripts/mock_data.py write-artifacts || fail_step "serving artifact build"
fi

npm --prefix web run build || fail_step "feature frontend build"
npm --prefix admin-web run build || fail_step "administration frontend build"
sudo -n /usr/bin/systemctl restart "$DEPLOY_WEB_UNIT" || fail_step "feature web restart"
systemctl --user restart "$DEPLOY_ADMIN_UNIT" || fail_step "administration web restart"

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

# Prune after the restarted supervisor opens the build this run wrote. A failed prune fails the
# deployment loudly, and the site keeps serving the build it just opened.
"$python" scripts/admin.py serving-artifacts --prune || fail_step "serving artifact prune"

printf 'deployed %s\n' "$tested_commit"
