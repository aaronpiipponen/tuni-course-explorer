/** Animates a content-sized block's height when its contents change. */
import { useLayoutEffect, useRef, useState, type ReactNode } from "react";

/**
 * Render one block whose height animates to its content's new height.
 *
 * The first measurement applies without animation, because a height that starts at `auto` has no
 * previous pixel value to animate from. Later changes animate through the shared curve.
 */
export function AnimatedHeight({ children }: { children: ReactNode }) {
  const inner = useRef<HTMLDivElement>(null);
  const [height, setHeight] = useState<number | null>(null);
  useLayoutEffect(() => {
    const element = inner.current;
    if (!element) return;
    const measure = () => setHeight(element.offsetHeight);
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  return (
    <div
      className="animated-height"
      style={height === null ? undefined : { height }}
    >
      <div ref={inner}>{children}</div>
    </div>
  );
}
