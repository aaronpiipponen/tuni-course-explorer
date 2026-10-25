/** Pane-lifetime hydration of summaries/reports required by placed additions. */
import { useEffect, useRef, useState } from "react";
import { DATASET_CHANGED_MESSAGE } from "../../app/cachedRead";
import { useReadCache } from "../../app/useReadCache";
import type {
  CourseSummary,
  StructureRule,
  StudyStructureReport,
} from "../../api/types";
import { readCachedCourseSummaries } from "../../shared/course/reads";
import type { PlacedContent } from "./model";
import { moduleVersionKey } from "./moduleVersions";
import { readCachedStudyStructures } from "./structureReads";

/**
 * Hydration inputs one operation supplies: the serving dataset identity, optional course summaries,
 * optional reports and the prospective selections those reports answer.
 */
export type ExtraContent = {
  datasetIdentity: string;
  courses?: readonly CourseSummary[];
  reports?: Readonly<Record<string, StudyStructureReport>>;
  /** The prospective selections those reports answer, required whenever reports are supplied. */
  moduleVersions?: Readonly<Record<string, string>>;
};

type SettledUnavailable = {
  courseIds: readonly string[];
  moduleIds: readonly string[];
};

type HydratedContent = {
  datasetIdentity: string;
  selectionKey: string;
  content: PlacedContent;
  unavailable: SettledUnavailable;
  selectionRequiredModuleIds: readonly string[];
};

function emptyHydration(
  datasetIdentity: string,
  selectionKey: string,
): HydratedContent {
  return {
    datasetIdentity,
    selectionKey,
    content: { reports: {}, courses: new Map() },
    unavailable: { courseIds: [], moduleIds: [] },
    selectionRequiredModuleIds: [],
  };
}

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
 * Summaries and structures read once through the shared cache owners. With `allowUnrepresented`, a
 * course a successful summary response omits and a root the structure response marks unavailable
 * are recorded as unavailable instead of failing the read, and a root that needs an explicit
 * version selection is recorded separately. Every other failure keeps its ordinary behavior. The
 * mode and the exact selection map are part of the request identity. A serving dataset or
 * selection identity change empties the hydrated view and reads the missing inputs once under the
 * discovered identity.
 */
export function usePlacedContent(
  courseIds: readonly string[],
  moduleIds: readonly string[],
  moduleVersions: Readonly<Record<string, string>>,
  allowUnrepresented = false,
): {
  content: PlacedContent;
  datasetIdentity: string;
  loading: boolean;
  error: Error | null;
  unavailableCourseIds: readonly string[];
  unavailableModuleIds: readonly string[];
  versionSelectionRequiredIds: readonly string[];
  extend(extra: ExtraContent): PlacedContent;
} {
  const cache = useReadCache();
  const observedIdentity = cache.getDatasetIdentity();
  const selectionKey = moduleVersionKey(moduleVersions);
  const [state, setState] = useState<HydratedContent>(() =>
    emptyHydration(observedIdentity, selectionKey),
  );
  const stateRef = useRef(state);
  const [error, setError] = useState<Error | null>(null);
  const rendered =
    state.datasetIdentity === observedIdentity &&
    state.selectionKey === selectionKey
      ? state
      : emptyHydration(observedIdentity, selectionKey);
  const courseKey = JSON.stringify(courseIds);
  const moduleKey = JSON.stringify(moduleIds);
  const missingCourses = courseIds.filter(
    (id) =>
      !rendered.content.courses.has(id) &&
      !rendered.unavailable.courseIds.includes(id),
  );
  const missingModules = moduleIds.filter(
    (id) =>
      !rendered.content.reports[id] &&
      !rendered.unavailable.moduleIds.includes(id) &&
      !rendered.selectionRequiredModuleIds.includes(id),
  );
  /**
   * Merge one operation's content into a prospective selection.
   *
   * Reports never cross selection keys: a different key starts from the same-dataset course
   * summaries alone, without the other key's reports or settled module lists. The merged result is
   * returned to the operation, and installed as live hydration only when it answers the live key.
   */
  const extend = (extra: ExtraContent): PlacedContent => {
    if (extra.datasetIdentity !== cache.getDatasetIdentity())
      throw new Error(DATASET_CHANGED_MESSAGE);
    const extraSelectionKey =
      extra.reports === undefined
        ? selectionKey
        : extra.moduleVersions === undefined
          ? (() => {
              throw new Error(
                "Prospective structure reports need their selections",
              );
            })()
          : moduleVersionKey(extra.moduleVersions);
    const current = stateRef.current;
    const sameDataset = current.datasetIdentity === extra.datasetIdentity;
    const sameSelection =
      sameDataset && current.selectionKey === extraSelectionKey;
    const base = sameDataset
      ? current
      : emptyHydration(extra.datasetIdentity, extraSelectionKey);
    const courses = new Map(base.content.courses);
    extra.courses?.forEach((course) => courses.set(course.group_id, course));
    for (const report of Object.values(extra.reports ?? {}))
      collectReportCourses(report, courses);
    const content: PlacedContent = {
      reports: {
        ...(sameSelection ? base.content.reports : {}),
        ...extra.reports,
      },
      courses,
    };
    const next: HydratedContent = {
      datasetIdentity: extra.datasetIdentity,
      selectionKey: extraSelectionKey,
      content,
      unavailable: {
        courseIds: base.unavailable.courseIds,
        moduleIds: sameSelection ? base.unavailable.moduleIds : [],
      },
      selectionRequiredModuleIds: sameSelection
        ? base.selectionRequiredModuleIds
        : [],
    };
    if (extraSelectionKey === selectionKey) {
      stateRef.current = next;
      setState(next);
    }
    return content;
  };
  const recordSettlement = (
    settled: SettledUnavailable,
    selectionRequiredIds: readonly string[],
  ) => {
    const current = stateRef.current;
    const next: HydratedContent = {
      ...current,
      unavailable: {
        courseIds: [
          ...new Set([...current.unavailable.courseIds, ...settled.courseIds]),
        ],
        moduleIds: [
          ...new Set([...current.unavailable.moduleIds, ...settled.moduleIds]),
        ],
      },
      selectionRequiredModuleIds: [
        ...new Set([
          ...current.selectionRequiredModuleIds,
          ...selectionRequiredIds,
        ]),
      ],
    };
    stateRef.current = next;
    setState(next);
  };
  useEffect(() => {
    if (
      stateRef.current.datasetIdentity !== observedIdentity ||
      stateRef.current.selectionKey !== selectionKey
    ) {
      const reset = emptyHydration(observedIdentity, selectionKey);
      stateRef.current = reset;
      setState(reset);
      setError(null);
    }
    const base = stateRef.current;
    const missingCourseIds = courseIds.filter(
      (id) =>
        !base.content.courses.has(id) &&
        !base.unavailable.courseIds.includes(id),
    );
    const missingModuleIds = moduleIds.filter(
      (id) =>
        !base.content.reports[id] &&
        !base.unavailable.moduleIds.includes(id) &&
        !base.selectionRequiredModuleIds.includes(id),
    );
    if (!missingCourseIds.length && !missingModuleIds.length) return;
    const controller = new AbortController();
    const jobs: Promise<{
      identity: string;
      courses?: readonly CourseSummary[];
      reports?: Readonly<Record<string, StudyStructureReport>>;
      courseIds: readonly string[];
      moduleIds: readonly string[];
      selectionRequiredIds: readonly string[];
    }>[] = [];
    if (missingCourseIds.length)
      jobs.push(
        readCachedCourseSummaries(
          cache,
          missingCourseIds,
          controller.signal,
        ).then((result) => {
          const found = new Set(
            result.results.map((course) => course.group_id),
          );
          const absent = missingCourseIds.filter((id) => !found.has(id));
          if (absent.length && !allowUnrepresented)
            throw new Error("Requested course summary is missing");
          return {
            identity: result.dataset_identity,
            courses: result.results,
            courseIds: absent,
            moduleIds: [],
            selectionRequiredIds: [],
          };
        }),
      );
    if (missingModuleIds.length)
      jobs.push(
        readCachedStudyStructures(
          cache,
          missingModuleIds,
          moduleVersions,
          allowUnrepresented,
          controller.signal,
        ).then((result) => ({
          identity: result.dataset_identity,
          reports: result.reports,
          courseIds: [],
          moduleIds: result.unavailable_root_group_ids,
          selectionRequiredIds: result.version_selection_required,
        })),
      );
    Promise.all(jobs).then(
      (results) => {
        if (controller.signal.aborted) return;
        const identities = new Set(results.map((result) => result.identity));
        if (identities.size > 1) {
          setError(new Error(DATASET_CHANGED_MESSAGE));
          return;
        }
        const [identity] = identities;
        const merged: {
          courses: CourseSummary[];
          reports: Record<string, StudyStructureReport>;
        } = { courses: [], reports: {} };
        const settled: SettledUnavailable = { courseIds: [], moduleIds: [] };
        const selectionRequiredIds: string[] = [];
        results.forEach((result) => {
          merged.courses.push(...(result.courses ?? []));
          Object.assign(merged.reports, result.reports);
          settled.courseIds = [...settled.courseIds, ...result.courseIds];
          settled.moduleIds = [...settled.moduleIds, ...result.moduleIds];
          selectionRequiredIds.push(...result.selectionRequiredIds);
        });
        setError(null);
        extend({
          datasetIdentity: identity,
          ...merged,
          moduleVersions,
        });
        recordSettlement(settled, selectionRequiredIds);
      },
      (caught: unknown) => {
        if (!controller.signal.aborted)
          setError(
            caught instanceof Error ? caught : new Error(String(caught)),
          );
      },
    );
    return () => controller.abort();
    // Keys represent the exact missing request set. The mode and selection decide how an absent
    // identity is answered, so they belong to the same identity. A discovered serving identity is a
    // new input.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    cache,
    courseKey,
    moduleKey,
    selectionKey,
    moduleVersions,
    allowUnrepresented,
    observedIdentity,
  ]);
  return {
    content: rendered.content,
    datasetIdentity: rendered.datasetIdentity,
    loading:
      (missingCourses.length > 0 || missingModules.length > 0) &&
      error === null,
    error,
    unavailableCourseIds: rendered.unavailable.courseIds,
    unavailableModuleIds: rendered.unavailable.moduleIds,
    versionSelectionRequiredIds: rendered.selectionRequiredModuleIds,
    extend,
  };
}
