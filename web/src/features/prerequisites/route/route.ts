/** Route summary from the native graph/route data and renderer-specific route lighting. */
import type { DisplayLanguage } from "../../../state/types";
import type {
  GraphDisplayNode,
  PrerequisiteGraphReport,
  PrerequisitePath,
  PrerequisitePathState,
} from "../../../api/types";
import type { GraphModel, ModelNode } from "../graph/model";
import { connectorLabel } from "../graph/model";
import { localizedName } from "../../../shared/course/presentation";
import { diagnosticText, reasonText, uiText } from "../../../shared/wording";

type RouteRow =
  | {
      kind: "course";
      course: NonNullable<ModelNode["course"]>;
      covered: boolean;
    }
  | { kind: "opaque"; key: string; credits: string };
/** One route rendered as its state, credits, rows, problems and shortfalls. */
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
    nodeId: string;
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

function courseLabel(
  graph: PrerequisiteGraphReport,
  id: string,
  language: DisplayLanguage,
): string | null {
  const course = graph.solver.courses.find((item) => item.group_id === id);
  if (!course) return null;
  return uiText(language, "{code} {name}", {
    code: course.code,
    name: localizedName(language, course.name_fi, course.name_en, ""),
  }).trim();
}
function displayNode(
  graph: PrerequisiteGraphReport,
  nodeId: string,
): GraphDisplayNode | null {
  return graph.display?.nodes.find((node) => node.node_id === nodeId) ?? null;
}
function pieceLabel(
  graph: PrerequisiteGraphReport,
  pieceId: string,
  language: DisplayLanguage,
): string | null {
  const piece = graph.solver.pieces.find((item) => item.piece_id === pieceId);
  if (!piece) return null;
  if (piece.kind === "module_block" && piece.module_group_id !== null) {
    const module = graph.solver.modules.find(
      (item) => item.group_id === piece.module_group_id,
    );
    if (module)
      return localizedName(
        language,
        module.name_fi,
        module.name_en,
        module.code ?? uiText(language, "module"),
      );
  }
  const value = (min: string | number | null, max: string | number | null) => {
    if (min === null) return "";
    const a = Number(min);
    const b = max === null ? a : Number(max);
    return a === b ? `${a}` : `${a} to ${b}`;
  };
  switch (piece.kind) {
    case "and":
      return uiText(language, "AND");
    case "or":
    case "expanded_course":
    case "course_alternatives":
      return uiText(language, "OR");
    case "cardinality":
      return uiText(language, "pick {range}", {
        range: value(piece.require_min, piece.require_max),
      });
    case "credits":
      return uiText(language, "{value} cr", {
        value: value(piece.credits_min, piece.credits_max),
      });
    case "course_count": {
      const count = value(piece.count_min, piece.count_max);
      return count === "1"
        ? uiText(language, "1 course")
        : uiText(language, "{value} courses", { value: count });
    }
    case "opaque_credits":
      return uiText(language, "{value} cr other", {
        value: value(piece.credits_min, piece.credits_max),
      });
    case "unresolved":
      return reasonText(piece.reason ?? "unresolved", language);
    default:
      return null;
  }
}
function nodeTitle(
  graph: PrerequisiteGraphReport,
  nodeId: string,
  language: DisplayLanguage,
  supportId: string | null = null,
): string | null {
  if (nodeId.startsWith("course:"))
    return courseLabel(graph, nodeId.slice("course:".length), language);
  const node = displayNode(graph, nodeId);
  if (node !== null) {
    if (node.kind === "module" && node.module_group_id !== null) {
      const module = graph.solver.modules.find(
        (item) => item.group_id === node.module_group_id,
      );
      if (module)
        return localizedName(
          language,
          module.name_fi,
          module.name_en,
          module.code ?? uiText(language, "module"),
        );
    }
    if (node.kind === "ignored")
      return reasonText(node.reason ?? "ignored", language);
    return connectorLabel(node, language);
  }
  const binding =
    (supportId === null
      ? undefined
      : graph.solver.bindings.find((item) => item.support_id === supportId)) ??
    graph.solver.bindings.find((item) => item.node_ids.includes(nodeId));
  return binding ? pieceLabel(graph, binding.piece_id, language) : null;
}
/** Return the display summary of one route result. */
export function buildRouteSummary(
  graph: PrerequisiteGraphReport,
  path: PrerequisitePath,
  language: DisplayLanguage,
): RouteSummary {
  const newIds = new Set(path.new_courses.map(({ course }) => course.group_id));
  const rows: RouteRow[] = [];
  if (routeStates.has(path.state)) {
    for (const entry of path.new_courses)
      rows.push({ kind: "course", course: entry.course, covered: false });
    for (const course of path.covered_courses)
      if (!newIds.has(course.group_id))
        rows.push({ kind: "course", course, covered: true });
    for (const item of path.new_opaque_work)
      rows.push({
        kind: "opaque",
        key: item.work_key,
        credits: format(Number(item.credits_min), language),
      });
  }
  const coveredCredits = path.covered_courses
    .filter((course) => !newIds.has(course.group_id))
    .reduce((sum, course) => sum + Number(course.credits_min), 0);
  const total =
    path.total_new_credits === null ? null : Number(path.total_new_credits);
  const blockedCourseIds = [...path.blocked_excluded_group_ids];
  const blockedNodeTitles = path.blocked_excluded_node_keys.map(
    (key) => nodeTitle(graph, key, language) ?? key,
  );
  const seen = new Set<string>();
  const problems = path.problems.flatMap((problem) => {
    const identity = [
      problem.node_id,
      problem.reason,
      problem.detail ?? "",
    ].join("|");
    if (seen.has(identity)) return [];
    seen.add(identity);
    const courseId = problem.node_id.startsWith("course:")
      ? problem.node_id.slice("course:".length)
      : null;
    return [
      {
        identity,
        nodeId: problem.node_id,
        courseId,
        title: nodeTitle(graph, problem.node_id, language, problem.support_id),
        reason: diagnosticText(problem.reason, problem.detail, language),
      },
    ];
  });
  const shortfalls = path.shortfalls.map((item) => {
    const label =
      nodeTitle(graph, item.node_id, language, item.support_id) ?? item.node_id;
    const count =
      item.kind === "all_mandatory" ||
      item.kind === "cardinality" ||
      item.kind === "course_count";
    return {
      title: label,
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

/** Return the drawn route lighting of one route result. */
export function buildRouteView(
  path: PrerequisitePath,
  model: GraphModel,
  summary: RouteSummary,
): RouteView {
  const litNodes = new Set<string>([model.rootId]);
  const litEdges = new Set<string>();
  if (routeStates.has(path.state)) {
    for (const nodeId of path.selected_nodes) litNodes.add(nodeId);
    const members = new Set(path.lit_members);
    for (const edge of model.edges)
      if (edge.memberIds.some((memberId) => members.has(memberId))) {
        litEdges.add(edge.id);
      }
  } else if (path.state === "no_solution" || path.state === "unresolved") {
    for (const nodeId of path.problems.map((problem) => problem.node_id))
      litNodes.add(nodeId);
    for (const nodeId of path.blocked_excluded_node_keys) litNodes.add(nodeId);
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
