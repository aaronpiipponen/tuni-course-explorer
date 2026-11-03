"""Render one mapped feedback issue and invoke the documented GitHub CLI creation command.

Rendering reads only the current definition's issue mapping and the designated attachment field, so
an unmapped answer, record metadata and another field's files never reach the issue. The CLI adapter
passes the fixed argv, body stdin and an owned empty configuration directory, copies each designated
image under its submitted filename, keeps the credential in the child environment alone, and
classifies the command's own outcome into one transient result.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from course_explorer.config import FeedbackSenderSettings
from course_explorer.feedback.definition import (
    AttachmentField,
    FeedbackDefinition,
    SelectField,
    TextField,
)


class PublicationInputError(ValueError):
    """A configured publication field or designated image cannot be read for one issue."""


@dataclass(frozen=True)
class PublicationResult:
    """The transient outcome of one external creation attempt.

    ``state`` is the current outcome, ``issue_url`` is the canonical link the command printed, and
    ``failure`` is the safe reason administration reads. The result is never saved as its own record.
    """

    state: Literal["published", "partial", "failed", "uncertain"]
    issue_url: str | None
    failure: str | None


@dataclass(frozen=True)
class RenderedIssue:
    """One issue's title, body and designated local images with their display filenames."""

    title: str
    body: str
    attachments: tuple[tuple[str, Path], ...]


def _current_option_label(field: SelectField, value: str | None) -> str:
    """Return the current English label of one selected option, or refuse an unknown answer."""
    if value is not None:
        for option in field.options:
            if option.value == value:
                return option.label.en
    raise PublicationInputError("a mapped select answer names no current option")


def render_publication(
    definition: FeedbackDefinition,
    answers: Mapping[str, str | None],
    attachments: Sequence[tuple[str, str, Path]],
) -> RenderedIssue:
    """Render one issue from the current definition's mapping alone.

    The title carries the selected type's English label uppercased and the mapped title answer. The
    body carries each mapped body field in mapping order under its English label, with a select shown
    by its current English option label and text preserved as submitted. Null optional body answers
    are omitted. Only the mapped attachment field contributes its existing local files.
    """
    fields = {field.id: field for field in definition.fields}
    mapping = definition.githubIssue

    type_field = fields[mapping.typeField]
    if not isinstance(type_field, SelectField):
        raise PublicationInputError("the mapped type field is not a select field")
    prefix = _current_option_label(type_field, answers.get(mapping.typeField)).upper()

    title_field = fields[mapping.titleField]
    if not isinstance(title_field, TextField):
        raise PublicationInputError("the mapped title field is not a text field")
    title_answer = answers.get(mapping.titleField)
    if not title_answer:
        raise PublicationInputError("the mapped title answer is missing")

    sections: list[str] = []
    for name in mapping.bodyFields:
        field = fields[name]
        value = answers.get(name)
        if value is None:
            if field.required:
                raise PublicationInputError("a required mapped body answer is missing")
            continue
        if isinstance(field, SelectField):
            rendered = _current_option_label(field, value)
        elif isinstance(field, TextField):
            rendered = value
        else:
            raise PublicationInputError("a mapped body field is not a text or select field")
        sections.append(f"## {field.label.en}\n\n{rendered}")
    body = "\n\n".join(sections)

    attachment_field = fields[mapping.attachmentField]
    if not isinstance(attachment_field, AttachmentField):
        raise PublicationInputError("the mapped attachment field is not an attachment field")
    files = tuple(
        (filename, path)
        for field_id, filename, path in attachments
        if field_id == mapping.attachmentField
    )
    if attachment_field.required and not files:
        raise PublicationInputError("a required mapped attachment field carries no file")
    for _, path in files:
        if not path.is_file():
            raise PublicationInputError("a designated image file is not readable")
    return RenderedIssue(title=f"[{prefix}] {title_answer}", body=body, attachments=files)


def _canonical_issue_url(stdout: str, repository: str) -> str | None:
    """Return the canonical created issue link, or ``None`` for any other output."""
    pattern = re.compile(rf"https://github\.com/{re.escape(repository)}/issues/[1-9][0-9]*")
    match = pattern.fullmatch(stdout.strip())
    return match.group(0) if match is not None else None


def _attachment_copies(
    directory: Path, attachments: Sequence[tuple[str, Path]]
) -> tuple[Path, ...]:
    """Copy the designated images under their own filenames, making repeated names distinct."""
    used: set[str] = set()
    copies: list[Path] = []
    for filename, source in attachments:
        stem = Path(filename).stem or "image"
        suffix = Path(filename).suffix
        name = f"{stem}{suffix}"
        index = 2
        while name.casefold() in used:
            name = f"{stem}-{index}{suffix}"
            index += 1
        used.add(name.casefold())
        target = directory / name
        shutil.copyfile(source, target)
        copies.append(target)
    return tuple(copies)


def create_github_issue(
    *,
    settings: FeedbackSenderSettings,
    title: str,
    body: str,
    attachments: tuple[tuple[str, Path], ...],
) -> PublicationResult:
    """Create one issue through the documented CLI and classify its outcome.

    The argument list is passed without a shell, the body arrives on stdin, and one designated file
    is attached per path, copied under its submitted filename so the issue shows readable names. The
    child receives only the configuration-free process names, the credential from this settings
    object and an owned empty configuration directory. A missing
    executable reports an unavailable command. A timeout, a nonzero exit without a canonical link or
    an unexpected success output reports an unconfirmed outcome. Output is discarded after
    classification.
    """
    environment = {
        name: value for name, value in os.environ.items() if name in {"HOME", "PATH", "LANG"}
    }
    with tempfile.TemporaryDirectory(prefix="feedback-gh-") as work_directory:
        root = Path(work_directory)
        config_directory = root / "config"
        config_directory.mkdir()
        argv = [
            "gh",
            "issue",
            "create",
            "--repo",
            settings.feedback_github_repository,
            "--title",
            title,
            "--body-file",
            "-",
        ]
        for path in _attachment_copies(root, attachments):
            argv.extend(("--attach", str(path)))
        environment.update(
            {
                "GH_TOKEN": settings.feedback_github_token.get_secret_value(),
                "GH_CONFIG_DIR": str(config_directory),
                "GH_PROMPT_DISABLED": "1",
            }
        )
        try:
            completed = subprocess.run(
                argv,
                input=body,
                text=True,
                capture_output=True,
                env=environment,
                timeout=settings.feedback_github_timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            return PublicationResult(
                state="uncertain",
                issue_url=None,
                failure="github_outcome_unconfirmed",
            )
        except OSError:
            return PublicationResult(
                state="failed",
                issue_url=None,
                failure="github_unavailable",
            )
    issue_url = _canonical_issue_url(completed.stdout or "", settings.feedback_github_repository)
    if issue_url is None:
        return PublicationResult(
            state="uncertain",
            issue_url=None,
            failure="github_outcome_unconfirmed",
        )
    if completed.returncode == 0:
        return PublicationResult(state="published", issue_url=issue_url, failure=None)
    return PublicationResult(
        state="partial",
        issue_url=issue_url,
        failure="attachment_upload_incomplete",
    )


__all__ = [
    "PublicationInputError",
    "PublicationResult",
    "RenderedIssue",
    "create_github_issue",
    "render_publication",
]
