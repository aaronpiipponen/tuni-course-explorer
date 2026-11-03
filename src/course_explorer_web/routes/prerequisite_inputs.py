"""Closed request model for the structural prerequisite graph read."""

from course_explorer_web.request_limits import BoundedRequest


class PrerequisiteGraphRequest(BoundedRequest):
    """Structural prerequisite graph inputs.

    An active-only read keeps an inactive selected course where the graph reaches it, and it draws
    the target course whether or not that course is active.
    """

    _identifier_fields = ("target_code",)
    _course_list_fields = ("selected_codes", "completed_codes")

    target_code: str
    selected_codes: tuple[str, ...] = ()
    completed_codes: tuple[str, ...] = ()
    include_recommended: bool = False
    include_inferred: bool = False
    active_only: bool = False
