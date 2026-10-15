/** Percentage presentation for command-owned discovery measurements. */
import { motion } from "framer-motion";

export function DiscoverMeter({
  label,
  value,
  title,
}: {
  label: string;
  value: number;
  title?: string;
}) {
  const percentage = Math.round(value);
  return (
    <div
      className="discover-meter"
      title={title}
      aria-label={`${label}: ${percentage}%`}
    >
      <span>{label}</span>
      <div className="discover-meter-track" aria-hidden="true">
        <motion.i
          initial={{ width: 0 }}
          animate={{ width: `${value}%` }}
          transition={{ duration: 0.55 }}
        />
      </div>
      <b>{percentage}%</b>
    </div>
  );
}
