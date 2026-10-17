/** Pane-lifetime hydration of summaries/reports required by placed additions. */
import { useEffect, useRef, useState } from "react";
import { ApiError } from "../../api/http";
import { readCourseSummaries } from "../../api/course-summaries";
import { readStudyStructure } from "../../api/study-structure";
import type {
  CourseSummary,
  StructureRule,
  StudyStructureReport,
} from "../../api/types";
import type { PlacedContent } from "./model";

type ExtraContent = {
  courses?: readonly CourseSummary[];
  reports?: Readonly<Record<string, StudyStructureReport>>;
};

type SettledUnavailable = {
  courseIds: readonly string[];
  moduleIds: readonly string[];
};

/**
 * Add the official courses a report already carries to the content map, so projecting the
 * report's default courses into the selection needs no second summary read.
 */
function collectReportCourses(
  report: StudyStructureReport,
  into: Map<string, CourseSummary>,
): void {
  const walk = (rule: StructureRule) => {
    if (rule.course) into.set(rule.course.group_id, rule.course);
    if (rule.module) walk(rule.module.rule);
    for (const child of rule.children) walk(child);
  };
  walk(report.root.rule);
}

/**
 * Hydrate the canonical summaries and official reports the placed identities need.
 *
 * With `allowUnrepresented`, an identity the catalogue does not answer for is recorded as
 * unavailable instead of failing the read: a course omitted from a successful summary response and
 * a structure report the route answers with 422. Recorded identities settle the request, so the
 * read finishes and a later pass does not ask again. Every other failure keeps its ordinary
 * behavior. The mode is part of the request identity.
 */
export function usePlacedContent(
  courseIds: readonly string[],
  moduleIds: readonly string[],
  allowUnrepresented = false,
): {
  content: PlacedContent;
  loading: boolean;
  error: Error | null;
  unavailableCourseIds: readonly string[];
  unavailableModuleIds: readonly string[];
  extend(extra: ExtraContent): PlacedContent;
} {
  const [content, setContent] = useState<PlacedContent>({
    reports: {},
    courses: new Map(),
  });
  const contentRef = useRef(content);
  const [error, setError] = useState<Error | null>(null);
  const [unavailable, setUnavailable] = useState<SettledUnavailable>({
    courseIds: [],
    moduleIds: [],
  });
  const courseKey = JSON.stringify(courseIds);
  const moduleKey = JSON.stringify(moduleIds);
  const missingCourses = courseIds.filter(
    (id) => !content.courses.has(id) && !unavailable.courseIds.includes(id),
  );
  const missingModules = moduleIds.filter(
    (id) => !content.reports[id] && !unavailable.moduleIds.includes(id),
  );
  const recordUnavailable = (settled: SettledUnavailable) =>
    setUnavailable((current) => ({
      courseIds: [...new Set([...current.courseIds, ...settled.courseIds])],
      moduleIds: [...new Set([...current.moduleIds, ...settled.moduleIds])],
    }));
  const extend = (extra: ExtraContent): PlacedContent => {
    const courses = new Map(contentRef.current.courses);
    extra.courses?.forEach((course) => courses.set(course.group_id, course));
    for (const report of Object.values(extra.reports ?? {}))
      collectReportCourses(report, courses);
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
    const jobs: Promise<ExtraContent & SettledUnavailable>[] = [];
    if (missingCourses.length)
      jobs.push(
        readCourseSummaries(missingCourses, controller.signal).then(
          (result) => {
            const found = new Set(
              result.results.map((course) => course.group_id),
            );
            const absent = missingCourses.filter((id) => !found.has(id));
            if (absent.length && !allowUnrepresented)
              throw new Error("Requested course summary is missing");
            return {
              courses: result.results,
              courseIds: absent,
              moduleIds: [],
            };
          },
        ),
      );
    for (const id of missingModules)
      jobs.push(
        readStudyStructure(id, controller.signal).then(
          (report) => ({
            reports: { [id]: report },
            courseIds: [],
            moduleIds: [],
          }),
          (caught: unknown) => {
            // This route answers 422 for an unknown root, no unique current version or no rule.
            if (
              allowUnrepresented &&
              caught instanceof ApiError &&
              caught.status === 422
            )
              return { courseIds: [], moduleIds: [id] };
            throw caught;
          },
        ),
      );
    Promise.all(jobs).then(
      (results) => {
        if (controller.signal.aborted) return;
        const merged: {
          courses: CourseSummary[];
          reports: Record<string, StudyStructureReport>;
        } = { courses: [], reports: {} };
        const settled: SettledUnavailable = { courseIds: [], moduleIds: [] };
        results.forEach((result) => {
          merged.courses.push(...(result.courses ?? []));
          Object.assign(merged.reports, result.reports);
          settled.courseIds = [...settled.courseIds, ...result.courseIds];
          settled.moduleIds = [...settled.moduleIds, ...result.moduleIds];
        });
        setError(null);
        extend(merged);
        recordUnavailable(settled);
      },
      (caught: unknown) => {
        if (!controller.signal.aborted)
          setError(
            caught instanceof Error ? caught : new Error(String(caught)),
          );
      },
    );
    return () => controller.abort();
    // Keys represent the exact missing request set. The mode decides how an absent identity is
    // answered, so it belongs to the same identity. Content changes when it completes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [courseKey, moduleKey, allowUnrepresented]);
  return {
    content,
    loading:
      (missingCourses.length > 0 || missingModules.length > 0) &&
      error === null,
    error,
    unavailableCourseIds: unavailable.courseIds,
    unavailableModuleIds: unavailable.moduleIds,
    extend,
  };
}
