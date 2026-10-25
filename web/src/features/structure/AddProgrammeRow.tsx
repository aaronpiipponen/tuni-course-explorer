/** Full-width row that starts adding one top-level programme. */
import { motion } from "framer-motion";
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
  const { t } = useWording();
  return (
    <motion.div
      className="add-programme-row"
      layout={reducedMotion ? false : "position"}
      transition={
        reducedMotion
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
