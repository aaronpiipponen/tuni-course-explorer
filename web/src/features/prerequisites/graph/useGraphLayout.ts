/** Transient asynchronous layout keyed only by graph structure. */
import { useEffect, useState } from "react";
import type { GraphModel } from "./model";
import { layoutGraph, type GraphLayout } from "./layout";

export function useGraphLayout(model: GraphModel | null): {
  graph: LaidOutGraph | null;
  layouting: boolean;
  error: Error | null;
} {
  const signature = model
    ? JSON.stringify([
        model.rootId,
        model.nodes.map(({ id, kind }) => [id, kind]),
        model.edges.map(({ id }) => id),
      ])
    : "";
  const [result, setResult] = useState<{
    signature: string;
    graphSignature: string | null;
    graph: LaidOutGraph | null;
    layouting: boolean;
    error: Error | null;
  }>({
    signature,
    graphSignature: null,
    graph: null,
    layouting: Boolean(model),
    error: null,
  });
  useEffect(() => {
    if (!model) {
      setResult({
        signature,
        graphSignature: null,
        graph: null,
        layouting: false,
        error: null,
      });
      return;
    }
    let current = true;
    setResult((old) => ({
      signature,
      graphSignature:
        old.graph?.model.rootId === model.rootId ? old.graphSignature : null,
      graph: old.graph?.model.rootId === model.rootId ? old.graph : null,
      layouting: true,
      error: null,
    }));
    layoutGraph(model).then(
      (layout) => {
        if (current)
          setResult({
            signature,
            graphSignature: signature,
            graph: { model, layout },
            layouting: false,
            error: null,
          });
      },
      (caught: unknown) => {
        if (current)
          setResult({
            signature,
            graphSignature: null,
            graph: null,
            layouting: false,
            error: caught instanceof Error ? caught : new Error(String(caught)),
          });
      },
    );
    return () => {
      current = false;
    };
  }, [signature]);
  if (
    result.signature === signature &&
    result.graph &&
    model &&
    result.graphSignature === signature
  )
    return {
      graph: { ...result.graph, model },
      layouting: result.layouting,
      error: result.error,
    };
  if (result.signature !== signature)
    return {
      graph: result.graph?.model.rootId === model?.rootId ? result.graph : null,
      layouting: Boolean(model),
      error: null,
    };
  return {
    graph: result.graph,
    layouting: result.layouting,
    error: result.error,
  };
}

export type LaidOutGraph = { model: GraphModel; layout: GraphLayout };
