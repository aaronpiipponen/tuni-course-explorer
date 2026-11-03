/**
 * One bounded persistent cache of discovery reports.
 *
 * The cache keeps four next-course reports and four recommendation reports for one serving dataset
 * identity. A report is stored only after a successful read, and the storage envelope is replaced on
 * a new report. The general in-memory read cache holds catalogue, summary, search, comparison and
 * graph reads.
 */
import type { NextCoursesReport, RecommendationsReport } from "../api/types";
import { ReadCache, type ReportCache } from "./readCache";

/** Storage key of the discovery report envelope. */
export const DISCOVERY_CACHE_STORAGE_KEY =
  "tuni-course-explorer/discovery-cache/1";

/** Envelope version. Another version clears the stored reports. */
const DISCOVERY_CACHE_VERSION = 1;

/** Reports retained for each discovery list. */
const DISCOVERY_CACHE_CAPACITY_PER_LIST = 4;

/** Largest serialized envelope the cache writes. */
const DISCOVERY_CACHE_MAX_BYTES = 2 * 1024 * 1024;

/** Age after which one stored report is discarded. */
const DISCOVERY_CACHE_TTL_MS = 30 * 24 * 60 * 60 * 1000;

type DiscoveryList = "next" | "recommended";
type DiscoveryReport = NextCoursesReport | RecommendationsReport;

type StoredEntry = readonly [string, DiscoveryReport, number];

type StoredEnvelope = {
  version: number;
  datasetIdentity: string;
  next: readonly StoredEntry[];
  recommended: readonly StoredEntry[];
};

function discoveryList(requestKey: string): DiscoveryList {
  const value: unknown = JSON.parse(requestKey);
  if (
    !Array.isArray(value) ||
    value.length !== 2 ||
    (value[0] !== "next" && value[0] !== "recommended")
  )
    throw new Error("the discovery cache key is not a discovery request");
  return value[0];
}

function isStoredEnvelope(value: unknown): value is StoredEnvelope {
  if (!value || typeof value !== "object") return false;
  const envelope = value as Record<string, unknown>;
  return (
    envelope.version === DISCOVERY_CACHE_VERSION &&
    typeof envelope.datasetIdentity === "string" &&
    Array.isArray(envelope.next) &&
    Array.isArray(envelope.recommended) &&
    envelope.next.every(isStoredEntry) &&
    envelope.recommended.every(isStoredEntry)
  );
}

function isStoredEntry(value: unknown): value is StoredEntry {
  return (
    Array.isArray(value) &&
    value.length === 3 &&
    typeof value[0] === "string" &&
    typeof value[1] === "object" &&
    value[1] !== null &&
    typeof value[2] === "number"
  );
}

function isQuotaError(error: unknown): boolean {
  return (
    typeof error === "object" &&
    error !== null &&
    "name" in error &&
    (error as { name?: unknown }).name === "QuotaExceededError"
  );
}

function serializedBytes(value: string): number {
  return new TextEncoder().encode(value).length;
}

/**
 * The two discovery lists of one serving dataset, with a persistent envelope behind them.
 *
 * A hit reads only memory. A miss publishes through `readCachedReport`, which calls `put` after the
 * response identity has been accepted. An envelope of another dataset identity, another version, an
 * invalid shape or an older entry is discarded before any report is published.
 */
export class DiscoveryReportCache implements ReportCache {
  private readonly next: ReadCache;
  private readonly recommended: ReadCache;
  private readonly savedAt = new Map<string, number>();
  private readonly storage: Storage | null;
  private readonly now: () => number;

  constructor(
    datasetIdentity: string,
    storage: Storage | null = null,
    now: () => number = Date.now,
  ) {
    this.next = new ReadCache(
      datasetIdentity,
      DISCOVERY_CACHE_CAPACITY_PER_LIST,
    );
    this.recommended = new ReadCache(
      datasetIdentity,
      DISCOVERY_CACHE_CAPACITY_PER_LIST,
    );
    this.storage = storage;
    this.now = now;
    this.hydrate();
  }

  getDatasetIdentity(): string {
    return this.next.getDatasetIdentity();
  }

  observeDatasetIdentity(datasetIdentity: string): void {
    if (datasetIdentity === this.getDatasetIdentity()) return;
    this.next.observeDatasetIdentity(datasetIdentity);
    this.recommended.observeDatasetIdentity(datasetIdentity);
    this.savedAt.clear();
    this.removeStorage();
  }

  get<T>(requestKey: string): T | undefined {
    const list = discoveryList(requestKey);
    const savedAt = this.savedAt.get(requestKey);
    if (
      savedAt !== undefined &&
      this.now() - savedAt > DISCOVERY_CACHE_TTL_MS
    ) {
      this.list(list).remove(requestKey);
      this.savedAt.delete(requestKey);
      return undefined;
    }
    return this.list(list).get<T>(requestKey);
  }

  put<T>(datasetIdentity: string, requestKey: string, value: T): void {
    this.observeDatasetIdentity(datasetIdentity);
    const report = value as DiscoveryReport;
    this.list(discoveryList(requestKey)).put(
      datasetIdentity,
      requestKey,
      report,
    );
    this.savedAt.set(requestKey, this.now());
    this.persist();
  }

  /** Remove every held report and the stored envelope. */
  clear(): void {
    this.next.clear();
    this.recommended.clear();
    this.savedAt.clear();
    this.removeStorage();
  }

  private list(list: DiscoveryList): ReadCache {
    return list === "next" ? this.next : this.recommended;
  }

  private hydrate(): void {
    if (!this.storage) return;
    const raw = this.storage.getItem(DISCOVERY_CACHE_STORAGE_KEY);
    if (raw === null) return;
    let value: unknown;
    try {
      value = JSON.parse(raw);
    } catch {
      this.removeStorage();
      return;
    }
    if (
      !isStoredEnvelope(value) ||
      value.datasetIdentity !== this.getDatasetIdentity()
    ) {
      this.removeStorage();
      return;
    }
    if (
      !this.insert("next", value.next) ||
      !this.insert("recommended", value.recommended)
    ) {
      this.clear();
    }
  }

  private insert(
    list: DiscoveryList,
    entries: readonly StoredEntry[],
  ): boolean {
    const now = this.now();
    for (const [requestKey, report, savedAt] of entries) {
      if (discoveryList(requestKey) !== list) return false;
      if (now - savedAt > DISCOVERY_CACHE_TTL_MS) continue;
      this.list(list).put(this.getDatasetIdentity(), requestKey, report);
      this.savedAt.set(requestKey, savedAt);
    }
    return true;
  }

  private persist(): void {
    if (!this.storage) return;
    let next = this.next.entriesSnapshot();
    let recommended = this.recommended.entriesSnapshot();
    const live = new Set(
      [...next, ...recommended].map(([requestKey]) => requestKey),
    );
    for (const requestKey of this.savedAt.keys()) {
      if (!live.has(requestKey)) this.savedAt.delete(requestKey);
    }
    const envelope = (): StoredEnvelope => ({
      version: DISCOVERY_CACHE_VERSION,
      datasetIdentity: this.getDatasetIdentity(),
      next: next.map(([requestKey, report]) => [
        requestKey,
        report as DiscoveryReport,
        this.savedAt.get(requestKey) ?? this.now(),
      ]),
      recommended: recommended.map(([requestKey, report]) => [
        requestKey,
        report as DiscoveryReport,
        this.savedAt.get(requestKey) ?? this.now(),
      ]),
    });
    let serialized = JSON.stringify(envelope());
    while (
      serializedBytes(serialized) > DISCOVERY_CACHE_MAX_BYTES &&
      (next.length > 0 || recommended.length > 0)
    ) {
      const target =
        next.length >= recommended.length ? this.next : this.recommended;
      this.evictOldest(target);
      next = this.next.entriesSnapshot();
      recommended = this.recommended.entriesSnapshot();
      serialized = JSON.stringify(envelope());
    }
    let attempts = 0;
    for (;;) {
      try {
        this.storage.setItem(DISCOVERY_CACHE_STORAGE_KEY, serialized);
        return;
      } catch (error) {
        if (!isQuotaError(error) || attempts > 0) {
          if (isQuotaError(error))
            this.storage.removeItem(DISCOVERY_CACHE_STORAGE_KEY);
          else throw error;
          return;
        }
        attempts += 1;
        const target =
          next.length >= recommended.length ? this.next : this.recommended;
        if (!this.evictOldest(target)) {
          this.storage.removeItem(DISCOVERY_CACHE_STORAGE_KEY);
          return;
        }
        next = this.next.entriesSnapshot();
        recommended = this.recommended.entriesSnapshot();
        serialized = JSON.stringify(envelope());
      }
    }
  }

  private evictOldest(list: ReadCache): boolean {
    const oldest = list.evictOldest();
    if (oldest === undefined) return false;
    this.savedAt.delete(oldest[0]);
    return true;
  }

  private removeStorage(): void {
    this.storage?.removeItem(DISCOVERY_CACHE_STORAGE_KEY);
  }
}
