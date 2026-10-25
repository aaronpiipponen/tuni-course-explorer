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
  getViewportForBounds,
  useReactFlow,
  type Edge,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/base.css";
import type {
  GraphNodeState,
  PrerequisiteGraphReport,
} from "../../../api/types";
import { useProfileSelector } from "../../../state/useProfileSelector";
import { useReducedMotion } from "../../../shared/useReducedMotion";
import { useWording } from "../../../shared/useWording";
import { RECENTER_ICON } from "../../../shared/icons";
import { toggleExcludedCourse } from "../actions";
import { buildGraphModel, connectionChain } from "./model";
import { useGraphLayout } from "./useGraphLayout";
import { useAnimatedGraph } from "./useAnimatedGraph";
import { usePhoneGraphSizes } from "./usePhoneGraphSizes";
import { NODE_SIZES } from "./sizes";
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
// The phone overview keeps a readable course title and never magnifies past the base size.
const PHONE_FIT_MIN_ZOOM = 0.6;
const PHONE_ROOT_TOP = 72;

/** Return the root and the two nearest drawing levels that the phone overview shows. */
function overviewNodes(model: {
  rootId: string;
  edges: readonly { source: string; target: string }[];
}): Set<string> {
  const ids = new Set<string>([model.rootId]);
  for (const edge of model.edges)
    if (edge.source === model.rootId) ids.add(edge.target);
  const first = new Set(ids);
  for (const edge of model.edges)
    if (first.has(edge.source)) ids.add(edge.target);
  return ids;
}

function GraphCanvas({
  report,
  nodeStates,
  recenterRef,
  route,
  summary,
  graphLoading,
}: {
  report: PrerequisiteGraphReport;
  nodeStates: readonly GraphNodeState[];
  recenterRef: MutableRefObject<(() => void) | null>;
  route: MinimumRouteSession;
  summary: RouteSummary | null;
  graphLoading: boolean;
}) {
  const { value: language } = useProfileSelector((state) => state.language);
  const { t } = useWording();
  const reducedMotion = useReducedMotion();
  const { store } = useProfileSelector(
    (state) => state.prerequisites.excludedCourseIds,
  );
  const baseModel = useMemo(
    () => buildGraphModel(report, language, nodeStates),
    [report, language, nodeStates],
  );
  const contentKey = useMemo(
    () =>
      JSON.stringify([
        baseModel.rootId,
        language,
        baseModel.nodes.map(({ id, kind, title, subtitle }) => [
          id,
          kind,
          title,
          subtitle,
        ]),
      ]),
    [baseModel, language],
  );
  const { phone, heights, onNodeHeight } = usePhoneGraphSizes(contentKey);
  const targetModel = useMemo(() => {
    if (!phone) return baseModel;
    return {
      ...baseModel,
      nodes: baseModel.nodes.map((node) =>
        (node.kind === "course" || node.kind === "module") &&
        heights.has(node.id)
          ? {
              ...node,
              size: { width: node.size.width, height: heights.get(node.id)! },
            }
          : node,
      ),
    };
  }, [baseModel, phone, heights]);
  const { graph, error, layouting } = useGraphLayout(targetModel);
  const model = graph?.model ?? targetModel;
  const layout = graph?.layout ?? null;
  const frame = useAnimatedGraph(graph);
  const view = useMemo(
    () =>
      route.result && summary
        ? buildRouteView(route.result, model, summary)
        : null,
    [report, route.result, model, summary],
  );
  // Only a real result or a pending explicit request dims the graph or drives route UI.
  const routing = view !== null || route.calculating;
  const lit = view?.lit ?? null;
  const { setViewport, zoomIn, zoomOut } = useReactFlow();
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
                phone,
                onNodeHeight,
                timeout:
                  view?.state === "approximation_failed" && Boolean(item.root),
                onMembers: setPanelId,
                onCourseExclude: (id: string) =>
                  toggleExcludedCourse(store, id),
                onNodeOpen: (id: string, open: boolean) =>
                  setMenuId(open ? id : null),
                interactionDisabled: exiting || layouting,
              },
              className: `${related ? "" : "dim"}${litNode ? " rt" : ""}${!routing && (item.id === hoverId || item.id === panelId || item.id === menuId) ? " hot" : ""}`,
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
                ...(item.kind === "course" || item.kind === "module"
                  ? ({
                      "--graph-node-min-height": `${NODE_SIZES[item.kind].height}px`,
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
      routing,
      lit,
      view,
      layouting,
      phone,
      onNodeHeight,
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
      const top = phone ? PHONE_ROOT_TOP : 30;
      void setViewport(
        {
          x: width / 2 - (root.x + 40 + root.w / 2) * zoom,
          y: top - (root.y + 30) * zoom,
          zoom,
        },
        { duration: animated && !reducedMotion ? 450 : 0 },
      );
    },
    [layout, model.rootId, setViewport, reducedMotion, phone],
  );
  const drawingBounds = useCallback(
    (ids: Set<string>) => {
      if (!layout) return null;
      const boxes = [...ids].flatMap((id) => {
        const placed = layout.nodes.get(id);
        return placed === undefined
          ? []
          : [
              {
                x: placed.x + 40,
                y: placed.y + 30,
                width: placed.w,
                height: placed.h,
              },
            ];
      });
      if (boxes.length === 0) return null;
      const left = Math.min(...boxes.map((box) => box.x));
      const top = Math.min(...boxes.map((box) => box.y));
      const right = Math.max(...boxes.map((box) => box.x + box.width));
      const bottom = Math.max(...boxes.map((box) => box.y + box.height));
      return { x: left, y: top, width: right - left, height: bottom - top };
    },
    [layout],
  );
  const fitOverview = useCallback(
    (animated: boolean) => {
      if (!phone || !box.current) return false;
      const bounds = drawingBounds(overviewNodes(model));
      if (bounds === null) return false;
      const panel = box.current.getBoundingClientRect();
      const viewport = getViewportForBounds(
        bounds,
        panel.width,
        panel.height,
        PHONE_FIT_MIN_ZOOM,
        1,
        0.06,
      );
      const root = layout?.nodes.get(model.rootId);
      const rootTop = root === undefined ? bounds.y : root.y + 30;
      void setViewport(
        {
          x: viewport.x,
          y: PHONE_ROOT_TOP - rootTop * viewport.zoom,
          zoom: viewport.zoom,
        },
        { duration: animated && !reducedMotion ? 450 : 0 },
      );
      return true;
    },
    [phone, model, drawingBounds, layout, setViewport, reducedMotion],
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
      if (!(phone && fitOverview(false))) centerRoot(false);
    }
  }, [layout, model.rootId, centerRoot, fitOverview, phone]);
  useEffect(() => {
    if (!phone || view === null || !box.current) return;
    // The rendered route sheet is measured, so its own stylesheet stays the only bound on its height.
    const timer = setTimeout(() => {
      const panel = box.current;
      if (!panel) return;
      const bounds = drawingBounds(lit?.nodes ?? new Set<string>());
      if (bounds === null) return;
      const stack =
        panel.parentElement?.querySelector<HTMLElement>(".route-stack");
      const sheet = stack?.getBoundingClientRect().height ?? 0;
      const visible = Math.max(
        160,
        panel.clientHeight - sheet - PHONE_ROOT_TOP - 8,
      );
      const fitted = getViewportForBounds(
        bounds,
        panel.clientWidth,
        visible,
        PHONE_FIT_MIN_ZOOM,
        1,
        0.06,
      );
      void setViewport(
        { ...fitted, y: fitted.y + PHONE_ROOT_TOP },
        { duration: reducedMotion ? 0 : 350 },
      );
    }, 320);
    return () => clearTimeout(timer);
  }, [phone, view, lit, drawingBounds, setViewport, reducedMotion]);
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
          attributionPosition={phone ? "top-right" : "bottom-right"}
          proOptions={{ hideAttribution: false }}
        />
      </div>
      <div className="graph-float-controls">
        <button
          type="button"
          aria-label={t("Recenter")}
          onClick={() => centerRoot(true)}
        >
          {RECENTER_ICON}
        </button>
        <button
          type="button"
          aria-label={t("Zoom in")}
          onClick={() => void zoomIn({ duration: reducedMotion ? 0 : 200 })}
        >
          +
        </button>
        <button
          type="button"
          aria-label={t("Zoom out")}
          onClick={() => void zoomOut({ duration: reducedMotion ? 0 : 200 })}
        >
          −
        </button>
      </div>
      <div className="route-stack">
        <RoutePanel view={summary} route={route} />
        <MemberPanel node={panelNode} onClose={() => setPanelId(null)} />
      </div>
    </div>
  );
}

/** Render the interactive prerequisite drawing of one graph report. */
export function PrerequisiteGraph({
  report,
  nodeStates,
  recenterRef,
  route,
  summary,
  graphLoading,
}: {
  report: PrerequisiteGraphReport;
  nodeStates: readonly GraphNodeState[];
  recenterRef: MutableRefObject<(() => void) | null>;
  route: MinimumRouteSession;
  summary: RouteSummary | null;
  graphLoading: boolean;
}) {
  return (
    <ReactFlowProvider>
      <GraphCanvas
        report={report}
        nodeStates={nodeStates}
        recenterRef={recenterRef}
        route={route}
        summary={summary}
        graphLoading={graphLoading}
      />
    </ReactFlowProvider>
  );
}
