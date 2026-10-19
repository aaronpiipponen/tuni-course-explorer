/**
 * Render the console's shared dropdown picker.
 *
 * One picker renders one fixed choice list behind a styled trigger. The menu is mounted in its
 * closed state so its opening and closing both transition, while its hidden state removes it from
 * the accessibility tree and the tab order. Selecting an option reports that value and closes the
 * menu. A click outside or Escape closes it without reporting a value.
 */
import { useEffect, useRef, useState } from "react";

/** One choice of a picker: the value the caller stores and the text the operator reads. */
export interface PickOption {
  value: string;
  label: string;
}

/** The menu's viewport gap from its trigger. */
const MENU_GAP = 6;

/** Render one styled choice list with an animated menu. */
export function Picker({
  label,
  value,
  options,
  onChange,
  disabled = false,
}: {
  label: string;
  value: string;
  options: PickOption[];
  onChange: (value: string) => void;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState<{
    top: number;
    left: number;
    width: number;
  } | null>(null);
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const selected = options.find((option) => option.value === value);

  useEffect(() => {
    if (!open) {
      return;
    }
    const place = (): void => {
      const rect = trigger.current?.getBoundingClientRect();
      if (rect !== undefined) {
        setPosition({
          top: rect.bottom + MENU_GAP,
          left: rect.left,
          width: rect.width,
        });
      }
    };
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    return () => {
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", place, true);
    };
  }, [open]);

  useEffect(() => {
    if (!open) {
      return;
    }
    const onPointerDown = (event: PointerEvent): void => {
      if (
        root.current !== null &&
        !root.current.contains(event.target as Node)
      ) {
        setOpen(false);
      }
    };
    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.key === "Escape") {
        setOpen(false);
      }
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <div className={`pick${open ? " open" : ""}`} ref={root}>
      <button
        className="pick-button"
        type="button"
        ref={trigger}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={label}
        disabled={disabled}
        onClick={() => {
          if (!open) {
            const rect = trigger.current?.getBoundingClientRect();
            if (rect !== undefined) {
              setPosition({
                top: rect.bottom + MENU_GAP,
                left: rect.left,
                width: rect.width,
              });
            }
          }
          setOpen((current) => !current);
        }}
      >
        <span className="pick-value">{selected?.label ?? value}</span>
        <span className="pick-arrow" aria-hidden="true" />
      </button>
      <ul
        className="pick-menu"
        role="listbox"
        aria-label={label}
        aria-hidden={!open}
        style={
          position === null
            ? undefined
            : {
                top: position.top,
                left: position.left,
                width: position.width,
              }
        }
      >
        {options.map((option) => (
          <li key={option.value}>
            <button
              className={`pick-option${option.value === value ? " on" : ""}`}
              type="button"
              role="option"
              aria-selected={option.value === value}
              data-value={option.value}
              tabIndex={open ? 0 : -1}
              onClick={() => {
                setOpen(false);
                onChange(option.value);
              }}
            >
              {option.label}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
