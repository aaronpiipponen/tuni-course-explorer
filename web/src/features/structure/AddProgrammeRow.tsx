/** Full-width row that starts adding one top-level programme. */
import { useContext } from "react";
import { motion } from "framer-motion";
import { PaneSlideContext } from "../../app/paneSlide";
import { useReducedMotion } from "../../shared/useReducedMotion";
import { useWording } from "../../shared/useWording";

/** Render the row that starts adding one top-level programme. */
export function AddProgrammeRow({
  onAdd,
  disabled,
}: {
  onAdd(): void;
  disabled: boolean;
}) {
  const reducedMotion = useReducedMotion();
  const paneSliding = useContext(PaneSlideContext);
  const still = reducedMotion || paneSliding;
  const { t } = useWording();
  return (
    <motion.div
      className="add-programme-row"
      layout={still ? false : "position"}
      transition={
        still
          ? { duration: 0 }
          : { duration: 0.45, ease: [0.22, 0.8, 0.2, 1] as const }
      }
    >
      <button
        className="pill-btn add-programme"
        type="button"
        disabled={disabled}
        onClick={onAdd}
      >
        <span aria-hidden="true">+</span>
        {t("Add programme")}
      </button>
    </motion.div>
  );
}
