/**
 * The Failures panel of the retained-server summary.
 *
 * Each row is one retained failure record of the summary. The canonical target identity is the
 * record's own group id, so no catalogue lookup happens and no course name is invented for it.
 */
import { AutoMarker } from "../../shared/AutoMarker";
import { moment } from "../../shared/format";
import { DataTable, Panel } from "../../shared/Panel";
import type { SummaryView } from "./Inference";
import { wording } from "../../shared/wording";

/** Render the failure records table from the shared summary read. */
export function Failures({ view }: { view: SummaryView }) {
  const detail = wording.inference;
  const failures = view.summary?.failures ?? [];
  return (
    <Panel
      title={detail.failures}
      span={12}
      marker={
        view.selectionEnabled === true ||
        (view.selectionEnabled === null && view.selectionFailure === null) ? (
          <AutoMarker
            reading={view.selectionEnabled === null || view.loading}
            lastSuccess={view.lastSuccess}
            label={detail.failures}
          />
        ) : undefined
      }
    >
      {view.selectionEnabled === true ? (
        <DataTable
          head={[
            detail.target,
            wording.row.stage,
            detail.attempts,
            detail.error,
            detail.reason,
            detail.exhausted,
            detail.created,
          ]}
          rows={failures.map((failure) => [
            <code key="target">{failure.target_group_id}</code>,
            failure.stage,
            failure.attempt_count,
            <code key="error">{failure.error_type}</code>,
            failure.reason,
            failure.exhausted ? wording.yes : wording.no,
            moment(failure.created_at),
          ])}
          align={["", "", "r", "", "", "", ""]}
        />
      ) : view.selectionEnabled === false ? (
        <p className="note">{wording.selectionDisabled}</p>
      ) : null}
    </Panel>
  );
}
