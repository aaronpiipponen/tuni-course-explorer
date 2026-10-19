/**
 * The Backups panel: the files under the backup root and their one explicit deletion.
 *
 * The listing reads automatically and reports the file name, its modification time and its size, so
 * no kind or creation time is inferred from a name. Every listed row offers deletion, the
 * confirmation names the exact listed file, cancelling posts nothing, and confirming closes the
 * dialog before its command starts. A successful deletion reloads the listing, a refused one keeps
 * it and the panel shows the command's own failure. The empty note describes a successful read that
 * lists no file.
 */
import { useState } from "react";
import { failureText, handleAdmissionFailure } from "../../api/http";
import { deleteBackup, readBackups } from "../../api/settings";
import type { BackupFile } from "../../api/types";
import { AutoMarker } from "../../shared/AutoMarker";
import { ConfirmDialog } from "../../shared/ConfirmDialog";
import { humanBytes, moment } from "../../shared/format";
import { DataTable, FailureNotice, Panel } from "../../shared/Panel";
import type { SessionAccess } from "../../shared/StagePanel";
import { usePanelRead } from "../../shared/usePanelRead";
import { wording } from "../../shared/wording";

const backupsRead = (signal: AbortSignal, automatic: boolean) =>
  readBackups(signal, automatic);

/** Render the backup cleanup panel. */
export function Backups({
  session,
  onRefusal,
}: {
  session: SessionAccess;
  onRefusal: (status: number) => void;
}) {
  const detail = wording.settings;
  const panel = usePanelRead(backupsRead, {
    pollSeconds: session.pollSeconds,
    enabled: true,
    onRefusal,
    failureTextValue: wording.readFailed,
  });
  const [confirming, setConfirming] = useState<BackupFile | null>(null);
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
      await deleteBackup(target.name, session.csrfToken);
      panel.reload();
    } catch (error) {
      if (handleAdmissionFailure(error, onRefusal)) {
        return;
      }
      setFailure(failureText(error, wording.writeFailed));
    } finally {
      setPending(false);
    }
  };

  const backups = panel.report?.backups ?? null;
  return (
    <Panel
      title={detail.backups}
      marker={
        <AutoMarker
          reading={panel.loading}
          lastSuccess={panel.lastSuccess}
          label={detail.backups}
        />
      }
    >
      <FailureNotice text={panel.failure} />
      {backups !== null && backups.length === 0 ? (
        <p className="note">{detail.noBackups}</p>
      ) : backups === null ? null : (
        <DataTable
          head={[detail.file, detail.modified, detail.size, ""]}
          rows={backups.map((entry) => [
            <code key="name">{entry.name}</code>,
            moment(entry.modified_at),
            humanBytes(entry.size_bytes),
            <button
              key="delete"
              className="btn xs danger"
              type="button"
              disabled={pending}
              onClick={() => setConfirming(entry)}
            >
              {wording.inference.delete}
            </button>,
          ])}
          align={["", "", "r", ""]}
        />
      )}
      <FailureNotice text={failure} />
      <ConfirmDialog
        open={confirming !== null}
        title={detail.deleteBackup}
        message={
          confirming === null
            ? ""
            : detail.backupMessage.replace("{name}", confirming.name)
        }
        pending={pending}
        onCancel={() => setConfirming(null)}
        onConfirm={() => void onConfirm()}
      />
    </Panel>
  );
}
