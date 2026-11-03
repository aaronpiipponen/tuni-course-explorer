/** Animate one scroll container's content when its scrollbar takes or releases space. */
import { useEffect } from "react";
import { useReducedMotion } from "./useReducedMotion";

/** One scrollbar shift's duration and curve, matching the app's panel motion. */
const SHIFT_MS = 180;
const SHIFT_EASING = "cubic-bezier(0.22, 0.8, 0.2, 1)";

/**
 * Animate the content width when a classic scrollbar appears or disappears.
 *
 * The content is the scroll container's first element child, which tracks the container's content
 * box, so it narrows by the scrollbar width while the container's own width stays. Only that case
 * animates, and a real resize of the panel applies at once. A container without an element child
 * raises an error.
 */
export function useScrollbarShift(
  scroll: HTMLElement | null,
  active = true,
): void {
  const reducedMotion = useReducedMotion();
  useEffect(() => {
    if (!active || !scroll) return;
    const content = scroll.firstElementChild;
    if (!(content instanceof HTMLElement))
      throw new Error("A scroll container holds no content element");
    let width: number | null = null;
    let border = 0;
    let animation: Animation | null = null;
    const settle = () => {
      animation?.cancel();
      animation = null;
      content.style.width = "";
    };
    const observer = new ResizeObserver(([entry]) => {
      const contentWidth = entry.contentRect.width;
      const borderWidth = scroll.offsetWidth;
      if (width === null) {
        width = contentWidth;
        border = borderWidth;
        return;
      }
      // The width animation itself reports intermediate widths, which are not new shifts.
      if (animation !== null) return;
      const resized = Math.abs(borderWidth - border) > 0.5;
      const from = width;
      width = contentWidth;
      border = borderWidth;
      if (resized || Math.abs(contentWidth - from) < 1 || from <= 0) return;
      if (reducedMotion) {
        content.style.width = "";
        return;
      }
      content.style.width = `${from}px`;
      const shift = content.animate(
        [{ width: `${from}px` }, { width: `${contentWidth}px` }],
        { duration: SHIFT_MS, easing: SHIFT_EASING },
      );
      animation = shift;
      shift.onfinish = () => {
        if (animation !== shift) return;
        animation = null;
        content.style.width = "";
      };
    });
    observer.observe(content);
    return () => {
      observer.disconnect();
      settle();
    };
  }, [scroll, active, reducedMotion]);
}
