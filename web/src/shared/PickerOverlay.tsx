/** Shared animated overlay for course and structure-root substring pickers. */
import { useEffect, type ReactNode } from "react";
import { useWording } from "./useWording";

export function PickerOverlay({
  open,
  onClose,
  eyebrow,
  anchorClassName,
  children,
}: {
  open: boolean;
  onClose: () => void;
  eyebrow: string;
  /** Class of a wrapper around the picker alone, which supplies its containing block. */
  anchorClassName?: string;
  children: ReactNode;
}) {
  const { t } = useWording();
  useEffect(() => {
    if (!open) return;
    const outside = (event: PointerEvent) => {
      if (
        event.target instanceof Element &&
        !event.target.closest(".root-picker") &&
        !event.target.closest('[role="dialog"], .dialog-scrim')
      )
        onClose();
    };
    const keys = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        // An open confirmation owns Escape, so dismissing it keeps the picker for the next pick.
        if (document.querySelector('[role="dialog"]')) return;
        event.stopPropagation();
        onClose();
      }
      if (event.key === "ArrowLeft" || event.key === "ArrowRight")
        event.stopImmediatePropagation();
    };
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", keys, true);
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("keydown", keys, true);
    };
  }, [open, onClose]);
  const picker = (
    <div
      className={`root-picker${open ? " open" : ""}`}
      aria-hidden={!open}
      inert={!open}
    >
      <section className="root-picker-card">
        <div className="root-picker-top">
          <span className="compare-eyebrow">{eyebrow}</span>
          <button type="button" className="pill-btn" onClick={onClose}>
            {t("Close")}
          </button>
        </div>
        {children}
      </section>
    </div>
  );
  return (
    <>
      <div
        className={`root-picker-scrim${open ? " open" : ""}`}
        aria-hidden="true"
      />
      {anchorClassName ? (
        <div className={anchorClassName}>{picker}</div>
      ) : (
        picker
      )}
    </>
  );
}
