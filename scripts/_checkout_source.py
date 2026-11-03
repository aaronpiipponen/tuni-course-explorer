"""Put the checkout that contains a script first on the import path and in ``PYTHONPATH``."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def install() -> str:
    """Prefer this checkout's package for the process and the children it starts.

    The source directory comes from the calling script's own checkout, so a copy built or run with
    a shared virtual environment reads and writes only that copy.
    """
    source = str(Path(__file__).resolve().parents[1] / "src")
    sys.path.insert(0, source)
    existing = os.environ.get("PYTHONPATH")
    os.environ["PYTHONPATH"] = source if not existing else f"{source}{os.pathsep}{existing}"
    return source
