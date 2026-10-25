/**
 * Dataset- and selection-bound structure reads over the memory cache, the persistent structure
 * store and one batch official read.
 *
 * Every successful per-root report is cached under its own root and exact selection key, and
 * network responses persist their roots under the response dataset identity. A network response of
 * another dataset identity never mixes roots of the previous identity into the result. A root that
 * is unavailable or still needs an explicit version selection settles this operation only and is
 * never cached as a successful report. `readProspectiveStructure` is the one prospective read of a
 * programme or module operation, and it answers from supplied content only when that content
 * matches the operation's dataset, selection and requested roots.
 */
import {
  DATASET_CHANGED_MESSAGE,
  acceptDatasetRead,
  acceptOperationIdentity,
  cancellationError,
} from "../../app/cachedRead";
import type { ReadCache } from "../../app/readCache";
import { readStudyStructures } from "../../api/study-structure";
import type { StudyStructureReport } from "../../api/types";
import { moduleVersionKey, structureRootGroupIds } from "./moduleVersions";
import type { PlacedContent } from "./model";
import type { StructureState } from "./state";
import type { ExtraContent } from "./usePlacedContent";
import {
  readPersistedStructures,
  writePersistedStructures,
} from "./structureStorage";

/** One structure read's dataset identity, reports and unresolved roots. */
export type CachedStructureRead = {
  dataset_identity: string;
  reports: Readonly<Record<string, StudyStructureReport>>;
  unavailable_root_group_ids: readonly string[];
  version_selection_required: readonly string[];
};

function rootKey(rootGroupId: string, selectionKey: string): string {
  return JSON.stringify(["study-structure", rootGroupId, selectionKey]);
}

/**
 * Return every requested root over one memory lookup, one persistent lookup and one batch read.
 *
 * Duplicate identities are read once. Unavailable and selection-required roots settle only this
 * operation and are never cached or persisted as successful structures. An empty request reads
 * nothing.
 */
export async function readCachedStudyStructures(
  cache: ReadCache,
  rootGroupIds: readonly string[],
  moduleVersions: Readonly<Record<string, string>>,
  allowUnavailable: boolean,
  signal: AbortSignal,
): Promise<CachedStructureRead> {
  const requested = [...new Set(rootGroupIds)];
  const selectionKey = moduleVersionKey(moduleVersions);
  const startingIdentity = cache.getDatasetIdentity();
  if (!requested.length)
    return {
      dataset_identity: startingIdentity,
      reports: {},
      unavailable_root_group_ids: [],
      version_selection_required: [],
    };

  const reports: Record<string, StudyStructureReport> = {};
  const remaining: string[] = [];
  for (const rootGroupId of requested) {
    const hit = cache.get<StudyStructureReport>(
      rootKey(rootGroupId, selectionKey),
    );
    if (hit === undefined) {
      remaining.push(rootGroupId);
      continue;
    }
    reports[rootGroupId] = hit;
  }

  if (remaining.length) {
    const persisted = await readPersistedStructures(
      startingIdentity,
      remaining,
      selectionKey,
    );
    // Publication is guarded before any persisted value is installed, so a read that a newer
    // dataset identity overtook cannot roll the cache backwards.
    acceptDatasetRead(cache, startingIdentity, startingIdentity, signal);
    for (const rootGroupId of [...remaining]) {
      const report = persisted[rootGroupId];
      if (report === undefined) continue;
      reports[rootGroupId] = report;
      cache.put(startingIdentity, rootKey(rootGroupId, selectionKey), report);
      remaining.splice(remaining.indexOf(rootGroupId), 1);
    }
  }

  if (!remaining.length) {
    acceptDatasetRead(cache, startingIdentity, startingIdentity, signal);
    return {
      dataset_identity: startingIdentity,
      reports,
      unavailable_root_group_ids: [],
      version_selection_required: [],
    };
  }

  const response = await readStudyStructures(
    remaining,
    moduleVersions,
    allowUnavailable,
    signal,
  );
  const responseIdentity = response.dataset_identity;
  acceptDatasetRead(cache, startingIdentity, responseIdentity, signal);
  // The cache observes the response identity, so the next explicit read starts under it.
  if (responseIdentity !== startingIdentity && Object.keys(reports).length)
    throw new Error(DATASET_CHANGED_MESSAGE);
  const returned: Record<string, StudyStructureReport> = {};
  for (const root of response.roots) {
    returned[root.module.group_id] = {
      academic_year_start: response.academic_year_start,
      root,
    };
  }
  for (const [rootGroupId, report] of Object.entries(returned)) {
    reports[rootGroupId] = report;
    cache.put(responseIdentity, rootKey(rootGroupId, selectionKey), report);
  }
  await writePersistedStructures(responseIdentity, returned, selectionKey);
  if (signal.aborted) throw cancellationError(signal);
  return {
    dataset_identity: responseIdentity,
    reports,
    unavailable_root_group_ids: response.unavailable_root_group_ids,
    version_selection_required: response.version_selection_required,
  };
}

/**
 * Read the reports one programme or module operation needs under its prospective selection.
 *
 * Supplied content answers only when its dataset identity, its selection identity and every
 * requested root match, so a root that already holds another nested version is read again. A batch
 * read accepts the operation identity before it is used, and an unavailable or selection-required
 * candidate raises `Programme is unavailable`.
 */
export async function readProspectiveStructure({
  cache,
  content,
  contentDatasetIdentity,
  contentSelectionKey,
  extend,
  state,
  groupId,
  moduleVersions,
  operationDatasetIdentity,
  signal,
}: {
  cache: ReadCache;
  content: PlacedContent;
  contentDatasetIdentity: string;
  contentSelectionKey: string;
  extend(extra: ExtraContent): PlacedContent;
  state: StructureState;
  groupId: string;
  moduleVersions: Readonly<Record<string, string>>;
  operationDatasetIdentity: string;
  signal: AbortSignal;
}): Promise<{ content: PlacedContent; report: StudyStructureReport }> {
  const requested = structureRootGroupIds(state, groupId);
  if (
    contentDatasetIdentity === cache.getDatasetIdentity() &&
    contentSelectionKey === moduleVersionKey(moduleVersions) &&
    requested.every((rootGroupId) => content.reports[rootGroupId] !== undefined)
  )
    return { content, report: content.reports[groupId] };
  const response = await readCachedStudyStructures(
    cache,
    requested,
    moduleVersions,
    false,
    signal,
  );
  if (signal.aborted) throw cancellationError(signal);
  acceptOperationIdentity(
    cache,
    operationDatasetIdentity,
    response.dataset_identity,
  );
  const report = response.reports[groupId];
  if (
    response.version_selection_required.includes(groupId) ||
    report === undefined
  )
    throw new Error("Programme is unavailable");
  return {
    content: extend({
      datasetIdentity: response.dataset_identity,
      reports: response.reports,
      moduleVersions,
    }),
    report,
  };
}
