/** Canonical course node with shared menu, official link, and shared completion state. */
import { Handle, Position, useReactFlow, type NodeProps } from "@xyflow/react";
import { useEffect, useRef, useState } from "react";
import { useProfileSelector } from "../../../state/useProfileSelector";
import { CourseTile } from "../../../shared/course/CourseTile";
import { useCourseCompletion } from "../../../shared/course/useCourseCompletion";
import { useWording } from "../../../shared/useWording";
import { useReducedMotion } from "../../../shared/useReducedMotion";
import type { ModelNode } from "./model";
import { useGraphNodeHeight } from "./usePhoneGraphSizes";

/** The common node payload of the prerequisite drawing. */
export type GraphNodeData = ModelNode & {
  onMembers: (id: string) => void;
  onCourseExclude: (id: string) => void;
  onNodeOpen: (id: string, open: boolean) => void;
  onNodeHeight: (id: string, height: number) => void;
  phone: boolean;
  timeout: boolean;
  interactionDisabled: boolean;
};
/** Render one canonical course node with its menu and completion state. */
export function CourseNode({ data }: NodeProps & { data: GraphNodeData }) {
  const course = data.course!;
  const { value: completed } = useProfileSelector((state) =>
    state.completedCourseIds.includes(course.group_id),
  );
  const { value: excluded } = useProfileSelector((state) =>
    state.prerequisites.excludedCourseIds.includes(course.group_id),
  );
  const { value: selectedOnly } = useProfileSelector(
    (state) =>
      state.prerequisites.basis === "selected" &&
      state.selectedCourseIds.includes(course.group_id) &&
      !state.completedCourseIds.includes(course.group_id),
  );
  const { t } = useWording();
  const reducedMotion = useReducedMotion();
  const { getViewport, setViewport } = useReactFlow();
  const [open, setOpen] = useState(false);
  const completeRef = useRef<HTMLButtonElement>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  useGraphNodeHeight(rootRef, data.phone, data.id, data.onNodeHeight);
  const completion = useCourseCompletion(course, () =>
    completeRef.current?.focus(),
  );
  useEffect(() => {
    if (data.interactionDisabled) setOpen(false);
  }, [data.interactionDisabled]);
  return (
    <div
      ref={rootRef}
      inert={data.interactionDisabled}
      className={`graph-course${data.root ? " root" : ""}${data.inferred ? " inferred" : ""}${data.active ? "" : " inactive"}${completed ? " done" : ""}${excluded ? " excl" : ""}${selectedOnly ? " sel" : ""}`}
    >
      <Handle type="target" position={Position.Top} />
      <CourseTile
        course={course}
        open={open}
        onOpenChange={(value) => {
          setOpen(value);
          data.onNodeOpen(data.id, value);
        }}
        onMenuOpen={(tile, menu) => {
          if (!data.phone) return;
          const node = tile.closest<HTMLElement>(".react-flow__node");
          const panel = tile.closest<HTMLElement>(".graph-panel");
          if (!node || !panel) return;
          const nodeRect = node.getBoundingClientRect();
          const panelRect = panel.getBoundingClientRect();
          const header =
            document.querySelector<HTMLElement>(".prereq-phone-head");
          const headerBottom = header
            ? header.getBoundingClientRect().bottom
            : panelRect.top;
          const menuTop = Math.min(
            menu.getBoundingClientRect().top,
            panelRect.bottom,
          );
          const available = Math.max(0, menuTop - headerBottom);
          const targetY =
            available >= nodeRect.height + 8
              ? headerBottom + (available - nodeRect.height) / 2
              : headerBottom + 8;
          const viewport = getViewport();
          setViewport(
            {
              x:
                viewport.x +
                panelRect.left +
                panelRect.width / 2 -
                (nodeRect.left + nodeRect.width / 2),
              y: viewport.y + targetY - nodeRect.top,
              zoom: viewport.zoom,
            },
            { duration: reducedMotion ? 0 : 300 },
          );
        }}
        tags={
          <>
            {data.inferred && (
              <i className="tile-tag inferred-tag">{t("inferred")}</i>
            )}
            {data.timeout && (
              <i className="tile-tag timeout-tag">{t("timeout")}</i>
            )}
          </>
        }
        actions={
          <>
            <button
              ref={completeRef}
              type="button"
              className={completed ? "is-done" : ""}
              aria-pressed={completed}
              aria-label={t(
                completed ? "Mark not completed" : "Mark completed",
              )}
              onClick={completion.toggle}
            >
              {t(completed ? "Completed (course)" : "Complete (course)")}
            </button>
            <button
              type="button"
              className={excluded ? "is-excl" : ""}
              aria-pressed={excluded}
              onClick={() => data.onCourseExclude(course.group_id)}
            >
              {t(excluded ? "Excluded" : "Exclude")}
            </button>
          </>
        }
      />
      {completion.dialog}
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}
