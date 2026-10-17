/** One comparison percentage row with a cancellable animated bar and null state. */
import { useEffect, useRef, useState } from "react";
import { useReducedMotion } from "../../shared/useReducedMotion";
import { useWording } from "../../shared/useWording";

export function ComparisonMeter({
  label,
  description,
  value,
  pending,
}: {
  label: string;
  description: string;
  value: number | null;
  pending: boolean;
}) {
  const { t } = useWording();
  const reducedMotion = useReducedMotion();
  const target = value ?? 0;
  const [shown, setShown] = useState(0);
  const displayed = useRef(0);
  useEffect(() => {
    if (reducedMotion) {
      displayed.current = target;
      setShown(target);
      return;
    }
    const from = displayed.current;
    const started = performance.now();
    let frame = 0;
    const tick = (now: number) => {
      const progress = Math.min(1, (now - started) / 700);
      const next = Math.round(
        from + (target - from) * (1 - Math.pow(1 - progress, 3)),
      );
      displayed.current = next;
      setShown(next);
      if (progress < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [target, reducedMotion]);
  return (
    <div
      className={`comparison-meter${!pending && value === null ? " na" : ""}`}
    >
      <label>
        <span>{label}</span>
        <small>{description}</small>
      </label>
      <div className="comparison-track">
        <i style={{ width: `${target}%` }} />
      </div>
      <b>
        {pending
          ? "–"
          : value === null
            ? t("not available")
            : `${reducedMotion ? Math.round(target) : shown} %`}
      </b>
    </div>
  );
}
