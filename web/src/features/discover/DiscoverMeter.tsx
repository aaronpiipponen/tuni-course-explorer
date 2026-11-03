/** Percentage presentation for command-owned discovery measurements. */
import { useContext } from "react";
import { motion } from "framer-motion";
import { PaneSlideContext } from "../../app/paneSlide";
import { useReducedMotion } from "../../shared/useReducedMotion";
import { useWording } from "../../shared/useWording";

/** Render one percentage measurement for a discovery result. */
export function DiscoverMeter({
  label,
  value,
  title,
}: {
  label: string;
  value: number;
  title?: string;
}) {
  const { t } = useWording();
  const reducedMotion = useReducedMotion();
  const paneSliding = useContext(PaneSlideContext);
  // A bar that grows while its pane slides is a second motion on top of the pane's own.
  const still = reducedMotion || paneSliding;
  const percentage = Math.round(value);
  return (
    <span
      className="discover-meter"
      title={title}
      aria-label={`${label}: ${t("{value}%", { value: percentage })}`}
    >
      <span>{label}</span>
      <span className="discover-meter-track" aria-hidden="true">
        <motion.i
          initial={still ? false : { width: 0 }}
          animate={{ width: `${value}%` }}
          transition={still ? { duration: 0 } : { duration: 0.55 }}
        />
      </span>
      <b>{t("{value}%", { value: percentage })}</b>
    </span>
  );
}
