/** Course list row whose single button opens the shared card menu. */
import { useState } from "react";
import type { CourseSummary } from "../../api/types";
import { useProfileSelector } from "../../state/useProfileSelector";
import { useWording } from "../useWording";
import { CourseMenu } from "./CourseMenu";
import { courseCredits, courseName } from "./presentation";

export function CourseListRow({
  course,
  trailing,
  onInteractionChange,
}: {
  course: CourseSummary;
  trailing?: string;
  onInteractionChange?: (active: boolean) => void;
}) {
  const language = useProfileSelector((state) => state.language).value;
  const { t } = useWording();
  const [open, setOpen] = useState(false);
  return (
    <CourseMenu
      course={course}
      open={open}
      onOpenChange={setOpen}
      onInteractionChange={onInteractionChange}
    >
      <button type="button" className={`course-list-row${open ? " open" : ""}`}>
        <span className="course-list-code">{course.code}</span>
        <span className="course-list-name">{courseName(course, language)}</span>
        <span className="course-list-credit">
          {!course.is_active && (
            <i className="course-list-inactive">{t("inactive")} · </i>
          )}
          {trailing ?? courseCredits(course, language)}
        </span>
      </button>
    </CourseMenu>
  );
}
