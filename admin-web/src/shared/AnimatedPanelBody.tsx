/**
 * The measured body of one console panel.
 *
 * The outer viewport holds the inner content's measured border-box height, so a content change
 * interpolates the box while the panel's own `hidden` state keeps governing layout, focus and
 * accessibility. The measurement comes from the browser's layout through `ResizeObserver`. jsdom
 * performs no layout, so its test substitute emits no measurement and real layout proof lives in
 * browser acceptance.
 */
import { useLayoutEffect, useRef, useState, type ReactNode } from "react";

/** Render the transitioned body of one panel around its children. */
export function AnimatedPanelBody({ children }: { children: ReactNode }) {
  const viewport = useRef<HTMLDivElement>(null);
  const content = useRef<HTMLDivElement>(null);
  const [height, setHeight] = useState<number | null>(null);

  useLayoutEffect(() => {
    const inner = content.current;
    if (inner === null) {
      return;
    }
    const measure = (): void => {
      const measured = inner.getBoundingClientRect().height;
      // A hidden tab measures zero, which is not a content size to hold.
      if (measured === 0) {
        return;
      }
      setHeight(measured);
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(inner);
    return () => observer.disconnect();
  }, []);

  return (
    <div
      className="panel-body"
      ref={viewport}
      style={height === null ? undefined : { height }}
    >
      <div className="pb" ref={content}>
        {children}
      </div>
    </div>
  );
}
