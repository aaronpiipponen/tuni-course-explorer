"""Unified administrative entrypoint: the operator menu plus exact machine commands.

Usage:
    uv run python scripts/admin.py                       # operator menu
    uv run python scripts/admin.py menu
    uv run python scripts/admin.py setup datasets
    uv run python scripts/admin.py setup worker [--branch BRANCH] [--code-only]
    uv run python scripts/admin.py self-host example
    uv run python scripts/admin.py self-host real-database
    uv run python scripts/admin.py preflight
    uv run python scripts/admin.py migrate selected
    uv run python scripts/admin.py migrate working
    uv run python scripts/admin.py migrate database
    uv run python scripts/admin.py datasets list
    uv run python scripts/admin.py datasets copy-to-working SOURCE_DATASET_ID
    uv run python scripts/admin.py datasets copy-to-selected SOURCE_DATASET_ID --confirm-restart
    uv run python scripts/admin.py datasets ensure-selected
    uv run python scripts/admin.py datasets delete DATASET_ID [--confirm-working]
    uv run python scripts/admin.py backups list
    uv run python scripts/admin.py backups delete NAME
    uv run python scripts/admin.py config list
    uv run python scripts/admin.py config read FILE
    uv run python scripts/admin.py config set FILE KEY VALUE
    uv run python scripts/admin.py password --username USERNAME
    uv run python scripts/admin.py server status
    uv run python scripts/admin.py logs sessions
    uv run python scripts/admin.py logs commands
    uv run python scripts/admin.py logs read STAGE SESSION_ID STREAM --lines N
    uv run python scripts/admin.py logs embedding --lines N
    uv run python scripts/admin.py usage --hours HOURS
    uv run python scripts/admin.py feedback list [--query TEXT] [--filters JSON]
    uv run python scripts/admin.py feedback attachment FEEDBACK_ID ATTACHMENT_ID
    uv run python scripts/admin.py feedback delete FEEDBACK_ID
    uv run python scripts/admin.py rebuild
    uv run python scripts/admin.py rebuild-admin
    uv run python scripts/admin.py restart-admin
    uv run python scripts/admin.py dispose inference TARGET_ID {nothing|done|failed}
    uv run python scripts/admin.py target inference TARGET_ID
    uv run python scripts/admin.py STAGE {start|pause|resume|status|stop}
    uv run python scripts/admin.py coverage CATEGORY --role {selected|working}
    uv run python scripts/admin.py summary <catalogue|inference> --role <selected|working>
    uv run python scripts/admin.py serving-artifacts [--dataset ID] [--prune]

Options:
    --branch BRANCH        Git branch the worker setup fast-forwards to, default main
    --code-only            update the worker code and its locked environment alone
    --confirm-working      confirm deletion of the Working dataset, with every stage idle
    --confirm-restart      confirm the serving restart of copy-to-selected
    --query TEXT           literal case-insensitive substring over the stored text answers
    --filters JSON         JSON object of select field names and option values, default {}
    --lines N              number of trailing log lines to read
    --hours HOURS          width of the usage window in hours
    --role ROLE            dataset role to report on, selected or working
    --dataset ID           in-pipeline dataset to target, default the selected dataset
    --prune                remove other builds, embedding directories and temporary outputs

STAGE is one of ingestion, embedding, translation and inference. STREAM is one of server-stdout,
server-stderr, keepalive, worker-runner and worker-runtime. A coverage category is teaching-text,
embedding or inference, and a summary category is catalogue or inference. Each subcommand prints its
own options and arguments when it runs with `--help`.

This adapter delegates once to the engine-owned ``course_explorer_admin.cli`` dispatcher, which
owns the parser, the JSON output and the safe-error presentation. The wrapper loads the package of
the checkout that contains it, so a copy writes only into that copy.
"""

from __future__ import annotations

from _checkout_source import install


def main() -> int:
    """Run the administration dispatcher from this checkout."""
    install()
    from course_explorer_admin.cli import main as run

    return run()


if __name__ == "__main__":
    raise SystemExit(main())
