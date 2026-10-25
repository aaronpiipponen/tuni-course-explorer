/** Persistence for graph-only marks, which leave shared course state alone. */
import { beforeEach, describe, expect, it } from "vitest";
import type { PrerequisiteGraphReport } from "../../api/types";
import { createBrowserStore } from "../../state/store";
import { toggleNodeCompleted, toggleNodeExcluded } from "./actions";
import { buildGraphModel } from "./graph/model";

const course = (group_id: string) => ({
  group_id,
  name_fi: null,
  name_en: group_id,
  code: group_id,
  credits_min: "5",
  credits_max: null,
  is_active: true,
  official_url: "https://example.invalid",
});
const box = (node_id: string, markable = true) => ({
  node_id,
  kind: "opaque_credits" as const,
  owner_group_id: "root",
  course_group_id: null,
  module_group_id: null,
  require_min: null,
  require_max: null,
  credits_min: "5",
  credits_max: null,
  count_min: null,
  count_max: null,
  referenced_group_id: null,
  reason: null,
  detail: null,
  member_group_ids: [],
  diagnostic_ids: [],
  is_root: false,
  via_inferred: false,
  via_recommended: false,
  has_official_provenance: true,
  has_inferred_provenance: false,
  display_as_inferred: false,
  markable,
});
const firstKey = "s:root:d:111111111111111111111111";
const secondKey = "s:root:d:222222222222222222222222";
const orphanKey = "s:root:d:333333333333333333333333";
const report = {
  drawing: {
    allowed: true,
    limit: null,
    course_count: 1,
    node_count: 3,
    edge_count: 0,
    element_count: 3,
  },
  dataset_identity: "synthetic-dataset",
  max_compact_nodes: 10000,
  solver: {
    root_group_id: "root",
    academic_year_start: 2026,
    root_use_id: null,
    pieces: [],
    uses: [],
    facts: [],
    diagnostics: [],
    root_diagnostic_ids: [],
    courses: [course("root")],
    modules: [],
    include_recommended: false,
    include_inferred: false,
    active_only: false,
    inferred_coverage: [],
    excluded_group_ids: [],
    completed_node_keys: [],
    excluded_node_keys: [],
    bindings: [],
    projection_root_context_id: null,
    projection_contexts: [],
    members: [],
  },
  display: {
    nodes: [
      {
        ...box("course:root", false),
        kind: "course" as const,
        course_group_id: "root",
        is_root: true,
      },
      box(firstKey),
      box(secondKey),
    ],
    edges: [],
  },
} as unknown as PrerequisiteGraphReport;

describe("prerequisite graph actions", () => {
  beforeEach(() => localStorage.clear());
  it("graph-only marks toggle one shared display piece and leave course state alone", () => {
    const store = createBrowserStore(localStorage);
    const state = () =>
      createBrowserStore(localStorage).getSnapshot().profiles.default.state;
    const nodes = buildGraphModel(report, "en", []).nodes;
    const first = nodes.find((node) => node.id === firstKey)!;
    const second = nodes.find((node) => node.id === secondKey)!;

    expect(first.markKey).toBe(firstKey);
    expect(second.markKey).toBe(secondKey);
    expect(first.markable).toBe(true);

    toggleNodeCompleted(store, first.markKey!);
    expect(state().prerequisites.completedNodeKeys).toEqual([firstKey]);

    toggleNodeExcluded(store, second.markKey!);
    let current = state();
    expect(current.prerequisites.completedNodeKeys).toEqual([firstKey]);
    expect(current.prerequisites.excludedNodeKeys).toEqual([secondKey]);

    toggleNodeCompleted(store, second.markKey!);
    current = state();
    expect(current.prerequisites.completedNodeKeys).toEqual([
      firstKey,
      secondKey,
    ]);
    expect(current.prerequisites.excludedNodeKeys).toEqual([]);

    toggleNodeCompleted(store, first.markKey!);
    current = state();
    expect(current.prerequisites.completedNodeKeys).toEqual([secondKey]);
    expect(current.selectedCourseIds).toEqual([]);
    expect(current.completedCourseIds).toEqual([]);

    // A saved mark for an undrawn box stays when another box's mark toggles.
    store.updateCurrent((value) => ({
      ...value,
      prerequisites: {
        ...value.prerequisites,
        completedNodeKeys: [
          ...value.prerequisites.completedNodeKeys,
          orphanKey,
        ],
      },
    }));
    toggleNodeExcluded(store, second.markKey!);
    expect(state().prerequisites.completedNodeKeys).toContain(orphanKey);
  });
});
