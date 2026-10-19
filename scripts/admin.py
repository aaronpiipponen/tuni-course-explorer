"""Unified administrative entrypoint: the operator menu plus exact machine commands.

Usage:
    uv run python scripts/admin.py                      # operator menu
    uv run python scripts/admin.py menu
    uv run python scripts/admin.py setup datasets
    uv run python scripts/admin.py setup worker [--branch BRANCH] [--code-only]
    uv run python scripts/admin.py preflight
    uv run python scripts/admin.py migrate datasets
    uv run python scripts/admin.py datasets list
    uv run python scripts/admin.py datasets delete DATASET_ID
    uv run python scripts/admin.py backups list
    uv run python scripts/admin.py backups delete NAME
    uv run python scripts/admin.py config list
    uv run python scripts/admin.py config read FILE
    uv run python scripts/admin.py config set FILE KEY VALUE
    uv run python scripts/admin.py password --username USERNAME
    uv run python scripts/admin.py server status
    uv run python scripts/admin.py logs sessions
    uv run python scripts/admin.py logs commands
    uv run python scripts/admin.py logs read {ingestion|embedding|translation|inference} SESSION_ID {server-stdout|server-stderr|keepalive|worker-runner|worker-runtime} --lines N
    uv run python scripts/admin.py logs embedding --lines N
    uv run python scripts/admin.py usage --hours HOURS
    uv run python scripts/admin.py rebuild
    uv run python scripts/admin.py rebuild-admin
    uv run python scripts/admin.py restart-admin
    uv run python scripts/admin.py dispose inference TARGET_ID {nothing|done|failed}
    uv run python scripts/admin.py target inference TARGET_ID
    uv run python scripts/admin.py <ingestion|translation|embedding|inference> <start|pause|resume|status|stop>
    uv run python scripts/admin.py coverage <teaching-text|embedding|inference>
    uv run python scripts/admin.py summary <catalogue|inference>
    uv run python scripts/admin.py hubs

This adapter delegates once to the engine-owned ``course_explorer_admin.cli`` dispatcher, which
owns the parser, the JSON output and the safe-error presentation.
"""

from __future__ import annotations

from course_explorer_admin.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
