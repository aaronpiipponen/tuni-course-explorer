/** One provider of the app-level transient notice to every mounted course surface. */
import { createContext } from "react";
import type { DisplayLanguage } from "../state/types";

/** One optional action beside a notice: its localized label and what it runs. */
export type NoticeAction = {
  label: (language: DisplayLanguage) => string;
  run(): void;
};

/** The notice API: show one formatter-resolved message and an optional action. */
export type NoticeApi = {
  show(
    text: (language: DisplayLanguage) => string,
    action?: NoticeAction,
  ): void;
};

/** React context carrying the app-level notice API. */
export const NoticeContext = createContext<NoticeApi | null>(null);
