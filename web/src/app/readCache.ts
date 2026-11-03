/** One bounded in-memory cache of successful reads, scoped to the serving dataset identity. */
/** Maximum number of successful reports retained by one read cache. */
export const READ_CACHE_CAPACITY = 8;

/** The dataset-bound cache surface one successful read publishes through. */
export interface ReportCache {
  /** Return the serving dataset identity the held values belong to. */
  getDatasetIdentity(): string;

  /** Record one serving dataset identity, clearing every held value of another identity. */
  observeDatasetIdentity(datasetIdentity: string): void;

  /** Return one successful value and mark it as the most recently used entry. */
  get<T>(requestKey: string): T | undefined;

  /** Store one successful value under its dataset identity. */
  put<T>(datasetIdentity: string, requestKey: string, value: T): void;
}

/** Dataset-scoped least-recently-used cache for successful browser reads. */
export class ReadCache implements ReportCache {
  private readonly capacity: number;
  private datasetIdentity: string;
  private readonly entries = new Map<string, unknown>();

  /**
   * Create one empty cache holding at most `capacity` successful values for `datasetIdentity`.
   */
  constructor(datasetIdentity: string, capacity: number) {
    this.datasetIdentity = datasetIdentity;
    this.capacity = capacity;
  }

  /** Return the serving dataset identity the held values belong to. */
  getDatasetIdentity(): string {
    return this.datasetIdentity;
  }

  /** Return one successful value and mark it as the most recently used entry. */
  get<T>(requestKey: string): T | undefined {
    const value = this.entries.get(requestKey);
    if (value === undefined) return undefined;
    this.entries.delete(requestKey);
    this.entries.set(requestKey, value);
    return value as T;
  }

  /** Return every held entry in least-recently-used to most-recently-used order. */
  entriesSnapshot(): readonly (readonly [string, unknown])[] {
    return [...this.entries.entries()];
  }

  /** Remove one held value without changing the observed dataset identity. */
  remove(requestKey: string): void {
    this.entries.delete(requestKey);
  }

  /** Remove every held value without changing the observed dataset identity. */
  clear(): void {
    this.entries.clear();
  }

  /** Remove the least recently used entry and return it, or `undefined` for an empty cache. */
  evictOldest(): readonly [string, unknown] | undefined {
    const oldest = this.entries.keys().next().value;
    if (oldest === undefined) return undefined;
    const value = this.entries.get(oldest);
    this.entries.delete(oldest);
    return value === undefined ? undefined : [oldest, value];
  }

  /**
   * Store one successful value under its dataset identity.
   *
   * Another dataset identity clears every held value first, because values keyed by the old
   * identity must never answer a read for the new one.
   */
  put<T>(datasetIdentity: string, requestKey: string, value: T): void {
    this.observeDatasetIdentity(datasetIdentity);
    this.entries.delete(requestKey);
    this.entries.set(requestKey, value);
    while (this.entries.size > this.capacity) {
      const oldest = this.entries.keys().next().value;
      if (oldest === undefined) break;
      this.entries.delete(oldest);
    }
  }

  /**
   * Record one serving dataset identity, clearing every held value of another identity.
   *
   * An empty successful read observes the identity this way without retaining a value.
   */
  observeDatasetIdentity(datasetIdentity: string): void {
    if (datasetIdentity !== this.datasetIdentity) {
      this.entries.clear();
      this.datasetIdentity = datasetIdentity;
    }
  }
}
