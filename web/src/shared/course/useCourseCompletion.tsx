/** One shared course completion interaction for the course menu and the graph Complete button. */
import { useState, type ReactNode } from "react";
import type { CourseSummary } from "../../api/types";
import { revealUnplacedStudies } from "../../features/structure/reveal";
import { toggleCompleted } from "../../state/course-actions";
import { useProfileSelector } from "../../state/useProfileSelector";
import { ConfirmDialog } from "../ConfirmDialog";
import { ErrorNotice } from "../ErrorNotice";
import { useAction } from "../useAction";
import { useNotice } from "../useNotice";
import { useWording } from "../useWording";
import { uiText } from "../wording";
import { courseName } from "./presentation";

/** Which completion changes one surface reports in a bottom notice. */
export type CompletionNotices = "always" | "added-only";

/** Return the completion toggle, its confirmation state and its dialog for one course. */
export function useCourseCompletion(
  course: CourseSummary,
  returnFocus: () => void,
  notices: CompletionNotices = "always",
): { toggle(): void; open: boolean; dialog: ReactNode } {
  const { store, value: selected } = useProfileSelector((state) =>
    state.selectedCourseIds.includes(course.group_id),
  );
  const { value: completed } = useProfileSelector((state) =>
    state.completedCourseIds.includes(course.group_id),
  );
  const { runAction, error } = useAction();
  const { language, t } = useWording();
  const notice = useNotice();
  const [asking, setAsking] = useState(false);

  const announceAdded = () =>
    notice.show(
      (messageLanguage) =>
        uiText(
          messageLanguage,
          "Added {code} to Unplaced studies and marked it completed",
          { code: course.code },
        ),
      undefined,
      {
        link: {
          label: (messageLanguage) =>
            uiText(messageLanguage, "Unplaced studies (notice)"),
          run: revealUnplacedStudies,
        },
      },
    );

  const toggle = () => {
    if (!selected) {
      setAsking(true);
      return;
    }
    const removing = completed;
    runAction(() => {
      toggleCompleted(store, course.group_id);
      if (notices !== "always") return;
      if (removing)
        notice.show((messageLanguage) =>
          uiText(messageLanguage, "Removed completion of course {code}", {
            code: course.code,
          }),
        );
      else
        notice.show((messageLanguage) =>
          uiText(messageLanguage, "Marked course {code} as completed", {
            code: course.code,
          }),
        );
    });
  };
  const confirm = () => {
    if (completed) {
      setAsking(false);
      return;
    }
    runAction(() => {
      toggleCompleted(store, course.group_id);
      setAsking(false);
      announceAdded();
    });
  };
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
