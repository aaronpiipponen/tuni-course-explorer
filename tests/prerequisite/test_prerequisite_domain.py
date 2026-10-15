"""Contracts for prerequisite expression round-trips and composed roles."""

from __future__ import annotations

from decimal import Decimal

from course_explorer.prerequisite.domain import (
    AndRequirement,
    ComposedAndRole,
    ComposedOrRole,
    CreditRequirement,
    InferenceEvidenceReference,
    InferenceNodeMetadata,
    InferredPrerequisiteCategory,
    ModuleBlockRequirement,
    ModuleRequirement,
    OfficialPrerequisiteKind,
    OpaqueCreditRequirement,
    OrRequirement,
    PrerequisiteOrigin,
    dump_prerequisite_expression,
    parse_prerequisite_expression,
)
from tests.prerequisite._expression_support import inferred_course, official_course


def inferred_metadata(
    confidence: str = "0.9",
    *,
    requirement_ids: tuple[str, ...] = ("R1",),
    evidence: tuple[InferenceEvidenceReference, ...] = (),
) -> InferenceNodeMetadata:
    """Build one inferred node metadata payload with explicit confidence."""
    return InferenceNodeMetadata(
        confidence=Decimal(confidence), requirement_ids=requirement_ids, evidence=evidence
    )


def test_expression_union_round_trips_every_node_kind_without_flattening() -> None:
    """A mixed OR/AND expression round-trips through the strict parser without flattening."""
    and_node = AndRequirement(
        type="and",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.COMPULSORY,
        children=(official_course("a"), official_course("a")),
    )
    or_node = OrRequirement(
        type="or",
        origin=PrerequisiteOrigin.COMPOSED,
        composed_role=ComposedOrRole.LOGICAL,
        children=(and_node, inferred_course("course-a", inference=inferred_metadata())),
    )
    module_node = ModuleRequirement(
        type="module",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
        module_group_id="module-a",
    )
    credit_node = CreditRequirement(
        type="credits",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
        credits_min=Decimal("0.90"),
        credits_max=Decimal("5.00"),
        child=module_node,
    )

    # The composed disjunction retains both distinct official/inferred child kinds exactly.
    dumped_or = dump_prerequisite_expression(or_node)
    assert parse_prerequisite_expression(dumped_or) == or_node
    assert [child["type"] for child in dumped_or["children"]] == [
        "and",
        "course",
    ]

    # Repeated children and their order survive exactly. No implicit deduplication.
    dumped_and = dump_prerequisite_expression(and_node)
    assert [child["course_group_id"] for child in dumped_and["children"]] == ["a", "a"]

    # Decimal values always dump as canonical fixed-point strings, never binary float.
    confidence_dump = dump_prerequisite_expression(
        inferred_course("course-a", inference=inferred_metadata("0.90"))
    )
    assert confidence_dump["inference"]["confidence"] == "0.9"
    assert parse_prerequisite_expression(confidence_dump).inference.confidence == Decimal("0.90")

    credit_dump = dump_prerequisite_expression(credit_node)
    assert credit_dump["credits_min"] == "0.9"
    assert credit_dump["credits_max"] == "5"

    # The two compiled-only official kinds are childless/opaque and boundary nodes with no
    # fabricated courses. Both round-trip through the strict parser beside the other node kinds.
    opaque_node = OpaqueCreditRequirement(
        type="opaque_credits",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
        work_key="work-a",
        credits_min=Decimal("5.00"),
        credits_max=Decimal("10"),
    )
    opaque_dump = dump_prerequisite_expression(opaque_node)
    assert opaque_dump["type"] == "opaque_credits"
    assert opaque_dump["work_key"] == "work-a"
    assert opaque_dump["credits_min"] == "5"
    assert opaque_dump["credits_max"] == "10"
    assert opaque_dump["official_kind"] == "module_rule"
    assert parse_prerequisite_expression(opaque_dump) == opaque_node

    block_node = ModuleBlockRequirement(
        type="module_block",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.COMPULSORY,
        module_group_id="module-a",
        child=opaque_node,
    )
    block_dump = dump_prerequisite_expression(block_node)
    assert block_dump["type"] == "module_block"
    assert block_dump["module_group_id"] == "module-a"
    assert block_dump["child"]["type"] == "opaque_credits"
    assert parse_prerequisite_expression(block_dump) == block_node


def test_composed_and_roles_validate_and_round_trip_without_changing_inferred_payloads() -> None:
    """Composed AND/OR roles round-trip exactly and never enter stored official/inferred payloads."""
    logical = AndRequirement(
        type="and",
        origin=PrerequisiteOrigin.COMPOSED,
        composed_role=ComposedAndRole.LOGICAL,
        children=(official_course("a"), official_course("b")),
    )
    expanded = AndRequirement(
        type="and",
        origin=PrerequisiteOrigin.COMPOSED,
        composed_role=ComposedAndRole.EXPANDED_COURSE,
        children=(official_course("a"), official_course("b")),
    )

    # Both valid AND roles survive the canonical dump/parse path with their role attached, and the
    # role is a field discriminator on the same eight-kind `and` node.
    logical_dump = dump_prerequisite_expression(logical)
    expanded_dump = dump_prerequisite_expression(expanded)
    assert logical_dump["composed_role"] == "logical"
    assert expanded_dump["composed_role"] == "expanded_course"
    assert parse_prerequisite_expression(logical_dump) == logical
    assert parse_prerequisite_expression(expanded_dump) == expanded

    # The same holds for composed OR roles beside the AND roles.
    logical_or = OrRequirement(
        type="or",
        origin=PrerequisiteOrigin.COMPOSED,
        composed_role=ComposedOrRole.LOGICAL,
        children=(
            official_course("a"),
            inferred_course("b", inference=inferred_metadata()),
        ),
    )
    alternatives = OrRequirement(
        type="or",
        origin=PrerequisiteOrigin.COMPOSED,
        composed_role=ComposedOrRole.COURSE_ALTERNATIVES,
        children=(
            official_course("a"),
            official_course("sub", OfficialPrerequisiteKind.SUBSTITUTION),
            inferred_course("equivalent", inference=inferred_metadata()),
        ),
    )
    logical_or_dump = dump_prerequisite_expression(logical_or)
    alternatives_dump = dump_prerequisite_expression(alternatives)
    assert logical_or_dump["composed_role"] == "logical"
    assert alternatives_dump["composed_role"] == "course_alternatives"
    assert parse_prerequisite_expression(logical_or_dump) == logical_or
    assert parse_prerequisite_expression(alternatives_dump) == alternatives

    # Official and inferred payloads omit the null role, so stored expression JSON and its
    # payload hashes are byte-for-byte identical. Official payloads carry the null category while
    # inferred nodes declare their explicit category.
    official_and = AndRequirement(
        type="and",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.COMPULSORY,
        children=(official_course("a"), official_course("b")),
    )
    inferred_and = AndRequirement(
        type="and",
        origin=PrerequisiteOrigin.INFERRED,
        inferred_category=InferredPrerequisiteCategory.REQUIRED,
        inference=inferred_metadata(),
        children=(
            inferred_course("a", inference=inferred_metadata()),
            inferred_course("b", inference=inferred_metadata()),
        ),
    )
    official_or = OrRequirement(
        type="or",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.COMPULSORY,
        children=(official_course("a"), official_course("b")),
    )
    inferred_or = OrRequirement(
        type="or",
        origin=PrerequisiteOrigin.INFERRED,
        inferred_category=InferredPrerequisiteCategory.REQUIRED,
        inference=inferred_metadata(),
        children=(
            inferred_course("a", inference=inferred_metadata()),
            inferred_course("b", inference=inferred_metadata()),
        ),
    )
    for node in (official_and, inferred_and, official_or, inferred_or):
        assert "composed_role" not in dump_prerequisite_expression(node)
        assert parse_prerequisite_expression(dump_prerequisite_expression(node)) == node
    assert dump_prerequisite_expression(official_and)["inferred_category"] is None
    assert dump_prerequisite_expression(inferred_and)["inferred_category"] == "required"
    assert dump_prerequisite_expression(official_or)["inferred_category"] is None
    assert dump_prerequisite_expression(inferred_or)["inferred_category"] == "required"
