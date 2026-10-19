#!/usr/bin/bash
# Serve the administration backend of this checkout through its own module.
# Usage: scripts/run_admin_web.sh
set -euo pipefail
exec ./.venv/bin/python -m course_explorer_admin_web
