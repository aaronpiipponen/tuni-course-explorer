/** ELK layered graph mapping. Source report edges and all graph nodes are uncapped. */
import type { GraphModel } from "./model";
import { layoutWithElk } from "./elk";

/** Node and edge spacing of the ELK layered layout, in pixels. */
export const SPACING = {
  nodeNode: 40,
  layerNode: 80,
  edgeNode: 24,
  edgeEdge: 14,
};
/** Laid-out node positions and sizes and edge points by identity. */
export type GraphLayout = {
  nodes: Map<string, { x: number; y: number; w: number; h: number }>;
  edges: Map<string, { points: { x: number; y: number }[] }>;
};
/** Return the layered layout of one graph model. */
export async function layoutGraph(model: GraphModel): Promise<GraphLayout> {
  const result = await layoutWithElk({
    id: "root",
    layoutOptions: {
      "elk.algorithm": "layered",
      "elk.direction": "DOWN",
      "elk.edgeRouting": "ORTHOGONAL",
      "elk.spacing.nodeNode": String(SPACING.nodeNode),
      "elk.layered.spacing.nodeNodeBetweenLayers": String(SPACING.layerNode),
      "elk.layered.spacing.edgeNodeBetweenLayers": String(SPACING.edgeNode),
      "elk.spacing.edgeEdge": String(SPACING.edgeEdge),
    },
    children: model.nodes.map((node) => ({
      id: node.id,
      width: node.size.width,
      height: node.size.height,
    })),
    edges: model.edges.map((edge) => ({
      id: edge.id,
      sources: [edge.source],
      targets: [edge.target],
    })),
  });
  const nodes = new Map<string, { x: number; y: number; w: number; h: number }>(
    (result.children ?? []).map(
      (node: {
        id: string;
        x?: number;
        y?: number;
        width?: number;
        height?: number;
      }) => [
        node.id,
        {
          x: node.x ?? 0,
          y: node.y ?? 0,
          w: node.width ?? 0,
          h: node.height ?? 0,
        },
      ],
    ),
  );
  const edges = new Map<string, { points: { x: number; y: number }[] }>(
    (result.edges ?? []).map(
      (edge: {
        id: string;
        sections?: {
          startPoint: { x: number; y: number };
          bendPoints?: { x: number; y: number }[];
          endPoint: { x: number; y: number };
        }[];
      }) => [
        edge.id,
        {
          points: edge.sections?.[0]
            ? [
                edge.sections[0].startPoint,
                ...(edge.sections[0].bendPoints ?? []),
                edge.sections[0].endPoint,
              ]
            : [],
        },
      ],
    ),
  );
  // Anchor the root at the origin so a structure change never shifts the graph under the viewport.
  const root = nodes.get(model.rootId);
  if (root) {
    const { x: dx, y: dy } = root;
    for (const node of nodes.values()) {
      node.x -= dx;
      node.y -= dy;
    }
    for (const { points } of edges.values())
      for (const point of points) {
        point.x -= dx;
        point.y -= dy;
      }
  }
  return { nodes, edges };
}
