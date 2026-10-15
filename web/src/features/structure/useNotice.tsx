/** Brief structure action notice. Text resolves in the live language. */
import { useEffect, useState, type ReactNode } from "react";
import type { DisplayLanguage } from "../../state/types";
import { useWording } from "../../shared/useWording";

export function useNotice(): {
  show(text: (language: DisplayLanguage) => string): void;
  toast: ReactNode;
} {
  const { language } = useWording();
  const [text, setText] = useState<
    ((language: DisplayLanguage) => string) | null
  >(null);
  useEffect(() => {
    if (!text) return;
    const timer = window.setTimeout(() => setText(null), 2200);
    return () => window.clearTimeout(timer);
  }, [text]);
  return {
    // Wrap so a formatter is stored as state value, not mistaken for a state updater.
    show: (formatter) => setText(() => formatter),
    toast: text ? (
      <div className="toast" role="status">
        {text(language)}
      </div>
    ) : null,
  };
}
