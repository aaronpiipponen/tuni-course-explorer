/** Animated, inert-aware disclosure shared by stacked graph panels. */
import { useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { useReducedMotion } from "./useReducedMotion";

export function Disclosure({
  open,
  className,
  children,
}: {
  open: boolean;
  className?: string;
  children: ReactNode;
}) {
  const reducedMotion = useReducedMotion();
  const [animating, setAnimating] = useState(false);
  const previous = useRef(open);
  useLayoutEffect(() => {
    // A suppressed transition never fires transitionend, so the flag clears on the preference
    // itself while an open change keeps the panel unanimated.
    if (reducedMotion) {
      previous.current = open;
      setAnimating(false);
      return;
    }
    if (previous.current !== open) {
      previous.current = open;
      setAnimating(true);
    }
  }, [open, reducedMotion]);
  return (
    <div
      className={`disclosure${open ? " open" : ""}${animating ? " anim" : ""}${className ? ` ${className}` : ""}`}
      inert={!open}
      onTransitionEnd={(event) => {
        if (
          event.target === event.currentTarget &&
          event.propertyName === "grid-template-rows"
        )
          setAnimating(false);
      }}
    >
      <div className="panelclip">{children}</div>
    </div>
  );
}
