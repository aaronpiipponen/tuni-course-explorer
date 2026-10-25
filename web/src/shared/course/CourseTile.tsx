/**
 * One compact official course tile for the prerequisite graph and the Structure of studies tab,
 * with a whole-tile menu trigger.
 */
import { useLayoutEffect, useRef, type ReactNode } from "react";
import type { CourseSummary } from "../../api/types";
import { useProfileSelector } from "../../state/useProfileSelector";
import { useWording } from "../useWording";
import { CourseMenu } from "./CourseMenu";
import { courseCredits, courseName } from "./presentation";
import { useCourseMenuTrigger } from "./useCourseMenuTrigger";
import { useMediaQuery } from "../useMediaQuery";
import { PHONE_CONTENT_QUERY } from "../viewport";

/** Render one compact official course tile with its whole-tile menu trigger. */
export function CourseTile({
  course,
  open,
  onOpenChange,
  onInteractionChange,
  onMenuOpen,
  tags,
  actions,
  className,
}: {
  course: CourseSummary;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onInteractionChange?: (active: boolean) => void;
  /** Called after the menu mounts, for a caller that moves its own surface. */
  onMenuOpen?: (tile: HTMLElement, menu: HTMLElement) => void;
  tags?: ReactNode;
  actions: ReactNode;
  className?: string;
}) {
  const language = useProfileSelector((state) => state.language).value;
  const { t } = useWording();
  const phone = useMediaQuery(PHONE_CONTENT_QUERY);
  const tileRef = useRef<HTMLDivElement>(null);
  const nameRef = useRef<HTMLElement>(null);
  // A one-line title spreads the spare card height over its three content gaps, so the code, name,
  // facts and completion row stay evenly spaced. A two-line title keeps the tighter fixed rhythm.
  useLayoutEffect(() => {
    const tile = tileRef.current;
    const name = nameRef.current;
    if (!tile || !name) return;
    const measure = () => {
      const lineHeight = Number.parseFloat(getComputedStyle(name).lineHeight);
      if (!Number.isFinite(lineHeight) || lineHeight <= 0) return;
      const lines = Math.max(
        1,
        Math.round(name.getBoundingClientRect().height / lineHeight),
      );
      tile.dataset.titleLines = String(lines);
    };
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(measure);
    observer.observe(name);
    return () => observer.disconnect();
  }, [course.group_id, language, phone]);
  const { tap, changeOpen } = useCourseMenuTrigger({
    open,
    onOpenChange,
    phone,
    getRevealTarget: (trigger) =>
      phone ? trigger.closest<HTMLElement>(".tile") : null,
    onMenuOpen,
  });
  return (
    <div ref={tileRef} className={`tile${className ? ` ${className}` : ""}`}>
      <CourseMenu
        course={course}
        open={open}
        onOpenChange={changeOpen}
        onInteractionChange={onInteractionChange}
      >
        <button
          className="tile-trigger"
          type="button"
          {...tap}
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
        <b className="tile-name">
          <span ref={nameRef}>{courseName(course, language)}</span>
        </b>
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
