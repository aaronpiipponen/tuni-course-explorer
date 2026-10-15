/** One comparison percentage row with a cancellable animated bar and null state. */
import { useEffect, useRef, useState } from "react";
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
  const target = value ?? 0;
  const [shown, setShown] = useState(0);
  const displayed = useRef(0);
  useEffect(() => {
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
  }, [target]);
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
        {pending ? "–" : value === null ? t("not available") : `${shown} %`}
      </b>
    </div>
  );
}
