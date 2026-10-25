/** Proof that cached structure reads keep one report per module selection. */
import { afterEach, describe, expect, it, vi } from "vitest";
import { READ_CACHE_CAPACITY, ReadCache } from "../../app/readCache";
import type { StructureModule, StudyStructuresReport } from "../../api/types";
import { readCachedStudyStructures } from "./structureReads";

vi.mock("./structureStorage", () => ({
  readPersistedStructures: vi.fn(async () => ({})),
  writePersistedStructures: vi.fn(async () => undefined),
}));

function report(
  sisuModuleId: string,
  courseCode: string,
): StudyStructuresReport {
  const root: StructureModule = {
    module: {
      group_id: "module-root",
      sisu_module_id: sisuModuleId,
      module_type: "Module",
      code: "ROOT",
      name_fi: null,
      name_en: "Root module",
    },
    target_credits_min: null,
    target_credits_max: null,
    rule: {
      node_type: "CourseUnitRule",
      sibling_position: 0,
      require_min: null,
      require_max: null,
      all_mandatory: null,
      credits_min: null,
      credits_max: null,
      count_min: null,
      count_max: null,
      referenced_group_id: "course-group",
      children: [],
      course: {
        group_id: "course-group",
        name_fi: null,
        name_en: courseCode,
        code: courseCode,
        credits_min: "5",
        credits_max: null,
        is_active: true,
        official_url: `https://example.invalid/${courseCode}`,
      },
      module: null,
      unresolved: null,
    },
  };
  return {
    academic_year_start: 2026,
    roots: [root],
    unavailable_root_group_ids: [],
    version_selection_required: [],
    dataset_identity: "dataset-one",
  };
}

afterEach(() => vi.unstubAllGlobals());

describe("selection-qualified structure reads", () => {
  it("keeps structure reports separate for different module selections", async () => {
    const fetchSpy = vi.fn(async (_path: string, init?: RequestInit) => {
      const body = JSON.parse(String(init?.body)) as {
        module_versions: Record<string, string>;
      };
      const selection = body.module_versions["module-root"];
      const payload =
        selection === "root-v1"
          ? report("root-v1", "V1")
          : report("root-v2", "V2");
      return new Response(JSON.stringify(payload), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    });
    vi.stubGlobal("fetch", fetchSpy);
    const cache = new ReadCache("dataset-one", READ_CACHE_CAPACITY);
    const first = { "module-root": "root-v1" };
    const second = { "module-root": "root-v2" };

    const firstRead = await readCachedStudyStructures(
      cache,
      ["module-root"],
      first,
      false,
      new AbortController().signal,
    );
    expect(firstRead.reports["module-root"].root.module.sisu_module_id).toBe(
      "root-v1",
    );
    expect(firstRead.reports["module-root"].root.rule.course?.code).toBe("V1");
    expect(fetchSpy).toHaveBeenCalledTimes(1);

    // The same selection reuses its own report without another request.
    const repeatedFirst = await readCachedStudyStructures(
      cache,
      ["module-root"],
      first,
      false,
      new AbortController().signal,
    );
    expect(repeatedFirst.reports["module-root"]).toEqual(
      firstRead.reports["module-root"],
    );
    expect(fetchSpy).toHaveBeenCalledTimes(1);

    // Another selection reads its own report and never gets the first one back.
    const secondRead = await readCachedStudyStructures(
      cache,
      ["module-root"],
      second,
      false,
      new AbortController().signal,
    );
    expect(secondRead.reports["module-root"].root.module.sisu_module_id).toBe(
      "root-v2",
    );
    expect(secondRead.reports["module-root"].root.rule.course?.code).toBe("V2");
    expect(fetchSpy).toHaveBeenCalledTimes(2);

    const repeatedSecond = await readCachedStudyStructures(
      cache,
      ["module-root"],
      second,
      false,
      new AbortController().signal,
    );
    expect(
      repeatedSecond.reports["module-root"].root.module.sisu_module_id,
    ).toBe("root-v2");
    expect(fetchSpy).toHaveBeenCalledTimes(2);
  });
});
