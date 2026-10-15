/** One localStorage-backed live-profile envelope with atomic publish-after-write updates. */
import { initialBrowserState, initialProfileState } from "./defaults";
import type { PrerequisitesState } from "../features/prerequisites/state";
import { initialPrerequisitesState } from "../features/prerequisites/state";
import type { BrowserState, ProfileState } from "./types";

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
    const currentId = this.#snapshot.currentProfileId;
    const current = this.#snapshot.profiles[currentId];
    if (!current) throw new Error("Current browser profile is unavailable");
    const updated = update(current.state);
    if (updated === current.state) return;
    const next: BrowserState = {
      ...this.#snapshot,
      profiles: {
        ...this.#snapshot.profiles,
        [currentId]: { ...current, state: updated },
      },
    };
    this.#commit(next);
  }

  switchProfile(id: string): void {
    if (!this.#snapshot.profiles[id])
      throw new Error("Browser profile is unavailable");
    if (id === this.#snapshot.currentProfileId) return;
    this.#commit({ ...this.#snapshot, currentProfileId: id });
  }

  saveAsProfile(name: string): void {
    const trimmed = name.trim();
    if (!trimmed) throw new Error("Profile name cannot be empty");
    const currentId = this.#snapshot.currentProfileId;
    const current = this.#snapshot.profiles[currentId];
    if (!current) throw new Error("Current browser profile is unavailable");
    if (Object.values(this.#snapshot.profiles).some((p) => p.name === trimmed))
      throw new Error("A profile with that name already exists");
    const id = `profile-${crypto.getRandomValues(new Uint32Array(4)).join("-")}`;
    const profiles = {
      ...this.#snapshot.profiles,
      [id]: { name: trimmed, state: structuredClone(current.state) },
    };
    this.#commit({ ...this.#snapshot, currentProfileId: id, profiles });
  }

  deleteProfile(id: string): void {
    if (!this.#snapshot.profiles[id])
      throw new Error("Browser profile is unavailable");
    const profiles = { ...this.#snapshot.profiles };
    delete profiles[id];
    const [first] = Object.keys(profiles);
    if (first === undefined)
      throw new Error("The last browser profile cannot be deleted");
    this.#commit({
      ...this.#snapshot,
      currentProfileId:
        id === this.#snapshot.currentProfileId
          ? first
          : this.#snapshot.currentProfileId,
      profiles,
    });
  }

  renameProfile(id: string, name: string): void {
    const current = this.#snapshot.profiles[id];
    if (!current) throw new Error("Browser profile is unavailable");
    const trimmed = name.trim();
    if (!trimmed) throw new Error("Profile name cannot be empty");
    if (current.name === trimmed) return;
    if (
      Object.entries(this.#snapshot.profiles).some(
        ([otherId, profile]) => otherId !== id && profile.name === trimmed,
      )
    )
      throw new Error("A profile with that name already exists");
    this.#commit({
      ...this.#snapshot,
      profiles: {
        ...this.#snapshot.profiles,
        [id]: { ...current, name: trimmed },
      },
    });
  }

  #commit(next: BrowserState): void {
    this.#storage.setItem(BROWSER_STORAGE_KEY, JSON.stringify(next));
    this.#snapshot = next;
    this.#listeners.forEach((listener) => listener());
  }
}

function mergePrerequisitesState(
  saved: Record<string, unknown>,
): PrerequisitesState {
  // Project the prerequisite shape: saved values fill the known fields, and a storage write
  // writes only those fields.
  const merged: Record<string, unknown> = {};
  for (const [field, fallback] of Object.entries(initialPrerequisitesState()))
    merged[field] = field in saved ? saved[field] : fallback;
  return merged as PrerequisitesState;
}

function mergeProfileState(value: unknown): ProfileState {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("Saved browser profile state is invalid");
  }
  const saved = value as Record<string, unknown>;
  const defaults = initialProfileState();
  const merged = { ...defaults, ...saved };
  for (const key of [
    "search",
    "compare",
    "prerequisites",
    "discover",
    "structure",
  ] as const) {
    const slice = saved[key];
    if (slice !== undefined) {
      if (!slice || typeof slice !== "object" || Array.isArray(slice)) {
        throw new Error(`Saved browser profile slice ${key} is invalid`);
      }
      (merged as Record<string, unknown>)[key] =
        key === "prerequisites"
          ? mergePrerequisitesState(slice as Record<string, unknown>)
          : { ...defaults[key], ...slice };
    }
  }
  return merged as ProfileState;
}

function readBrowserState(storage: Storage): BrowserState {
  const raw = storage.getItem(BROWSER_STORAGE_KEY);
  if (raw === null) {
    const initial = initialBrowserState();
    storage.setItem(BROWSER_STORAGE_KEY, JSON.stringify(initial));
    return initial;
  }
  const value: unknown = JSON.parse(raw);
  if (!value || typeof value !== "object" || Array.isArray(value))
    throw new Error("Saved browser state is invalid");
  const saved = value as Record<string, unknown>;
  if (saved.schemaVersion !== 1)
    throw new Error("Unsupported saved browser state schema");
  if (
    typeof saved.currentProfileId !== "string" ||
    !saved.profiles ||
    typeof saved.profiles !== "object" ||
    Array.isArray(saved.profiles)
  ) {
    throw new Error("Saved browser state has no current profile");
  }
  const profiles: BrowserState["profiles"] = {};
  for (const [id, profile] of Object.entries(saved.profiles)) {
    if (!profile || typeof profile !== "object" || Array.isArray(profile))
      throw new Error("Saved browser profile is invalid");
    const stored = profile as Record<string, unknown>;
    if (typeof stored.name !== "string" || !stored.state)
      throw new Error("Saved browser profile is invalid");
    profiles[id] = {
      name: stored.name,
      state: mergeProfileState(stored.state),
    };
  }
  if (!profiles[saved.currentProfileId])
    throw new Error("Saved browser state has no current profile");
  return {
    schemaVersion: 1,
    currentProfileId: saved.currentProfileId,
    profiles,
  };
}

export function createBrowserStore(storage: Storage): BrowserStore {
  return new BrowserStore(storage, readBrowserState(storage));
}
