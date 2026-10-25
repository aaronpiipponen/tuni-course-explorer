/** Route projection guarantees from native display identities and route-only results. */
import { describe, expect, it } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type {
  GraphDisplayNode,
  PrerequisiteGraphReport,
  PrerequisitePath,
} from "../../../api/types";
import { buildGraphModel } from "../graph/model";
import { buildRouteSummary, buildRouteView } from "./route";
import { uiText } from "../../../shared/wording";
import { ReadCacheContext } from "../../../app/readCacheContext";
import { READ_CACHE_CAPACITY, ReadCache } from "../../../app/readCache";
import { StoreContext } from "../../../state/context";
import { createBrowserStore } from "../../../state/store";
import { WebFeaturesContext } from "../../../app/webFeaturesContext";
import { NoticeProvider } from "../../../shared/NoticeProvider";
import { RoutePanel } from "./RoutePanel";
import type { MinimumRouteSession } from "./useMinimumRoute";

const course = (group_id: string, credits_min: string) => ({
  group_id,
  name_fi: null,
  name_en: group_id,
  code: group_id,
  credits_min,
  credits_max: null,
  is_active: true,
  official_url: "https://example.invalid",
});
const orNode = "s:root:d:aaaaaaaaaaaaaaaaaaaaaaaa";
const displayNode = (node: Partial<GraphDisplayNode>): GraphDisplayNode => ({
  node_id: "",
  kind: "or",
  owner_group_id: "root",
  course_group_id: null,
  module_group_id: null,
  require_min: null,
  require_max: null,
  credits_min: null,
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
  markable: false,
  ...node,
});
const courseNode = (group_id: string, is_root = false): GraphDisplayNode =>
  displayNode({
    node_id: `course:${group_id}`,
    kind: "course",
    course_group_id: group_id,
    is_root,
    owner_group_id: null,
  });
const graphReport = (
  members: readonly string[] = ["m:first"],
  displayAllowed = true,
): PrerequisiteGraphReport =>
  ({
    drawing: {
      allowed: displayAllowed,
      limit: 200,
      course_count: 4,
      node_count: 5,
      edge_count: 4,
      element_count: 9,
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
      courses: [
        course("root", "5"),
        course("new", "3"),
        course("covered", "4"),
        course("unused", "8"),
      ],
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
    display: displayAllowed
      ? {
          nodes: [
            courseNode("root", true),
            courseNode("new"),
            courseNode("covered"),
            courseNode("unused"),
            displayNode({ node_id: orNode }),
          ],
          edges: [
            {
              edge_id: "e:root-or",
              source_node_id: "course:root",
              target_node_id: orNode,
              member_ids: ["m:root"],
              inferred_only: false,
            },
            {
              edge_id: "e:or-new",
              source_node_id: orNode,
              target_node_id: "course:new",
              member_ids: members,
              inferred_only: false,
            },
            {
              edge_id: "e:or-covered",
              source_node_id: orNode,
              target_node_id: "course:covered",
              member_ids: ["m:covered"],
              inferred_only: false,
            },
            {
              edge_id: "e:or-unused",
              source_node_id: orNode,
              target_node_id: "course:unused",
              member_ids: ["m:unused"],
              inferred_only: false,
            },
          ],
        }
      : null,
  }) as unknown as PrerequisiteGraphReport;
const path = (
  state: string,
  overrides: Record<string, unknown> = {},
): PrerequisitePath =>
  ({
    state,
    new_courses: [],
    total_new_credits: null,
    new_opaque_work: [],
    selected_nodes: [],
    lit_members: [],
    covered_courses: [],
    facts: [],
    shortfalls: [],
    blocked_excluded_group_ids: [],
    blocked_excluded_node_keys: [],
    problems: [],
    ...overrides,
  }) as unknown as PrerequisitePath;

describe("minimum-route projection", () => {
  it("lights returned members and sums new plus covered credits without a drawing", () => {
    for (const language of ["en", "fi"] as const) {
      const graph = graphReport();
      const route = path("exact", {
        new_courses: [{ course: course("new", "3"), node_ids: ["course:new"] }],
        total_new_credits: "3",
        selected_nodes: ["course:root", orNode, "course:new", "course:covered"],
        lit_members: ["m:root", "m:first", "m:covered"],
        covered_courses: [course("covered", "4")],
      });
      const model = buildGraphModel(graph, language, []);
      const summary = buildRouteSummary(graph, route, language);
      const view = buildRouteView(route, model, summary);
      expect([...view.lit.edges]).toEqual([
        "e:root-or",
        "e:or-new",
        "e:or-covered",
      ]);
      expect(view.lit.nodes).toEqual(
        new Set(["course:root", orNode, "course:new", "course:covered"]),
      );
      expect(view.lit.edges.has("e:or-unused")).toBe(false);
      expect(view.lit.levels.get("course:new")).toBe(2);
      expect(view.newCredits).toBe(
        uiText(language, "{value} cr", { value: 3 }),
      );
      expect(view.fullCredits).toBe(
        uiText(language, "{value} cr", { value: 7 }),
      );
      expect(
        view.rows.map(
          (row) => row.kind === "course" && [row.course.group_id, row.covered],
        ),
      ).toEqual([
        ["new", false],
        ["covered", true],
      ]);
      // A refused drawing still produces the identical totals, rows and titles.
      const refused = graphReport(["m:first"], false);
      const refusedSummary = buildRouteSummary(refused, route, language);
      expect(refusedSummary.newCredits).toBe(summary.newCredits);
      expect(refusedSummary.fullCredits).toBe(summary.fullCredits);
      expect(refusedSummary.rows).toEqual(summary.rows);
      expect(refused.display).toBeNull();
    }
  });

  it("lights one connection when any returned member is lit", () => {
    const graph = graphReport(["m:first", "m:second"]);
    const model = buildGraphModel(graph, "en", []);
    const build = (members: string[]) => {
      const route = path("exact", {
        new_courses: [{ course: course("new", "3"), node_ids: ["course:new"] }],
        total_new_credits: "3",
        selected_nodes: ["course:root", orNode, "course:new"],
        lit_members: members,
      });
      return buildRouteView(
        route,
        model,
        buildRouteSummary(graph, route, "en"),
      );
    };
    expect(model.edges.filter((edge) => edge.id === "e:or-new")).toHaveLength(
      1,
    );
    expect(build(["m:first"]).lit.edges.has("e:or-new")).toBe(true);
    expect(build(["m:second"]).lit.edges.has("e:or-new")).toBe(true);
    expect(build([]).lit.edges.has("e:or-new")).toBe(false);
  });

  it("presents each of the six path states with its own rows, problems and missing course ids", () => {
    const courseEntry = {
      course: course("new", "3"),
      node_ids: ["course:new"],
    };
    const exactInput = path("exact", {
      new_courses: [courseEntry],
      total_new_credits: "3",
      selected_nodes: ["course:new"],
      lit_members: ["m:first"],
    });
    const build = (graph: PrerequisiteGraphReport, route: PrerequisitePath) =>
      buildRouteView(
        route,
        buildGraphModel(graph, "en", []),
        buildRouteSummary(graph, route, "en"),
      );
    const graph = graphReport();
    const exact = build(graph, exactInput);
    expect(exact.rows).toHaveLength(1);
    expect(exact.missingCourseIds).toEqual(["new"]);
    const approximateInput = path("approximate", {
      new_courses: [courseEntry],
      total_new_credits: "3",
      selected_nodes: ["course:new"],
      lit_members: ["m:first"],
    });
    const approximateView = build(graph, approximateInput);
    expect(approximateView.state).toBe("approximate");
    expect(approximateView.rows).toHaveLength(1);
    const failed = path("approximation_failed", {
      problems: [
        {
          node_id: orNode,
          support_id: null,
          fact_id: null,
          state: "unresolved",
          reason: "search_too_large",
          detail: null,
          referenced_group_id: null,
        },
      ],
    });
    const failedView = build(graph, failed);
    expect(failedView.problems[0]).toMatchObject({ nodeId: orNode });
    expect(failedView.rows).toEqual([]);
    expect(failedView.newCredits).toBeNull();
    expect(failedView.lit.nodes).toEqual(new Set(["course:root"]));
    const blocked = {
      node_id: "course:unused",
      support_id: null,
      fact_id: null,
      state: "no_solution",
      reason: "excluded_node",
      detail: null,
      referenced_group_id: "unused",
    };
    const noSolution = path("no_solution", {
      blocked_excluded_group_ids: ["unused"],
      blocked_excluded_node_keys: [orNode],
      problems: [blocked, blocked],
    });
    const noSolutionView = build(graph, noSolution);
    expect(noSolutionView.blockedCourseIds).toEqual(["unused"]);
    expect(noSolutionView.blockedNodeTitles).toEqual(["OR"]);
    expect(noSolutionView.problems).toHaveLength(1);
    expect(noSolutionView.newCredits).toBeNull();
    expect(noSolutionView.lit.nodes).toEqual(
      new Set(["course:root", "course:unused", orNode]),
    );
    const renderPanel = (view: ReturnType<typeof buildRouteSummary>) => {
      const session: MinimumRouteSession = {
        result: noSolution,
        calculating: false,
        error: null,
        expanded: false,
        find() {},
        clear() {},
        setExpanded() {},
      };
      const html = renderToStaticMarkup(
        createElement(
          StoreContext.Provider,
          { value: createBrowserStore(localStorage) },
          createElement(
            WebFeaturesContext.Provider,
            {
              value: {
                embeddings_enabled: true,
                inference_enabled: true,
                dataset_identity: "synthetic-dataset",
              },
            },
            createElement(
              ReadCacheContext.Provider,
              {
                value: new ReadCache("synthetic-dataset", READ_CACHE_CAPACITY),
              },
              createElement(
                NoticeProvider,
                null,
                createElement(RoutePanel, { view, route: session }),
              ),
            ),
          ),
        ),
      );
      const element = document.createElement("div");
      element.innerHTML = html;
      return element;
    };
    const problemList =
      renderPanel(noSolutionView).querySelector(".route-problems")!;
    expect(problemList.textContent).toContain("unused");
    expect(problemList.querySelectorAll("li")).toHaveLength(1);
    const unresolved = path("unresolved", {
      problems: [
        {
          ...blocked,
          node_id: orNode,
          state: "unresolved",
        },
        {
          ...blocked,
          node_id: orNode,
          state: "unresolved",
        },
        {
          ...blocked,
          node_id: orNode,
          state: "unresolved",
          detail: "second location",
        },
      ],
    });
    const unresolvedView = build(graph, unresolved);
    expect(unresolvedView.problems.map((problem) => problem.identity)).toEqual([
      `${orNode}|excluded_node|`,
      `${orNode}|excluded_node|second location`,
    ]);
    expect(unresolvedView.problems.map((problem) => problem.title)).toEqual([
      "OR",
      "OR",
    ]);
    expect(unresolvedView.lit.nodes.has(orNode)).toBe(true);
    const shortfall = path("shortfall", {
      new_courses: [courseEntry],
      total_new_credits: "3",
      selected_nodes: ["course:new"],
      lit_members: ["m:first"],
      shortfalls: [
        {
          kind: "cardinality",
          node_id: orNode,
          support_id: null,
          required_count: 2,
          achieved_count: 1,
          required_credits: null,
          achieved_credits: null,
        },
      ],
    });
    const shortfallView = build(graph, shortfall);
    expect(shortfallView.rows).toHaveLength(1);
    expect(shortfallView.missingCourseIds).toEqual(["new"]);
    expect(shortfallView.shortfalls).toEqual([
      { title: "OR", text: "1 of 2 courses" },
    ]);
    expect(
      renderPanel(shortfallView).querySelector(".route-problems")?.textContent,
    ).toContain("1 of 2 courses");
    const zero = path("exact", { total_new_credits: "0" });
    expect(build(graph, zero).rows).toEqual([]);
  });
});
