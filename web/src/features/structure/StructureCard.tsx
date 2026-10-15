/** Structure course tile with shared menu and browser-owned completion. */
import { useState } from "react";
import type { CourseSummary } from "../../api/types";
import { useProfileSelector } from "../../state/useProfileSelector";
import { toggleCompleted } from "../../state/course-actions";
import { useAction } from "../../shared/useAction";
import { ErrorNotice } from "../../shared/ErrorNotice";
import { useWording } from "../../shared/useWording";
import { CourseTile } from "../../shared/course/CourseTile";

export function StructureCard({
  course,
  completed,
  added,
}: {
  course: CourseSummary;
  completed: boolean;
  added: boolean;
}) {
  const { store } = useProfileSelector((state) => state.selectedCourseIds);
  const [open, setOpen] = useState(false);
  const { runAction, error } = useAction();
  const { language, t } = useWording();
  return (
    <>
      <CourseTile
        course={course}
        open={open}
        onOpenChange={setOpen}
        className={`structure-card${completed ? " done" : ""}${course.is_active ? "" : " inactive"}${added ? " added" : ""}`}
        actions={
          <button
            className={completed ? "is-done" : ""}
            type="button"
            aria-pressed={completed}
            aria-label={t(completed ? "Mark not completed" : "Mark completed")}
            onClick={() =>
              runAction(() => toggleCompleted(store, course.group_id))
            }
          >
            {t(completed ? "Completed (course)" : "Complete (course)")}
          </button>
        }
      />
      {error && <ErrorNotice error={error} language={language} />}
    </>
  );
}
