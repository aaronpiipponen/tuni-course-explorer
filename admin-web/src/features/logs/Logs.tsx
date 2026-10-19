/**
 * The Logs tab: the command log, the session inventory and the runtime and usage reads.
 *
 * The tab owns one log-session inventory read, which the session log panel and the runtime log
 * panel share, so the console discovers the stage sessions once. Every other panel owns its own
 * read, and a worker log is read only by that panel's explicit control.
 */
import { useMemo } from "react";
import { readLogSessions } from "../../api/logs";
import type { LogSessionEntry } from "../../api/types";
import type { SessionAccess } from "../../shared/StagePanel";
import { usePanelRead } from "../../shared/usePanelRead";
import { wording } from "../../shared/wording";
import { CommandLog } from "./CommandLog";
import { RuntimeLogs } from "./RuntimeLogs";
import { SessionLogs } from "./SessionLogs";
import { Usage } from "./Usage";

const sessionsRead = (signal: AbortSignal, automatic: boolean) =>
  readLogSessions(signal, automatic);

/** Render the Logs tab. */
export function Logs({
  session,
  onRefusal,
}: {
  session: SessionAccess;
  onRefusal: (status: number) => void;
}) {
  const inventory = usePanelRead(sessionsRead, {
    pollSeconds: session.pollSeconds,
    enabled: true,
    onRefusal,
    failureTextValue: wording.readFailed,
  });
  const sessions: LogSessionEntry[] = useMemo(
    () => inventory.report?.sessions ?? [],
    [inventory.report],
  );
  return (
    <div className="grid">
      <CommandLog session={session} onRefusal={onRefusal} />
      <SessionLogs
        session={session}
        onRefusal={onRefusal}
        sessions={sessions}
        sessionsFailure={inventory.failure}
        sessionsLoading={inventory.loading}
      />
      <RuntimeLogs
        session={session}
        onRefusal={onRefusal}
        sessions={sessions}
        sessionsFailure={inventory.failure}
        sessionsLoading={inventory.loading}
      />
      <Usage session={session} onRefusal={onRefusal} />
    </div>
  );
}
