"""Unified administrative entrypoint: the operator menu plus exact machine commands.

Usage:
    uv run python scripts/admin.py                      # operator menu
    uv run python scripts/admin.py menu
    uv run python scripts/admin.py setup datasets
    uv run python scripts/admin.py setup worker [--branch BRANCH] [--code-only]
    uv run python scripts/admin.py preflight
    uv run python scripts/admin.py migrate datasets
    uv run python scripts/admin.py dispose inference TARGET_ID {nothing|done|failed}
    uv run python scripts/admin.py <ingestion|translation|embedding|inference> <start|pause|resume|status|stop>
    uv run python scripts/admin.py coverage <teaching-text|embedding|inference>
    uv run python scripts/admin.py summary <catalogue|inference>

This adapter delegates once to the engine-owned ``course_explorer_admin.cli`` dispatcher, which
owns the parser, the JSON output and the safe-error presentation.
"""

from __future__ import annotations

from course_explorer_admin.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
