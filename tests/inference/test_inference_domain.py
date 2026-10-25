"""Contract tests for the strict complete-target-result domain model."""

from __future__ import annotations

import json
from decimal import Decimal

from course_explorer.inference.domain import (
    DirectnessOutcome,
    EquivalenceFlag,
    InferenceTargetResultV2,
    OptionFlag,
    RoutingFlag,
    parse_target_result,
)


def option(codes: list[str], confidence: float = 0.9) -> dict[str, object]:
    return {
        "course_codes": codes,
        "evidence": "teaches the assumed entry knowledge",
        "confidence": confidence,
        "finding_flags": [],
    }


def required_set(requirement_id: str, options: list[dict[str, object]]) -> dict[str, object]:
    return {"requirement_id": requirement_id, "options": options}


def test_target_result_preserves_complete_grouped_contract() -> None:
    """Required/recommended OR-of-AND grouping, evidence, and routing survive intact."""
    payload = {
        "required": [
            required_set("required_1", [option(["MATH.101"])]),
            required_set("required_2", [option(["PHYS.101", "PHYS.102"]), option(["CHEM.101"])]),
        ],
        "recommended": [required_set("recommended_1", [option(["STAT.101"])])],
        "equivalence": [
            {
                "members": ["MATH.101", "MATH.102"],
                "evidence": "course-wide interchangeable teaching content",
                "confidence": 0.81,
                "finding_flags": [],
            }
        ],
        "routing": {
            "confidence": 0.78,
            "flags": ["directness_ambiguity"],
            "suppressed": [
                {
                    "course_code": "MATH.010",
                    "outcome": "too_basic_transitive",
                    "evidence": "general foundation below the target entry level",
                }
            ],
        },
    }
    parsed = parse_target_result(json.dumps(payload), "v2")

    assert tuple(parsed.required[0].options[0].course_codes) == ("MATH.101",)
    assert tuple(parsed.required[1].options[0].course_codes) == ("PHYS.101", "PHYS.102")
    assert tuple(parsed.required[1].options[1].course_codes) == ("CHEM.101",)
    assert tuple(parsed.recommended[0].options[0].course_codes) == ("STAT.101",)
    assert parsed.required[0].options[0].confidence == Decimal("0.9")
    assert parsed.equivalence[0].members == ("MATH.101", "MATH.102")
    assert parsed.routing.flags == (RoutingFlag.DIRECTNESS_AMBIGUITY,)
    assert parsed.routing.suppressed[0].outcome is DirectnessOutcome.TOO_BASIC_TRANSITIVE
    assert parsed.routing.suppressed[0].course_code == "MATH.010"


def _v2_payload() -> dict[str, object]:
    return {
        "required": [
            {
                "requirement_id": "required_1",
                "options": [
                    {
                        "course_codes": ["A", "B"],
                        "evidence": "entry knowledge",
                        "confidence": 0.9,
                        "finding_flags": ["requiredness_uncertain", "member_uncertain"],
                    }
                ],
            }
        ],
        "recommended": [],
        "equivalence": [
            {
                "members": ["A", "B"],
                "evidence": "course-wide interchangeable",
                "confidence": 0.5,
                "finding_flags": ["group_scope_uncertain"],
            }
        ],
        "routing": {"confidence": 0.5, "flags": [], "suppressed": []},
    }


def test_v2_places_multiple_finding_flags() -> None:
    """v2 carries distinct per-finding flags on options and equivalence groups."""
    parsed = parse_target_result(json.dumps(_v2_payload()), "v2")

    assert isinstance(parsed, InferenceTargetResultV2)
    assert parsed.required[0].options[0].finding_flags == (
        OptionFlag.REQUIREDNESS_UNCERTAIN,
        OptionFlag.MEMBER_UNCERTAIN,
    )
    assert parsed.equivalence[0].finding_flags == (EquivalenceFlag.GROUP_SCOPE_UNCERTAIN,)
