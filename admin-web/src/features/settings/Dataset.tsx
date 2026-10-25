/**
 * The Dataset panel: the serving pointer, the selected dataset and its two maintenance actions.
 *
 * The panel reuses the retained-dataset listing for the selected entry and the signed-in shell's
 * shared dashboard report for the serving pointer, the selection state and the schema facts.
 * Enrollment and migration are two separate confirmed actions, and each renders the receipt or the
 * verification its own command returned and refreshes both the listing and the shared report. The
 * receipt's recorded Alembic revision and the live database head stay distinct observations, and a
 * refused action leaves the data with its own failure. The listing reads only while the site
 * reports its selection enabled, so a disabled site states that reason instead of repeating a
 * refused read.
 */
import { useState } from "react";
import { failureText, handleAdmissionFailure } from "../../api/http";
import { readDatasets } from "../../api/inference";
import { migrateDataset, setupDataset } from "../../api/settings";
import type {
  DatasetReceipt,
  DatasetVerification,
  ServerStatusReport,
} from "../../api/types";
import { AutoMarker } from "../../shared/AutoMarker";
import { ConfirmDialog } from "../../shared/ConfirmDialog";
import { count } from "../../shared/format";
import { FailureNotice, Panel, Row, Rows } from "../../shared/Panel";
import type { SessionAccess } from "../../shared/StagePanel";
import { usePanelRead, type PanelRead } from "../../shared/usePanelRead";
import { wording } from "../../shared/wording";

const datasetsRead = (signal: AbortSignal, automatic: boolean) =>
  readDatasets(signal, automatic);

/** Render the number of tables one verification read counted. */
function verifiedTables(verification: DatasetVerification): string {
  return count(Object.keys(verification.table_row_counts).length);
}

/** Render the dataset panel. */
export function Dataset({
  session,
  onRefusal,
  dashboard,
}: {
  session: SessionAccess;
  onRefusal: (status: number) => void;
  dashboard: PanelRead<ServerStatusReport>;
}) {
  const detail = wording.settings;
  const selectionEnabled = dashboard.report?.serving.selection_enabled ?? null;
  const listing = usePanelRead(datasetsRead, {
    pollSeconds: session.pollSeconds,
    enabled: selectionEnabled === true,
    onRefusal,
    failureTextValue: wording.readFailed,
  });
  const [confirming, setConfirming] = useState<"enroll" | "migrate" | null>(
    null,
  );
  const [pending, setPending] = useState(false);
  const [receipt, setReceipt] = useState<DatasetReceipt | null>(null);
  const [verification, setVerification] = useState<DatasetVerification | null>(
    null,
  );
  const [failure, setFailure] = useState<string | null>(null);

  const onEnroll = async (): Promise<void> => {
    setPending(true);
    setFailure(null);
    try {
      setReceipt(await setupDataset(session.csrfToken));
      setVerification(null);
      listing.reload();
      dashboard.reload();
    } catch (error) {
      if (handleAdmissionFailure(error, onRefusal)) {
        return;
      }
      setFailure(failureText(error, wording.writeFailed));
    } finally {
      setPending(false);
    }
  };

  const onMigrate = async (): Promise<void> => {
    setPending(true);
    setFailure(null);
    try {
      setVerification(await migrateDataset(session.csrfToken));
      setReceipt(null);
      listing.reload();
      dashboard.reload();
    } catch (error) {
      if (handleAdmissionFailure(error, onRefusal)) {
        return;
      }
      setFailure(failureText(error, wording.writeFailed));
    } finally {
      setPending(false);
    }
  };

  const selected = (listing.report?.datasets ?? []).find(
    (entry) => entry.selected,
  );
  const serving = dashboard.report?.serving;
  const database = dashboard.report?.database;
  return (
    <Panel
      title={detail.dataset}
      marker={
        selectionEnabled === true ||
        (selectionEnabled === null && dashboard.failure === null) ? (
          <AutoMarker
            reading={selectionEnabled === null || listing.loading}
            lastSuccess={listing.lastSuccess}
            label={detail.dataset}
          />
        ) : undefined
      }
    >
      <FailureNotice text={dashboard.failure} />
      {selectionEnabled === true ? (
        <FailureNotice text={listing.failure} />
      ) : null}
      <Rows>
        <Row
          label={wording.dashboard.pointer}
          value={<code>{serving?.pointer ?? wording.unknown}</code>}
        />
        {selectionEnabled === true ? (
          <>
            <Row
              label={wording.dashboard.selectedDataset}
              value={
                selected?.dataset_id ?? serving?.dataset_id ?? wording.unknown
              }
            />
            <Row
              label={wording.dashboard.kind}
              value={selected?.kind ?? serving?.kind ?? wording.unknown}
            />
            <Row
              label={wording.dashboard.namedDatabase}
              value={
                selected === undefined ? (
                  wording.unknown
                ) : (
                  <code>{selected.database_name}</code>
                )
              }
            />
          </>
        ) : null}
        <Row
          label={detail.recordedHead}
          value={
            <code>{serving?.receipt_schema_revision ?? wording.unknown}</code>
          }
        />
        <Row
          label={detail.liveHead}
          value={<code>{database?.schema_revision ?? wording.unknown}</code>}
        />
        <Row
          label={wording.dashboard.atHead}
          value={
            database?.at_head === null || database?.at_head === undefined
              ? wording.unknown
              : database.at_head
                ? wording.yes
                : wording.no
          }
        />
      </Rows>
      {selectionEnabled === false && dashboard.failure === null ? (
        <p className="note">{wording.selectionDisabled}</p>
      ) : null}
      {receipt === null ? null : (
        <p className="note">
          {detail.datasetReceipt
            .replace("{dataset_id}", receipt.dataset_id)
            .replace("{kind}", receipt.kind)
            .replace("{database_name}", receipt.database_name)}
        </p>
      )}
      {receipt === null ? null : (
        <Rows>
          <Row
            label={detail.recordedHead}
            value={<code>{receipt.verification.alembic_revision}</code>}
          />
          <Row
            label={detail.verifiedTables}
            value={verifiedTables(receipt.verification)}
          />
        </Rows>
      )}
      {verification === null ? null : (
        <Rows>
          <Row
            label={detail.liveHead}
            value={<code>{verification.alembic_revision}</code>}
          />
          <Row
            label={detail.verifiedTables}
            value={verifiedTables(verification)}
          />
        </Rows>
      )}
      <div className="acts">
        <button
          className="btn p"
          type="button"
          disabled={pending}
          onClick={() => setConfirming("enroll")}
        >
          {detail.enroll}
        </button>
        <button
          className="btn"
          type="button"
          disabled={pending}
          onClick={() => setConfirming("migrate")}
        >
          {detail.migrate}
        </button>
      </div>
      <FailureNotice text={failure} />
      <ConfirmDialog
        open={confirming !== null}
        title={confirming === "migrate" ? detail.migrate : detail.enroll}
        message={
          confirming === "migrate"
            ? detail.migrateConfirm
            : detail.enrollConfirm
        }
        pending={pending}
        onCancel={() => setConfirming(null)}
        onConfirm={() => {
          const action = confirming;
          setConfirming(null);
          if (action === "migrate") {
            void onMigrate();
          } else if (action === "enroll") {
            void onEnroll();
          }
        }}
      />
    </Panel>
  );
}
