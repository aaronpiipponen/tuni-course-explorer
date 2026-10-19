/** Route projection guarantees from graph-issued occurrences and route-only results. */
import { describe, expect, it } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type {
  GraphEdge,
  GraphEdgeRelationship,
  PrerequisiteGraphReport,
  PrerequisitePath,
} from "../../../api/types";
import { buildGraphModel } from "../graph/model";
import { buildRouteSummary, buildRouteView } from "./route";
import { uiText } from "../../../shared/wording";
import { StoreContext } from "../../../state/context";
import { createBrowserStore } from "../../../state/store";
import { WebFeaturesContext } from "../../../app/webFeaturesContext";
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
const relationship = (
  occurrence_ids: string[],
  condition_occurrence_ids: string[] = [],
): GraphEdgeRelationship => ({
  origin: "official",
  official_kind: "compulsory",
  inferred_category: null,
  inference: null,
  occurrence_ids,
  condition_occurrence_ids,
});
const edge = (
  source_node_id: string,
  target_node_id: string,
  relationships: GraphEdgeRelationship[],
): GraphEdge => ({
  source_node_id,
  target_node_id,
  relationships,
});
const graphReport = (
  groupedMembers: GraphEdgeRelationship[] = [
    relationship(["chosen"]),
    relationship(["alt-chosen"], ["gate"]),
  ],
): PrerequisiteGraphReport =>
  ({
    drawing: {
      allowed: true,
      limit: 200,
      course_count: 4,
      node_count: 5,
      edge_count: 4,
      element_count: 9,
    },
    selected_group_ids: [],
    completed_group_ids: [],
    basis: "completed",
    excluded_group_ids: [],
    completed_node_keys: [],
    excluded_node_keys: [],
    compilation: {
      tree: {
        root: course("root", "5"),
        courses: [
          course("new", "3"),
          course("covered", "4"),
          course("unused", "8"),
        ],
        ignored_parts: [],
        issues: [],
        excluded_group_ids: [],
      },
      graph: {
        course_nodes: [
          {
            node_id: "course:root",
            action_key: "course:root",
            course: course("root", "5"),
            is_root: true,
            display_as_inferred: false,
          },
          {
            node_id: "course:new",
            action_key: "course:new",
            course: course("new", "3"),
            is_root: false,
            display_as_inferred: false,
          },
          {
            node_id: "course:covered",
            action_key: "course:covered",
            course: course("covered", "4"),
            is_root: false,
            display_as_inferred: false,
          },
          {
            node_id: "course:unused",
            action_key: "course:unused",
            course: course("unused", "8"),
            is_root: false,
            display_as_inferred: false,
          },
        ],
        connector_nodes: [
          {
            node_id: "connector:or",
            action_key: "connector:or",
            kind: "or",
            require_min: null,
            require_max: null,
            credits_min: null,
            credits_max: null,
            count_min: null,
            count_max: null,
            referenced_group_id: null,
            unresolved_reason: null,
            detail: null,
            member_group_ids: [],
          },
        ],
        module_nodes: [],
        ignored_nodes: [],
        node_states: [],
        edges: [
          edge("course:root", "connector:or", [relationship(["root-or"])]),
          edge("connector:or", "course:new", groupedMembers),
          edge("connector:or", "course:covered", [relationship(["covered"])]),
          edge("connector:or", "course:unused", [relationship(["unused"])]),
        ],
      },
    },
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
    selected_occurrence_ids: [],
    shortfalls: [],
    blocked_excluded_group_ids: [],
    blocked_excluded_node_keys: [],
    problems: [],
    ...overrides,
  }) as unknown as PrerequisitePath;

describe("minimum-route projection", () => {
  it("lights only edges with a selected occurrence and sums new plus basis-covered route credits", () => {
    for (const language of ["en", "fi"] as const) {
      const graph = graphReport();
      const route = path("exact", {
        new_courses: [
          { course: course("new", "3"), occurrence_ids: ["chosen"] },
        ],
        total_new_credits: "3",
        selected_occurrence_ids: ["root-or", "chosen", "covered"],
      });
      const model = buildGraphModel(graph, language);
      const summary = buildRouteSummary(graph, route, language);
      const view = buildRouteView(graph, route, model, summary);
      expect([...view.lit.edges]).toEqual([
        "course:root>connector:or-0",
        "connector:or>course:new-1",
        "connector:or>course:covered-2",
      ]);
      expect(view.lit.nodes).toEqual(
        new Set([
          "course:root",
          "connector:or",
          "course:new",
          "course:covered",
        ]),
      );
      expect(view.lit.edges.has("connector:or>course:unused-3")).toBe(false);
      expect(view.lit.levels.get("course:new")).toBe(2);
      expect(view.newCredits).toBe(
        uiText(language, "{value} cr", { value: 3 }),
      );
      expect(view.fullCredits).toBe(
        uiText(language, "{value} cr", { value: 7 }),
      );
      expect(summary.fullCredits).toBe(
        uiText(language, "{value} cr", { value: 7 }),
      );
      expect(summary.rows).toEqual(view.rows);
      expect(
        view.rows.map(
          (row) => row.kind === "course" && [row.course.group_id, row.covered],
        ),
      ).toEqual([
        ["new", false],
        ["covered", true],
      ]);
    }
  });

  it("lights a grouped connection only through a complete member relationship", () => {
    const graph = graphReport([
      relationship(["chosen"], ["gate-a"]),
      relationship(["alt-chosen"], ["gate-b1", "gate-b2"]),
    ]);
    const model = buildGraphModel(graph, "en");
    const connection = "connector:or>course:new-1";
    const build = (selected: string[]) => {
      const route = path("exact", {
        new_courses: [
          { course: course("new", "3"), occurrence_ids: ["chosen"] },
        ],
        total_new_credits: "3",
        selected_occurrence_ids: selected,
      });
      return buildRouteView(
        graph,
        route,
        model,
        buildRouteSummary(graph, route, "en"),
      );
    };

    // One supplied connection produces exactly one model edge, never one per relationship member.
    expect(model.edges).toHaveLength(4);
    expect(model.edges.filter((edge) => edge.id === connection)).toHaveLength(
      1,
    );

    // Each differently gated member lights the same connection through its own complete relationship.
    expect(build(["chosen", "gate-a"]).lit.edges.has(connection)).toBe(true);
    expect(
      build(["alt-chosen", "gate-b1", "gate-b2"]).lit.edges.has(connection),
    ).toBe(true);
    // A terminal whose own gate chain is incomplete is dark, and one member's terminal never
    // borrows the other member's gates.
    expect(build(["alt-chosen", "gate-b1"]).lit.edges.has(connection)).toBe(
      false,
    );
    expect(
      build(["chosen", "gate-b1", "gate-b2"]).lit.edges.has(connection),
    ).toBe(false);
  });

  it("presents each of the six path states with its own rows, problems and missing course ids", () => {
    const courseEntry = {
      course: course("new", "3"),
      occurrence_ids: ["chosen"],
    };
    const exactInput = path("exact", {
      new_courses: [courseEntry],
      total_new_credits: "3",
      selected_occurrence_ids: ["chosen"],
    });
    const build = (graph: PrerequisiteGraphReport, route: PrerequisitePath) =>
      buildRouteView(
        graph,
        route,
        buildGraphModel(graph, "en"),
        buildRouteSummary(graph, route, "en"),
      );
    const graph = graphReport();
    const exact = build(graph, exactInput);
    expect(exact.rows).toHaveLength(1);
    expect(exact.missingCourseIds).toEqual(["new"]);
    const approximateInput = path("approximate", {
      new_courses: [courseEntry],
      total_new_credits: "3",
      selected_occurrence_ids: ["chosen"],
    });
    const approximateView = build(graph, approximateInput);
    expect(approximateView.state).toBe("approximate");
    expect(approximateView.rows).toHaveLength(1);
    expect(approximateView.missingCourseIds).toEqual(["new"]);
    const failed = path("approximation_failed", {
      problems: [
        {
          action_key: "connector:or",
          occurrence_id: "timeout-occurrence",
          state: "unresolved",
          reason: "search_too_large",
          detail: null,
          referenced_group_id: null,
        },
      ],
    });
    const failedView = build(graph, failed);
    expect(failedView.problems[0]).toMatchObject({
      occurrenceId: "timeout-occurrence",
      actionKey: "connector:or",
    });
    expect(failedView.rows).toEqual([]);
    expect(failedView.newCredits).toBeNull();
    expect(failedView.missingCourseIds).toEqual([]);
    expect(failedView.lit.nodes).toEqual(new Set(["course:root"]));
    const blocked = {
      action_key: "course:unused",
      occurrence_id: "unused",
      state: "no_solution",
      reason: "excluded_node",
      detail: null,
      referenced_group_id: "unused",
    };
    const noSolution = path("no_solution", {
      blocked_excluded_group_ids: ["unused"],
      blocked_excluded_node_keys: ["connector:or"],
      problems: [blocked, blocked],
    });
    const noSolutionView = build(graph, noSolution);
    expect(noSolutionView.blockedCourseIds).toEqual(["unused"]);
    expect(noSolutionView.blockedNodeTitles).toEqual(["OR"]);
    expect(noSolutionView.problems).toHaveLength(1);
    expect(noSolutionView.newCredits).toBeNull();
    expect(noSolutionView.lit.nodes).toEqual(
      new Set(["course:root", "course:unused", "connector:or"]),
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
            { value: { embeddings_enabled: true, inference_enabled: true } },
            createElement(RoutePanel, { view, route: session }),
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
    expect(problemList.closest(".route-list-disclosure")).toBeNull();
    const unresolved = path("unresolved", {
      problems: [
        { ...blocked, action_key: "connector:or", state: "unresolved" },
        { ...blocked, action_key: "connector:or", state: "unresolved" },
        {
          ...blocked,
          action_key: "connector:or",
          state: "unresolved",
          occurrence_id: "second-location",
        },
      ],
    });
    expect(
      build(graph, unresolved).problems.map((problem) => problem.identity),
    ).toEqual([
      "unused|connector:or|excluded_node",
      "second-location|connector:or|excluded_node",
    ]);
    const shortfall = path("shortfall", {
      new_courses: [courseEntry],
      total_new_credits: "3",
      selected_occurrence_ids: ["chosen"],
      shortfalls: [
        {
          kind: "cardinality",
          occurrence_id: "or",
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
    const zero = path("exact", {
      total_new_credits: "0",
      selected_occurrence_ids: [],
    });
    expect(build(graph, zero).rows).toEqual([]);
  });
});
