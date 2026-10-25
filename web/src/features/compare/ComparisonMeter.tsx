/** One comparison percentage row with a cancellable animated bar and null state. */
import { useEffect, useRef, useState } from "react";
import { useReducedMotion } from "../../shared/useReducedMotion";
import { useWording } from "../../shared/useWording";

/** Render one animated comparison measurement. */
export function ComparisonMeter({
  label,
  description,
  value,
  pending,
  loading,
}: {
  label: string;
  description: string;
  value: number | null;
  pending: boolean;
  loading: boolean;
}) {
  const { t } = useWording();
  const reducedMotion = useReducedMotion();
  const [target, setTarget] = useState(value ?? 0);
  const [shown, setShown] = useState(0);
  const displayed = useRef(0);
  // A replacement pair keeps the held meter positions until its report settles.
  useEffect(() => {
    if (loading) return;
    setTarget(value ?? 0);
  }, [loading, value]);
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
