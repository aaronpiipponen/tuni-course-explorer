/** Shared substring box, activity control, loading/error states and selectable course rows. */
import { useEffect, useRef } from "react";
import type { CatalogueCourse } from "../../api/types";
import { ActivitySwitch } from "../ActivitySwitch";
import { ErrorNotice } from "../ErrorNotice";
import { LookupSkeletons } from "../LookupSkeletons";
import { LookupVirtualList } from "../LookupVirtualList";
import { useWording } from "../useWording";
import type { CoursePick } from "./CourseCard";
import { courseCredits, courseName } from "./presentation";
import { useCourseLookup } from "./useCourseLookup";
import { useTapGuardCapture } from "./useTapGuard";

/** One course row's canonical identity. */
const courseKey = (course: CatalogueCourse) => course.group_id;

/** Render one course substring lookup with its activity control, states and selectable rows. */
export function CourseLookupBox({
  open,
  query,
  onQuery,
  activeOnly,
  onActiveOnly,
  pick,
}: {
  open: boolean;
  query: string;
  onQuery: (q: string) => void;
  activeOnly: boolean;
  onActiveOnly: (a: boolean) => void;
  pick: (course: CatalogueCourse) => CoursePick;
}) {
  const input = useRef<HTMLInputElement>(null);
  const tap = useTapGuardCapture<HTMLDivElement>();
  const { language, t } = useWording();
  const { report, loading, error } = useCourseLookup(open, query, activeOnly);
  useEffect(() => {
    if (open) input.current?.focus();
  }, [open]);
  const courses = report?.results ?? [];
  return (
    <>
      <div className="course-lookup-controls">
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <circle cx="11" cy="11" r="7" />
          <path d="m20 20-3.5-3.5" />
        </svg>
        <input
          ref={input}
          value={query}
          onChange={(event) => onQuery(event.target.value)}
          placeholder={t("Filter courses by name or code")}
          aria-label={t("Filter courses by name or code")}
        />
      </div>
      <div className="course-lookup-filters">
        <ActivitySwitch activeOnly={activeOnly} onChange={onActiveOnly} />
      </div>
      {error && <ErrorNotice error={error} language={language} />}
      {loading && <LookupSkeletons label={t("Loading courses")} />}
      {!loading &&
        !error &&
        (query.trim() ? (
          courses.length ? (
            <LookupVirtualList
              items={courses}
              getItemKey={courseKey}
              className="course-lookup-list"
              resetKey={`${open}-${query}-${language}-${activeOnly}`}
              inputRef={input}
              containerProps={tap}
              renderRow={(course) => {
                const chosen = pick(course);
                return (
                  <button
                    className="prow"
                    type="button"
                    aria-label={chosen.ariaLabel}
                    onClick={chosen.onPick}
                  >
                    <span className="code">{course.code}</span>
                    <span className="pn">{courseName(course, language)}</span>
                    <span className="cr">
                      {courseCredits(course, language)}
                    </span>
                    <span className="add">{chosen.text}</span>
                  </button>
                );
              }}
            />
          ) : (
            report && (
              <p className="course-lookup-empty">
                {t("No courses match this search.")}
              </p>
            )
          )
        ) : (
          <p className="course-lookup-empty">
            {t("Type to search courses by name or code.")}
          </p>
        ))}
    </>
  );
}
