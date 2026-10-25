/** Course list row whose single button opens the shared card menu. */
import { useState } from "react";
import type { CourseSummary } from "../../api/types";
import { useProfileSelector } from "../../state/useProfileSelector";
import { useWording } from "../useWording";
import { CourseMenu } from "./CourseMenu";
import { courseCredits, courseName } from "./presentation";
import { useCourseMenuTrigger } from "./useCourseMenuTrigger";
import { useMediaQuery } from "../useMediaQuery";
import { PHONE_CONTENT_QUERY } from "../viewport";

/** Render one course list row whose single button opens the shared course menu. */
export function CourseListRow({
  course,
  trailing,
  onInteractionChange,
  reveal = false,
  hideCredits = false,
  showMarkers = false,
}: {
  course: CourseSummary;
  trailing?: string;
  onInteractionChange?: (active: boolean) => void;
  /** Center the row before its menu opens, used by the Discover basis list and the route list. */
  reveal?: boolean;
  /** Omit the credits on a phone while keeping a caller-supplied trailing mark. */
  hideCredits?: boolean;
  /** Show the completion or selection mark and the activity mark. */
  showMarkers?: boolean;
}) {
  const language = useProfileSelector((state) => state.language).value;
  const { t } = useWording();
  const { value: completed } = useProfileSelector((state) =>
    state.completedCourseIds.includes(course.group_id),
  );
  const { value: selected } = useProfileSelector((state) =>
    state.selectedCourseIds.includes(course.group_id),
  );
  const phone = useMediaQuery(PHONE_CONTENT_QUERY);
  const [open, setOpen] = useState(false);
  const { tap, changeOpen } = useCourseMenuTrigger({
    open,
    onOpenChange: setOpen,
    phone,
    getRevealTarget: (trigger) => (reveal && phone ? trigger : null),
    getRevealContainer: (trigger) =>
      trigger.closest<HTMLElement>(".discover-basis-list"),
  });
  return (
    <CourseMenu
      course={course}
      open={open}
      onOpenChange={changeOpen}
      onInteractionChange={onInteractionChange}
    >
      <button
        type="button"
        className={`course-list-row${open ? " open" : ""}${showMarkers ? " has-markers" : ""}`}
        {...tap}
      >
        <span className="course-list-code">{course.code}</span>
        <span className="course-list-name">{courseName(course, language)}</span>
        {(!hideCredits || !phone || trailing !== undefined) && (
          <span className="course-list-credit">
            {!course.is_active && (
              <i className="course-list-inactive">{t("inactive")} · </i>
            )}
            {trailing ?? courseCredits(course, language)}
          </span>
        )}
        {showMarkers && (
          <span className="course-list-markers">
            {completed ? (
              <span className="course-badge completed">{t("completed")}</span>
            ) : selected ? (
              <span className="course-badge">{t("selected")}</span>
            ) : null}
            <span
              className={`course-activity ${course.is_active ? "active" : "inactive"}`}
            >
              <i aria-hidden="true" />
              {t(course.is_active ? "active" : "inactive")}
            </span>
          </span>
        )}
      </button>
    </CourseMenu>
  );
}
