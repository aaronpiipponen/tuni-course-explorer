"""The feedback intake boundary: one ordered definition, validated attachments and the owning
submission store.
"""


class FeedbackValidationError(ValueError):
    """A submitted answer or attachment that the feedback definition in force refuses."""


__all__ = ["FeedbackValidationError"]
