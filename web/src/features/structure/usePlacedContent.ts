/** Pane-lifetime hydration of summaries/reports required by placed additions. */
import { useEffect, useRef, useState } from "react";
import { readCourseSummaries } from "../../api/course-summaries";
import { readStudyStructure } from "../../api/study-structure";
import type { CourseSummary, StudyStructureReport } from "../../api/types";
import type { PlacedContent } from "./model";

type ExtraContent = {
  courses?: readonly CourseSummary[];
  reports?: Readonly<Record<string, StudyStructureReport>>;
};

export function usePlacedContent(
  courseIds: readonly string[],
  moduleIds: readonly string[],
): {
  content: PlacedContent;
  loading: boolean;
  error: Error | null;
  extend(extra: ExtraContent): PlacedContent;
} {
  const [content, setContent] = useState<PlacedContent>({
    reports: {},
    courses: new Map(),
  });
  const contentRef = useRef(content);
  const [error, setError] = useState<Error | null>(null);
  const courseKey = JSON.stringify(courseIds);
  const moduleKey = JSON.stringify(moduleIds);
  const missingCourses = courseIds.filter((id) => !content.courses.has(id));
  const missingModules = moduleIds.filter((id) => !content.reports[id]);
  const extend = (extra: ExtraContent): PlacedContent => {
    const courses = new Map(contentRef.current.courses);
    extra.courses?.forEach((course) => courses.set(course.group_id, course));
    const merged: PlacedContent = {
      reports: { ...contentRef.current.reports, ...extra.reports },
      courses,
    };
    contentRef.current = merged;
    setContent(merged);
    return merged;
  };
  useEffect(() => {
    if (!missingCourses.length && !missingModules.length) return;
    const controller = new AbortController();
    const jobs: Promise<ExtraContent>[] = [];
    if (missingCourses.length)
      jobs.push(
        readCourseSummaries(missingCourses, controller.signal).then(
          (result) => {
            const found = new Set(
              result.results.map((course) => course.group_id),
            );
            if (missingCourses.some((id) => !found.has(id)))
              throw new Error("Requested course summary is missing");
            return { courses: result.results };
          },
        ),
      );
    for (const id of missingModules)
      jobs.push(
        readStudyStructure(id, controller.signal).then((report) => ({
          reports: { [id]: report },
        })),
      );
    Promise.all(jobs).then(
      (results) => {
        if (controller.signal.aborted) return;
        const merged: {
          courses: CourseSummary[];
          reports: Record<string, StudyStructureReport>;
        } = { courses: [], reports: {} };
        results.forEach((result) => {
          merged.courses?.push(...(result.courses ?? []));
          Object.assign(merged.reports, result.reports);
        });
        setError(null);
        extend(merged);
      },
      (caught: unknown) => {
        if (!controller.signal.aborted)
          setError(
            caught instanceof Error ? caught : new Error(String(caught)),
          );
      },
    );
    return () => controller.abort();
    // Keys represent the exact missing request set. Content changes when it completes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [courseKey, moduleKey]);
  return {
    content,
    loading:
      (missingCourses.length > 0 || missingModules.length > 0) &&
      error === null,
    error,
    extend,
  };
}
