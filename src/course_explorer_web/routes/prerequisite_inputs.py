"""Closed request model for the structural prerequisite graph read."""

from pydantic import BaseModel, ConfigDict


class PrerequisiteGraphRequest(BaseModel):
    """Structural prerequisite graph inputs.

    An active-only read keeps an inactive selected course where the graph reaches it, and it draws
    the target course whether or not that course is active.
    """

    model_config = ConfigDict(extra="forbid")
    target_code: str
    selected_codes: tuple[str, ...] = ()
    completed_codes: tuple[str, ...] = ()
    include_recommended: bool = False
    include_inferred: bool = False
    active_only: bool = False
