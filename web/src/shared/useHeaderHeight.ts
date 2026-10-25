/** Keep one root CSS header-height property in step with a mounted header's border-box height. */
import { useLayoutEffect, type RefObject } from "react";

/**
 * Measure the header at `ref` into `variable` on the document root.
 *
 * The property is written in pixels and updated whenever the header's border box changes size.
 * Unmount removes the property. `ResizeObserver` is required.
 */
export function useHeaderHeight(
  ref: RefObject<HTMLElement | null>,
  variable: "--app-header-height" | "--docs-header-height",
): void {
  useLayoutEffect(() => {
    const header = ref.current;
    if (!header) return;
    const root = document.documentElement;
    const measure = () => {
      root.style.setProperty(
        variable,
        `${header.getBoundingClientRect().height}px`,
      );
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(header);
    return () => {
      observer.disconnect();
      root.style.removeProperty(variable);
    };
  }, [ref, variable]);
}
