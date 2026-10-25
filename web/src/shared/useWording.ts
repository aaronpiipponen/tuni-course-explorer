/**
 * Live-profile wording subscription that binds the shared FI/EN resource to the current profile
 * language.
 */
import { useMemo } from "react";
import type { DisplayLanguage } from "../state/types";
import { useProfileSelector } from "../state/useProfileSelector";
import { uiText, type UiTextKey } from "./wording";

/** Subscribe one component to the current profile's language and text lookup. */
export function useWording(): {
  language: DisplayLanguage;
  t: (
    key: UiTextKey,
    values?: Readonly<Record<string, string | number>>,
  ) => string;
} {
  const { value: language } = useProfileSelector((state) => state.language);
  return useMemo(
    () => ({
      language,
      t: (key, values) => uiText(language, key, values),
    }),
    [language],
  );
}
