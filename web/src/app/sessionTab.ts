/**
 * One session-local owner of the browser tab's open app tab.
 *
 * The value lives in this browser tab's session storage, so a reload keeps it and another
 * browser tab keeps its own. Storage failure propagates to the caller.
 */
import { useSyncExternalStore } from "react";
import type { TabId } from "../state/types";
import { TABS } from "./tabs";

const ACTIVE_TAB_STORAGE_KEY = "tuni-course-explorer-active-tab";
const DEFAULT_TAB: TabId = "search";
const TAB_IDS: readonly string[] = TABS.map((tab) => tab.id);

let cached: TabId | null = null;
const listeners = new Set<() => void>();

function readStored(): TabId {
  const stored = sessionStorage.getItem(ACTIVE_TAB_STORAGE_KEY);
  return stored !== null && TAB_IDS.includes(stored)
    ? (stored as TabId)
    : DEFAULT_TAB;
}

function getSnapshot(): TabId {
  cached ??= readStored();
  return cached;
}

function getServerSnapshot(): TabId {
  return DEFAULT_TAB;
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Open one app tab in this browser tab, after its value is stored. */
export function setActiveTab(tab: TabId): void {
  sessionStorage.setItem(ACTIVE_TAB_STORAGE_KEY, tab);
  cached = tab;
  listeners.forEach((listener) => listener());
}

/** Subscribe one component to this browser tab's open app tab. */
export function useActiveTab(): TabId {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}
