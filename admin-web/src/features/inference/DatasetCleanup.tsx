/**
 * The Dataset cleanup panel: the retained chain listing and its one explicit deletion.
 *
 * The listing reads automatically while the site reports its selection enabled, and is selected-first
 * as its owning command returns it. Every non-selected row, the initial dataset included, offers
 * deletion, and the selected row shows the selected marker in place of that control. A confirmation
 * names the exact dataset id and database name of the row it belongs to, cancelling sends nothing,
 * and confirming posts only that listed dataset id. The dialog closes when the confirmed command
 * starts, a successful deletion refreshes the listing, and a failed one keeps the row and shows the
 * command's own failure in the panel. A disabled site states its reason in place of the listing and
 * its rows, so a retained row or open confirmation is not shown.
 */
import { useState } from "react";
import { failureText, handleAdmissionFailure } from "../../api/http";
import { deleteDataset, readDatasets } from "../../api/inference";
import type { DatasetListEntry } from "../../api/types";
import { AutoMarker } from "../../shared/AutoMarker";
import { ConfirmDialog } from "../../shared/ConfirmDialog";
import { DataTable, FailureNotice, Panel } from "../../shared/Panel";
import type { SessionAccess } from "../../shared/StagePanel";
import { usePanelRead } from "../../shared/usePanelRead";
import { wording } from "../../shared/wording";

const datasetsRead = (signal: AbortSignal, automatic: boolean) =>
  readDatasets(signal, automatic);

/** Render the dataset cleanup panel. */
export function DatasetCleanup({
  session,
  onRefusal,
  selectionEnabled,
  selectionFailure,
}: {
  session: SessionAccess;
  onRefusal: (status: number) => void;
  selectionEnabled: boolean | null;
  selectionFailure: string | null;
}) {
  const detail = wording.inference;
  const panel = usePanelRead(datasetsRead, {
    pollSeconds: session.pollSeconds,
    enabled: selectionEnabled === true,
    onRefusal,
    failureTextValue: wording.readFailed,
  });
  const [confirming, setConfirming] = useState<DatasetListEntry | null>(null);
  const [pending, setPending] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  const onConfirm = async (): Promise<void> => {
    if (confirming === null) {
      return;
    }
    const target = confirming;
    setConfirming(null);
    setPending(true);
    setFailure(null);
    try {
      await deleteDataset(target.dataset_id, session.csrfToken);
      panel.reload();
    } catch (error) {
      setFailure(failureText(error, wording.writeFailed));
      handleAdmissionFailure(error, onRefusal);
    } finally {
      setPending(false);
    }
  };

  const datasets = panel.report?.datasets ?? [];
  const rows = datasets.map((entry) => [
    <b key="id">{entry.dataset_id}</b>,
    <code key="database">{entry.database_name}</code>,
    entry.dump_path ?? wording.unknown,
    entry.selected ? (
      <span key="selected" className="tag ok">
        {detail.selectedTag}
      </span>
    ) : (
      <button
        key="delete"
        className="btn xs danger dataset-delete"
        type="button"
        disabled={pending}
        onClick={() => setConfirming(entry)}
      >
        {detail.delete}
      </button>
    ),
  ]);

  return (
    <Panel
      title={detail.datasetCleanup}
      marker={
        selectionEnabled === true ||
        (selectionEnabled === null && selectionFailure === null) ? (
          <AutoMarker
            reading={selectionEnabled === null || panel.loading}
            lastSuccess={panel.lastSuccess}
            label={detail.datasetCleanup}
          />
        ) : undefined
      }
    >
      {selectionEnabled === true ? (
        <>
          <FailureNotice text={panel.failure} />
          <DataTable
            head={[detail.datasetName, detail.namedDatabase, detail.dump, ""]}
            rows={rows}
            align={["", "", "", ""]}
          />
          <FailureNotice text={failure} />
          <ConfirmDialog
            open={confirming !== null}
            title={detail.deleteDataset}
            message={
              confirming === null
                ? ""
                : detail.deleteMessage
                    .replace("{dataset_id}", confirming.dataset_id)
                    .replace("{database_name}", confirming.database_name)
            }
            pending={pending}
            onCancel={() => setConfirming(null)}
            onConfirm={() => void onConfirm()}
          />
        </>
      ) : (
        <>
          <FailureNotice text={selectionFailure} />
          {selectionFailure === null && selectionEnabled === false ? (
            <p className="note">{wording.selectionDisabled}</p>
          ) : null}
        </>
      )}
    </Panel>
  );
}
