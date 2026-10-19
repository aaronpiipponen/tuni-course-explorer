/**
 * The Generation identities panel of the retained-server summary.
 *
 * Every row is one entry of the summary's coverage generation_counts, which are the genuine retained
 * pointers grouped by their recorded run identity and route. An explicit operator DONE target
 * contributes no generation identity and therefore no row.
 */
import { AutoMarker } from "../../shared/AutoMarker";
import { count } from "../../shared/format";
import { DataTable, Panel } from "../../shared/Panel";
import type { SummaryView } from "./Inference";
import { wording } from "../../shared/wording";

/** Render the generation identities table from the shared summary read. */
export function GenerationIdentities({ view }: { view: SummaryView }) {
  const detail = wording.inference;
  const counts = view.summary?.coverage.generation_counts ?? [];
  return (
    <Panel
      title={detail.identities}
      marker={
        view.selectionEnabled === true ||
        (view.selectionEnabled === null && view.selectionFailure === null) ? (
          <AutoMarker
            reading={view.selectionEnabled === null || view.loading}
            lastSuccess={view.lastSuccess}
            label={detail.identities}
          />
        ) : undefined
      }
    >
      {view.selectionEnabled === true ? (
        <DataTable
          head={[
            detail.model,
            detail.prompt,
            detail.schema,
            detail.pipeline,
            detail.route,
            detail.targets,
          ]}
          rows={counts.map((entry) => [
            entry.model_identity,
            entry.prompt_version,
            entry.schema_version,
            entry.pipeline_version,
            <span key="route" className="nw">
              {entry.route}
            </span>,
            count(entry.targets),
          ])}
          align={["", "", "", "", "", "r"]}
        />
      ) : view.selectionEnabled === false ? (
        <p className="note">{wording.selectionDisabled}</p>
      ) : null}
    </Panel>
  );
}
