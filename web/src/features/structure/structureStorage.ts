/**
 * Persistent derived store of successful official structure reports.
 *
 * The store holds only pure per-root structure reports, keyed by serving dataset identity, canonical
 * root identity and the exact selection identity that produced them. Every operation prunes entries
 * of other dataset identities in the same transaction, so the store never serves another generation.
 * Storage failures reject.
 */
import type { StudyStructureReport } from "../../api/types";

const DATABASE_NAME = "tuni-course-explorer-structures";
const DATABASE_VERSION = 2;
const STORE_NAME = "reports";

function openDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DATABASE_NAME, DATABASE_VERSION);
    request.onupgradeneeded = () => {
      // A store keyed by dataset and root alone cannot answer another selection, so the upgrade
      // discards the stored reports. Only this derived store is dropped, so profiles and every
      // other stored value are kept.
      if (request.result.objectStoreNames.contains(STORE_NAME))
        request.result.deleteObjectStore(STORE_NAME);
      request.result.createObjectStore(STORE_NAME);
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () =>
      reject(
        request.error ?? new Error("The structure store could not be opened"),
      );
    request.onblocked = () =>
      reject(new Error("The structure store is blocked by another connection"));
  });
}

function completion(transaction: IDBTransaction): Promise<void> {
  return new Promise((resolve, reject) => {
    transaction.oncomplete = () => resolve();
    transaction.onerror = () =>
      reject(
        transaction.error ??
          new Error("The structure store transaction failed"),
      );
    transaction.onabort = () =>
      reject(
        transaction.error ??
          new Error("The structure store transaction was aborted"),
      );
  });
}

function pruneOtherIdentities(
  store: IDBObjectStore,
  datasetIdentity: string,
): void {
  const cursorRequest = store.openKeyCursor();
  cursorRequest.onsuccess = () => {
    const cursor = cursorRequest.result;
    if (!cursor) return;
    const key = cursor.key;
    if (!Array.isArray(key) || key[0] !== datasetIdentity)
      store.delete(cursor.primaryKey);
    cursor.continue();
  };
}

async function withDatabase<T>(
  operation: (database: IDBDatabase) => Promise<T>,
): Promise<T> {
  const database = await openDatabase();
  try {
    return await operation(database);
  } finally {
    database.close();
  }
}

/** Return the stored report of every requested root for this dataset and selection identity. */
export function readPersistedStructures(
  datasetIdentity: string,
  rootGroupIds: readonly string[],
  selectionKey: string,
): Promise<Readonly<Record<string, StudyStructureReport>>> {
  return withDatabase((database) => {
    const transaction = database.transaction(STORE_NAME, "readwrite");
    const store = transaction.objectStore(STORE_NAME);
    pruneOtherIdentities(store, datasetIdentity);
    const reports: Record<string, StudyStructureReport> = {};
    for (const rootGroupId of new Set(rootGroupIds)) {
      const request = store.get([datasetIdentity, rootGroupId, selectionKey]);
      request.onsuccess = () => {
        if (request.result !== undefined)
          reports[rootGroupId] = request.result as StudyStructureReport;
      };
    }
    return completion(transaction).then(() => reports);
  });
}

/** Store the supplied reports under one dataset and selection identity, dropping other datasets. */
export function writePersistedStructures(
  datasetIdentity: string,
  reports: Readonly<Record<string, StudyStructureReport>>,
  selectionKey: string,
): Promise<void> {
  return withDatabase((database) => {
    const transaction = database.transaction(STORE_NAME, "readwrite");
    const store = transaction.objectStore(STORE_NAME);
    pruneOtherIdentities(store, datasetIdentity);
    for (const [rootGroupId, report] of Object.entries(reports))
      store.put(report, [datasetIdentity, rootGroupId, selectionKey]);
    return completion(transaction);
  });
}
