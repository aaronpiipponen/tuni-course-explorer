"""Official structure of studies: one programme/module's typed rule tree as one JSON report.

Usage:
    uv run python scripts/catalogue.py
    uv run python scripts/study_structure.py <group_id-from-the-catalogue>
    uv run python scripts/study_structure.py <group_id> --module-version <group_id>=<version_id>

An ambiguous module group needs one repeatable `--module-version` selection per group. An
ambiguous root without that selection fails with `StudyStructureVersionSelectionRequired` and a
nonzero exit, while an ambiguous nested module stays a typed unresolved node in a successful
report.
"""

import argparse
from collections.abc import Sequence

from course_explorer.study_structure.commands import run_study_structure_command


def _module_version(value: str) -> tuple[str, str]:
    """Return the stripped group and version identity of one `GROUP_ID=VERSION_ID` selection."""
    group_id, separator, version_id = value.partition("=")
    if not separator or not group_id.strip() or not version_id.strip():
        raise argparse.ArgumentTypeError("module version must be GROUP_ID=VERSION_ID")
    return group_id.strip(), version_id.strip()


def main(argv: Sequence[str] | None = None) -> int:
    """Parse one canonical root identity and its selections, delegate once, and print one report."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root_group_id")
    parser.add_argument(
        "--module-version",
        action="append",
        default=[],
        type=_module_version,
        metavar="GROUP_ID=VERSION_ID",
    )
    args = parser.parse_args(argv)
    module_versions: dict[str, str] = {}
    for group_id, version_id in args.module_version:
        if group_id in module_versions:
            parser.error(f"duplicate module version for {group_id}")
        module_versions[group_id] = version_id
    report = run_study_structure_command(args.root_group_id, module_versions=module_versions)
    print(report.model_dump_json())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
