/** One provider of the app-level notice to every mounted course surface. */
import { createContext } from "react";
import type { DisplayLanguage, TabId } from "../state/types";

/** One optional action beside a notice: its localized label and what it runs. */
export type NoticeAction = {
  label: (language: DisplayLanguage) => string;
  run(): void;
};

/** One linked phrase inside a notice: the localized words and what they open. */
export type NoticeLink = {
  label: (language: DisplayLanguage) => string;
  run(): void;
};

/** How one notice behaves: a stable key, whether it stays, and an optional linked phrase. */
export type NoticeOptions = {
  /** Replaces a notice that already carries the same key instead of adding another. */
  key?: string;
  /** Keeps the notice visible until its key is dismissed. */
  persistent?: boolean;
  /** Makes one phrase of the message open the surface it names. */
  link?: NoticeLink;
};

/** One visible notice, owned by the tab that showed it. */
export type Notice = {
  id: number;
  text: (language: DisplayLanguage) => string;
  action?: NoticeAction;
  link?: NoticeLink;
  key?: string;
  persistent: boolean;
  /** The app tab that showed the notice. Its stack rides with that tab. */
  tab: TabId;
};

/** The notice API: show one formatter-resolved message and an optional action. */
export type NoticeApi = {
  show(
    text: (language: DisplayLanguage) => string,
    action?: NoticeAction,
    options?: NoticeOptions,
  ): void;
  /** Remove the notice that carries one key. */
  dismiss(key: string): void;
};

/** React context carrying the app-level notice API. */
export const NoticeContext = createContext<NoticeApi | null>(null);

/** Every notice the provider holds, which each tab pane filters to its own. */
export const NoticeListContext = createContext<readonly Notice[]>([]);
