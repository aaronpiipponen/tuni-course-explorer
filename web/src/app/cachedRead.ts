/**
 * Publish one dataset-bound successful read through the shared cache.
 *
 * Cancellation stops a read before publication. A cache that already discovered another serving
 * dataset rejects a response of the previous dataset, so an older outstanding request never rolls
 * the cache backwards. Otherwise the response identity becomes the cache's observed identity.
 */
import type { ReadCache } from "./readCache";

/** Error text used when a read crosses serving dataset identities. */
export const DATASET_CHANGED_MESSAGE =
  "The serving dataset changed during the read";

/** Return the abort reason as an Error, or a generic cancellation error for another reason. */
export function cancellationError(signal: AbortSignal): Error {
  return signal.reason instanceof Error
    ? signal.reason
    : new Error("The read was cancelled");
}

/**
 * Accept one operation's response identity, or throw when the response or cache identity differs.
 *
 * The operation captured its identity before its read, so either comparison failing means another
 * dataset replaced the one the operation started against.
 */
export function acceptOperationIdentity(
  cache: ReadCache,
  operationIdentity: string,
  responseIdentity: string,
): void {
  if (
    responseIdentity !== operationIdentity ||
    cache.getDatasetIdentity() !== operationIdentity
  )
    throw new Error(DATASET_CHANGED_MESSAGE);
}

/** Accept one read response after checking cancellation and dataset identity. */
export function acceptDatasetRead(
  cache: ReadCache,
  startingIdentity: string,
  responseIdentity: string,
  signal: AbortSignal,
): void {
  if (signal.aborted) throw cancellationError(signal);
  if (
    cache.getDatasetIdentity() !== startingIdentity &&
    responseIdentity !== cache.getDatasetIdentity()
  )
    throw new Error(DATASET_CHANGED_MESSAGE);
  cache.observeDatasetIdentity(responseIdentity);
}

/**
 * Return a cached successful report, or read it once and cache it under its own identity.
 *
 * The request key names one exact request inside the cache's single dataset partition. Errors
 * propagate unchanged, and nothing is cached for them.
 */
export async function readCachedReport<T extends { dataset_identity: string }>(
  cache: ReadCache,
  key: string,
  read: (signal: AbortSignal) => Promise<T>,
  signal: AbortSignal,
): Promise<T> {
  const hit = cache.get<T>(key);
  if (hit !== undefined) return hit;
  const startingIdentity = cache.getDatasetIdentity();
  const report = await read(signal);
  acceptDatasetRead(cache, startingIdentity, report.dataset_identity, signal);
  cache.put(report.dataset_identity, key, report);
  return report;
}
