#!/usr/bin/bash
# Serve the administration backend of the checkout that contains this script.
# Usage: scripts/run_admin_web.sh
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec env PYTHONPATH="$SCRIPT_DIR/../src" "$SCRIPT_DIR/../.venv/bin/python" -m course_explorer_admin_web
