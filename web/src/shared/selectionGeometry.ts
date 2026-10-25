/** Measured selection geometry shared by the sliding activity and language switches. */
import { useLayoutEffect } from "react";

/** Write the selected element's box into the container's selection custom properties. */
export function applySelectionGeometry(
  container: HTMLElement | null,
  selected: HTMLElement | null | undefined,
): void {
  if (!container || !selected) return;
  container.style.setProperty("--selection-x", `${selected.offsetLeft}px`);
  container.style.setProperty("--selection-y", `${selected.offsetTop}px`);
  container.style.setProperty("--selection-w", `${selected.offsetWidth}px`);
  container.style.setProperty("--selection-h", `${selected.offsetHeight}px`);
}

/** Re-run one selection measurement on every resize for the mounted lifetime. */
export function useSelectionGeometry(measure: () => void): void {
  useLayoutEffect(() => {
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [measure]);
}
