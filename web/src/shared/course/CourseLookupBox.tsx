/** Shared substring box, activity control, loading/error states and selectable course rows. */
import { useEffect, useRef } from "react";
import type { CourseSummary } from "../../api/types";
import { ActivitySwitch } from "../ActivitySwitch";
import { ErrorNotice } from "../ErrorNotice";
import { LookupSkeletons } from "../LookupSkeletons";
import { useWording } from "../useWording";
import { CourseCard, type CoursePick } from "./CourseCard";
import { useCourseLookup } from "./useCourseLookup";

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
  pick: (course: CourseSummary) => CoursePick;
}) {
  const input = useRef<HTMLInputElement>(null);
  const { language, t } = useWording();
  const { report, loading, error } = useCourseLookup(open, query, activeOnly);
  useEffect(() => {
    if (open) input.current?.focus();
  }, [open]);
  const courses = report?.results ?? [];
  return (
    <>
      <div className="course-lookup-controls">
        <input
          ref={input}
          value={query}
          onChange={(event) => onQuery(event.target.value)}
          placeholder={t("Filter courses by name or code")}
          aria-label={t("Filter courses by name or code")}
        />
        <ActivitySwitch activeOnly={activeOnly} onChange={onActiveOnly} />
      </div>
      {error && <ErrorNotice error={error} language={language} />}
      {loading && <LookupSkeletons label={t("Loading courses")} />}
      {!loading &&
        !error &&
        (query.trim() ? (
          courses.length ? (
            <div className="list course-lookup-list">
              {courses.map((course, index) => (
                <CourseCard
                  key={course.group_id}
                  course={course}
                  isFirst={index === 0}
                  isLast={index === courses.length - 1}
                  pick={pick(course)}
                />
              ))}
            </div>
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
