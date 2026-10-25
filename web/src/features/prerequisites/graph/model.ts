/** Pure mapping from the native graph report to renderer-owned node data. */
import type { DisplayLanguage } from "../../../state/types";
import type {
  CourseSummary,
  GraphDisplayNode,
  GraphNodeState,
  ModuleSummary,
  PrerequisiteGraphReport,
} from "../../../api/types";
import { NODE_SIZES } from "./sizes";
import { localizedName } from "../../../shared/course/presentation";
import { diagnosticText, reasonText, uiText } from "../../../shared/wording";

/** One renderer-owned node of the prerequisite drawing. */
export type ModelNode = {
  id: string;
  kind: "course" | "module" | "connector" | "ignored";
  size: { width: number; height: number };
  markKey: string | null;
  markable: boolean;
  state: GraphNodeState | null;
  title: string;
  subtitle: string;
  course?: CourseSummary;
  module?: ModuleSummary;
  members?: readonly CourseSummary[];
  label?: string;
  inferred?: boolean;
  root?: boolean;
  active?: boolean;
  subtype?: string;
};
/** One renderer-owned connection between two drawn nodes. */
export type ModelEdge = {
  id: string;
  source: string;
  target: string;
  inferred: boolean;
  parentIndex: number;
  memberIds: readonly string[];
};
/** The renderer model of one drawing: its nodes, edges and root. */
export type GraphModel = {
  nodes: ModelNode[];
  edges: ModelEdge[];
  rootId: string;
};
const range = (
  min: number | string | null,
  max: number | string | null,
): string => {
  if (min === null && max === null) return "";
  if (max === null) return `${min}+`;
  if (min === null) return `≤${max}`;
  const a = Number(min),
    b = Number(max);
  return a === b ? `${a}` : `${a}–${b}`;
};
/** Return the display label of one logical, numeric or unresolved node. */
export function connectorLabel(
  node: GraphDisplayNode,
  language: DisplayLanguage,
): string {
  switch (node.kind) {
    case "and":
      return uiText(language, "AND");
    case "or":
      return uiText(language, "OR");
    case "cardinality":
      return uiText(language, "pick {range}", {
        range: range(node.require_min, node.require_max),
      });
    case "credits":
      return uiText(language, "{value} cr", {
        value: range(node.credits_min, node.credits_max),
      });
    case "course_count": {
      const value = range(node.count_min, node.count_max);
      return value === "1"
        ? uiText(language, "1 course")
        : uiText(language, "{value} courses", { value });
    }
    case "opaque_credits":
      return uiText(language, "{value} cr other", {
        value: range(node.credits_min, node.credits_max),
      });
    case "internal_requirement":
      return uiText(
        language,
        node.member_group_ids.length === 1
          ? "{count} course"
          : "{count} courses",
        { count: node.member_group_ids.length },
      );
    case "unresolved":
      return reasonText(node.reason ?? node.kind, language);
    default:
      return "";
  }
}
/** Return the renderer model of one report under the given language and node states. */
export function buildGraphModel(
  report: PrerequisiteGraphReport,
  language: DisplayLanguage,
  nodeStates: readonly GraphNodeState[],
): GraphModel {
  const display = report.display;
  if (display === null) throw new Error("graph report has no display");
  const states = new Map(nodeStates.map((state) => [state.node_id, state]));
  const courses = new Map(
    report.solver.courses.map((course) => [course.group_id, course]),
  );
  const modules = new Map(
    report.solver.modules.map((module) => [module.group_id, module]),
  );
  const nodes: ModelNode[] = [];
  const resolvedMembers = (item: GraphDisplayNode): CourseSummary[] =>
    item.member_group_ids.map((group_id) => {
      const course = courses.get(group_id);
      if (course === undefined) {
        throw new Error(
          `graph node ${item.node_id} references missing member ${group_id}`,
        );
      }
      return course;
    });
  for (const item of display.nodes) {
    const state = states.get(item.node_id) ?? null;
    if (item.kind === "course") {
      const course = courses.get(String(item.course_group_id));
      if (course === undefined) {
        throw new Error(
          `graph node ${item.node_id} references missing course ${String(item.course_group_id)}`,
        );
      }
      nodes.push({
        id: item.node_id,
        kind: "course",
        size: NODE_SIZES.course,
        markKey: null,
        markable: false,
        state,
        title: course.code,
        subtitle: localizedName(language, course.name_fi, course.name_en, ""),
        course,
        inferred: item.display_as_inferred,
        root: item.is_root,
        active: course.is_active,
      });
      continue;
    }
    if (item.kind === "module") {
      const module = modules.get(String(item.module_group_id));
      if (module === undefined) {
        throw new Error(
          `graph node ${item.node_id} references missing module ${String(item.module_group_id)}`,
        );
      }
      const members = resolvedMembers(item);
      nodes.push({
        id: item.node_id,
        kind: "module",
        size: NODE_SIZES.module,
        markKey: item.markable ? item.node_id : null,
        markable: item.markable,
        state,
        title: localizedName(
          language,
          module.name_fi,
          module.name_en,
          module.code ?? uiText(language, "module"),
        ),
        subtitle: uiText(
          language,
          members.length === 1 ? "{count} course" : "{count} courses",
          { count: members.length },
        ),
        module,
        members,
        label: connectorLabel(item, language),
        subtype: item.kind,
      });
      continue;
    }
    if (item.kind === "ignored") {
      nodes.push({
        id: item.node_id,
        kind: "ignored",
        size: NODE_SIZES.label,
        markKey: null,
        markable: false,
        state,
        title: reasonText(item.reason ?? "ignored", language),
        subtitle:
          item.detail === null
            ? ""
            : diagnosticText(item.reason ?? "ignored", item.detail, language),
      });
      continue;
    }
    const numeric = [
      "cardinality",
      "credits",
      "course_count",
      "opaque_credits",
    ].includes(item.kind);
    const junction = ["and", "or"].includes(item.kind);
    const members =
      item.kind === "internal_requirement" ? resolvedMembers(item) : undefined;
    nodes.push({
      id: item.node_id,
      kind: "connector",
      size: numeric
        ? NODE_SIZES.constraint
        : junction
          ? NODE_SIZES.junction
          : NODE_SIZES.label,
      markKey: item.markable ? item.node_id : null,
      markable: item.markable,
      state,
      title: connectorLabel(item, language),
      subtitle:
        item.detail !== null
          ? diagnosticText(item.reason ?? item.kind, item.detail, language)
          : item.reason !== null
            ? reasonText(item.reason, language)
            : "",
      members,
      label: connectorLabel(item, language),
      subtype: item.kind,
    });
  }
  const order = new Map<string, number>();
  const edges = display.edges.map((edge) => {
    if (!order.has(edge.source_node_id))
      order.set(edge.source_node_id, order.size);
    return {
      id: edge.edge_id,
      source: edge.source_node_id,
      target: edge.target_node_id,
      inferred: edge.inferred_only,
      parentIndex: order.get(edge.source_node_id)!,
      memberIds: edge.member_ids,
    };
  });
  const root = nodes.find((node) => node.kind === "course" && node.root);
  if (root === undefined) {
    throw new Error(
      `graph report has no root course node for ${report.solver.root_group_id}`,
    );
  }
  return {
    nodes,
    edges,
    rootId: root.id,
  };
}
/**
 * Return the nodes and connections a hover or an open panel highlights.
 *
 * Two independent walks start at the requested node. The parent walk follows a connection only
 * into its source, and the child walk follows it only into its target. Each walk continues
 * through every non-course box and stops at a course, so only the nearest course boundary is
 * reached and a sibling behind a shared parent is not lit.
 */
export function connectionChain(
  model: GraphModel,
  nodeId: string,
): { nodes: Set<string>; edges: Set<string> } {
  const nodes = new Set<string>([nodeId]);
  const edges = new Set<string>();
  const kinds = new Map(model.nodes.map((node) => [node.id, node.kind]));
  const walk = (toward: "source" | "target"): void => {
    const visited = new Set<string>([nodeId]);
    const queue = [nodeId];
    while (queue.length) {
      const current = queue.shift()!;
      for (const edge of model.edges) {
        const next =
          toward === "source"
            ? edge.target === current
              ? edge.source
              : null
            : edge.source === current
              ? edge.target
              : null;
        if (next === null) continue;
        edges.add(edge.id);
        nodes.add(next);
        if (visited.has(next)) continue;
        visited.add(next);
        if (kinds.get(next) !== "course") queue.push(next);
      }
    }
  };
  walk("source");
  walk("target");
  return { nodes, edges };
}
