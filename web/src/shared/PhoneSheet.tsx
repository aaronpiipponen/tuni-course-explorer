/** One bottom sheet above the phone tab bar, shared by the pane option surfaces. */
import { useEffect, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "framer-motion";
import { useWording } from "./useWording";
import { usePhoneTabsOnClose } from "./usePhoneTabsOnClose";
import { useReducedMotion } from "./useReducedMotion";
import { isUnhandledEscape } from "./escape";
import "./phone-sheet.css";

/**
 * Render one pane-level sheet over the phone tab bar.
 *
 * The portal keeps the fixed surface independent of the tab pane's transition transform. The
 * sheet owns the Escape listener and calls `onClose` unless a nested layer has already handled
 * the key, and the caller owns the focus return that goes with its own trigger. Nothing renders
 * while the sheet is closed.
 */
export function PhoneSheet({
  open,
  title,
  onClose,
  children,
}: {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  const { t } = useWording();
  const reducedMotion = useReducedMotion();
  usePhoneTabsOnClose(open);
  useEffect(() => {
    if (!open) return;
    const keydown = (event: KeyboardEvent) => {
      if (isUnhandledEscape(event)) onClose();
    };
    document.addEventListener("keydown", keydown);
    return () => document.removeEventListener("keydown", keydown);
  }, [open, onClose]);
  return createPortal(
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            className="phone-sheet-scrim"
            aria-hidden="true"
            onClick={onClose}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: reducedMotion ? 0 : 0.16 }}
          />
          <motion.section
            className="phone-sheet"
            role="dialog"
            aria-label={title}
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 24 }}
            transition={{
              duration: reducedMotion ? 0 : 0.22,
              ease: [0.22, 0.8, 0.2, 1],
            }}
          >
            <header className="phone-sheet-head">
              <b>{title}</b>
              <button className="pill-btn" type="button" onClick={onClose}>
                {t("Close")}
              </button>
            </header>
            {children}
          </motion.section>
        </>
      )}
    </AnimatePresence>,
    document.body,
  );
}
