"""Contracts for fuzzy, exact multi-code, and substring official course lookup."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date

import pytest

from course_explorer.config import DatabaseSettings
from course_explorer.curriculum import (
    CatalogueCurriculumPeriod,
    CatalogueModuleLookup,
    CatalogueModuleVersionIdentity,
    RepresentedCourseSummary,
    course_summary,
)
from course_explorer.enums import ModuleType
from course_explorer.search import lookup_commands as catalogue_module
from course_explorer.search.projection import build_lookup_rows
from tests.search._lookup_support import course, service, version
from tests.support import FakeCurriculum, settings_factory


def test_fuzzy_name_search_uses_config_or_override_and_orders_active_by_score() -> None:
    """Config/override cutoffs apply, and ordering is active-first then descending score/name."""
    active_exact = course(
        "group-active-exact", version("source-active-exact", name_en="Linear Algebra")
    )
    active_partial = course(
        "group-active-partial", version("source-active-partial", name_en="Linear Algebra II")
    )
    inactive_exact = course(
        "group-inactive-exact",
        version("source-inactive-exact", name_en="Linear Algebra"),
        is_active=False,
    )
    unrelated = course("group-unrelated", version("source-unrelated", name_en="Quantum Mechanics"))
    lookup, curriculum = service(
        (active_exact, active_partial, inactive_exact, unrelated),
        active_courses=(active_exact, active_partial, unrelated),
    )

    results = lookup.fuzzy_name_search("linear algebra", display_language="en")

    assert [result.course.group_id for result in results] == [
        "group-active-exact",
        "group-active-partial",
        "group-inactive-exact",
    ]
    assert [result.score for result in results] == pytest.approx([100.0, 95.0, 100.0])
    assert curriculum.calls == [None]

    overridden = lookup.fuzzy_name_search("linear algebra", display_language="en", min_score=96)
    assert [result.course.group_id for result in overridden] == [
        "group-active-exact",
        "group-inactive-exact",
    ]

    # A different configured cutoff alone changes which names qualify.
    strict, _ = service(
        (active_exact, active_partial, inactive_exact, unrelated),
        fuzzy_min_score=96,
        active_courses=(active_exact, active_partial, unrelated),
    )
    configured = strict.fuzzy_name_search("linear algebra", display_language="en")
    assert [result.course.group_id for result in configured] == [
        "group-active-exact",
        "group-inactive-exact",
    ]

    active_only = lookup.fuzzy_name_search(
        "linear algebra", display_language="en", include_inactive=False
    )
    assert [result.course.group_id for result in active_only] == [
        "group-active-exact",
        "group-active-partial",
    ]
    assert curriculum.calls[-1] is True

    typo_lookup, _ = service(
        (
            course("full-title", version("source-full", name_en="Machine Learning")),
            course(
                "long-title",
                version("source-long", name_en="Time Series Analysis using Machine Learning"),
            ),
            course(
                "inactive-title",
                version("source-inactive", name_en="Machine Learning"),
                is_active=False,
            ),
        )
    )
    typo = typo_lookup.fuzzy_name_search("machien learnign", display_language="en")
    assert {result.course.group_id for result in typo} == {
        "full-title",
        "long-title",
        "inactive-title",
    }
    assert typo[-1].course.group_id == "inactive-title"
    assert next(result.score for result in typo if result.course.group_id == "long-title") > 80
    exact = typo_lookup.fuzzy_name_search("machine learning", display_language="en")
    assert [result.course.group_id for result in exact] == [
        "full-title",
        "long-title",
        "inactive-title",
    ]
    assert exact[0].score == 100
    assert exact[1].score == 95


def test_fuzzy_name_search_uses_only_resolved_displayed_official_name() -> None:
    """Requested official name wins, the other is fallback only, and hidden names never match."""
    bilingual = course(
        "group-bilingual",
        version(
            "source-bilingual",
            name_fi="Salaperäinen viestintä",
            name_en="Cryptography",
        ),
    )
    fallback = course("group-fallback", version("source-fallback", name_en="Fallback English"))
    unnamed = course("group-unnamed", version("source-unnamed", code="NO.NAME"))

    lookup, _ = service((bilingual, fallback, unnamed))

    finnish = lookup.fuzzy_name_search("salaperäinen viestintä", display_language="fi")
    assert [result.course.group_id for result in finnish] == ["group-bilingual"]

    english = lookup.fuzzy_name_search("cryptography", display_language="en")
    assert [result.course.group_id for result in english] == ["group-bilingual"]

    # The English name is hidden while Finnish is requested, so it must not fuzzy-match.
    hidden = lookup.fuzzy_name_search("cryptography", display_language="fi")
    assert hidden == ()

    # The fallback course resolves through its other official name and matches.
    resolved_fallback = lookup.fuzzy_name_search("fallback english", display_language="fi")
    assert [result.course.group_id for result in resolved_fallback] == ["group-fallback"]

    # The unnamed course is skipped rather than matching an empty string.
    assert all(result.course.group_id != "group-unnamed" for result in english)


def test_exact_code_search_parses_comma_whitespace_or_casefolds_and_deduplicates() -> None:
    """Comma/whitespace splitting, casefolding, OR matching, and dedupe all hold."""
    beta = course("group-beta", version("source-beta", name_fi="Beeta", code="COMP.CS.200"))
    alpha = course("group-alpha", version("source-alpha", name_fi="Alfa", code="COMP.CS.100"))
    inactive = course(
        "group-inactive",
        version("source-inactive", name_fi="Vanha", code="COMP.CS.050"),
        is_active=False,
    )
    math = course("group-math", version("source-math", name_fi="Matikka", code="MATH.1"))
    unrepresented = course("group-none", None)

    lookup, curriculum = service((beta, alpha, inactive, math, unrepresented))

    results = lookup.exact_code_search(
        "comp.cs.100, COMP.CS.200 comp.cs.100 comp.cs.999", display_language="fi"
    )
    assert [result.group_id for result in results] == ["group-alpha", "group-beta"]
    assert curriculum.calls == [None]


def test_substring_search_matches_displayed_name_or_code_without_cap() -> None:
    """Substring name/code containment, hidden-name exclusion, named-first order, and no cap."""
    many = tuple(
        course(
            f"group-{index:02d}",
            version(f"source-{index:02d}", name_fi=f"Kurssi {index:02d}", code=f"SUBJ.{index:02d}"),
        )
        for index in range(12)
    )
    named_code_match = course(
        "group-name", version("source-name", name_fi="Lineaarialgebra", code="NAME.1")
    )
    hidden = course(
        "group-hidden",
        version("source-hidden", name_fi="Lineaarialgebra", name_en="Linear algebra", code="H.1"),
    )
    unnamed_code_match = course("group-unnamed", version("source-unnamed", code="SUBJ.CODE"))
    unrepresented = course("group-none", None)

    lookup, _ = service(many + (named_code_match, hidden, unnamed_code_match, unrepresented))

    # Every match is returned, ordered alphabetically by displayed name.
    capped = lookup.substring_search("SUBJ", display_language="fi")
    assert len(capped) == 13
    assert [result.group_id for result in capped[:12]] == [
        f"group-{index:02d}" for index in range(12)
    ]
    assert capped[-1].group_id == "group-unnamed"

    # Displayed name containment.
    by_name = lookup.substring_search("lineaari", display_language="fi")
    assert [result.group_id for result in by_name] == ["group-hidden", "group-name"]

    # Code containment is case-insensitive.
    by_code = lookup.substring_search("name.1", display_language="fi")
    assert [result.group_id for result in by_code] == ["group-name"]

    # The English name is hidden while Finnish is requested.
    assert lookup.substring_search("linear", display_language="fi") == ()
    assert [
        result.group_id for result in lookup.substring_search("linear", display_language="en")
    ] == (["group-hidden"])


def test_supplied_represented_summaries_skip_the_curriculum_read() -> None:
    """A caller-supplied represented sequence is used directly and performs no curriculum read."""
    alpha = course("group-alpha", version("source-alpha", name_fi="Alfa", code="A.1"))
    beta = course("group-beta", version("source-beta", name_fi="Beeta", code="B.1"))
    lookup, curriculum = service((alpha, beta))

    supplied = tuple(
        RepresentedCourseSummary(
            summary=course_summary(item),
            sisu_course_unit_id=item.representative.sisu_course_unit_id,
            source_hash=item.representative.source_hash,
        )
        for item in (beta,)
    )

    assert [
        result.course.group_id
        for result in lookup.fuzzy_name_search(
            "beeta",
            display_language="fi",
            rows=build_lookup_rows(tuple(record.summary for record in supplied)),
        )
    ] == ["group-beta"]
    assert curriculum.calls == []


def test_course_resolver_matches_canonical_id_before_exact_code_and_fails_loudly() -> None:
    """Scoped resolution keeps caller order, repeats summaries, and fails on bad input."""
    beta = course("group-beta", version("source-beta", name_fi="Beeta", code="COMP.CS.200"))
    alpha = course("group-alpha", version("source-alpha", name_fi="Alfa", code="COMP.CS.100"))
    inactive = course(
        "group-inactive",
        version("source-inactive", name_fi="Vanha", code="COMP.CS.050"),
        is_active=False,
    )
    unicode_course = course(
        "group-unicode", version("source-unicode", name_fi="Ä", code="CO\u0308MP.1")
    )
    unrepresented = course("group-none", None)
    lookup, curriculum = service(
        (beta, alpha, inactive, unicode_course, unrepresented),
        active_courses=(beta, alpha, unicode_course),
    )

    # `resolve_courses` matches an outer-trimmed canonical group id first through the scoped getter
    # and skips the code projection entirely when every input is canonical.
    code_reads_before = len(curriculum.code_identity_calls)
    scoped_before = len(curriculum.scoped_summary_calls)
    assert lookup.resolve_courses(()) == ()
    assert len(curriculum.scoped_summary_calls) == scoped_before
    assert len(curriculum.code_identity_calls) == code_reads_before

    all_canonical = lookup.resolve_courses(("group-beta", "group-alpha"))
    assert [record.summary.group_id for record in all_canonical] == ["group-beta", "group-alpha"]
    assert len(curriculum.code_identity_calls) == code_reads_before
    assert curriculum.scoped_summary_calls[-1] == (("group-alpha", "group-beta"), None)

    # A mixed id/code input resolves in caller order, repeats the shared record, and reads
    # only candidates, never an unrelated or unrepresented catalogue card.
    scoped_before_mixed = len(curriculum.scoped_summary_calls)
    records = lookup.resolve_courses(("group-beta", "comp.cs.100", "group-alpha", "group-beta"))
    assert [record.summary.group_id for record in records] == [
        "group-beta",
        "group-alpha",
        "group-alpha",
        "group-beta",
    ]
    assert records[0] is records[3]
    assert records[1] is records[2]
    assert records[1].summary.code == "COMP.CS.100"
    assert records[0].sisu_course_unit_id == "source-beta"
    assert curriculum.calls == []
    mixed_requested = {
        group_id
        for batch, _ in curriculum.scoped_summary_calls[scoped_before_mixed:]
        for group_id in batch
    }
    assert "group-none" not in mixed_requested
    assert "group-inactive" not in mixed_requested

    inactive_record = lookup.resolve_courses(("group-inactive",))
    assert [record.summary.group_id for record in inactive_record] == ["group-inactive"]
    assert inactive_record[0].summary.is_active is False

    # An unrepresented canonical ID falls through to code matching and fails as unknown.
    with pytest.raises(ValueError):
        lookup.resolve_courses(("group-none",))
    with pytest.raises(ValueError):
        lookup.resolve_courses(("COMP.CS.999",))
    duplicate_lookup, _ = service(
        (
            course("group-duplicate-a", version("source-dup-a", code="DUP.1")),
            course("group-duplicate-b", version("source-dup-b", code="DUP.1")),
        )
    )
    with pytest.raises(ValueError):
        duplicate_lookup.resolve_courses(("dup.1",))


def _module_version(
    sisu_module_id: str,
    *,
    module_type: ModuleType = ModuleType.STUDY_MODULE,
    code: str | None = None,
    name_fi: str | None = None,
    name_en: str | None = None,
    curriculum_periods: tuple[CatalogueCurriculumPeriod, ...] = (),
    validity_start: date | None = None,
    validity_end: date | None = None,
) -> CatalogueModuleVersionIdentity:
    """Build one projected module-version identity fixture."""
    return CatalogueModuleVersionIdentity(
        sisu_module_id=sisu_module_id,
        module_type=module_type,
        code=code,
        name_fi=name_fi,
        name_en=name_en,
        validity_start=validity_start,
        validity_end=validity_end,
        curriculum_periods=curriculum_periods,
    )


def _module(group_id: str, *versions: CatalogueModuleVersionIdentity) -> CatalogueModuleLookup:
    """Build one canonical module lookup fixture from its projected versions."""
    return CatalogueModuleLookup(group_id=group_id, versions=versions)


def test_catalogue_command_selects_strict_module_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The catalogue keeps every strict-year module candidate and omits the ineligible groups."""
    period_2026 = (CatalogueCurriculumPeriod(id="period-2026", academic_year_start=2026),)
    period_2027 = (CatalogueCurriculumPeriod(id="period-2027", academic_year_start=2027),)

    degree = _module(
        "module-degree",
        _module_version(
            "degree-v1",
            module_type=ModuleType.DEGREE_PROGRAMME,
            code="MOD.A",
            name_fi="Ohjelma",
            name_en="Degree",
            curriculum_periods=period_2026,
        ),
    )
    validity = _module(
        "module-validity",
        _module_version(
            "validity-v1",
            code="VAL.1",
            name_fi="Voimassa oleva",
            validity_start=date(2020, 1, 1),
        ),
    )
    absent = _module(
        "module-absent",
        _module_version(
            "absent-v1",
            code="ABS.1",
            name_en="Absent",
            curriculum_periods=period_2027,
        ),
    )
    ambiguous = _module(
        "module-ambiguous",
        _module_version(
            "ambiguous-v1",
            code="AMB.1",
            name_fi="Yhteinen kuvaus",
            curriculum_periods=period_2026,
        ),
        _module_version(
            "ambiguous-v2",
            code="AMB.2",
            name_fi="Yhteinen kuvaus",
            curriculum_periods=period_2026,
        ),
    )
    curriculum = FakeCurriculum(
        (),
        summaries_by_activity={None: ()},
        module_lookup=(degree, validity, absent, ambiguous),
    )

    @contextmanager
    def _context(_settings: DatabaseSettings):
        yield object()

    monkeypatch.setattr(catalogue_module, "CurriculumRepository", lambda _factory: curriculum)
    monkeypatch.setattr(catalogue_module, "_database_context", _context)
    monkeypatch.setattr(
        catalogue_module, "load_database_settings", lambda: settings_factory(DatabaseSettings)
    )

    report = catalogue_module.run_catalogue_command()

    assert [module.group_id for module in report.modules] == [
        "module-ambiguous",
        "module-degree",
        "module-validity",
    ]
    # The report lists every eligible candidate of one canonical group with its exact identity and
    # name, so both versions appear.
    assert [
        (candidate.sisu_module_id, candidate.code, candidate.name_fi)
        for candidate in report.modules[0].candidates
    ] == [
        ("ambiguous-v1", "AMB.1", "Yhteinen kuvaus"),
        ("ambiguous-v2", "AMB.2", "Yhteinen kuvaus"),
    ]
    assert report.modules[0].candidates[0].curriculum_periods == period_2026
    assert report.modules[0].candidates[0].validity_start is None
    assert report.modules[1].candidates[0].module_type is ModuleType.DEGREE_PROGRAMME
    assert report.modules[1].candidates[0].sisu_module_id == "degree-v1"
    # A version tied only to another academic year is absent, while a membership-free version
    # inside its own validity bounds is eligible.
    assert [candidate.code for candidate in report.modules[2].candidates] == ["VAL.1"]
    assert report.modules[2].candidates[0].validity_start == date(2020, 1, 1)
    assert report.modules[2].candidates[0].curriculum_periods == ()
