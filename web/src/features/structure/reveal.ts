/** Open Structure of studies at its Unplaced studies row, which may still be loading. */
import { setActiveTab } from "../../app/sessionTab";
import { prefersReducedMotion } from "../../shared/useReducedMotion";

/** The attribute the structure tree puts on its Unplaced studies row. */
const UNPLACED_ROW = "[data-structure-unplaced]";

// A reveal requested before the structure tree holds its Unplaced studies row waits here.
let waiting = false;

/** Bring one rendered Unplaced studies row to the top of its pane. */
function show(row: HTMLElement): void {
  row.scrollIntoView({
    block: "start",
    behavior: prefersReducedMotion() ? "auto" : "smooth",
  });
}

/** Open Structure of studies at its Unplaced studies row. */
export function revealUnplacedStudies(): void {
  setActiveTab("structure");
  const row = document.querySelector<HTMLElement>(
    `.tab-pane[data-tab="structure"]:not(.exiting) ${UNPLACED_ROW}`,
  );
  waiting = row === null;
  if (row) show(row);
}

/** Scroll a waiting reveal once the structure tree holds its Unplaced studies row. */
export function settleUnplacedReveal(tree: HTMLElement | null): void {
  if (!waiting) return;
  const row = tree?.querySelector<HTMLElement>(UNPLACED_ROW);
  if (!row) return;
  waiting = false;
  show(row);
}

/** Drop a reveal that the structure pane never reached. */
export function forgetUnplacedReveal(): void {
  waiting = false;
}
