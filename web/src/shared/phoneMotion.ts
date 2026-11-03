/** The phone rise timing, the closing body class and the hooks that set and read it. */
import { useEffect, useRef } from "react";

/** The body class that marks a bottom surface folding away. */
const CLOSING_CLASS = "phone-surface-closing";

/** Let the notice make room back as a bottom surface folds away. */
export function usePhoneSurfaceClosing(open: boolean): void {
  const wasOpen = useRef(open);
  useEffect(() => {
    if (wasOpen.current && !open) {
      setPhoneSurfaceClosing(true);
      const timer = window.setTimeout(
        () => setPhoneSurfaceClosing(false),
        PHONE_RISE_SECONDS * 1000,
      );
      wasOpen.current = open;
      return () => {
        window.clearTimeout(timer);
        setPhoneSurfaceClosing(false);
      };
    }
    wasOpen.current = open;
  }, [open]);
}

/** The one rise that every bottom surface shares on the phone. */
export const PHONE_RISE_SECONDS = 0.24;

/** The easing of the phone rise, shared by the sheets and the notice stack's own transition. */
export const PHONE_RISE_EASE: [number, number, number, number] = [
  0.22, 0.8, 0.2, 1,
];

/** Mark a bottom surface as folding away, so the notice makes room back at once. */
function setPhoneSurfaceClosing(closing: boolean): void {
  document.body.classList.toggle(CLOSING_CLASS, closing);
}

/** Return whether a bottom surface is folding away. */
export function phoneSurfaceIsClosing(): boolean {
  return document.body.classList.contains(CLOSING_CLASS);
}
