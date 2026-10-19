/**
 * The publication diagnostics panel of the retained-server summary.
 *
 * Every count covers the summary's own eligible cohort, and the two live route-count spellings
 * describe the one non-local counter, rendered under Route other. The three policy rows state the
 * configured inference policy values the report carries.
 */
import type { PublicationDiagnostics as Diagnostics } from "../../api/types";
import { AutoMarker } from "../../shared/AutoMarker";
import { count } from "../../shared/format";
import { Panel, Row, Rows } from "../../shared/Panel";
import type { SummaryView } from "./Inference";
import { wording } from "../../shared/wording";

function otherRouteTargets(diagnostics: Diagnostics): number | null {
  return (
    diagnostics.other_route_targets ??
    diagnostics.oversize_cloud_targets ??
    null
  );
}

/** Render the publication diagnostics panel from the shared summary read. */
export function PublicationDiagnostics({ view }: { view: SummaryView }) {
  const detail = wording.inference;
  const summary = view.summary;
  return (
    <Panel
      title={detail.diagnostics}
      marker={
        view.selectionEnabled === true ||
        (view.selectionEnabled === null && view.selectionFailure === null) ? (
          <AutoMarker
            reading={view.selectionEnabled === null || view.loading}
            lastSuccess={view.lastSuccess}
            label={detail.diagnostics}
          />
        ) : undefined
      }
    >
      {view.selectionEnabled === true ? (
        <>
          {summary === null ? null : (
            <Rows>
              <Row
                label={detail.selected}
                value={count(summary.publication.selected_targets)}
              />
              <Row
                label={detail.processed}
                value={count(summary.publication.processed_targets)}
              />
              <Row
                label={detail.accepted}
                value={count(summary.publication.accepted_targets)}
              />
              <Row
                label={detail.published}
                value={count(summary.publication.published_targets)}
              />
              <Row
                label={detail.routeLocal}
                value={count(summary.publication.local_targets)}
              />
              <Row
                label={detail.routeOther}
                value={count(otherRouteTargets(summary.publication))}
              />
              <Row
                label={detail.observedCandidates}
                value={count(summary.publication.observed_packet_candidates)}
              />
              <Row
                label={detail.expectedCandidates}
                value={count(summary.publication.expected_packet_candidates)}
              />
              <Row
                label={detail.transitiveWarnings}
                value={count(summary.publication.transitive_warnings.length)}
              />
              <Row
                label={detail.routingPolicy}
                value={<code>{summary.routing_policy}</code>}
              />
              <Row
                label={detail.recommendationPolicy}
                value={<code>{summary.recommendation_policy}</code>}
              />
              <Row
                label={detail.findingFilterPolicy}
                value={<code>{summary.finding_filter_policy}</code>}
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
