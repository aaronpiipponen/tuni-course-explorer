/** One shared course completion interaction for the course menu and the graph Complete button. */
import { useState, type ReactNode } from "react";
import type { CourseSummary } from "../../api/types";
import { toggleCompleted } from "../../state/course-actions";
import { useProfileSelector } from "../../state/useProfileSelector";
import { ConfirmDialog } from "../ConfirmDialog";
import { ErrorNotice } from "../ErrorNotice";
import { useAction } from "../useAction";
import { useWording } from "../useWording";
import { courseName } from "./presentation";

/** Return the completion toggle, its confirmation state and its dialog for one course. */
export function useCourseCompletion(
  course: CourseSummary,
  returnFocus: () => void,
): { toggle(): void; open: boolean; dialog: ReactNode } {
  const { store, value: selected } = useProfileSelector((state) =>
    state.selectedCourseIds.includes(course.group_id),
  );
  const { value: completed } = useProfileSelector((state) =>
    state.completedCourseIds.includes(course.group_id),
  );
  const { runAction, error } = useAction();
  const { language, t } = useWording();
  const [asking, setAsking] = useState(false);

  const toggle = () => {
    if (selected) runAction(() => toggleCompleted(store, course.group_id));
    else setAsking(true);
  };
  const confirm = () =>
    runAction(() => {
      if (!completed) toggleCompleted(store, course.group_id);
      setAsking(false);
    });
  const cancel = () => setAsking(false);

  const dialog = (
    <>
      <ConfirmDialog
        open={asking}
        title={t("Mark completed?")}
        description={t(
          "Add {name} to Unplaced studies and mark it completed?",
          { name: `${course.code} ${courseName(course, language)}` },
        )}
        confirmLabel={t("Add and complete")}
        error={error}
        onCancel={cancel}
        onConfirm={confirm}
        returnFocus={returnFocus}
      />
      {!asking && error && <ErrorNotice error={error} language={language} />}
    </>
  );

  return { toggle, open: asking, dialog };
}
