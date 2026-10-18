/** Canonical course node with shared menu, official link, and shared completion state. */
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { useEffect, useState } from "react";
import { toggleCompleted } from "../../../state/course-actions";
import { useProfileSelector } from "../../../state/useProfileSelector";
import { useAction } from "../../../shared/useAction";
import { CourseTile } from "../../../shared/course/CourseTile";
import { ErrorNotice } from "../../../shared/ErrorNotice";
import { useWording } from "../../../shared/useWording";
import type { ModelNode } from "./model";

export type GraphNodeData = ModelNode & {
  onMembers: (id: string) => void;
  onCourseExclude: (id: string) => void;
  onNodeOpen: (id: string, open: boolean) => void;
  timeout: boolean;
  interactionDisabled: boolean;
};
export function CourseNode({ data }: NodeProps & { data: GraphNodeData }) {
  const course = data.course!;
  const { store, value: completed } = useProfileSelector((state) =>
    state.completedCourseIds.includes(course.group_id),
  );
  const { value: excluded } = useProfileSelector(
    (state) =>
      state.prerequisites.excludedCourseIds.includes(course.group_id) ||
      state.prerequisites.excludedNodeKeys.includes(data.actionKey),
  );
  const { value: selectedOnly } = useProfileSelector(
    (state) =>
      state.prerequisites.basis === "selected" &&
      state.selectedCourseIds.includes(course.group_id) &&
      !state.completedCourseIds.includes(course.group_id),
  );
  const { runAction, error } = useAction();
  const { language, t } = useWording();
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (data.interactionDisabled) setOpen(false);
  }, [data.interactionDisabled]);
  return (
    <div
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
              type="button"
              className={completed ? "is-done" : ""}
              aria-pressed={completed}
              aria-label={t(
                completed ? "Mark not completed" : "Mark completed",
              )}
              onClick={() =>
                runAction(() => toggleCompleted(store, course.group_id))
              }
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
      {error && <ErrorNotice error={error} language={language} />}
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}
