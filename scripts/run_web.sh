#!/usr/bin/bash
# Hand only the web allowlist to its launcher. Configuration loads automatically.
set -euo pipefail
exec ./.venv/bin/python -m course_explorer_web.launch
