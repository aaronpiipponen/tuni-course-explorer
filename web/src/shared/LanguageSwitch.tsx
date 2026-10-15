/** Accessible FI/EN control that flips the current profile's app and official-name language. */
import { setLanguage } from "../app/actions";
import { useCurrentProfile } from "../state/useCurrentProfile";
import { useAction } from "./useAction";
import { ErrorNotice } from "./ErrorNotice";
import { useWording } from "./useWording";
import { useCallback, useRef } from "react";
import {
  applySelectionGeometry,
  useSelectionGeometry,
} from "./selectionGeometry";

export function LanguageSwitch() {
  const { store, profile } = useCurrentProfile();
  const { runAction, error } = useAction();
  const { language, t } = useWording();
  const button = useRef<HTMLButtonElement>(null);
  const labels = useRef<(HTMLSpanElement | null)[]>([]);
  const measure = useCallback(() => {
    applySelectionGeometry(
      button.current,
      labels.current[profile.state.language === "fi" ? 0 : 1],
    );
  }, [profile.state.language]);
  useSelectionGeometry(measure);
  return (
    <div className="language-control">
      <button
        ref={button}
        style={{ position: "relative" }}
        type="button"
        className="language-switch"
        aria-label={t("App language: {language}", {
          language: profile.state.language.toUpperCase(),
        })}
        onClick={() =>
          runAction(() =>
            setLanguage(store, profile.state.language === "fi" ? "en" : "fi"),
          )
        }
      >
        {(["fi", "en"] as const).map((option) => {
          const selected = profile.state.language === option;
          return (
            <span
              key={option}
              ref={(element) => {
                labels.current[option === "fi" ? 0 : 1] = element;
              }}
              aria-hidden="true"
              className={selected ? "selected" : ""}
            >
              {option.toUpperCase()}
            </span>
          );
        })}
      </button>
      {error && <ErrorNotice error={error} language={language} />}
    </div>
  );
}
