/** Shared animated overlay for course and structure-root substring pickers. */
import { useEffect, type ReactNode } from "react";
import { useWording } from "./useWording";

export function PickerOverlay({
  open,
  onClose,
  eyebrow,
  children,
}: {
  open: boolean;
  onClose: () => void;
  eyebrow: string;
  children: ReactNode;
}) {
  const { t } = useWording();
  useEffect(() => {
    if (!open) return;
    const outside = (event: PointerEvent) => {
      if (
        event.target instanceof Element &&
        !event.target.closest(".root-picker")
      )
        onClose();
    };
    const keys = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
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
  return (
    <>
      <div
        className={`root-picker-scrim${open ? " open" : ""}`}
        aria-hidden="true"
      />
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
    </>
  );
}
