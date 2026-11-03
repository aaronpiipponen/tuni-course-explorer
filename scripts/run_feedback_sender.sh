#!/usr/bin/bash
# Dispatch one bounded feedback publication attempt through the checkout that contains this script.
# Usage: scripts/run_feedback_sender.sh
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec env PYTHONPATH="$SCRIPT_DIR/../src" "$SCRIPT_DIR/../.venv/bin/python" -m course_explorer.feedback.sender
