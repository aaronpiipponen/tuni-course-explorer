"""Validate PNG and JPEG uploads and write them beneath the configured attachment root.

The store owns the one generated filesystem layout. Validation decodes the whole collection before
any file exists, so a refused upload leaves nothing on disk. Writing uses generated identities,
exclusive file creation and owner-only modes, and a failed write removes only the entries that call
created.
"""

from __future__ import annotations

import os
import uuid
import warnings
from collections.abc import Sequence
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict

from course_explorer import administration
from course_explorer.feedback import FeedbackValidationError
from course_explorer.feedback.definition import AttachmentField, FeedbackDefinition

_MIME_BY_FORMAT = {"PNG": "image/png", "JPEG": "image/jpeg"}
_SUFFIX_BY_MIME = {"image/png": ".png", "image/jpeg": ".jpg"}
_MAX_FILENAME_LENGTH = 200


@dataclass(frozen=True)
class AttachmentUpload:
    """One untrusted attachment field, its display filename and the bytes supplied for it."""

    field_id: str
    filename: str
    content: bytes


@dataclass(frozen=True)
class ValidatedUpload:
    """One validated attachment with its display filename and the type its bytes carry."""

    field_id: str
    filename: str
    content: bytes
    mime_type: str


class StoredAttachment(BaseModel):
    """The identity, owner and stored metadata of one written attachment."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    id: uuid.UUID
    feedback_id: uuid.UUID
    field_id: str
    filename: str
    mime_type: str


def _clean_filename(value: str) -> str:
    """Return one display filename, refusing a name that is not a plain, bounded basename."""
    filename = value.strip()
    if not filename or filename in {".", ".."}:
        raise FeedbackValidationError("an attachment must carry a filename")
    if len(filename) > _MAX_FILENAME_LENGTH:
        raise FeedbackValidationError("an attachment filename is too long")
    if "/" in filename or "\\" in filename:
        raise FeedbackValidationError("an attachment filename is not a plain basename")
    if any(ord(character) < 32 or ord(character) == 127 for character in filename):
        raise FeedbackValidationError("an attachment filename carries a control character")
    return filename


def _detect_image_type(content: bytes) -> str:
    """Return the PNG or JPEG type genuine image bytes carry, or refuse them."""
    try:
        with Image.open(BytesIO(content), formats=tuple(_MIME_BY_FORMAT)) as image:
            image.verify()
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content), formats=tuple(_MIME_BY_FORMAT)) as image:
                image.load()
                detected_format = image.format
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as error:
        raise FeedbackValidationError("an attachment is not a valid PNG or JPEG image") from error
    mime_type = _MIME_BY_FORMAT.get(detected_format or "")
    if mime_type is None:
        raise FeedbackValidationError("an attachment is not a valid PNG or JPEG image")
    return mime_type


class AttachmentStore:
    """Resolve the configured attachment root and own the files written beneath it.

    Construction and :meth:`path_for` create nothing. A relative root resolves against the checkout,
    and a root beginning with ``~/`` resolves against the home directory. Every path is derived from
    a validated field ID and generated identities, and a resolved path must stay beneath the root.
    """

    def __init__(self, root: Path) -> None:
        expanded = root.expanduser()
        if not expanded.is_absolute():
            expanded = administration.repository_root() / expanded
        self._root = expanded.resolve()

    def validate_uploads(
        self, definition: FeedbackDefinition, uploads: Sequence[AttachmentUpload]
    ) -> tuple[ValidatedUpload, ...]:
        """Validate one complete upload collection against the definition without writing files."""
        fields = {
            field.id: field for field in definition.fields if isinstance(field, AttachmentField)
        }
        counts: dict[str, int] = {}
        for upload in uploads:
            if upload.field_id not in fields:
                raise FeedbackValidationError("an attachment names no configured attachment field")
            counts[upload.field_id] = counts.get(upload.field_id, 0) + 1
        for field in fields.values():
            if field.required and counts.get(field.id, 0) == 0:
                raise FeedbackValidationError("a required attachment field carries no file")

        validated: list[ValidatedUpload] = []
        for upload in uploads:
            field = fields[upload.field_id]
            if counts[upload.field_id] > field.maxFiles:
                raise FeedbackValidationError("an attachment field carries too many files")
            if not upload.content:
                raise FeedbackValidationError("an attachment must not be empty")
            if len(upload.content) > field.maxBytesPerFile:
                raise FeedbackValidationError("an attachment exceeds its file size limit")
            filename = _clean_filename(upload.filename)
            mime_type = _detect_image_type(upload.content)
            if mime_type not in field.acceptedMimeTypes:
                raise FeedbackValidationError("an attachment uses an unaccepted image type")
            validated.append(
                ValidatedUpload(
                    field_id=upload.field_id,
                    filename=filename,
                    content=upload.content,
                    mime_type=mime_type,
                )
            )
        return tuple(validated)

    def write_submission(
        self, feedback_id: uuid.UUID, uploads: Sequence[ValidatedUpload]
    ) -> tuple[StoredAttachment, ...]:
        """Write the validated uploads for one submission and return their metadata.

        Each submission directory is created once, and a collision or symlink there fails. A raised
        write error removes only the directories and files this call created, then re-raises. The
        generated identities sort in write order, so a read ordered by field and identity lists one
        submission's attachments in upload order.
        """
        self._root.mkdir(parents=True, exist_ok=True, mode=0o700)
        created_directories: list[Path] = []
        written_files: list[Path] = []
        created_submission_directories: set[Path] = set()
        stored: list[StoredAttachment] = []
        try:
            for upload in uploads:
                field_directory = self._root / upload.field_id
                if not field_directory.exists():
                    field_directory.mkdir(mode=0o700)
                    created_directories.append(field_directory)
                submission_directory = field_directory / str(feedback_id)
                if submission_directory not in created_submission_directories:
                    submission_directory.mkdir(mode=0o700)
                    created_submission_directories.add(submission_directory)
                    created_directories.append(submission_directory)
                attachment = StoredAttachment(
                    id=uuid.uuid7(),
                    feedback_id=feedback_id,
                    field_id=upload.field_id,
                    filename=upload.filename,
                    mime_type=upload.mime_type,
                )
                path = self.path_for(attachment)
                descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                written_files.append(path)
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(upload.content)
                stored.append(attachment)
        except Exception:
            for path in written_files:
                path.unlink()
            for directory in reversed(created_directories):
                directory.rmdir()
            raise
        return tuple(stored)

    def path_for(self, attachment: StoredAttachment) -> Path:
        """Return the one generated path of a stored attachment."""
        try:
            suffix = _SUFFIX_BY_MIME[attachment.mime_type]
        except KeyError as error:
            raise ValueError("a stored attachment has an unsupported image type") from error
        candidate = (
            self._root
            / attachment.field_id
            / str(attachment.feedback_id)
            / f"{attachment.id.hex}{suffix}"
        ).resolve()
        if not candidate.is_relative_to(self._root):
            raise ValueError("an attachment path leaves the configured root")
        return candidate

    def discard_submission(self, attachments: Sequence[StoredAttachment]) -> None:
        """Remove exactly these written files and their empty submission directories.

        The field and root directories stay. A failed unlink or a non-empty submission directory
        raises instead of hiding the leftover entry.
        """
        directories: list[Path] = []
        for attachment in attachments:
            path = self.path_for(attachment)
            path.unlink()
            if path.parent not in directories:
                directories.append(path.parent)
        for directory in directories:
            directory.rmdir()


__all__ = [
    "AttachmentStore",
    "AttachmentUpload",
    "StoredAttachment",
    "ValidatedUpload",
]
