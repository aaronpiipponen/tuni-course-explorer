/** One bounded in-memory cache of successful reads, scoped to the serving dataset identity. */
/** Maximum number of successful reports retained by one read cache. */
export const READ_CACHE_CAPACITY = 8;

/** Dataset-scoped least-recently-used cache for successful browser reads. */
export class ReadCache {
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
