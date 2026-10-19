"""Inference-owned publication of an accepted cohort into the final stores.

This module is the only inference-side publication adapter. Given an explicitly scoped,
caller-supplied cohort of exact retained proposal pointers, it reads each accepted proposal's
foreign-key-owned work and completion facts and validates that ownership once, builds the exact
target inferred-set and global equivalence-group publications, and materializes them only through
the graph/path-owned repositories. It never derives currentness from a stored timestamp or
old work id, never reruns selection, reranking, or model work, never writes a final table directly,
and never relabels inferred output as official.

A target absent from the cohort's accepted pointers is uncovered, never a complete empty result. An
explicit operator DONE target completes with no inferred output: it is excluded from the accepted
pointers, contributes no proposal/final row, and its inference-owned output is withdrawn through
the same repositories. Retained complete output is overwritten only by an accepted whole-target result. Retained proposals and their completion
facts are never rewritten. Publication only materializes accepted retained output, and inference-owned
output that a fresh cohort stops supporting is withdrawn through the same repositories. The
publisher itself never calls a model, reranker, provider route, or GPU worker.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel, ConfigDict, field_validator, model_validator
from sqlalchemy.orm import Session, sessionmaker

from course_explorer.config import InferenceSelectionSettings, InferenceSettings
from course_explorer.curriculum import CatalogueCourseActivity
from course_explorer.curriculum_repository import CurriculumRepository
from course_explorer.enums import (
    InferredCoverageState,
    InferredProducerKind,
)
from course_explorer.hashing import canonical_json_sha256
from course_explorer.inference.diagnostics import (
    PublicationDiagnostics,
    strict_ancestor_warnings,
)
from course_explorer.inference.evidence import (
    InferenceModelAttemptRecord,
    InferencePipelineRunRecord,
)
from course_explorer.inference.proposal_repository import InferenceProposalRepository
from course_explorer.inference.proposals import (
    EquivalenceProposalCandidate,
    TargetProposal,
    aggregate_equivalence_candidates,
)
from course_explorer.prerequisite.domain import (
    CurrentEquivalenceGroup,
    EquivalenceGroupMember,
    EquivalenceGroupPublication,
    InferenceEvidenceKind,
    InferenceEvidenceReference,
    InferenceNodeMetadata,
    InferredReadState,
    InferredSetCoverage,
    InferredSetPublication,
    expression_course_leaf_group_ids,
)
from course_explorer.prerequisite.equivalence_repository import InferredEquivalenceRepository
from course_explorer.prerequisite.repository import InferredPrerequisiteRepository
from course_explorer.validation import require_text as _require_text

_PRODUCER_NAME = "course_explorer.inference"


class _PublicationModel(BaseModel):
    """Frozen, closed, strict DTO base for the inference publication boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class CurrentInferenceCohort(_PublicationModel):
    """One explicitly scoped, caller-proven current selection and accepted-pointer cohort.

    ``eligible_target_group_ids`` is the sorted unique set of active canonical targets the cohort
    covers. ``accepted_proposal_ids`` names, for the targets the caller has selected, the exact
    retained proposal that is their current accepted whole-target result. A target absent from that
    mapping is uncovered, never a complete empty result. ``completed_without_output_target_group_ids``
    names the active targets whose explicit operator DONE decision completes them with no inferred
    output. They are transient cohort identities, disjoint from the accepted pointers, and never carry
    a proposal, generation identity or equivalence supporter. The cohort is partial rather than a full catalogue. A retained pointer names its own target through the accepted-proposal
    row's foreign-key ownership rather than through any generator, prompt, or
    official-snapshot equality, so retained output carries across a generation or calendar
    change and is overwritten only by an accepted target result.
    """

    eligible_target_group_ids: tuple[str, ...]
    accepted_proposal_ids: dict[str, UUID]
    completed_without_output_target_group_ids: tuple[str, ...] = ()

    @field_validator("eligible_target_group_ids")
    @classmethod
    def validate_eligible_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Require distinct nonblank canonical identities in sorted order."""
        seen: set[str] = set()
        for group_id in value:
            if not isinstance(group_id, str) or not group_id.strip():
                raise ValueError("eligible target group IDs must be nonblank strings")
            if group_id in seen:
                raise ValueError("eligible target group IDs must be unique")
            seen.add(group_id)
        if value != tuple(sorted(value)):
            raise ValueError("eligible target group IDs must be sorted")
        return value

    @field_validator("accepted_proposal_ids")
    @classmethod
    def validate_proposal_ids(cls, value: dict[str, UUID]) -> dict[str, UUID]:
        """Require each supplied pointer to map a nonblank target to an actual proposal UUID."""
        for target_group_id, proposal_id in value.items():
            if not isinstance(target_group_id, str) or not target_group_id.strip():
                raise ValueError("accepted proposal ids require nonblank target group IDs")
            if not isinstance(proposal_id, UUID):
                raise ValueError("accepted proposal ids must be UUID identities")
        return value

    @field_validator("completed_without_output_target_group_ids")
    @classmethod
    def validate_completed_without_output_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Require distinct nonblank complete-without-output identities in sorted order."""
        seen: set[str] = set()
        for group_id in value:
            if not isinstance(group_id, str) or not group_id.strip():
                raise ValueError(
                    "complete-without-output target group IDs must be nonblank strings"
                )
            if group_id in seen:
                raise ValueError("complete-without-output target group IDs must be unique")
            seen.add(group_id)
        if value != tuple(sorted(value)):
            raise ValueError("complete-without-output target group IDs must be sorted")
        return value

    @model_validator(mode="after")
    def validate_ids_within_scope(self) -> CurrentInferenceCohort:
        """Require every supplied identity to be an eligible target in this cohort."""
        ineligible = sorted(set(self.accepted_proposal_ids) - set(self.eligible_target_group_ids))
        if ineligible:
            raise ValueError(
                "accepted proposal ids must belong to eligible targets: " + ", ".join(ineligible)
            )
        unknown = sorted(
            set(self.completed_without_output_target_group_ids)
            - set(self.eligible_target_group_ids)
        )
        if unknown:
            raise ValueError(
                "complete-without-output ids must belong to eligible targets: " + ", ".join(unknown)
            )
        overlapping = sorted(
            set(self.completed_without_output_target_group_ids) & set(self.accepted_proposal_ids)
        )
        if overlapping:
            raise ValueError(
                "complete-without-output ids must not also be accepted pointer targets: "
                + ", ".join(overlapping)
            )
        return self


class CurrentPublicationPlan(_PublicationModel):
    """One read-only preparation of the current cohort: accepted proposals and exact payloads."""

    cohort: CurrentInferenceCohort
    proposals: tuple[TargetProposal, ...]
    target_publications: tuple[InferredSetPublication, ...]
    group_publications: tuple[EquivalenceGroupPublication, ...]
    diagnostics: PublicationDiagnostics


@dataclass(frozen=True)
class _PublicationOwners:
    """The read/write owners the publication adapter composes."""

    proposals: InferenceProposalRepository
    curriculum: CurriculumRepository
    inferred_sets: InferredPrerequisiteRepository
    equivalence: InferredEquivalenceRepository


def _open_publication_owners(factory: sessionmaker[Session]) -> _PublicationOwners:
    """Construct the repository owners over one shared session factory."""
    return _PublicationOwners(
        proposals=InferenceProposalRepository(factory),
        curriculum=CurriculumRepository(factory),
        inferred_sets=InferredPrerequisiteRepository(factory),
        equivalence=InferredEquivalenceRepository(factory),
    )


def _current_run_route(run: InferencePipelineRunRecord) -> str:
    """Return one shared execution's recorded route fact.

    The stored route is an opaque nonblank executor token. This validates only that a fact was
    recorded, never a fixed route vocabulary, so every persisted route is readable.
    """
    route = run.spec.configuration["route"]
    if not isinstance(route, str):
        raise ValueError("a shared execution must record a route")
    return _require_text(route, "execution route")


def _validate_current_target(
    target: CatalogueCourseActivity, retained_target_group_id: str
) -> None:
    """Require the current active canonical target to match the retained work's own target."""
    if target.group_id != retained_target_group_id:
        raise ValueError("the read target does not match the retained work target")
    if not target.is_active:
        raise ValueError(f"cannot publish an inferred result for inactive target {target.group_id}")


def _build_target_publication(
    proposal: TargetProposal,
    attempt: InferenceModelAttemptRecord,
    target: CatalogueCourseActivity,
) -> InferredSetPublication:
    """Build one complete retained inferred-set publication from an accepted proposal.

    The generated timestamp is the retained completion's own finish time and the source counts come
    from its recorded completion facts, so a calendar-only re-publication of accepted
    output does not counterfeit a new generation time.
    """
    candidate_count = attempt.payload.facts.candidate_count
    accepted_source_count = len(expression_course_leaf_group_ids(proposal.expression))
    return InferredSetPublication(
        target_group_id=proposal.target_group_id,
        activity_as_of_academic_year_start=target.activity_as_of_academic_year_start,
        activity_window_years=target.activity_window_years,
        producer_kind=InferredProducerKind.INFERENCE,
        producer_name=_PRODUCER_NAME,
        producer_version=proposal.proposal_version,
        input_hash=proposal.identity_sha256,
        coverage_state=InferredCoverageState.COMPLETE,
        coverage=InferredSetCoverage(
            eligible_source_count=candidate_count,
            processed_source_count=candidate_count,
            accepted_source_count=accepted_source_count,
        ),
        expression=proposal.expression,
        generated_at=attempt.finished_at,
    )


def _group_id_for_members(members: Sequence[str]) -> UUID:
    """Derive one stable exact-group id from the original member tuple only."""
    return uuid5(NAMESPACE_URL, canonical_json_sha256({"members": list(members)}))


def _group_input_hash(
    members: Sequence[str],
    supporters: Sequence[tuple[UUID, EquivalenceProposalCandidate]],
    identity_by_proposal_id: Mapping[UUID, str],
) -> str:
    """Hash the exact original members plus sorted supporter identity/candidate records."""
    records = [
        {
            "proposal_identity_sha256": identity_by_proposal_id[proposal_id],
            "candidate": candidate.model_dump(mode="json"),
        }
        for proposal_id, candidate in sorted(
            supporters, key=lambda item: identity_by_proposal_id[item[0]]
        )
    ]
    return canonical_json_sha256({"members": list(members), "supporters": records})


def _build_group_publications(
    proposals: tuple[TargetProposal, ...],
    curriculum: CurriculumRepository,
    finished_at_by_proposal_id: Mapping[UUID, datetime],
) -> tuple[EquivalenceGroupPublication, ...]:
    """Build the exact global group publications for the cohort's current accepted proposals.

    Each exact original member tuple retains its own stable group UUID even when activity trims its
    membership. Overlapping originals are distinct. A group with fewer than two active
    members is not published, and the caller's withdrawal pass removes any stored materialization.
    The producer version is the joined actual distinct supporter proposal versions and the
    generation time is the maximum supporter attempt finish, so retained historical support keeps
    its real provenance instead of being relabeled with current configuration.
    """
    groups = aggregate_equivalence_candidates(proposals)
    identity_by_proposal_id = {
        proposal.proposal_id: proposal.identity_sha256 for proposal in proposals
    }
    version_by_proposal_id = {
        proposal.proposal_id: proposal.proposal_version for proposal in proposals
    }
    member_group_ids = sorted(
        {
            member
            for supporters in groups
            for _, candidate in supporters
            for member in candidate.members
        }
    )
    activities = {
        activity.group_id: activity
        for activity in curriculum.get_course_activities(member_group_ids)
    }
    publications: list[EquivalenceGroupPublication] = []
    for supporters in groups:
        members = supporters[0][1].members
        confidence = min(candidate.inference.confidence for _, candidate in supporters)
        references = tuple(
            InferenceEvidenceReference(
                kind=InferenceEvidenceKind.EXPRESSION_PROPOSAL,
                reference_id=str(proposal_id),
            )
            for proposal_id, _ in sorted(supporters, key=lambda item: str(item[0]))
        )
        producer_version = "+".join(
            sorted({version_by_proposal_id[proposal_id] for proposal_id, _ in supporters})
        )
        generated_at = max(finished_at_by_proposal_id[proposal_id] for proposal_id, _ in supporters)
        live_members: list[EquivalenceGroupMember] = []
        for member_group_id in members:
            activity = activities.get(member_group_id)
            if activity is None:
                raise ValueError(
                    f"equivalence group member {member_group_id} is not a canonical course"
                )
            if not activity.is_active:
                continue
            live_members.append(
                EquivalenceGroupMember(
                    course_group_id=member_group_id,
                    activity_as_of_academic_year_start=(
                        activity.activity_as_of_academic_year_start
                    ),
                    activity_window_years=activity.activity_window_years,
                )
            )
        if len(live_members) < 2:
            continue
        publications.append(
            EquivalenceGroupPublication(
                group_id=_group_id_for_members(members),
                members=tuple(sorted(live_members, key=lambda member: member.course_group_id)),
                producer_kind=InferredProducerKind.INFERENCE,
                producer_name=_PRODUCER_NAME,
                producer_version=producer_version,
                input_hash=_group_input_hash(members, supporters, identity_by_proposal_id),
                inference=InferenceNodeMetadata(
                    confidence=confidence,
                    requirement_ids=(),
                    evidence=references,
                ),
                generated_at=generated_at,
            )
        )
    return tuple(sorted(publications, key=lambda publication: publication.group_id))


def prepare_current_publication(
    factory: sessionmaker[Session],
    cohort: CurrentInferenceCohort,
    settings: InferenceSettings,
    selection: InferenceSelectionSettings,
) -> CurrentPublicationPlan:
    """Read and validate the whole cohort before any write and build its exact publications.

    For every supplied accepted pointer this reads the exact retained proposal with its
    foreign-key-owned work, completion and shared execution run, then validates that ownership, the
    recorded execution route, and the retained proposal's own identity. Uncovered eligible targets
    contribute diagnostics and never a final publication. A selected pointer with a missing
    or mismatched retained proposal/work/completion raises before any mutation rather than silently
    disappearing or falling back to another proposal. Retained historical output is accepted on that
    FK ownership, not on current generator/prompt/official equality, and each built target/group
    payload is retained only when the matching current final row is absent. The retained-proposal
    history is counted over every eligible target in one aggregate, independently of selection, work
    status, or acceptance. Explicit operator DONE cohort targets contribute only the
    complete-without-output diagnostic count: no proposal, completion, final row, model timestamp or
    equivalence supporter is created for them. It performs no final mutation.
    """
    owners = _open_publication_owners(factory)
    proposals: list[TargetProposal] = []
    target_publications: list[InferredSetPublication] = []
    finished_at_by_proposal_id: dict[UUID, datetime] = {}
    selected = 0
    processed = 0
    local = 0
    other = 0
    accepted = 0
    published = 0
    observed = 0
    historical = owners.proposals.count_for_targets(cohort.eligible_target_group_ids)
    activities = {
        activity.group_id: activity
        for activity in owners.curriculum.get_course_activities(cohort.eligible_target_group_ids)
    }
    # Every eligible target must be a canonical active course before preparation can skip its absent
    # pointer as genuinely uncovered: an unknown or inactive eligible target is not valid coverage.
    for target_group_id in cohort.eligible_target_group_ids:
        activity = activities.get(target_group_id)
        if activity is None:
            raise ValueError(f"current target {target_group_id} is not a canonical course")
        _validate_current_target(activity, target_group_id)
    # The selected proposals and the stored sets of their targets are read in a fixed number of
    # queries before the per-target validation.
    selected_target_group_ids = tuple(
        target_group_id
        for target_group_id in cohort.eligible_target_group_ids
        if target_group_id in cohort.accepted_proposal_ids
    )
    completed = owners.proposals.read_completed_many(
        [
            cohort.accepted_proposal_ids[target_group_id]
            for target_group_id in selected_target_group_ids
        ]
    )
    stored_sets = owners.inferred_sets.read_many(selected_target_group_ids)
    for target_group_id in selected_target_group_ids:
        selected += 1
        activity = activities[target_group_id]
        proposal, work, attempt, run = completed[cohort.accepted_proposal_ids[target_group_id]]
        if proposal.target_group_id != target_group_id:
            raise ValueError("the selected proposal does not belong to its cohort target")
        if work.request.target_group_id != target_group_id:
            raise ValueError("the retained work does not match its cohort target")
        _validate_current_target(activity, work.request.target_group_id)
        processed += 1
        if _current_run_route(run) == "local":
            local += 1
        else:
            other += 1
        observed += attempt.payload.facts.candidate_count
        accepted += 1
        proposals.append(proposal)
        finished_at_by_proposal_id[proposal.proposal_id] = attempt.finished_at
        publication = _build_target_publication(proposal, attempt, activity)
        stored = stored_sets[target_group_id]
        if (
            stored.state is InferredReadState.CURRENT
            and stored.current_set is not None
            and stored.current_set.input_hash == proposal.identity_sha256
            and stored.current_set.producer_kind is InferredProducerKind.INFERENCE
            and stored.current_set.coverage_state is InferredCoverageState.COMPLETE
        ):
            published += 1
        else:
            target_publications.append(publication)
    group_publications = _build_group_publications(
        tuple(proposals), owners.curriculum, finished_at_by_proposal_id
    )
    diagnostics = PublicationDiagnostics(
        eligible_targets=len(cohort.eligible_target_group_ids),
        selected_targets=selected,
        processed_targets=processed,
        local_targets=local,
        other_route_targets=other,
        accepted_targets=accepted,
        published_targets=published,
        operator_done_targets=len(cohort.completed_without_output_target_group_ids),
        observed_packet_candidates=observed,
        expected_packet_candidates=selected * selection.inference_selection_final_k,
        historical_proposal_rows=historical,
        current_equivalence_groups=len(group_publications),
        transitive_warnings=strict_ancestor_warnings(tuple(proposals)),
        proposal_version=settings.inference_proposal_version,
        prompt_version=settings.inference_prompt_version,
        schema_version=settings.inference_schema_version,
        pipeline_version=settings.inference_pipeline_version,
    )
    return CurrentPublicationPlan(
        cohort=cohort,
        proposals=tuple(proposals),
        target_publications=tuple(target_publications),
        group_publications=group_publications,
        diagnostics=diagnostics,
    )


def _current_input_hashes(
    cohort: CurrentInferenceCohort, plan: CurrentPublicationPlan
) -> dict[str, str | None]:
    """Map every eligible target to its current accepted proposal identity or None."""
    accepted_by_target = {
        proposal.target_group_id: proposal.identity_sha256 for proposal in plan.proposals
    }
    return {
        target_group_id: accepted_by_target.get(target_group_id)
        for target_group_id in cohort.eligible_target_group_ids
    }


def _reject_incomplete_cohort(owners: _PublicationOwners, cohort: CurrentInferenceCohort) -> None:
    """Refuse a partial cohort that omits a live inference-published target before writes."""
    published_targets = set(owners.inferred_sets.list_inference_target_group_ids())
    missing = sorted(published_targets - set(cohort.eligible_target_group_ids))
    if missing:
        raise ValueError(
            "the cohort omits previously published inference targets: " + ", ".join(missing)
        )


def _group_matches_stored(
    equivalence: InferredEquivalenceRepository,
    prepared: EquivalenceGroupPublication,
    member_cache: dict[str, tuple[CurrentEquivalenceGroup, ...]],
) -> bool:
    """Return whether the prepared group already matches its stored same-UUID row semantically.

    It reads one prepared live member's stored groups once and caches the result per publication
    call, so no full-catalogue read happens. Generation year/window differences on the stored
    members are ignored here: active INFERENCE retained reads already validate
    eligibility, and a calendar-only rerun must preserve the stored contexts/timestamps instead of
    rewriting them. A changed supporter set or real membership difference does not match and is
    republished whole.
    """
    if not prepared.members:
        return False
    member_group_id = prepared.members[0].course_group_id
    if member_group_id not in member_cache:
        member_cache[member_group_id] = equivalence.read_for_member(member_group_id)
    prepared_member_ids = tuple(member.course_group_id for member in prepared.members)
    for stored in member_cache[member_group_id]:
        if stored.group_id != prepared.group_id:
            continue
        if (
            stored.producer_kind is InferredProducerKind.INFERENCE
            and stored.producer_name == prepared.producer_name
            and stored.producer_version == prepared.producer_version
            and stored.input_hash == prepared.input_hash
            and tuple(member.course_group_id for member in stored.members) == prepared_member_ids
            and stored.inference == prepared.inference
        ):
            return True
    return False


def publish_current_cohort(
    factory: sessionmaker[Session],
    cohort: CurrentInferenceCohort,
    settings: InferenceSettings,
    selection: InferenceSelectionSettings,
) -> PublicationDiagnostics:
    """Materialize the prepared cohort through the repositories and return diagnostics.

    The whole cohort is prepared and validated before any write. It then reconciles equivalence
    member activity, publishes each accepted target absent from the current final store, skips an
    exact group whose stored same-UUID row already matches the prepared payload, reconciles target
    activity with the cohort's current accepted identities, and withdraws inference-owned groups the
    cohort stops supporting. Every transaction is idempotent. A mid-batch failure raises
    and leaves immutable evidence and completed work intact for a deterministic retry. No
    cross-repository all-or-nothing atomicity is claimed.
    """
    plan = prepare_current_publication(factory, cohort, settings, selection)
    owners = _open_publication_owners(factory)
    _reject_incomplete_cohort(owners, cohort)
    owners.equivalence.reconcile_activity()
    for publication in plan.target_publications:
        owners.inferred_sets.publish(publication)
    member_cache: dict[str, tuple[CurrentEquivalenceGroup, ...]] = {}
    for group_publication in plan.group_publications:
        if _group_matches_stored(owners.equivalence, group_publication, member_cache):
            continue
        owners.equivalence.publish(group_publication)
    owners.inferred_sets.reconcile_activity(
        current_inference_input_hashes=_current_input_hashes(cohort, plan)
    )
    owners.equivalence.withdraw_absent_inference_groups(
        tuple(publication.group_id for publication in plan.group_publications)
    )
    return plan.diagnostics.model_copy(
        update={"published_targets": plan.diagnostics.accepted_targets}
    )


def read_inference_publication_diagnostics(
    factory: sessionmaker[Session],
    cohort: CurrentInferenceCohort,
    settings: InferenceSettings,
    selection: InferenceSelectionSettings,
) -> PublicationDiagnostics:
    """Read-only preparation of the cohort's diagnostics with no final mutation."""
    return prepare_current_publication(factory, cohort, settings, selection).diagnostics
