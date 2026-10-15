/** Shared measured two-option sliding switch used by activity and route controls. */
import { useCallback, useRef } from "react";
import {
  applySelectionGeometry,
  useSelectionGeometry,
} from "./selectionGeometry";

export function TwoOptionSwitch({
  labels,
  firstSelected,
  onChange,
  ariaLabel,
  className,
}: {
  labels: readonly [string, string];
  firstSelected: boolean;
  onChange: (firstSelected: boolean) => void;
  ariaLabel: string;
  className?: string;
}) {
  const root = useRef<HTMLDivElement>(null);
  const options = useRef<(HTMLButtonElement | null)[]>([]);
  // Translated labels change the option widths, so re-measure when they change.
  const [firstLabel, secondLabel] = labels;
  const measure = useCallback(() => {
    applySelectionGeometry(
      root.current,
      options.current[firstSelected ? 0 : 1],
    );
  }, [firstSelected, firstLabel, secondLabel]);
  useSelectionGeometry(measure);
  return (
    <div
      className={`activity-switch seg slide${className ? ` ${className}` : ""}`}
      ref={root}
      role="group"
      aria-label={ariaLabel}
    >
      {labels.map((label, index) => {
        const selected = firstSelected === (index === 0);
        return (
          <button
            key={label}
            ref={(element) => {
              options.current[index] = element;
            }}
            type="button"
            aria-pressed={selected}
            className={selected ? "on" : ""}
            onClick={() => {
              if (!selected) onChange(index === 0);
            }}
          >
            {label}
          </button>
        );
      })}
    </div>
  );
}
