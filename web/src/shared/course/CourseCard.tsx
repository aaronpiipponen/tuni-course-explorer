/** Shared official course fact card and its single interactive trigger/menu composition. */
import { memo, useState } from "react";
import type { CourseSummary, SearchMethod } from "../../api/types";
import { useWebFeatures } from "../../app/useWebFeatures";
import { useProfileSelector } from "../../state/useProfileSelector";
import { useWording } from "../useWording";
import { searchMethodLabel } from "../wording";
import { courseCredits, courseName } from "./presentation";
import { CourseMenu } from "./CourseMenu";

export type CoursePick = {
  onPick: () => void;
  text: string;
  ariaLabel: string;
};

function CourseCardView({
  course,
  matchSources,
  tag,
  onInteractionChange,
  isFirst,
  isLast,
  pick,
}: {
  course: CourseSummary;
  matchSources?: readonly SearchMethod[];
  tag?: string;
  onInteractionChange?: (active: boolean) => void;
  isFirst?: boolean;
  isLast?: boolean;
  pick?: CoursePick;
}) {
  const { language, t } = useWording();
  const { embeddings_enabled } = useWebFeatures();
  const { value: completed } = useProfileSelector((state) =>
    state.completedCourseIds.includes(course.group_id),
  );
  const { value: selected } = useProfileSelector((state) =>
    state.selectedCourseIds.includes(course.group_id),
  );
  const { value: slot } = useProfileSelector((state) =>
    state.compare.slots.indexOf(course.group_id),
  );
  const [menuOpen, setMenuOpen] = useState(false);
  const parts = [
    t("{code} {name}", {
      code: course.code,
      name: courseName(course, language),
    }),
    t(course.is_active ? "active" : "inactive"),
    t(completed ? "completed" : selected ? "selected" : "not selected"),
  ];
  if (embeddings_enabled && slot >= 0)
    parts.push(t("comparison slot {slot}", { slot: slot === 0 ? "A" : "B" }));
  const trigger = (
    <button
      className={`course-card${matchSources?.length ? " has-course-sources" : ""}`}
      type="button"
      onClick={pick?.onPick}
      aria-label={pick ? pick.ariaLabel : parts.join("; ")}
    >
      <span className="course-comparison">
        {embeddings_enabled && slot >= 0 && (
          <span className="course-badge comparison-badge">
            ⇄ {slot === 0 ? "A" : "B"}
          </span>
        )}
      </span>
      <span className="course-code">{course.code}</span>
      <span className="course-name course-name-cell">
        {courseName(course, language)}
      </span>
      <span className="course-meta course-meta-cell">
        <span className="course-credit">{courseCredits(course, language)}</span>
        <span
          className={`course-activity ${course.is_active ? "active" : "inactive"}`}
        >
          <i aria-hidden="true" />
          {t(course.is_active ? "active" : "inactive")}
        </span>
        {tag && <span className="course-badge">{tag}</span>}
      </span>
      <span className="course-state-cell">
        {(completed || selected) && (
          <span className={`course-badge${completed ? " completed" : ""}`}>
            {t(completed ? "completed" : "selected")}
          </span>
        )}
      </span>
      <span className="course-source-cell">
        {!pick && matchSources?.length ? (
          <span className="course-sources">
            {matchSources.map((source, index) => (
              <span
                className={index === 0 ? "primary" : ""}
                key={`${source}-${index}`}
              >
                {searchMethodLabel(source, language)}
              </span>
            ))}
          </span>
        ) : null}
      </span>
      {pick && <span className="course-pick-text">{pick.text}</span>}
    </button>
  );
  return (
    <article
      data-course-id={course.group_id}
      className={`course-card-shell course-row${course.is_active ? "" : " inactive"}${menuOpen ? " open" : ""}`}
      data-first={isFirst || undefined}
      data-last={isLast || undefined}
    >
      {pick ? (
        trigger
      ) : (
        <CourseMenu
          course={course}
          open={menuOpen}
          onOpenChange={setMenuOpen}
          onInteractionChange={onInteractionChange}
        >
          {trigger}
        </CourseMenu>
      )}
    </article>
  );
}

export const CourseCard = memo(CourseCardView);
