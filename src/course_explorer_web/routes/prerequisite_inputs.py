"""Shared closed request model for both explicit prerequisite operations."""

from pydantic import BaseModel, ConfigDict


class PrerequisitesRequest(BaseModel):
    """Prerequisite command inputs shared by the graph and minimum-route adapters."""

    model_config = ConfigDict(extra="forbid")
    target_code: str
    completed_codes: tuple[str, ...] = ()
    selected_codes: tuple[str, ...] = ()
    excluded_codes: tuple[str, ...] = ()
    include_recommended: bool = False
    include_inferred: bool = False
    active_only: bool = False
    basis: str = "completed"
    completed_node_keys: tuple[str, ...] = ()
    excluded_node_keys: tuple[str, ...] = ()
