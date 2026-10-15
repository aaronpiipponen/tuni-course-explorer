/** One compact official course tile shared by prerequisite graph and Structure. The whole tile opens its menu. */
import type { ReactNode } from "react";
import type { CourseSummary } from "../../api/types";
import { useProfileSelector } from "../../state/useProfileSelector";
import { useWording } from "../useWording";
import { CourseMenu } from "./CourseMenu";
import { courseCredits, courseName } from "./presentation";

export function CourseTile({
  course,
  open,
  onOpenChange,
  onInteractionChange,
  tags,
  actions,
  className,
}: {
  course: CourseSummary;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onInteractionChange?: (active: boolean) => void;
  tags?: ReactNode;
  actions: ReactNode;
  className?: string;
}) {
  const language = useProfileSelector((state) => state.language).value;
  const { t } = useWording();
  return (
    <div className={`tile${className ? ` ${className}` : ""}`}>
      <CourseMenu
        course={course}
        open={open}
        onOpenChange={onOpenChange}
        onInteractionChange={onInteractionChange}
      >
        <button
          className="tile-trigger"
          type="button"
          aria-label={t("{code} {name}", {
            code: course.code,
            name: courseName(course, language),
          })}
        />
      </CourseMenu>
      <div className="tile-head">
        <span className="tile-code">
          <span className="code">{course.code}</span>
          {tags}
        </span>
        <b className="tile-name">{courseName(course, language)}</b>
      </div>
      <div className="tile-facts">
        <span>{courseCredits(course, language)}</span>
        <span
          className={`course-activity ${course.is_active ? "active" : "inactive"}`}
        >
          <i aria-hidden="true" />
          {t(course.is_active ? "active" : "inactive")}
        </span>
      </div>
      <div className="tile-actions nodrag nopan nowheel">{actions}</div>
    </div>
  );
}
