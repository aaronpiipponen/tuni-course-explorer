/** Local narrowing proofs over the minimal official catalogue payload. */
import { describe, expect, it } from "vitest";
import type { CatalogueCourse, CatalogueReport } from "../../api/types";
import { narrowCourses, narrowModules } from "./narrowing";

function course(
  groupId: string,
  code: string,
  names: { fi?: string | null; en?: string | null } = {},
  is_active = true,
): CatalogueCourse {
  return {
    group_id: groupId,
    code,
    name_fi: names.fi ?? null,
    name_en: names.en ?? null,
    credits_min: "5",
    credits_max: null,
    is_active,
  };
}

function version(
  moduleType: string,
  code: string | null,
  names: { fi?: string | null; en?: string | null } = {},
  sisuModuleId = code ?? `${moduleType}-version`,
  periods: readonly { id: string; academic_year_start: number }[] = [],
) {
  return {
    sisu_module_id: sisuModuleId,
    module_type: moduleType,
    code,
    name_fi: names.fi ?? null,
    name_en: names.en ?? null,
    validity_start: null,
    validity_end: null,
    curriculum_periods: periods,
  };
}

describe("local official narrowing", () => {
  it("matches and orders the displayed official courses locally", () => {
    const many = Array.from({ length: 12 }, (_, index) =>
      course(
        `group-${String(index).padStart(2, "0")}`,
        `SUBJ.${String(index).padStart(2, "0")}`,
        { fi: `Kurssi ${String(index).padStart(2, "0")}` },
      ),
    );
    const hidden = course("group-hidden", "H.1", {
      fi: "Lineaarialgebra",
      en: "Linear algebra",
    });
    const fallback = course("group-fallback", "F.1", {
      en: "Fallback English",
    });
    const unicode = course("group-unicode", "U.1", { en: "Straße" });
    const fullwidth = course("group-fullwidth", "FW.1", {
      en: "ＣＯＭＰ course",
    });
    const inactive = course(
      "group-inactive",
      "SUBJ.99",
      { fi: "Aalto" },
      false,
    );
    const courses = [...many, hidden, fallback, unicode, fullwidth, inactive];

    // Name containment is casefolded, and the code contains the query as well.
    expect(
      narrowCourses(courses, "lineaari", "fi", false).map(
        (item) => item.group_id,
      ),
    ).toEqual(["group-hidden"]);
    // The English name is hidden while Finnish is requested.
    expect(narrowCourses(courses, "linear", "fi", false)).toEqual([]);
    expect(
      narrowCourses(courses, "linear", "en", false).map(
        (item) => item.group_id,
      ),
    ).toEqual(["group-hidden"]);
    // The other official name answers only when the requested one is absent.
    expect(
      narrowCourses(courses, "fallback english", "fi", false).map(
        (item) => item.group_id,
      ),
    ).toEqual(["group-fallback"]);
    // Casefolding expands the German sharp s, and NFKC folds the full-width letters.
    expect(
      narrowCourses(courses, "STRASSE", "en", false).map(
        (item) => item.group_id,
      ),
    ).toEqual(["group-unicode"]);
    expect(
      narrowCourses(courses, "comp course", "en", false).map(
        (item) => item.group_id,
      ),
    ).toEqual(["group-fullwidth"]);

    // Every match is returned, ordered by activity, named before unnamed, name, code and ID.
    const bounded = narrowCourses(courses, "SUBJ", "fi", false);
    expect(bounded).toHaveLength(13);
    expect(bounded.map((item) => item.group_id)).toEqual([
      ...many.map((item) => item.group_id),
      "group-inactive",
    ]);
    expect(
      narrowCourses(courses, "SUBJ", "fi", true).map((item) => item.group_id),
    ).toEqual(many.map((item) => item.group_id));

    const ordered = [
      course("group-un", "SUBJ.13"),
      course("group-b", "SUBJ.02", { fi: "Beeta" }),
      course("group-a", "SUBJ.10", { fi: "Alfa" }),
      course("group-inactive", "SUBJ.00", { fi: "Aalto" }, false),
      course("group-b-2", "SUBJ.02", { fi: "Beeta" }),
    ];
    expect(
      narrowCourses(ordered, "subj", "fi", false).map((item) => item.group_id),
    ).toEqual([
      "group-a",
      "group-b",
      "group-b-2",
      "group-un",
      "group-inactive",
    ]);

    // An empty normalized query returns no rows.
    expect(narrowCourses(courses, "   ", "fi", false)).toEqual([]);
  });

  it("narrows eligible module groups in programme order without guessing a version", () => {
    const modules: CatalogueReport["modules"] = [
      {
        group_id: "module-study",
        candidates: [version("StudyModule", "MOD.B", { fi: "Beeta moduuli" })],
      },
      {
        group_id: "module-degree",
        candidates: [
          version("DegreeProgramme", "MOD.A", {
            fi: "Zulu moduuli",
            en: "Alpha module",
          }),
        ],
      },
      {
        group_id: "module-grouping",
        candidates: [version("GroupingModule", null, { fi: "Gamma moduuli" })],
      },
      {
        group_id: "module-fallback",
        candidates: [
          version("StudyModule", "FALL.1", { en: "Fallback English" }),
        ],
      },
      {
        group_id: "module-ambiguous",
        candidates: [
          version(
            "StudyModule",
            "AMB.1",
            { fi: "Yhteinen kuvaus" },
            "ambiguous-v1",
          ),
          version(
            "StudyModule",
            "AMB.2",
            { fi: "Yhteinen kuvaus" },
            "ambiguous-v2",
          ),
        ],
      },
      {
        group_id: "module-tied",
        candidates: [
          version("StudyModule", "TIE.1", { fi: "Sama kuvaus" }, "tie-b"),
          version("StudyModule", "TIE.1", { fi: "Sama kuvaus" }, "tie-a"),
        ],
      },
      {
        group_id: "module-display",
        candidates: [
          version("StudyModule", "DIS.9", { fi: "Zulu näyttö" }, "display-z"),
          version("StudyModule", "DIS.1", { fi: "Aalto näyttö" }, "display-a"),
        ],
      },
    ];

    // Programmes precede other modules, then the displayed name and code decide the order, and
    // every matching group is returned.
    const programmesFirst = narrowModules(modules, "moduuli", "fi");
    expect(programmesFirst.map((item) => item.group_id)).toEqual([
      "module-degree",
      "module-study",
      "module-grouping",
    ]);
    expect(programmesFirst[0].module_type).toBe("DegreeProgramme");
    expect(narrowModules(modules, "alpha module", "fi")).toEqual([]);
    expect(
      narrowModules(modules, "alpha module", "en").map((item) => item.group_id),
    ).toEqual(["module-degree"]);
    // The other official name answers only when the requested one is absent.
    expect(
      narrowModules(modules, "fallback english", "fi").map(
        (item) => item.group_id,
      ),
    ).toEqual(["module-fallback"]);
    // One row stands for the whole group and carries every eligible candidate of it.
    const ambiguous = narrowModules(modules, "amb.1", "fi");
    expect(ambiguous.map((item) => item.group_id)).toEqual([
      "module-ambiguous",
    ]);
    expect(
      ambiguous[0].candidates.map((candidate) => candidate.sisu_module_id),
    ).toEqual(["ambiguous-v1", "ambiguous-v2"]);
    expect(ambiguous[0].code).toBe("AMB.1");
    // A query that matches one sibling keeps the sibling rows of the group as they are.
    const sibling = narrowModules(modules, "amb.2", "fi");
    expect(sibling).toHaveLength(1);
    expect(sibling[0].candidates).toHaveLength(2);
    expect(sibling[0].code).toBe("AMB.2");
    // Equal candidate keys settle on the exact version identity for the displayed fields, while
    // the group keeps the candidates in their original order.
    const tied = narrowModules(modules, "sama", "fi");
    expect(tied).toHaveLength(1);
    expect(tied[0].code).toBe("TIE.1");
    expect(
      tied[0].candidates.map((candidate) => candidate.sisu_module_id),
    ).toEqual(["tie-b", "tie-a"]);
    // Different candidate keys order the display fields by name and then code.
    const display = narrowModules(modules, "näyttö", "fi");
    expect(display).toHaveLength(1);
    expect(display[0].code).toBe("DIS.1");
    expect(display[0].name_fi).toBe("Aalto näyttö");
    expect(display[0].candidates).toHaveLength(2);
    // A group the query does not touch never appears.
    expect(narrowModules(modules, "gamma", "fi")).toHaveLength(1);
    expect(narrowModules(modules, "no such module", "en")).toEqual([]);
    expect(narrowModules(modules, "  ", "en")).toEqual([]);
  });
});
