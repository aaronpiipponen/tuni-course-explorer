/** ELK-laid-out React Flow canvas for every node and edge in the drawing report. */
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type MutableRefObject,
} from "react";
import {
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  type Edge,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/base.css";
import type { PrerequisiteGraphReport } from "../../../api/types";
import { useProfileSelector } from "../../../state/useProfileSelector";
import { useReducedMotion } from "../../../shared/useReducedMotion";
import { toggleExcludedCourse } from "../actions";
import { buildGraphModel, connectionChain } from "./model";
import { useGraphLayout } from "./useGraphLayout";
import { useAnimatedGraph } from "./useAnimatedGraph";
import { CourseNode, type GraphNodeData } from "./CourseNode";
import { ModuleNode } from "./ModuleNode";
import { ConnectorNode } from "./ConnectorNode";
import { IgnoredNode } from "./IgnoredNode";
import { PrerequisiteEdge } from "./PrerequisiteEdge";
import { MemberPanel } from "./MemberPanel";
import { ErrorNotice } from "../../../shared/ErrorNotice";
import { buildRouteView, type RouteSummary } from "../route/route";
import { RouteControl } from "../route/RouteControl";
import { RoutePanel } from "../route/RoutePanel";
import type { MinimumRouteSession } from "../route/useMinimumRoute";
import "./graph.css";

const nodeTypes = {
  course: CourseNode,
  module: ModuleNode,
  connector: ConnectorNode,
  ignored: IgnoredNode,
};
const edgeTypes = { prereq: PrerequisiteEdge };

function GraphCanvas({
  report,
  recenterRef,
  route,
  summary,
  graphLoading,
}: {
  report: PrerequisiteGraphReport;
  recenterRef: MutableRefObject<(() => void) | null>;
  route: MinimumRouteSession;
  summary: RouteSummary | null;
  graphLoading: boolean;
}) {
  const { value: language } = useProfileSelector((state) => state.language);
  const reducedMotion = useReducedMotion();
  const { store } = useProfileSelector(
    (state) => state.prerequisites.excludedCourseIds,
  );
  const { value: basis } = useProfileSelector(
    (state) => state.prerequisites.basis,
  );
  const targetModel = useMemo(
    () => buildGraphModel(report, language),
    [report, language],
  );
  const { graph, error, layouting } = useGraphLayout(targetModel);
  const model = graph?.model ?? targetModel;
  const layout = graph?.layout ?? null;
  const frame = useAnimatedGraph(graph);
  const view = useMemo(
    () =>
      route.result && summary
        ? buildRouteView(report, route.result, model, summary)
        : null,
    [report, route.result, model, summary],
  );
  // Only a real result or a pending explicit request dims the graph or drives route UI.
  const routing = view !== null || route.calculating;
  const lit = view?.lit ?? null;
  const { setViewport } = useReactFlow();
  const [hoverId, setHoverId] = useState<string | null>(null);
  const [menuId, setMenuId] = useState<string | null>(null);
  const [panelId, setPanelId] = useState<string | null>(null);
  const box = useRef<HTMLDivElement>(null);
  const highlightId = menuId ?? panelId ?? hoverId;
  const chain = routing
    ? null
    : highlightId
      ? connectionChain(model, highlightId)
      : null;
  const nodes = useMemo<Node<GraphNodeData>[]>(
    () =>
      frame
        ? frame.nodes.map(({ node: item, position, opacity, exiting }) => {
            const related = routing
              ? !lit || lit.nodes.has(item.id)
              : !chain || chain.nodes.has(item.id);
            const litNode = lit !== null && lit.nodes.has(item.id);
            return {
              id: item.id,
              type: item.kind,
              position: { x: position.x + 40, y: position.y + 30 },
              width: position.w,
              height: position.h,
              // Controlled nodes are recreated every frame, so React Flow re-adopts them by identity.
              // Supplying the fixed footprint keeps the measured handle bounds mounted
              // rather than treating each frame as an unmeasured node.
              measured: { width: position.w, height: position.h },
              data: {
                ...item,
                selectedOnly:
                  basis === "selected" &&
                  item.kind === "course" &&
                  Boolean(
                    item.state?.satisfied_by_basis &&
                    !item.state.completed_by_courses,
                  ),
                timeout:
                  view?.state === "approximation_failed" && Boolean(item.root),
                onMembers: setPanelId,
                onCourseExclude: (id: string) =>
                  toggleExcludedCourse(store, id),
                onNodeOpen: (id: string, open: boolean) =>
                  setMenuId(open ? id : null),
                interactionDisabled: exiting || layouting,
              },
              className: `${related ? "" : "dim"}${litNode ? " rt" : ""}${litNode ? ` route-delay-${lit.levels.get(item.id) ?? 0}` : ""}${!routing && (item.id === hoverId || item.id === panelId || item.id === menuId) ? " hot" : ""}`,
              style: {
                opacity:
                  opacity *
                  (related ? 1 : 0.28) *
                  (item.kind === "course" && item.active === false ? 0.6 : 1),
                pointerEvents: exiting || layouting ? "none" : "auto",
                ...(litNode
                  ? ({
                      "--dl": `${(lit.levels.get(item.id) ?? 0) * 0.32}s`,
                    } as React.CSSProperties)
                  : {}),
              },
            };
          })
        : [],
    [
      frame,
      chain,
      hoverId,
      panelId,
      menuId,
      store,
      basis,
      routing,
      lit,
      view,
      layouting,
    ],
  );
  const edges = useMemo<Edge[]>(
    () =>
      frame
        ? frame.edges.map(({ edge: item, points, opacity }) => {
            const litEdge = lit !== null && lit.edges.has(item.id);
            const delay = litEdge
              ? `${(lit.levels.get(item.source) ?? 0) * 0.32 + 0.14}s`
              : undefined;
            const dim = routing
              ? !litEdge
              : Boolean(chain && !chain.edges.has(item.id));
            return {
              id: item.id,
              source: item.source,
              target: item.target,
              type: "prereq",
              style: {
                opacity: opacity * (dim ? 0.28 : 1),
                ...(delay ? { "--dl": delay } : {}),
              } as React.CSSProperties,
              data: {
                ...item,
                delay,
                points: points.map((point) => ({
                  x: point.x + 40,
                  y: point.y + 30,
                })),
                opacity,
              },
              className: `${routing ? (litEdge ? "rt" : "dim") : chain && !chain.edges.has(item.id) ? "dim" : ""}${!routing && chain?.edges.has(item.id) ? " hot" : ""}`,
            };
          })
        : [],
    [frame, chain, routing, lit],
  );
  const centerRoot = useCallback(
    (animated: boolean) => {
      const root = layout?.nodes.get(model.rootId);
      if (!root || !box.current) return;
      const width = box.current.clientWidth;
      const zoom = 1;
      void setViewport(
        {
          x: width / 2 - (root.x + 40 + root.w / 2) * zoom,
          y: 30 - (root.y + 30) * zoom,
          zoom,
        },
        { duration: animated && !reducedMotion ? 450 : 0 },
      );
    },
    [layout, model.rootId, setViewport, reducedMotion],
  );
  useEffect(() => {
    recenterRef.current = () => centerRoot(true);
    return () => {
      recenterRef.current = null;
    };
  }, [centerRoot, recenterRef]);
  const centeredRoot = useRef<string | null>(null);
  useEffect(() => {
    if (layout && centeredRoot.current !== model.rootId) {
      centeredRoot.current = model.rootId;
      centerRoot(false);
    }
  }, [layout, model.rootId, centerRoot]);
  useEffect(() => {
    if (menuId && !targetModel.nodes.some((node) => node.id === menuId))
      setMenuId(null);
    if (panelId && !targetModel.nodes.some((node) => node.id === panelId))
      setPanelId(null);
  }, [targetModel, menuId, panelId]);
  useEffect(() => {
    if (layouting) setPanelId(null);
  }, [layouting]);
  useEffect(() => {
    if (!panelId) return;
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setPanelId(null);
    };
    document.addEventListener("keydown", escape);
    return () => document.removeEventListener("keydown", escape);
  }, [panelId]);
  if (error) return <ErrorNotice error={error} language={language} />;
  const panelNode = model.nodes.find((node) => node.id === panelId) ?? null;
  return (
    <div className={`graph-stage${chain ? " hl" : ""}`}>
      <RouteControl
        route={route}
        disabled={graphLoading || route.calculating}
      />
      <div ref={box} className={`graph-panel${routing ? " route" : ""}`}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable={false}
          nodesFocusable={false}
          edgesFocusable={false}
          disableKeyboardA11y
          panOnDrag
          zoomOnScroll
          zoomOnPinch
          minZoom={0.15}
          maxZoom={2.2}
          onNodeMouseEnter={(_, node) => setHoverId(node.id)}
          onNodeMouseLeave={() => setHoverId(null)}
          onPaneClick={() => setPanelId(null)}
          proOptions={{ hideAttribution: false }}
        />
      </div>
      <div className="route-stack">
        <RoutePanel view={summary} route={route} />
        <MemberPanel node={panelNode} onClose={() => setPanelId(null)} />
      </div>
    </div>
  );
}

export function PrerequisiteGraph({
  report,
  recenterRef,
  route,
  summary,
  graphLoading,
}: {
  report: PrerequisiteGraphReport;
  recenterRef: MutableRefObject<(() => void) | null>;
  route: MinimumRouteSession;
  summary: RouteSummary | null;
  graphLoading: boolean;
}) {
  return (
    <ReactFlowProvider>
      <GraphCanvas
        report={report}
        recenterRef={recenterRef}
        route={route}
        summary={summary}
        graphLoading={graphLoading}
      />
    </ReactFlowProvider>
  );
}
