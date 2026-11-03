/** ELK-laid-out React Flow canvas for every node and edge in the drawing report. */
import {
  useCallback,
  useEffect,
  useLayoutEffect,
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
import { useMediaQuery } from "../../../shared/useMediaQuery";
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
/** One phone sheet fold, shared by its rectangle and the content it crossfades. */
const SHEET_FOLD_MS = 340;
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
  // A touch pointer never leaves a node, so it must not own a resting hover light.
  const canHover = useMediaQuery("(hover: hover)");
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
  const stackRef = useRef<HTMLDivElement>(null);
  // The phone sheet changes from the bottom strip to the inset sheet in one layout, so the
  // change animates the sheet's own rectangle instead of a scale that would squash its contents.
  const sheetRect = useRef<DOMRect | null>(null);
  const compactRect = useRef<DOMRect | null>(null);
  const previousExpanded = useRef(route.expanded);
  const sheetAnimation = useRef<Animation | null>(null);
  // A fold started by a control holds its rectangle until that control commits the new layout,
  // so the open content stays laid out and is clipped by the shrinking sheet instead of snapping.
  const heldSheet = useRef(false);
  const contentAnimation = useRef<Animation | null>(null);
  // The open content keeps its place through the fold and fades only as the sheet reaches its end.
  const startContentFade = useCallback((element: HTMLElement) => {
    contentAnimation.current?.cancel();
    contentAnimation.current =
      element.querySelector<HTMLElement>(".route-panel")?.animate(
        [
          { opacity: 1, offset: 0 },
          { opacity: 1, offset: 0.8, easing: "ease-in" },
          { opacity: 0, offset: 1 },
        ],
        { duration: SHEET_FOLD_MS, easing: "linear", fill: "forwards" },
      ) ?? null;
  }, []);
  const settleSheet = useCallback((element: HTMLElement) => {
    element.style.top = "";
    element.style.left = "";
    element.style.right = "";
    element.style.bottom = "";
    element.style.width = "";
    element.style.height = "";
    element.style.overflow = "";
    element.style.transform = "";
  }, []);
  /** Release the held rectangle and bring back content a fold faded out. */
  const releaseSheet = useCallback(
    (element: HTMLElement) => {
      settleSheet(element);
      const faded = contentAnimation.current;
      if (faded === null) return;
      contentAnimation.current = null;
      faded.cancel();
      // Only a sheet that stays on screen brings its compact content back.
      if (element.querySelector(".route-panel.open") === null) return;
      element
        .querySelector<HTMLElement>(".route-panel")
        ?.animate([{ opacity: 0 }, { opacity: 1 }], {
          duration: 120,
          easing: "ease-out",
        });
    },
    [settleSheet],
  );
  /** Animate the sheet's own rectangle and resolve when it settles or is replaced. */
  const runSheetMotion = useCallback(
    (
      element: HTMLElement,
      from: DOMRect,
      to: { top: number; left: number; width: number; height: number },
      settle: boolean,
    ) => {
      sheetAnimation.current?.cancel();
      // The inline rectangle is the target, so releasing the animation keeps the folded box.
      // The keyframes below carry the motion from the old rectangle.
      const style = element.style;
      style.top = `${to.top}px`;
      style.left = `${to.left}px`;
      style.right = "auto";
      style.bottom = "auto";
      style.width = `${to.width}px`;
      style.height = `${to.height}px`;
      style.overflow = "hidden";
      style.transform = "none";
      const animation = element.animate(
        [
          {
            top: `${from.top}px`,
            left: `${from.left}px`,
            width: `${from.width}px`,
            height: `${from.height}px`,
            right: "auto",
            bottom: "auto",
            transform: "none",
          },
          {
            top: `${to.top}px`,
            left: `${to.left}px`,
            width: `${to.width}px`,
            height: `${to.height}px`,
            right: "auto",
            bottom: "auto",
            transform: "none",
          },
        ],
        { duration: SHEET_FOLD_MS, easing: "cubic-bezier(0.22, 0.8, 0.2, 1)" },
      );
      sheetAnimation.current = animation;
      return animation.finished
        .then(() => {
          if (sheetAnimation.current !== animation) return;
          sheetAnimation.current = null;
          if (settle) settleSheet(element);
        })
        .catch(() => undefined);
    },
    [settleSheet],
  );
  useLayoutEffect(() => {
    const element = stackRef.current;
    if (!element) return;
    const next = element.getBoundingClientRect();
    const previous = sheetRect.current;
    const wasExpanded = previousExpanded.current;
    previousExpanded.current = route.expanded;
    sheetRect.current = next;
    if (!phone) return;
    if (heldSheet.current) {
      // The open layout still paints the folded content, so keep the folded rectangle.
      if (element.querySelector(".route-panel.expanded") !== null) return;
      heldSheet.current = false;
      releaseSheet(element);
      return;
    }
    if (reducedMotion || previous === null || wasExpanded === route.expanded)
      return;
    void runSheetMotion(element, previous, next, true);
  });
  useEffect(() => {
    const element = stackRef.current;
    if (!element || !phone) return;
    // The compact strip settles after the panel's own open animation, so its size is tracked
    // rather than read on a render that may run before the sheet is painted at full height.
    const observer = new ResizeObserver(() => {
      if (heldSheet.current || sheetAnimation.current !== null) return;
      const rect = element.getBoundingClientRect();
      sheetRect.current = rect;
      if (
        rect.height > 0 &&
        !route.expanded &&
        element.querySelector(".route-panel.open") !== null
      )
        compactRect.current = rect;
    });
    observer.observe(element);
    // A fold ends when the open layout that kept its content painted is gone, which is a DOM
    // change of the panel rather than a render of the canvas.
    const classes = new MutationObserver(() => {
      if (!heldSheet.current) return;
      if (element.querySelector(".route-panel.expanded") !== null) return;
      heldSheet.current = false;
      releaseSheet(element);
    });
    classes.observe(element, {
      attributes: true,
      attributeFilter: ["class"],
      subtree: true,
    });
    return () => {
      observer.disconnect();
      classes.disconnect();
    };
  }, [phone, route.expanded, releaseSheet, settleSheet]);
  /**
   * Fold the open phone sheet onto its compact strip so the caller commits the collapsed layout.
   */
  const sheetCollapse = useCallback(async () => {
    const element = stackRef.current;
    const target = compactRect.current;
    if (!phone || reducedMotion || !element || target === null) return;
    const from = element.getBoundingClientRect();
    if (Math.abs(from.height - target.height) < 2) return;
    heldSheet.current = true;
    startContentFade(element);
    await runSheetMotion(element, from, target, false);
  }, [phone, reducedMotion, runSheetMotion, startContentFade]);
  /** Fold the open phone sheet away entirely, and let the caller drop the route it shows. */
  const sheetExit = useCallback(async () => {
    const element = stackRef.current;
    if (!phone || reducedMotion || !element) return;
    const from = element.getBoundingClientRect();
    if (from.height < 2) return;
    heldSheet.current = true;
    startContentFade(element);
    // The leaving sheet folds to the same strip a collapse folds to, so the rows travel the
    // same distance at the same speed.
    const target = compactRect.current;
    await runSheetMotion(
      element,
      from,
      target ?? {
        top: from.top + from.height,
        left: from.left,
        width: from.width,
        height: 0,
      },
      false,
    );
  }, [phone, reducedMotion, runSheetMotion, startContentFade]);
  // A card action can remove the node under an open menu or panel, or the new structure can
  // replace it, so a highlight that names a node the model no longer has is dropped.
  useEffect(() => {
    const ids = new Set(model.nodes.map((node) => node.id));
    if (menuId !== null && !ids.has(menuId)) setMenuId(null);
    if (panelId !== null && !ids.has(panelId)) setPanelId(null);
    if (hoverId !== null && !ids.has(hoverId)) setHoverId(null);
  }, [model, menuId, panelId, hoverId]);
  // A structure change makes a card menu's action stale even when the card stays drawn, so an
  // open menu and its chain highlight close with that change.
  useEffect(() => {
    setMenuId(null);
    setPanelId(null);
    setHoverId(null);
  }, [report, route.result]);
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
              // React Flow re-adopts the controlled nodes by identity, since every frame
              // recreates them.
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
                onNodeOpen: (id: string, open: boolean) => {
                  setMenuId(open ? id : null);
                  // The menu itself lights the chain. A rest hover would outlive it after a touch.
                  if (open) setHoverId(null);
                },
                interactionDisabled: exiting || layouting || graphLoading,
              },
              className: `${related ? "" : "dim"}${litNode ? " rt" : ""}${!routing && (item.id === hoverId || item.id === panelId || item.id === menuId) ? " hot" : ""}`,
              style: {
                opacity:
                  opacity *
                  (related ? 1 : 0.28) *
                  (item.kind === "course" && item.active === false ? 0.6 : 1),
                pointerEvents:
                  exiting || layouting || graphLoading ? "none" : "auto",
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
      graphLoading,
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
    if (!layout || centeredRoot.current === model.rootId) return;
    // The first graph takes its place at once. A root change glides the viewport with the graph.
    const first = centeredRoot.current === null;
    centeredRoot.current = model.rootId;
    if (phone && fitOverview(!first)) return;
    centerRoot(!first);
  }, [layout, model.rootId, centerRoot, fitOverview, phone]);
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
          onNodeMouseEnter={(_, node) => {
            if (canHover) setHoverId(node.id);
          }}
          onNodeMouseLeave={() => setHoverId(null)}
          onPaneClick={() => setPanelId(null)}
          proOptions={{ hideAttribution: true }}
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
      <div className="route-stack" ref={stackRef}>
        <RoutePanel
          view={summary}
          route={route}
          sheetCollapse={phone ? sheetCollapse : undefined}
          sheetExit={phone ? sheetExit : undefined}
        />
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
