/**
 * One transient animation owner for a changing graph layout. Nodes glide to their target
 * positions. An edge only fades out and back in at its final routed geometry when its drawn path
 * actually changes. An edge whose path is identical holds its place, so a drawing-neutral refresh
 * moves nothing and cold-mounts no edge. Edge polylines are drawn only at their final geometry, so a
 * layout change shows no slanted partial route. Under the reduced-motion preference each target
 * frame is published as it is, so no glide or fade runs.
 */
import { useEffect, useRef, useState } from "react";
import { useReducedMotion } from "../../../shared/useReducedMotion";
import type { ModelEdge, ModelNode } from "./model";
import type { LaidOutGraph } from "./useGraphLayout";

type AnimatedGraphFrame = {
  rootId: string;
  nodes: {
    node: ModelNode;
    position: { x: number; y: number; w: number; h: number };
    opacity: number;
    exiting: boolean;
  }[];
  edges: {
    edge: ModelEdge;
    points: { x: number; y: number }[];
    opacity: number;
    exiting: boolean;
  }[];
};

type Geometry = {
  node: ModelNode;
  position: { x: number; y: number; w: number; h: number };
  opacity: number;
  exiting: boolean;
};
type EdgeGeometry = {
  edge: ModelEdge;
  points: { x: number; y: number }[];
  opacity: number;
  exiting: boolean;
};
const duration = 600;
const ease = (value: number) => 1 - Math.pow(1 - value, 3);
const nodeFrame = (target: LaidOutGraph): Geometry[] =>
  target.model.nodes.map((node) => ({
    node,
    position: target.layout.nodes.get(node.id) ?? {
      x: 0,
      y: 0,
      w: node.size.width,
      h: node.size.height,
    },
    opacity: 1,
    exiting: false,
  }));
const edgeFrame = (target: LaidOutGraph): EdgeGeometry[] =>
  target.model.edges.map((edge) => ({
    edge,
    points: target.layout.edges.get(edge.id)?.points ?? [],
    opacity: 1,
    exiting: false,
  }));
const pointsEqual = (
  a: readonly { x: number; y: number }[],
  b: readonly { x: number; y: number }[],
) =>
  a.length === b.length &&
  a.every((point, index) => point.x === b[index].x && point.y === b[index].y);
/** True when the target already equals the frame on screen, so nothing should move or fade. */
const sameGeometry = (
  previous: AnimatedGraphFrame,
  nextNodes: Geometry[],
  nextEdges: EdgeGeometry[],
): boolean => {
  if (
    previous.nodes.length !== nextNodes.length ||
    previous.edges.length !== nextEdges.length
  )
    return false;
  const nodes = new Map(
    previous.nodes.map((item) => [item.node.id, item.position]),
  );
  for (const item of nextNodes) {
    const before = nodes.get(item.node.id);
    if (
      !before ||
      before.x !== item.position.x ||
      before.y !== item.position.y ||
      before.w !== item.position.w ||
      before.h !== item.position.h
    )
      return false;
  }
  const edges = new Map(
    previous.edges.map((item) => [item.edge.id, item.points]),
  );
  for (const item of nextEdges) {
    const before = edges.get(item.edge.id);
    if (!before || !pointsEqual(before, item.points)) return false;
  }
  return true;
};

export function useAnimatedGraph(
  target: LaidOutGraph | null,
): AnimatedGraphFrame | null {
  const [frame, setFrame] = useState<AnimatedGraphFrame | null>(null);
  const current = useRef<AnimatedGraphFrame | null>(null);
  const raf = useRef<number | null>(null);
  const reducedMotion = useReducedMotion();
  useEffect(() => {
    if (!target) {
      if (raf.current !== null) cancelAnimationFrame(raf.current);
      raf.current = null;
      current.current = null;
      setFrame(null);
      return;
    }
    const nextNodes = nodeFrame(target),
      nextEdges = edgeFrame(target);
    const previous = current.current;
    if (
      reducedMotion ||
      !previous ||
      previous.rootId !== target.model.rootId ||
      sameGeometry(previous, nextNodes, nextEdges)
    ) {
      // Publish the exact frame with no transition: the first graph, a changed root, identical
      // geometry, or the reduced-motion preference.
      if (raf.current !== null) cancelAnimationFrame(raf.current);
      raf.current = null;
      const initial = {
        rootId: target.model.rootId,
        nodes: nextNodes,
        edges: nextEdges,
      };
      current.current = initial;
      setFrame(initial);
      return;
    }
    if (raf.current !== null) cancelAnimationFrame(raf.current);
    const oldNodes = new Map(
      previous.nodes.map((item) => [item.node.id, item]),
    );
    const newNodes = new Map(nextNodes.map((item) => [item.node.id, item]));
    const oldEdges = new Map(
      previous.edges.map((item) => [item.edge.id, item]),
    );
    const newEdges = new Map(nextEdges.map((item) => [item.edge.id, item]));
    const start = performance.now();
    const tick = (now: number) => {
      const raw = Math.min(1, (now - start) / duration),
        t = ease(raw);
      // A changing edge is invisible at raw 0.5, so its routed geometry swaps at that midpoint.
      const fadeOut = Math.min(1, raw / 0.5);
      const fadeIn = Math.max(0, (raw - 0.5) / 0.5);
      const nodes = [
        ...new Set([...oldNodes.keys(), ...newNodes.keys()]),
      ].flatMap((id) => {
        const before = oldNodes.get(id),
          after = newNodes.get(id);
        if (!before && !after) return [];
        const a = before?.position ?? after!.position,
          b = after?.position ?? before!.position;
        return [
          {
            node: after?.node ?? before!.node,
            position: {
              x: a.x + (b.x - a.x) * t,
              y: a.y + (b.y - a.y) * t,
              w: a.w + (b.w - a.w) * t,
              h: a.h + (b.h - a.h) * t,
            },
            opacity: before && after ? 1 : before ? 1 - t : t,
            exiting: Boolean(before && !after),
          },
        ];
      });
      const edges = [
        ...new Set([...oldEdges.keys(), ...newEdges.keys()]),
      ].flatMap((id) => {
        const before = oldEdges.get(id),
          after = newEdges.get(id);
        if (!before && !after) return [];
        // An identical edge produces no fade or movement.
        if (before && after && pointsEqual(before.points, after.points))
          return [
            {
              edge: after.edge,
              points: after.points,
              opacity: 1,
              exiting: false,
            },
          ];
        const showFinal = !before || (Boolean(after) && raw >= 0.5);
        const opacity = before
          ? before.opacity * (1 - fadeOut) +
            (after ? after.opacity * fadeIn : 0)
          : after!.opacity * fadeIn;
        return [
          {
            edge: after?.edge ?? before!.edge,
            points: (showFinal ? after! : before!).points,
            opacity,
            exiting: Boolean(before && !after),
          },
        ];
      });
      const value = { rootId: target.model.rootId, nodes, edges };
      current.current = value;
      setFrame(value);
      if (raw < 1) raf.current = requestAnimationFrame(tick);
      else {
        const exact = {
          rootId: target.model.rootId,
          nodes: nextNodes,
          edges: nextEdges,
        };
        current.current = exact;
        setFrame(exact);
        raf.current = null;
      }
    };
    raf.current = requestAnimationFrame(tick);
    return () => {
      if (raf.current !== null) cancelAnimationFrame(raf.current);
    };
  }, [target?.model, target?.layout, reducedMotion]);
  return frame;
}
