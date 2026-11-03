"""Shared feedback fixtures: stored row counts, filesystem entries and genuine image bytes."""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

from PIL import Image
from sqlalchemy import func, select

from course_explorer.feedback.models import FeedbackAttachment, FeedbackSubmission
from tests.feedback.conftest import FeedbackDatabase


def _image_bytes(
    image_format: str, *, size: tuple[int, int] = (2, 2), noise: bool = False
) -> bytes:
    """Encode one genuine small PNG or JPEG image."""
    if noise:
        payload = random.Random(0).randbytes(size[0] * size[1] * 3)
        image = Image.frombytes("RGB", size, payload)
    else:
        image = Image.new("RGB", size, (180, 40, 40))
    buffer = BytesIO()
    image.save(buffer, format=image_format)
    return buffer.getvalue()


def _row_counts(database: FeedbackDatabase) -> tuple[int, int]:
    """Return the submission and attachment row counts."""
    with database.factory() as session:
        submissions = session.scalar(select(func.count()).select_from(FeedbackSubmission))
        attachments = session.scalar(select(func.count()).select_from(FeedbackAttachment))
    return int(submissions or 0), int(attachments or 0)


def _stored_entries(root: Path) -> list[Path]:
    """Return every filesystem entry beneath the temporary attachment root."""
    if not root.exists():
        return []
    return sorted(root.rglob("*"))


@dataclass(frozen=True)
class PublisherCall:
    """The argv, body, environment, timeout and attached files one publication attempt received."""

    argv: tuple[str, ...]
    body: str
    environment: dict[str, str]
    timeout: float
    attached: dict[str, bytes]


class PublisherDouble:
    """Publisher double that replaces only the publication command execution and records each
    attempt's inputs.

    The real adapter keeps its argv construction, credential environment and outcome
    classification, and calls this double where it would call ``subprocess.run``. A missing
    ``stdout`` produces the canonical link of the repository the argv names.
    """

    def __init__(
        self,
        *,
        returncode: int = 0,
        stdout: str | None = None,
        error: BaseException | None = None,
    ) -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.error = error
        self.calls: list[PublisherCall] = []

    def __call__(self, argv: Sequence[str], **options: object) -> object:
        attached = {
            Path(argv[index + 1]).name: Path(argv[index + 1]).read_bytes()
            for index, item in enumerate(argv)
            if item == "--attach"
        }
        self.calls.append(
            PublisherCall(
                argv=tuple(argv),
                body=str(options["input"]),
                environment=dict(options["env"]),
                timeout=float(options["timeout"]),
                attached=attached,
            )
        )
        if self.error is not None:
            raise self.error
        stdout = self.stdout
        if stdout is None:
            repository = argv[argv.index("--repo") + 1]
            stdout = f"https://github.com/{repository}/issues/17\n"
        return SimpleNamespace(returncode=self.returncode, stdout=stdout, stderr="")
