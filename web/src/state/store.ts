/**
 * One localStorage-backed live-profile envelope whose mutations re-read the stored value,
 * apply their change to it and write before publishing.
 */
import { initialBrowserState } from "./defaults";
import type {
  BrowserImport,
  BrowserProfileFile,
  BrowserState,
  BrowserStateFile,
  Profile,
  ProfileState,
} from "./types";
import { validateBrowserState, validateProfile } from "./validation";
import { parseSisuCapture } from "../features/structure/sisu";

export const BROWSER_STORAGE_KEY = "tuni-course-explorer";

export class BrowserStore {
  #storage: Storage;
  #snapshot: BrowserState;
  #listeners = new Set<() => void>();

  constructor(storage: Storage, snapshot: BrowserState) {
    this.#storage = storage;
    this.#snapshot = snapshot;
  }

  getSnapshot = (): BrowserState => this.#snapshot;

  subscribe = (listener: () => void): (() => void) => {
    this.#listeners.add(listener);
    return () => this.#listeners.delete(listener);
  };

  updateCurrent(update: (state: ProfileState) => ProfileState): void {
    this.#commit((latest) => {
      const current = latest.profiles[latest.currentProfileId];
      if (!current) throw new Error("Current browser profile is unavailable");
      const updated = update(current.state);
      if (updated === current.state) return latest;
      return {
        ...latest,
        profiles: {
          ...latest.profiles,
          [latest.currentProfileId]: { ...current, state: updated },
        },
      };
    });
  }

  switchProfile(id: string): void {
    this.#commit((latest) => {
      if (!latest.profiles[id])
        throw new Error("Browser profile is unavailable");
      if (id === latest.currentProfileId) return latest;
      return { ...latest, currentProfileId: id };
    });
  }

  saveAsProfile(name: string): void {
    this.#commit((latest) => {
      const current = latest.profiles[latest.currentProfileId];
      if (!current) throw new Error("Current browser profile is unavailable");
      return this.#withNewProfile(latest, name, current.state);
    });
  }

  deleteProfile(id: string): void {
    this.#commit((latest) => {
      if (!latest.profiles[id])
        throw new Error("Browser profile is unavailable");
      const profiles = { ...latest.profiles };
      delete profiles[id];
      const [first] = Object.keys(profiles);
      if (first === undefined)
        throw new Error("The last browser profile cannot be deleted");
      return {
        ...latest,
        currentProfileId:
          id === latest.currentProfileId ? first : latest.currentProfileId,
        profiles,
      };
    });
  }

  renameProfile(id: string, name: string): void {
    this.#commit((latest) => {
      const profile = latest.profiles[id];
      if (!profile) throw new Error("Browser profile is unavailable");
      const trimmed = name.trim();
      if (!trimmed) throw new Error("Profile name cannot be empty");
      if (profile.name === trimmed) return latest;
      if (
        Object.entries(latest.profiles).some(
          ([otherId, other]) => otherId !== id && other.name === trimmed,
        )
      )
        throw new Error("A profile with that name already exists");
      return {
        ...latest,
        profiles: { ...latest.profiles, [id]: { ...profile, name: trimmed } },
      };
    });
  }

  /**
   * Adopt the stored envelope as the live snapshot. Reading another tab's write and an
   * absent key both land here, and an equal value keeps the current snapshot references.
   */
  refreshFromStorage(): BrowserState {
    const latest = readBrowserState(this.#storage);
    if (JSON.stringify(latest) !== JSON.stringify(this.#snapshot)) {
      this.#snapshot = latest;
      this.#listeners.forEach((listener) => listener());
    }
    return this.#snapshot;
  }

  /** Return a profile file for one stored profile, read from the stored envelope. */
  exportProfile(id: string): BrowserProfileFile {
    const snapshot = this.refreshFromStorage();
    const profile = snapshot.profiles[id];
    if (!profile) throw new Error("Browser profile is unavailable");
    return {
      type: "tuni-course-explorer/profile/2",
      profile: structuredClone(profile),
    };
  }

  /** Return a whole-state file that holds the stored envelope text as it is. */
  exportState(): BrowserStateFile {
    return exportSavedBrowserData(this.#storage);
  }

  /** Add an imported profile as a new current profile. A duplicate or blank name is refused. */
  importProfile(profile: Profile): void {
    this.#commit((latest) =>
      this.#withNewProfile(latest, profile.name, profile.state),
    );
  }

  /** Replace every stored profile with one imported envelope and publish it. */
  restoreState(state: BrowserState): void {
    this.#write(state);
  }

  /** Replace every stored profile with the initial envelope and publish it. */
  resetSavedData(): void {
    this.#write(initialBrowserState());
  }

  #withNewProfile(
    latest: BrowserState,
    name: string,
    state: ProfileState,
  ): BrowserState {
    const trimmed = name.trim();
    if (!trimmed) throw new Error("Profile name cannot be empty");
    if (
      Object.values(latest.profiles).some((profile) => profile.name === trimmed)
    )
      throw new Error("A profile with that name already exists");
    const id = `profile-${crypto.getRandomValues(new Uint32Array(4)).join("-")}`;
    return {
      ...latest,
      currentProfileId: id,
      profiles: {
        ...latest.profiles,
        [id]: { name: trimmed, state: structuredClone(state) },
      },
    };
  }

  #commit(update: (latest: BrowserState) => BrowserState): void {
    const latest = readBrowserState(this.#storage);
    const next = update(latest);
    if (next === latest) {
      this.#adopt(latest);
      return;
    }
    this.#write(next);
  }

  #write(next: BrowserState): void {
    this.#storage.setItem(BROWSER_STORAGE_KEY, JSON.stringify(next));
    this.#snapshot = next;
    this.#listeners.forEach((listener) => listener());
  }

  #adopt(latest: BrowserState): void {
    if (JSON.stringify(latest) === JSON.stringify(this.#snapshot)) return;
    this.#snapshot = latest;
    this.#listeners.forEach((listener) => listener());
  }
}

function readBrowserState(storage: Storage): BrowserState {
  const raw = storage.getItem(BROWSER_STORAGE_KEY);
  if (raw === null) return initialBrowserState();
  let value: unknown;
  try {
    value = JSON.parse(raw);
  } catch {
    throw new Error("Saved browser state is invalid");
  }
  return validateBrowserState(value);
}

/** Build the first-visit envelope through the explicit reset writer. */
export function resetBrowserStore(storage: Storage): BrowserStore {
  const store = new BrowserStore(storage, initialBrowserState());
  store.resetSavedData();
  return store;
}

export function createBrowserStore(storage: Storage): BrowserStore {
  if (storage.getItem(BROWSER_STORAGE_KEY) === null)
    return resetBrowserStore(storage);
  return new BrowserStore(storage, readBrowserState(storage));
}

/** Wrap the stored envelope text unchanged, so unreadable data can leave the browser. */
export function exportSavedBrowserData(storage: Storage): BrowserStateFile {
  const data = storage.getItem(BROWSER_STORAGE_KEY);
  if (data === null) throw new Error("There is no saved data to export");
  return { type: "tuni-course-explorer/state/2", data };
}

/** Dispatch one imported file on its `type` field, validate its payload and parse a Sisu capture. */
export function parseBrowserImport(text: string): BrowserImport {
  let value: unknown;
  try {
    value = JSON.parse(text);
  } catch {
    throw new Error("Invalid import file");
  }
  if (!value || typeof value !== "object" || Array.isArray(value))
    throw new Error("Invalid import file");
  const file = value as Record<string, unknown>;
  if (file.type === "tuni-course-explorer/profile/2")
    return {
      type: "tuni-course-explorer/profile/2",
      profile: validateProfile(file.profile),
    };
  if (file.type === "tuni-course-explorer/state/2") {
    if (typeof file.data !== "string") throw new Error("Invalid import file");
    let data: unknown;
    try {
      data = JSON.parse(file.data);
    } catch {
      throw new Error("Invalid import file");
    }
    return {
      type: "tuni-course-explorer/state/2",
      state: validateBrowserState(data),
    };
  }
  if (file.type === "tuni-course-explorer/sisu/1")
    return parseSisuCapture(value);
  if (typeof file.type === "string") throw new Error("Unsupported file type");
  throw new Error("Invalid import file");
}
