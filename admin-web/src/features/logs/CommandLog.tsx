/**
 * The Command log panel: the retained administration command log its owner reports.
 *
 * The report is read automatically and rendered newest first as a display copy, while the report
 * keeps the owner's own oldest-first order. Each row carries its own command label, exit status,
 * duration, outcome and the one safe failure line that belongs to it, and no row invents captured
 * output or an argument.
 */
import { readCommandLog } from "../../api/logs";
import type { CommandLogEntry, CommandOutcome } from "../../api/types";
import type { ReactNode } from "react";
import { AutoMarker } from "../../shared/AutoMarker";
import { moment, shortDuration } from "../../shared/format";
import { DataTable, FailureNotice, Panel } from "../../shared/Panel";
import type { SessionAccess } from "../../shared/StagePanel";
import { usePanelRead } from "../../shared/usePanelRead";
import { wording } from "../../shared/wording";

const commandLogRead = (signal: AbortSignal, automatic: boolean) =>
  readCommandLog(signal, automatic);

const OUTCOME_CLASS: Record<CommandOutcome, string> = {
  success: "tag ok",
  failure: "tag no",
  login: "tag",
  "failed-login": "tag no",
  lock: "tag no",
};

/** Return the one fixed outcome word of a retained entry. */
function outcomeText(outcome: CommandOutcome): string {
  if (outcome === "success") {
    return wording.logs.ok;
  }
  if (outcome === "failure") {
    return wording.logs.failed;
  }
  if (outcome === "login") {
    return wording.logs.login;
  }
  if (outcome === "failed-login") {
    return wording.logs.failedLogin;
  }
  return wording.logs.lock;
}

function entryRow(entry: CommandLogEntry): ReactNode[] {
  return [
    moment(entry.time),
    <span key="command">
      <code>{entry.command}</code>
      {entry.failure_line === null ? null : (
        <span className="fail">{entry.failure_line}</span>
      )}
    </span>,
    entry.exit_code,
    shortDuration(entry.duration_seconds),
    <span key="result" className={OUTCOME_CLASS[entry.result]}>
      {outcomeText(entry.result)}
    </span>,
  ];
}

/** Render the command log panel. */
export function CommandLog({
  session,
  onRefusal,
}: {
  session: SessionAccess;
  onRefusal: (status: number) => void;
}) {
  const detail = wording.logs;
  const panel = usePanelRead(commandLogRead, {
    pollSeconds: session.pollSeconds,
    enabled: true,
    onRefusal,
    failureTextValue: wording.readFailed,
  });
  const newestFirst = [...(panel.report?.entries ?? [])].reverse();
  return (
    <Panel
      title={detail.commandLog}
      span={12}
      marker={
        <AutoMarker
          reading={panel.loading}
          lastSuccess={panel.lastSuccess}
          label={detail.commandLog}
        />
      }
    >
      <FailureNotice text={panel.failure} />
      <DataTable
        head={[
          detail.time,
          detail.command,
          detail.exit,
          detail.duration,
          detail.result,
        ]}
        rows={newestFirst.map(entryRow)}
        align={["", "", "r", "r", "c"]}
        scrollClassName="log-scroll"
      />
    </Panel>
  );
}
