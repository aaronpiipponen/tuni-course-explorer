/** One pending catalogue fetch per read cache, removed when it settles. */
import { readCachedReport } from "../../app/cachedRead";
import type { ReadCache } from "../../app/readCache";
import { readCatalogue } from "../../api/catalogue";
import type { CatalogueReport } from "../../api/types";

const CATALOGUE_KEY = JSON.stringify(["catalogue"]);

type PendingCatalogue = {
  identity: string;
  promise: Promise<CatalogueReport>;
};

const pending = new WeakMap<ReadCache, PendingCatalogue>();

/**
 * Return the minimal official catalogue, reading it once and sharing one in-flight fetch.
 *
 * The cache holds the settled catalogue. A fetch in progress is shared by every caller of the same
 * cache generation, so simultaneous initial consumers send one request, and the fetch finishes even
 * when one consumer stops waiting. A cache that observed another dataset identity never reuses the
 * pending entry.
 */
export function readCachedCatalogue(
  cache: ReadCache,
): Promise<CatalogueReport> {
  const hit = cache.get<CatalogueReport>(CATALOGUE_KEY);
  if (hit !== undefined) return Promise.resolve(hit);
  const identity = cache.getDatasetIdentity();
  const existing = pending.get(cache);
  if (existing && existing.identity === identity) return existing.promise;
  const controller = new AbortController();
  const promise = readCachedReport(
    cache,
    CATALOGUE_KEY,
    readCatalogue,
    controller.signal,
  );
  const entry: PendingCatalogue = { identity, promise };
  pending.set(cache, entry);
  const settle = () => {
    if (pending.get(cache) === entry) pending.delete(cache);
  };
  promise.then(settle, settle);
  return promise;
}
