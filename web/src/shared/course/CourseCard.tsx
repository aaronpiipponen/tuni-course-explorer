/** Shared official course fact card and its single interactive trigger/menu composition. */
import { memo, useState } from "react";
import type { ComponentPropsWithoutRef, ReactElement } from "react";
import type { CourseSummary, SearchMethod } from "../../api/types";
import { useWebFeatures } from "../../app/useWebFeatures";
import { useProfileSelector } from "../../state/useProfileSelector";
import { useWording } from "../useWording";
import { searchMethodLabel } from "../wording";
import { courseCredits, courseName } from "./presentation";
import { CourseMenu } from "./CourseMenu";
import { useCourseMenuTrigger } from "./useCourseMenuTrigger";
import { useMediaQuery } from "../useMediaQuery";
import { PHONE_CONTENT_QUERY } from "../viewport";

/** One pick action a lookup row offers: its callback, its label and its accessible name. */
export type CoursePick = {
  onPick: () => void;
  text: string;
  ariaLabel: string;
};

/** Props one caller supplies to the element that opens its course menu. */
export type CourseCardTriggerProps = Pick<
  ComponentPropsWithoutRef<"button">,
  | "className"
  | "type"
  | "onClick"
  | "onPointerDown"
  | "onPointerMove"
  | "onPointerCancel"
  | "aria-label"
  | "children"
>;

type CourseCardViewProps = {
  course: CourseSummary;
  matchSources?: readonly SearchMethod[];
  tag?: string;
  onInteractionChange?: (active: boolean) => void;
  isFirst?: boolean;
  isLast?: boolean;
  /** One extra class on the card button for a caller that rearranges its grid. */
  cardClassName?: string;
  /** Renders the menu trigger as the Discover result row's own motion button. */
  renderTrigger?: (props: CourseCardTriggerProps) => ReactElement;
};

function CourseCardView({
  course,
  matchSources,
  tag,
  onInteractionChange,
  isFirst,
  isLast,
  cardClassName,
  renderTrigger,
}: CourseCardViewProps) {
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
  const phone = useMediaQuery(PHONE_CONTENT_QUERY);
  const { tap, changeOpen } = useCourseMenuTrigger({
    open: menuOpen,
    onOpenChange: setMenuOpen,
    phone,
    getRevealTarget: (trigger) =>
      phone ? trigger.closest<HTMLElement>(".course-card-shell") : null,
  });
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
  const triggerProps: CourseCardTriggerProps = {
    className: `course-card${matchSources?.length ? " has-course-sources" : ""}${cardClassName ? ` ${cardClassName}` : ""}`,
    type: "button",
    ...tap,
    "aria-label": parts.join("; "),
    children: (
      <>
        <span className="course-comparison">
          {embeddings_enabled && slot >= 0 && (
            <span className="course-badge comparison-badge">
              ⇄ {slot === 0 ? "A" : "B"}
            </span>
          )}
        </span>
        <span className="course-code">
          <span className="course-code-text">{course.code}</span>
          {phone && tag && <span className="course-badge">{tag}</span>}
        </span>
        <span className="course-name course-name-cell">
          {courseName(course, language)}
        </span>
        <span className="course-meta course-meta-cell">
          <span className="course-credit">
            {courseCredits(course, language)}
          </span>
          <span
            className={`course-activity ${course.is_active ? "active" : "inactive"}`}
          >
            <i aria-hidden="true" />
            {t(course.is_active ? "active" : "inactive")}
          </span>
          {tag && !phone && <span className="course-badge">{tag}</span>}
        </span>
        <span className="course-state-cell">
          {(completed || selected) && (
            <span className={`course-badge${completed ? " completed" : ""}`}>
              {t(completed ? "completed" : "selected")}
            </span>
          )}
        </span>
        <span className="course-source-cell">
          {matchSources?.length ? (
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
      </>
    ),
  };
  const trigger = renderTrigger ? (
    renderTrigger(triggerProps)
  ) : (
    <button {...triggerProps} />
  );
  return (
    <article
      data-course-id={course.group_id}
      className={`course-card-shell course-row${course.is_active ? "" : " inactive"}${menuOpen ? " open" : ""}`}
      data-first={isFirst || undefined}
      data-last={isLast || undefined}
    >
      <CourseMenu
        course={course}
        open={menuOpen}
        onOpenChange={changeOpen}
        onInteractionChange={onInteractionChange}
      >
        {trigger}
      </CourseMenu>
    </article>
  );
}

/** Render one official course fact card with its menu trigger. */
export const CourseCard = memo(CourseCardView);
