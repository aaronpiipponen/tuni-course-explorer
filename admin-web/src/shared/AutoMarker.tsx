/**
 * The read marker of one panel.
 *
 * It renders the elapsed whole seconds, minutes, hours or days since that panel's last successful
 * read, and it states that no read has completed rather than implying a fresh one. Its own second
 * tick is the only timer: it issues no command. A demand panel's marker names the operator's own
 * read instead of an automatic one, and a reading panel shows the read in progress. A marker without
 * its indicator states the same read without the live light.
 */
import { useEffect, useState } from "react";
import { relativeAge } from "./format";
import { wording } from "./wording";

/** Render one panel's read marker for its last successful read. */
export function AutoMarker({
  lastSuccess,
  label,
  reading = false,
  demand = false,
  indicator = true,
}: {
  lastSuccess: number | null;
  label: string;
  reading?: boolean;
  demand?: boolean;
  indicator?: boolean;
}) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  const elapsed =
    lastSuccess !== null
      ? relativeAge((now - lastSuccess) / 1000)
      : reading
        ? wording.reading
        : wording.notRead;
  return (
    <span className="live" aria-label={label}>
      <span className="live-state">
        {indicator ? <i /> : null}
        {demand ? wording.manual : wording.auto}
      </span>
      <span className="live-age">
        · <b>{elapsed}</b>
      </span>
    </span>
  );
}
