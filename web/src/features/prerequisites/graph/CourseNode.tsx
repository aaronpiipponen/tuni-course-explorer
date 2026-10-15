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
  selectedOnly: boolean;
  timeout: boolean;
  interactionDisabled: boolean;
};
export function CourseNode({ data }: NodeProps & { data: GraphNodeData }) {
  const { store } = useProfileSelector((state) => state.activeTab);
  const { runAction, error } = useAction();
  const { language, t } = useWording();
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (data.interactionDisabled) setOpen(false);
  }, [data.interactionDisabled]);
  const course = data.course!;
  return (
    <div
      inert={data.interactionDisabled}
      className={`graph-course${data.root ? " root" : ""}${data.inferred ? " inferred" : ""}${data.active ? "" : " inactive"}${data.state?.completed_by_courses ? " done" : ""}${data.state?.is_excluded ? " excl" : ""}${data.selectedOnly ? " sel" : ""}`}
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
              className={data.state?.completed_by_courses ? "is-done" : ""}
              aria-pressed={data.state?.completed_by_courses ?? false}
              aria-label={t(
                data.state?.completed_by_courses
                  ? "Mark not completed"
                  : "Mark completed",
              )}
              onClick={() =>
                runAction(() => toggleCompleted(store, course.group_id))
              }
            >
              {t(
                data.state?.completed_by_courses
                  ? "Completed (course)"
                  : "Complete (course)",
              )}
            </button>
            <button
              type="button"
              className={data.state?.is_excluded ? "is-excl" : ""}
              aria-pressed={data.state?.is_excluded ?? false}
              onClick={() => data.onCourseExclude(course.group_id)}
            >
              {t(data.state?.is_excluded ? "Excluded" : "Exclude")}
            </button>
          </>
        }
      />
      {error && <ErrorNotice error={error} language={language} />}
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}
