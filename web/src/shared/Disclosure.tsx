/** Animated, inert-aware disclosure shared by stacked graph panels. */
import { useLayoutEffect, useRef, useState, type ReactNode } from "react";

export function Disclosure({
  open,
  className,
  children,
}: {
  open: boolean;
  className?: string;
  children: ReactNode;
}) {
  const [animating, setAnimating] = useState(false);
  const previous = useRef(open);
  useLayoutEffect(() => {
    if (previous.current !== open) {
      previous.current = open;
      setAnimating(true);
    }
  }, [open]);
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
