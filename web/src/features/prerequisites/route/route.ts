/** Route summary from authoritative graph/route data and renderer-specific route lighting. */
import type { DisplayLanguage } from "../../../state/types";
import type {
  GraphEdgeRelationship,
  PrerequisiteGraphReport,
  PrerequisitePath,
  PrerequisitePathState,
} from "../../../api/types";
import type { GraphModel, ModelNode } from "../graph/model";
import { connectorLabel } from "../graph/model";
import { localizedName } from "../../../shared/course/presentation";
import { diagnosticText, uiText } from "../../../shared/wording";

type RouteRow =
  | {
      kind: "course";
      course: NonNullable<ModelNode["course"]>;
      covered: boolean;
    }
  | { kind: "opaque"; key: string; credits: string };
export type RouteSummary = {
  state: PrerequisitePathState;
  newCredits: string | null;
  fullCredits: string | null;
  rows: RouteRow[];
  missingCourseIds: string[];
  blockedCourseIds: string[];
  blockedNodeTitles: string[];
  problems: {
    identity: string;
    actionKey: string;
    occurrenceId: string;
    courseId: string | null;
    title: string | null;
    reason: string;
  }[];
  shortfalls: { title: string; text: string }[];
};
type RouteView = RouteSummary & {
  lit: { nodes: Set<string>; edges: Set<string>; levels: Map<string, number> };
};
const format = (value: number, language: DisplayLanguage): string =>
  uiText(language, "{value} cr", { value: Number(value.toFixed(2)) });
const routeStates = new Set<PrerequisitePathState>([
  "exact",
  "approximate",
  "shortfall",
]);

/** One drawing connection lights when any single member's own terminal-and-all-gates predicate holds. */
export function edgeLights(
  relationships: readonly GraphEdgeRelationship[],
  selected: ReadonlySet<string>,
): boolean {
  return relationships.some(
    (relationship) =>
      relationship.occurrence_ids.some((id) => selected.has(id)) &&
      relationship.condition_occurrence_ids.every((id) => selected.has(id)),
  );
}

function courseLabel(
  graph: PrerequisiteGraphReport,
  id: string,
  language: DisplayLanguage,
): string | null {
  const course = graph.compilation.graph.course_nodes.find(
    (node) => node.course.group_id === id,
  )?.course;
  if (!course) return null;
  return uiText(language, "{code} {name}", {
    code: course.code,
    name: localizedName(language, course.name_fi, course.name_en, ""),
  }).trim();
}
function actionTitle(
  graph: PrerequisiteGraphReport,
  action: string,
  language: DisplayLanguage,
): string | null {
  if (action.startsWith("course:"))
    return courseLabel(graph, action.slice("course:".length), language);
  const module = graph.compilation.graph.module_nodes.find(
    (item) => item.action_key === action,
  );
  if (module)
    return localizedName(
      language,
      module.module.name_fi,
      module.module.name_en,
      module.module.code,
    );
  const connector = graph.compilation.graph.connector_nodes.find(
    (item) => item.action_key === action,
  );
  return connector ? connectorLabel(connector, language) : null;
}
export function buildRouteSummary(
  graph: PrerequisiteGraphReport,
  path: PrerequisitePath,
  language: DisplayLanguage,
): RouteSummary {
  const selected = new Set(path.selected_occurrence_ids);
  const courseIds = new Set<string>();
  for (const edge of graph.compilation.graph.edges) {
    if (!edgeLights(edge.relationships, selected)) continue;
    for (const endpoint of [edge.source_node_id, edge.target_node_id])
      if (endpoint.startsWith("course:"))
        courseIds.add(endpoint.slice("course:".length));
  }
  const newIds = new Set(path.new_courses.map(({ course }) => course.group_id));
  const rows: RouteRow[] = [];
  if (routeStates.has(path.state)) {
    for (const entry of path.new_courses)
      rows.push({ kind: "course", course: entry.course, covered: false });
    for (const item of graph.compilation.graph.course_nodes)
      if (
        !item.is_root &&
        courseIds.has(item.course.group_id) &&
        !newIds.has(item.course.group_id)
      )
        rows.push({ kind: "course", course: item.course, covered: true });
    for (const item of path.new_opaque_work)
      rows.push({
        kind: "opaque",
        key: item.work_key,
        credits: format(Number(item.credits_min), language),
      });
  }
  const coveredCredits = graph.compilation.graph.course_nodes
    .filter(
      (item) =>
        !item.is_root &&
        courseIds.has(item.course.group_id) &&
        !newIds.has(item.course.group_id),
    )
    .reduce((sum, item) => sum + Number(item.course.credits_min), 0);
  const total =
    path.total_new_credits === null ? null : Number(path.total_new_credits);
  const blockedCourseIds = [...path.blocked_excluded_group_ids];
  const blockedNodeTitles = path.blocked_excluded_node_keys.map(
    (key) => actionTitle(graph, key, language) ?? key,
  );
  const seen = new Set<string>();
  const problems = path.problems.flatMap((problem) => {
    const identity = [
      problem.occurrence_id,
      problem.action_key,
      problem.reason,
    ].join("|");
    if (seen.has(identity)) return [];
    seen.add(identity);
    const courseId = problem.action_key.startsWith("course:")
      ? problem.action_key.slice(7)
      : null;
    return [
      {
        identity,
        actionKey: problem.action_key,
        occurrenceId: problem.occurrence_id,
        courseId,
        title: actionTitle(graph, problem.action_key, language),
        reason: diagnosticText(problem.reason, problem.detail, language),
      },
    ];
  });
  const shortfalls = path.shortfalls.map((item) => {
    const title = graph.compilation.graph.module_nodes.find(
      (module) => module.node_id === `module:${item.occurrence_id}`,
    );
    const connector = graph.compilation.graph.connector_nodes.find(
      (node) => node.node_id === `connector:${item.occurrence_id}`,
    );
    const label = title
      ? localizedName(
          language,
          title.module.name_fi,
          title.module.name_en,
          title.module.code,
        )
      : connector
        ? connectorLabel(connector, language)
        : item.occurrence_id;
    const count =
      item.kind === "all_mandatory" ||
      item.kind === "cardinality" ||
      item.kind === "course_count";
    return {
      title: label ?? item.occurrence_id,
      text: count
        ? uiText(language, "{achieved} of {required} courses", {
            achieved: item.achieved_count ?? 0,
            required: item.required_count ?? 0,
          })
        : uiText(language, "{achieved} of {required} cr", {
            achieved: Number(item.achieved_credits),
            required: Number(item.required_credits),
          }),
    };
  });
  return {
    state: path.state,
    newCredits: total === null ? null : format(total, language),
    fullCredits:
      total === null ? null : format(total + coveredCredits, language),
    rows,
    missingCourseIds: path.new_courses.map(({ course }) => course.group_id),
    blockedCourseIds,
    blockedNodeTitles,
    problems,
    shortfalls,
  };
}

export function buildRouteView(
  graph: PrerequisiteGraphReport,
  path: PrerequisitePath,
  model: GraphModel,
  summary: RouteSummary,
): RouteView {
  const selected = new Set(path.selected_occurrence_ids);
  const litEdges = new Set(
    routeStates.has(path.state)
      ? model.edges
          .filter((edge) => edgeLights(edge.relationships, selected))
          .map((edge) => edge.id)
      : [],
  );
  const litNodes = new Set<string>([model.rootId]);
  if (path.state === "no_solution" || path.state === "unresolved") {
    const actions = new Set([
      ...path.problems.map((problem) => problem.action_key),
      ...path.blocked_excluded_node_keys,
    ]);
    const blockedCourses = new Set(path.blocked_excluded_group_ids);
    for (const node of graph.compilation.graph.course_nodes)
      if (blockedCourses.has(node.course.group_id))
        actions.add(node.action_key);
    for (const node of model.nodes)
      if (actions.has(node.actionKey)) litNodes.add(node.id);
  } else if (path.state !== "approximation_failed") {
    for (const edge of model.edges)
      if (litEdges.has(edge.id)) {
        litNodes.add(edge.source);
        litNodes.add(edge.target);
      }
  }
  const levels = new Map<string, number>([[model.rootId, 0]]);
  const children = new Map<string, string[]>();
  for (const edge of model.edges) {
    const targets = children.get(edge.source) ?? [];
    targets.push(edge.target);
    children.set(edge.source, targets);
  }
  const queue = [model.rootId];
  while (queue.length) {
    const current = queue.shift()!;
    for (const target of children.get(current) ?? [])
      if (!levels.has(target)) {
        levels.set(target, levels.get(current)! + 1);
        queue.push(target);
      }
  }
  return {
    ...summary,
    lit: { nodes: litNodes, edges: litEdges, levels },
  };
}
