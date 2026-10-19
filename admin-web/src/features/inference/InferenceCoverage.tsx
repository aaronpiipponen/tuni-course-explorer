/**
 * The Coverage panel of the retained-server summary.
 *
 * The counts are the summary's coverage member under its own field names, and the explicit operator
 * DONE count is the summary's own operator_done_targets, shown separately rather than as a fabricated
 * model identity row. This panel is the retained server dataset's coverage, not an unreturned worker
 * cycle's progress.
 */
import { AutoMarker } from "../../shared/AutoMarker";
import { count, stateText } from "../../shared/format";
import { Panel, Row, Rows } from "../../shared/Panel";
import type { SummaryView } from "./Inference";
import { wording } from "../../shared/wording";

/** Render the coverage panel from the shared summary read. */
export function InferenceCoverage({ view }: { view: SummaryView }) {
  const detail = wording.inference;
  const summary = view.summary;
  const coverage = summary?.coverage ?? null;
  return (
    <Panel
      title={detail.coverage}
      marker={
        view.selectionEnabled === true ||
        (view.selectionEnabled === null && view.selectionFailure === null) ? (
          <AutoMarker
            reading={view.selectionEnabled === null || view.loading}
            lastSuccess={view.lastSuccess}
            label={detail.coverage}
          />
        ) : undefined
      }
    >
      {view.selectionEnabled === true ? (
        <>
          <p className="note">{detail.retainedScope}</p>
          {coverage === null || summary === null ? null : (
            <Rows>
              <Row
                label={detail.eligibleTargets}
                value={count(coverage.eligible_targets)}
              />
              <Row
                label={detail.retainedComplete}
                value={count(coverage.retained_complete_targets)}
              />
              <Row
                label={detail.published}
                value={count(coverage.published_targets)}
              />
              <Row
                label={detail.uncovered}
                value={count(coverage.uncovered_targets)}
              />
              <Row
                label={wording.row.pending}
                value={count(coverage.pending_targets)}
              />
              <Row
                label={wording.row.failed}
                value={count(coverage.failed_targets)}
              />
              <Row
                label={detail.operatorDone}
                value={count(summary.operator_done_targets)}
              />
              <Row
                label={detail.equivalenceGroups}
                value={count(coverage.current_equivalence_groups)}
              />
              <Row
                label={detail.proposalRows}
                value={count(coverage.historical_proposal_rows)}
              />
              <Row
                label={wording.row.cycle}
                value={<code>{coverage.cycle_id ?? wording.unknown}</code>}
              />
              <Row
                label={wording.row.stage}
                value={stateText(coverage.stage)}
              />
            </Rows>
          )}
        </>
      ) : view.selectionEnabled === false ? (
        <p className="note">{wording.selectionDisabled}</p>
      ) : null}
    </Panel>
  );
}
