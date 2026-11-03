"""Validate the ordered feedback form definition that intake and operator reads share.

The definition file owns the field order and kinds, the bilingual labels and options, the upload
limits and the GitHub issue mapping. The models here are closed, reject unknown keys and hide their
inputs from validation errors, so an edited definition fails without echoing its values.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

_FIELD_ID = re.compile(r"[a-z][a-z0-9_]*")
_SUPPORTED_MIME_TYPES = frozenset({"image/png", "image/jpeg"})


class _DefinitionModel(BaseModel):
    """Frozen, closed base for the external definition contract."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class LocalizedText(_DefinitionModel):
    """One English and one Finnish text that both state a nonblank value."""

    en: StrictStr
    fi: StrictStr

    @field_validator("en", "fi")
    @classmethod
    def reject_blank_label(cls, value: str) -> str:
        """Reject a blank label without normalizing it."""
        if not value.strip():
            raise ValueError("feedback labels must not be blank")
        return value


class FeedbackOption(_DefinitionModel):
    """One selectable option with its stable value, its label and its publication default."""

    value: StrictStr
    label: LocalizedText
    publicIssueByDefault: StrictBool | None = None

    @field_validator("value")
    @classmethod
    def reject_blank_value(cls, value: str) -> str:
        """Reject a blank option value without normalizing it."""
        if not value.strip():
            raise ValueError("feedback option values must not be blank")
        return value


class TextField(_DefinitionModel):
    """One single-row or multiline text answer with its maximum character count."""

    kind: Literal["text", "textarea"]
    id: StrictStr
    label: LocalizedText
    required: StrictBool
    maxLength: StrictInt = Field(gt=0)


class SelectField(_DefinitionModel):
    """One select answer with its ordered options."""

    kind: Literal["select"]
    id: StrictStr
    label: LocalizedText
    required: StrictBool
    options: tuple[FeedbackOption, ...] = Field(min_length=1)


class AttachmentField(_DefinitionModel):
    """One attachment answer with its permitted image types and upload limits."""

    kind: Literal["attachment"]
    id: StrictStr
    label: LocalizedText
    required: StrictBool
    acceptedMimeTypes: tuple[StrictStr, ...] = Field(min_length=1)
    maxFiles: StrictInt = Field(gt=0)
    maxBytesPerFile: StrictInt = Field(gt=0)

    @field_validator("acceptedMimeTypes")
    @classmethod
    def require_supported_image_types(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Require the supported PNG and JPEG types only, without duplicates."""
        if len(set(value)) != len(value) or not set(value) <= _SUPPORTED_MIME_TYPES:
            raise ValueError("feedback attachments accept PNG and JPEG image types alone")
        return value


FeedbackField = Annotated[TextField | SelectField | AttachmentField, Field(discriminator="kind")]


class GithubIssueMapping(_DefinitionModel):
    """The configured field names that a published GitHub issue takes its parts from."""

    typeField: StrictStr
    titleField: StrictStr
    bodyFields: tuple[StrictStr, ...]
    attachmentField: StrictStr


class FeedbackDefinition(_DefinitionModel):
    """The ordered fields, the unchosen select placeholder and the issue mapping."""

    selectPlaceholder: LocalizedText
    fields: tuple[FeedbackField, ...] = Field(min_length=1)
    githubIssue: GithubIssueMapping

    @field_validator("fields")
    @classmethod
    def require_unique_ids_and_option_values(
        cls, value: tuple[FeedbackField, ...]
    ) -> tuple[FeedbackField, ...]:
        """Require unique identifier-shaped field IDs and unique option values per select."""
        seen: set[str] = set()
        for field in value:
            if _FIELD_ID.fullmatch(field.id) is None:
                raise ValueError("feedback field IDs must match [a-z][a-z0-9_]*")
            if field.id in seen:
                raise ValueError("feedback field IDs must be unique")
            seen.add(field.id)
            if isinstance(field, SelectField):
                option_values = [option.value for option in field.options]
                if len(set(option_values)) != len(option_values):
                    raise ValueError("feedback select option values must be unique within a field")
        return value

    @model_validator(mode="after")
    def require_issue_mapping_fields(self) -> FeedbackDefinition:
        """Require each mapped name to exist with the kind the publication rule needs."""
        by_id = {field.id: field for field in self.fields}
        mapping = self.githubIssue
        type_field = by_id.get(mapping.typeField)
        if not isinstance(type_field, SelectField):
            raise ValueError("the issue type field must name a select field")
        title_field = by_id.get(mapping.titleField)
        if not isinstance(title_field, TextField):
            raise ValueError("the issue title field must name a text field")
        if len(set(mapping.bodyFields)) != len(mapping.bodyFields):
            raise ValueError("the issue body fields must be unique")
        for name in mapping.bodyFields:
            body_field = by_id.get(name)
            if not isinstance(body_field, (TextField, SelectField)):
                raise ValueError("each issue body field must name a text or select field")
        attachment_field = by_id.get(mapping.attachmentField)
        if not isinstance(attachment_field, AttachmentField):
            raise ValueError("the issue attachment field must name an attachment field")
        return self


def load_feedback_definition(root: Path) -> FeedbackDefinition:
    """Read and validate the definition beneath ``root``, without caching it."""
    payload = (root / "config/feedback-form.json").read_text(encoding="utf-8")
    return FeedbackDefinition.model_validate(json.loads(payload))


__all__ = [
    "AttachmentField",
    "FeedbackDefinition",
    "FeedbackField",
    "FeedbackOption",
    "GithubIssueMapping",
    "LocalizedText",
    "SelectField",
    "TextField",
    "load_feedback_definition",
]
