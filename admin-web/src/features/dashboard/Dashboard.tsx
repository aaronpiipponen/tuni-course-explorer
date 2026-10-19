/**
 * The Dashboard tab: the one server status report as five panels.
 *
 * Each fact states what kind it is, measured, configured, checkout identity, serving receipt or file
 * time, and a fact the owner reports as absent renders as unknown. The restart hint appears only for
 * a hub file the report measures as written after the served process started.
 */
import type { HubStatus, ServerStatusReport } from "../../api/types";
import { AutoMarker } from "../../shared/AutoMarker";
import {
  count,
  humanBytes,
  humanDuration,
  moment,
  stateText,
} from "../../shared/format";
import { FailureNotice, Panel, Row, Rows } from "../../shared/Panel";
import type { PanelRead } from "../../shared/usePanelRead";
import { wording } from "../../shared/wording";

function hubText(hubs: HubStatus[], alias: string): string {
  const hub = hubs.find((entry) => entry.alias === alias);
  if (hub === undefined) {
    return wording.unknown;
  }
  return `${hub.path}, ${moment(hub.modified_at)}`;
}

function restartHint(hubs: HubStatus[]): string | null {
  const written = hubs.filter((hub) => hub.newer_than_web_start === true);
  if (written.length === 0) {
    return null;
  }
  const time = moment(written[0].modified_at);
  return wording.dashboard.restartHint.replace("{time}", time);
}

function ServingPanel({
  report,
  lastSuccess,
  reading,
}: {
  report: ServerStatusReport | null;
  lastSuccess: number | null;
  reading: boolean;
}) {
  const detail = wording.dashboard;
  const hint = report === null ? null : restartHint(report.hubs);
  return (
    <Panel
      title={detail.serving}
      span={12}
      marker={
        <AutoMarker
          reading={reading}
          lastSuccess={lastSuccess}
          label={detail.serving}
        />
      }
    >
      {report === null ? null : (
        <>
          <Rows>
            <Row
              label={detail.selectedDataset}
              value={<b>{report.serving.dataset_id ?? wording.unknown}</b>}
            />
            <Row label={detail.kind} value={stateText(report.serving.kind)} />
            <Row
              label={detail.predecessor}
              value={report.serving.predecessor_id ?? wording.unknown}
            />
            <Row
              label={detail.pointer}
              value={<code>{report.serving.pointer ?? wording.unknown}</code>}
            />
            <Row
              label={detail.schemaHead}
              value={
                <code>
                  {report.serving.receipt_schema_revision ?? wording.unknown}
                </code>
              }
            />
            <Row
              label={detail.embeddingHub}
              value={hubText(report.hubs, "EMBEDDING_HUB_VECTOR")}
            />
            <Row
              label={detail.outcomesHub}
              value={hubText(report.hubs, "EMBEDDING_OUTCOMES_HUB_VECTOR")}
            />
            <Row
              label={detail.webServerHubs}
              value={detail.hubsAtProcessStart}
            />
          </Rows>
          {hint === null ? null : <p className="warn-note">{hint}</p>}
        </>
      )}
    </Panel>
  );
}

function WebsitePanel({
  report,
  lastSuccess,
  reading,
}: {
  report: ServerStatusReport | null;
  lastSuccess: number | null;
  reading: boolean;
}) {
  const detail = wording.dashboard;
  return (
    <Panel
      title={detail.website}
      marker={
        <AutoMarker
          reading={reading}
          lastSuccess={lastSuccess}
          label={detail.website}
        />
      }
    >
      {report === null ? null : (
        <Rows>
          <Row
            label={wording.row.state}
            value={stateText(report.website.state)}
          />
          <Row
            label={detail.bind}
            value={
              <code>
                {report.website.host}:{report.website.port}
              </code>
            }
          />
          <Row
            label={detail.configuredProcesses}
            value={count(report.website.configured_workers)}
          />
          <Row
            label={detail.entryPoint}
            value={<code>{report.website.entry_point}</code>}
          />
          <Row
            label={detail.checkout}
            value={
              <code>
                {report.website.checkout_branch}{" "}
                {report.website.checkout_revision.slice(0, 9)}
              </code>
            }
          />
          <Row
            label={detail.uptime}
            value={humanDuration(report.website.uptime_seconds)}
          />
          <Row
            label={detail.started}
            value={moment(report.website.started_at)}
          />
        </Rows>
      )}
    </Panel>
  );
}

function HostPanel({
  report,
  lastSuccess,
  reading,
}: {
  report: ServerStatusReport | null;
  lastSuccess: number | null;
  reading: boolean;
}) {
  const detail = wording.dashboard;
  return (
    <Panel
      title={detail.host}
      marker={
        <AutoMarker
          reading={reading}
          lastSuccess={lastSuccess}
          label={detail.host}
        />
      }
    >
      {report === null ? null : (
        <Rows>
          <Row
            label={detail.uptime}
            value={humanDuration(report.host.uptime_seconds)}
          />
          <Row
            label={detail.cpuUsage}
            value={`${report.host.cpu_usage_percent.toFixed(1)}%`}
          />
          <Row
            label={detail.memory}
            value={`${humanBytes(report.host.memory_used_bytes)} of ${humanBytes(
              report.host.memory_total_bytes,
            )}`}
          />
          <Row
            label={detail.dataBytes}
            value={humanBytes(report.host.data_bytes)}
          />
          <Row
            label={detail.modelsBytes}
            value={humanBytes(report.host.models_bytes)}
          />
          <Row
            label={detail.backupsBytes}
            value={humanBytes(report.host.backups_bytes)}
          />
          <Row
            label={detail.freeSpace}
            value={`${humanBytes(report.host.disk_free_bytes)} of ${humanBytes(
              report.host.disk_total_bytes,
            )}`}
          />
        </Rows>
      )}
    </Panel>
  );
}

function DatabasePanel({
  report,
  lastSuccess,
  reading,
}: {
  report: ServerStatusReport | null;
  lastSuccess: number | null;
  reading: boolean;
}) {
  const detail = wording.dashboard;
  return (
    <Panel
      title={detail.database}
      marker={
        <AutoMarker
          reading={reading}
          lastSuccess={lastSuccess}
          label={detail.database}
        />
      }
    >
      {report === null ? null : (
        <Rows>
          <Row
            label={wording.row.state}
            value={stateText(report.database.container.state)}
          />
          <Row
            label={detail.image}
            value={
              <code>{report.database.container.image ?? wording.unknown}</code>
            }
          />
          <Row
            label={detail.address}
            value={
              <code>
                {report.database.host}:{report.database.port}
              </code>
            }
          />
          <Row
            label={detail.namedDatabase}
            value={<code>{report.database.name}</code>}
          />
          <Row
            label={detail.schemaHead}
            value={<code>{report.database.expected_schema_revision}</code>}
          />
          <Row label={detail.migration} value={migrationText(report)} />
          <Row
            label={detail.sharedMemory}
            value={humanBytes(report.database.shared_memory_bytes)}
          />
          <Row
            label={detail.size}
            value={humanBytes(report.database.size_bytes)}
          />
          <Row
            label={detail.connections}
            value={count(report.database.connections)}
          />
        </Rows>
      )}
    </Panel>
  );
}

function migrationText(report: ServerStatusReport): string {
  if (report.database.at_head === null) {
    return wording.unknown;
  }
  if (report.database.at_head) {
    return wording.dashboard.atHead;
  }
  return stateText(report.database.schema_revision);
}

function EmbeddingPanel({
  report,
  lastSuccess,
  reading,
}: {
  report: ServerStatusReport | null;
  lastSuccess: number | null;
  reading: boolean;
}) {
  const detail = wording.dashboard;
  return (
    <Panel
      title={detail.embedding}
      marker={
        <AutoMarker
          reading={reading}
          lastSuccess={lastSuccess}
          label={detail.embedding}
        />
      }
    >
      {report === null ? null : (
        <Rows>
          <Row
            label={wording.row.state}
            value={stateText(report.embedding.container.state)}
          />
          <Row
            label={detail.image}
            value={
              <code>{report.embedding.container.image ?? wording.unknown}</code>
            }
          />
          <Row label={detail.model} value={report.embedding.model} />
          <Row
            label={detail.artifact}
            value={<code>{report.embedding.artifact}</code>}
          />
          <Row
            label={detail.address}
            value={
              <code>
                {report.embedding.host}:{report.embedding.port}
              </code>
            }
          />
          <Row label={detail.context} value={report.embedding.context_size} />
          <Row label={detail.threads} value={report.embedding.threads} />
          <Row label={detail.pooling} value={report.embedding.pooling} />
          <Row
            label={detail.normalization}
            value={report.embedding.normalization}
          />
        </Rows>
      )}
    </Panel>
  );
}

/** Render the Dashboard tab from the signed-in shell's one server-status read. */
export function Dashboard({ panel }: { panel: PanelRead<ServerStatusReport> }) {
  return (
    <div>
      <FailureNotice text={panel.failure} />
      <div className="grid">
        <ServingPanel
          report={panel.report}
          lastSuccess={panel.lastSuccess}
          reading={panel.loading}
        />
        <WebsitePanel
          report={panel.report}
          lastSuccess={panel.lastSuccess}
          reading={panel.loading}
        />
        <HostPanel
          report={panel.report}
          lastSuccess={panel.lastSuccess}
          reading={panel.loading}
        />
        <DatabasePanel
          report={panel.report}
          lastSuccess={panel.lastSuccess}
          reading={panel.loading}
        />
        <EmbeddingPanel
          report={panel.report}
          lastSuccess={panel.lastSuccess}
          reading={panel.loading}
        />
      </div>
    </div>
  );
}
