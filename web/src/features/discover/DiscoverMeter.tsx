/** Percentage presentation for command-owned discovery measurements. */
import { motion } from "framer-motion";
import { useReducedMotion } from "../../shared/useReducedMotion";

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
  const reducedMotion = useReducedMotion();
  const percentage = Math.round(value);
  return (
    <span
      className="discover-meter"
      title={title}
      aria-label={`${label}: ${percentage}%`}
    >
      <span>{label}</span>
      <span className="discover-meter-track" aria-hidden="true">
        <motion.i
          initial={reducedMotion ? false : { width: 0 }}
          animate={{ width: `${value}%` }}
          transition={reducedMotion ? { duration: 0 } : { duration: 0.55 }}
        />
      </span>
      <b>{percentage}%</b>
    </span>
  );
}
