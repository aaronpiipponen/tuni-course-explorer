/** Pure mapping from the authoritative graph report DTOs to renderer-owned node data. */
import type { DisplayLanguage } from "../../../state/types";
import type {
  GraphEdgeRelationship,
  GraphNodeState,
  PrerequisiteGraphReport,
} from "../../../api/types";
import { NODE_SIZES } from "./sizes";
import { localizedName } from "../../../shared/course/presentation";
import { diagnosticText, reasonText, uiText } from "../../../shared/wording";

export type ModelNode = {
  id: string;
  kind: "course" | "module" | "connector" | "ignored";
  size: { width: number; height: number };
  actionKey: string;
  markable: boolean;
  state: GraphNodeState | null;
  title: string;
  subtitle: string;
  course?: PrerequisiteGraphReport["compilation"]["tree"]["root"];
  module?: PrerequisiteGraphReport["compilation"]["graph"]["module_nodes"][number];
  members?: readonly PrerequisiteGraphReport["compilation"]["tree"]["courses"][number][];
  label?: string;
  inferred?: boolean;
  root?: boolean;
  active?: boolean;
  subtype?: string;
};
export type ModelEdge = {
  id: string;
  source: string;
  target: string;
  recommended: boolean;
  parentIndex: number;
  relationships: readonly GraphEdgeRelationship[];
};
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
export function connectorLabel(
  node: PrerequisiteGraphReport["compilation"]["graph"]["connector_nodes"][number],
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
    case "course_count":
      return uiText(language, "{value} courses", {
        value: range(node.count_min, node.count_max),
      });
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
      return reasonText(node.unresolved_reason ?? node.kind, language);
  }
}
export function buildGraphModel(
  report: PrerequisiteGraphReport,
  language: DisplayLanguage,
): GraphModel {
  const graph = report.compilation.graph,
    tree = report.compilation.tree;
  const states = new Map(
    graph.node_states.map((state) => [state.action_key, state]),
  );
  const nodes: ModelNode[] = [];
  for (const item of graph.course_nodes)
    nodes.push({
      id: item.node_id,
      kind: "course",
      size: NODE_SIZES.course,
      actionKey: item.action_key,
      markable: false,
      state: states.get(item.action_key) ?? null,
      title: item.course.code,
      subtitle: localizedName(
        language,
        item.course.name_fi,
        item.course.name_en,
        "",
      ),
      course: item.course,
      inferred: item.display_as_inferred,
      root: item.is_root,
      active: item.course.is_active,
    });
  for (const item of graph.module_nodes)
    nodes.push({
      id: item.node_id,
      kind: "module",
      size: NODE_SIZES.module,
      actionKey: item.action_key,
      markable: true,
      state: states.get(item.action_key) ?? null,
      title: localizedName(
        language,
        item.module.name_fi,
        item.module.name_en,
        item.module.code ?? uiText(language, "module"),
      ),
      subtitle: uiText(language, "{count} courses", {
        count: item.member_courses.length,
      }),
      module: item,
      members: item.member_courses,
    });
  for (const item of graph.connector_nodes) {
    const numeric = [
      "cardinality",
      "credits",
      "course_count",
      "opaque_credits",
    ].includes(item.kind);
    const junction = ["and", "or"].includes(item.kind);
    const members =
      item.kind === "internal_requirement"
        ? tree.courses.filter((course) =>
            item.member_group_ids.includes(course.group_id),
          )
        : undefined;
    nodes.push({
      id: item.node_id,
      kind: "connector",
      size: numeric
        ? NODE_SIZES.constraint
        : junction
          ? NODE_SIZES.junction
          : NODE_SIZES.label,
      actionKey: item.action_key,
      markable: numeric,
      state: states.get(item.action_key) ?? null,
      title: connectorLabel(item, language),
      subtitle:
        item.detail !== null
          ? diagnosticText(
              item.unresolved_reason ?? item.kind,
              item.detail,
              language,
            )
          : item.unresolved_reason !== null
            ? reasonText(item.unresolved_reason, language)
            : "",
      members,
      label: connectorLabel(item, language),
      subtype: item.kind,
    });
  }
  for (const item of graph.ignored_nodes) {
    const part = tree.ignored_parts.find(
      (candidate) => candidate.part_id === item.part_id,
    );
    nodes.push({
      id: item.node_id,
      kind: "ignored",
      size: NODE_SIZES.label,
      actionKey: item.action_key,
      markable: false,
      state: states.get(item.action_key) ?? null,
      title: part
        ? reasonText(part.kind, language)
        : reasonText("ignored", language),
      subtitle: part ? diagnosticText(part.kind, part.detail, language) : "",
    });
  }
  const order = new Map<string, number>();
  const edges = graph.edges.map((edge, index) => {
    if (!order.has(edge.source_node_id))
      order.set(edge.source_node_id, order.size);
    return {
      // One renderer edge per server-supplied connection: the backend already grouped equal endpoints
      // and provenance class, so the exact report order supplies the deterministic renderer suffix.
      id: `${edge.source_node_id}>${edge.target_node_id}-${index}`,
      source: edge.source_node_id,
      target: edge.target_node_id,
      recommended:
        edge.relationships[0].official_kind === "recommended" ||
        edge.relationships[0].inferred_category === "recommended",
      parentIndex: order.get(edge.source_node_id)!,
      relationships: edge.relationships,
    };
  });
  return {
    nodes,
    edges,
    rootId:
      graph.course_nodes.find((node) => node.is_root)?.node_id ??
      `course:${tree.root.group_id}`,
  };
}
export function connectionChain(
  model: GraphModel,
  nodeId: string,
): { nodes: Set<string>; edges: Set<string> } {
  const nodes = new Set([nodeId]),
    edges = new Set<string>(),
    queue = [nodeId];
  const kinds = new Map(model.nodes.map((node) => [node.id, node.kind]));
  while (queue.length) {
    const current = queue.shift()!;
    for (const edge of model.edges) {
      const next =
        edge.source === current
          ? edge.target
          : edge.target === current
            ? edge.source
            : null;
      if (next !== null) {
        edges.add(edge.id);
        if (!nodes.has(next)) {
          nodes.add(next);
          if (kinds.get(next) === "connector") queue.push(next);
        }
      }
    }
  }
  return { nodes, edges };
}
