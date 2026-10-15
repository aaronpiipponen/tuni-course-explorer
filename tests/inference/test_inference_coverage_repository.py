"""Opt-in PostgreSQL proofs for the owning inference coverage and publication-cohort reads.

These tests seed a genuine canonical catalogue, real completed evidence/proposals, and real final
inferred sets through the repositories, then exercise the read-only coverage/cohort
projections.
"""

from __future__ import annotations

import pytest
from sqlalchemy import Engine, func, select, update

from course_explorer.config import load_inference_selection_settings, load_inference_settings
from course_explorer.db.models import (
    Course,
    InferenceCourseProcessing,
    InferenceProcessingCycle,
    InferenceProcessingTarget,
    InferenceProposal,
    InferredEquivalenceGroup,
    InferredPrerequisiteSet,
)
from course_explorer.db.session import session_scope
from course_explorer.enums import InferredProducerKind
from course_explorer.inference.prompts import load_prompt_pack
from course_explorer.inference.publication import publish_current_cohort
from course_explorer.inference.scheduling_repository import InferenceSchedulingRepository
from tests.inference._scheduling_support import (
    build_pool,
    build_target_input,
    complete_target,
    publish_final_set,
    reconcile,
    seed_courses,
)

pytestmark = [
    pytest.mark.integration,
]

_CANDIDATES = tuple(f"cov-c{index:02d}" for index in range(50))
_CYCLE_CANDIDATES = tuple(f"cyc-c{index:02d}" for index in range(50))


def _completed_proposal(factory, target_group_id: str, candidate_group_ids: tuple[str, ...]):
    """Build one genuine completed target result and return its saved proposal."""
    pack = load_prompt_pack("v9")
    pool = build_pool(factory, target_group_id, candidate_group_ids)
    target_input = build_target_input(pool)
    return complete_target(factory, target_input, pack).proposal


@pytest.mark.parametrize("authority", ["pointer", "done"])
def test_inference_coverage_and_cohort_preserve_genuine_bootstrap_then_pointer_authority(
    database: tuple[Engine, object],
    authority: str,
) -> None:
    """Bootstrap uses genuine complete finals. After markers the stored pointer or done is authority."""
    _, factory = database
    seed_courses(
        factory,
        [
            ("cov-target", "COV-T", True),
            ("cov-source", "COV-S", True),
            ("cov-test", "COV-X", True),
        ]
        + [(group_id, f"COV.{index:02d}", True) for index, group_id in enumerate(_CANDIDATES)],
    )
    proposal = _completed_proposal(factory, "cov-target", _CANDIDATES)
    publish_final_set(factory, "cov-target", input_hash=proposal.identity_sha256)
    # A test-owned final set is never a bootstrap seed or coverage.
    publish_final_set(
        factory,
        "cov-test",
        input_hash="f" * 64,
        producer_kind=InferredProducerKind.TEST,
    )

    repository = InferenceSchedulingRepository(factory)
    cohort = repository.read_publication_cohort()
    assert cohort.eligible_target_group_ids == tuple(
        sorted(("cov-source", "cov-target", "cov-test", *_CANDIDATES))
    )
    assert cohort.accepted_proposal_ids == {"cov-target": proposal.proposal_id}

    coverage = repository.read_coverage()
    assert coverage.eligible_targets == 3 + len(_CANDIDATES)
    assert coverage.retained_complete_targets == 1
    assert coverage.published_targets == 1
    assert coverage.uncovered_targets == 2 + len(_CANDIDATES)
    assert coverage.historical_proposal_rows == 1
    assert coverage.current_equivalence_groups == 0
    assert coverage.cycle_id is None
    assert coverage.stage is None
    assert len(coverage.generation_counts) == 1
    assert coverage.generation_counts[0].route == "local"
    assert coverage.generation_counts[0].targets == 1

    # A genuine bootstrap seed reconciles the marker with the exact retained pointer.
    seeds = repository.read_seed_proposals()
    assert seeds == {"cov-target": proposal.proposal_id}
    reconcile(factory, seeds)

    # The stored marker pointer is authority over the published final rows. The read never falls back
    # to an unmatched final row or to raw/history output.
    publish_final_set(factory, "cov-target", input_hash="e" * 64)
    cohort = repository.read_publication_cohort()
    assert cohort.accepted_proposal_ids == {"cov-target": proposal.proposal_id}
    coverage = repository.read_coverage()
    assert coverage.retained_complete_targets == 1
    assert coverage.published_targets == 0
    assert coverage.historical_proposal_rows == 1

    if authority == "done":
        # An explicit done target suppresses selected publication while its marker pointer
        # is retained, counts as complete coverage with no generation identity, and is not
        # published while stale inference output is present.
        assert repository.set_target_disposition("cov-target", "done").disposition == "done"
        cohort = repository.read_publication_cohort()
        assert cohort.accepted_proposal_ids == {}
        assert cohort.completed_without_output_target_group_ids == ("cov-target",)
        coverage = repository.read_coverage()
        assert coverage.retained_complete_targets == 1
        assert coverage.operator_done_targets == 1
        assert coverage.generation_counts == ()
        assert coverage.published_targets == 0

        # The sole publisher withdraws the stale output. Only then does done count as published.
        publish_current_cohort(
            factory,
            repository.read_publication_cohort(),
            load_inference_settings(),
            load_inference_selection_settings(),
        )
        coverage = repository.read_coverage()
        assert coverage.published_targets == 1
        assert coverage.operator_done_targets == 1

        # Clearing restores genuine pointer selection and real provenance with no further model row.
        assert repository.set_target_disposition("cov-target", None).disposition is None
        assert repository.read_publication_cohort().accepted_proposal_ids == {
            "cov-target": proposal.proposal_id
        }
        assert (
            repository.read_target_processing("cov-target").accepted_proposal_id
            == proposal.proposal_id
        )
        with session_scope(factory) as session:
            assert session.scalar(select(func.count()).select_from(InferenceProposal)) == 1


def test_inference_coverage_reports_cycle_progress_and_refuses_broken_selected_chain(
    database: tuple[Engine, object],
) -> None:
    """Cycle progress tracks coverage and a mismatched selected pointer fails rather than vanishing."""
    _, factory = database
    seed_courses(
        factory,
        [("cyc-target", "CYC-T", True), ("cyc-source", "CYC-S", True)]
        + [
            (group_id, f"CYC.{index:02d}", True) for index, group_id in enumerate(_CYCLE_CANDIDATES)
        ],
    )
    reconcile(factory)
    repository = InferenceSchedulingRepository(factory)
    cycle = repository.begin_cycle("a" * 64, ["cyc-target"])

    coverage = repository.read_coverage()
    assert coverage.cycle_id == cycle.cycle_id
    assert coverage.stage == "multiview"
    assert coverage.multiview_completed == 0
    assert coverage.failed_targets == 0
    assert coverage.pending_targets == 1
    assert coverage.retained_complete_targets == 0

    # A marker pointer that names a genuinely completed proposal for another target fails the
    # relational selected-pointer check instead of quietly reporting zero coverage.
    source_proposal = _completed_proposal(factory, "cyc-source", _CYCLE_CANDIDATES)
    with session_scope(factory) as session:
        session.execute(
            update(InferenceCourseProcessing)
            .where(
                InferenceCourseProcessing.course_id
                == session.scalar(select(Course.id).where(Course.group_id == "cyc-target"))
            )
            .values(accepted_proposal_id=source_proposal.proposal_id)
        )
    with pytest.raises(ValueError):
        repository.read_publication_cohort()
    with pytest.raises(ValueError):
        repository.read_coverage()

    # No partial/invented rows were created by the read-only failure.
    with session_scope(factory) as session:
        assert (
            session.scalar(
                select(InferenceProcessingTarget).where(
                    InferenceProcessingTarget.cycle_id == cycle.cycle_id
                )
            )
            is not None
        )
        assert (
            session.scalar(
                select(InferenceProcessingCycle).where(
                    InferenceProcessingCycle.id == cycle.cycle_id
                )
            )
            is not None
        )
        assert session.scalar(select(InferredPrerequisiteSet)) is None
        assert session.scalar(select(InferredEquivalenceGroup)) is None
