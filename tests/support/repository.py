"""One temporary repository root whose tracked product files resolve from this checkout.

The product reads its tracked configuration, migrations, native libraries and frontend bundle
relative to the one ``course_explorer.administration.repository_root`` owner. A test that redirects
that owner to a temporary root gets the same reads through links to this checkout. Product state,
usage and serving writes resolve under the root and land in the temporary root. Each linked entry
is the checkout's own path, so a write through a link reaches this checkout.
"""

from __future__ import annotations

from pathlib import Path

from course_explorer import administration, configuration

_CHECKOUT = Path(__file__).resolve().parents[2]
_PRODUCT_ENTRIES = (
    ".env",
    ".git",
    ".venv",
    "alembic.ini",
    "alembic_feedback.ini",
    "config",
    "docker",
    "docker-compose.yml",
    "migrations",
    "migrations_feedback",
    "native",
    "pyproject.toml",
    "scripts",
    "tests",
    "uv.lock",
    "web",
)


def scratch_repository(directory: Path) -> Path:
    """Build one temporary repository root and return it.

    Each listed tracked entry is linked from this checkout when it is absent from the temporary
    root and exists in the checkout. Calling the function again on a prepared root leaves it
    unchanged.
    """
    directory.mkdir(parents=True, exist_ok=True)
    for name in _PRODUCT_ENTRIES:
        target = _CHECKOUT / name
        link = directory / name
        if (link.exists() or link.is_symlink()) or not target.exists():
            continue
        link.symlink_to(target, target_is_directory=target.is_dir())
    return directory


def redirect_repository_root(directory: Path) -> Path:
    """Point the one repository-root owner at one prepared temporary root for the whole process.

    A child process has no monkeypatch, so this assigns the owner directly and returns the root.
    """
    root = scratch_repository(directory)
    administration.repository_root = lambda: root
    return root


def bind_repository_root(monkeypatch, directory: Path) -> Path:
    """Point the one repository-root owner at one prepared temporary root."""
    root = scratch_repository(directory)
    monkeypatch.setattr(administration, "repository_root", lambda: root)
    configuration.clear_configuration_caches()
    return root
