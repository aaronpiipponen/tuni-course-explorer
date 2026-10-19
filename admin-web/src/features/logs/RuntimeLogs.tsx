/**
 * The Runtime logs panel: the embedding runtime log and the listed remote runtime logs.
 *
 * The embedding service's own container log reads automatically, while a translation or inference
 * runtime log lives on the worker and is read only by the explicit Read control. The panel offers
 * the embedding runtime alone when the inventory lists no remote session, and it never contacts the
 * worker while it lists its choices.
 */
import { useEffect, useRef, useState } from "react";
import { readEmbeddingLog, readSessionLog } from "../../api/logs";
import type { LogSessionEntry } from "../../api/types";
import { AutoMarker } from "../../shared/AutoMarker";
import { FailureNotice, Panel } from "../../shared/Panel";
import { Picker } from "../../shared/Picker";
import type { SessionAccess } from "../../shared/StagePanel";
import { useDemandRead } from "../../shared/useDemandRead";
import { usePanelRead } from "../../shared/usePanelRead";
import { wording } from "../../shared/wording";
import {
  DEFAULT_LOG_LINES,
  LogLineCount,
  LogReading,
  positiveWhole,
  remoteStage,
} from "./SessionLogs";

/** The picker value of the embedding service's own runtime log. */
const EMBEDDING_PICK = "embedding";

/** The stage a remote runtime log belongs to, and the source that reads it. */
const REMOTE_RUNTIME_SOURCE = "worker-runtime";

/** Render the runtime log panel over the shared session inventory. */
export function RuntimeLogs({
  session,
  onRefusal,
  sessions,
  sessionsFailure,
  sessionsLoading,
}: {
  session: SessionAccess;
  onRefusal: (status: number) => void;
  sessions: LogSessionEntry[];
  sessionsFailure: string | null;
  sessionsLoading: boolean;
}) {
  const remote = sessions.filter((entry) => remoteStage(entry.stage));
  const [picked, setPicked] = useState(EMBEDDING_PICK);
  const [lines, setLines] = useState(DEFAULT_LOG_LINES);
  const [lineDraft, setLineDraft] = useState(String(DEFAULT_LOG_LINES));
  const [lineFailure, setLineFailure] = useState<string | null>(null);
  const chosen = remote.find(
    (entry) => `${entry.stage}/${entry.session_id}` === picked,
  );

  useEffect(() => {
    if (picked !== EMBEDDING_PICK && chosen === undefined && !sessionsLoading) {
      setPicked(EMBEDDING_PICK);
    }
  }, [picked, chosen, sessionsLoading]);

  const embedding = picked === EMBEDDING_PICK;
  const local = usePanelRead(
    (signal: AbortSignal, automatic: boolean) =>
      readEmbeddingLog(lines, session.csrfToken, signal, automatic),
    {
      pollSeconds: session.pollSeconds,
      enabled: embedding,
      onRefusal,
      failureTextValue: wording.readFailed,
    },
  );
  const demand = useDemandRead(
    (signal: AbortSignal) => {
      if (chosen === undefined) {
        throw new Error("a runtime log read needs a selected session");
      }
      return readSessionLog(
        chosen.stage,
        chosen.session_id,
        REMOTE_RUNTIME_SOURCE,
        lines,
        session.csrfToken,
        signal,
      );
    },
    {
      identity: `${picked}/${lines}`,
      onRefusal,
      failureTextValue: wording.readFailed,
    },
  );
  const reloadLocal = local.reload;
  const seenLines = useRef(lines);
  useEffect(() => {
    if (seenLines.current === lines) {
      return;
    }
    seenLines.current = lines;
    reloadLocal();
  }, [lines, reloadLocal]);

  const title = wording.logs.runtimeLogs;
  const active = embedding ? local : demand;
  return (
    <Panel
      title={title}
      marker={
        <AutoMarker
          reading={active.loading}
          lastSuccess={active.lastSuccess}
          label={title}
          demand={!embedding}
        />
      }
    >
      <FailureNotice text={sessionsFailure} />
      <div className="lookup">
        <Picker
          label={wording.logs.runtimePicker}
          value={embedding ? EMBEDDING_PICK : picked}
          options={[
            {
              value: EMBEDDING_PICK,
              label: wording.logs.embeddingOption,
            },
            ...remote.map((entry) => ({
              value: `${entry.stage}/${entry.session_id}`,
              label: `${entry.stage} ${entry.session_id}`,
            })),
          ]}
          onChange={setPicked}
        />
      </div>
      <LogLineCount
        draft={lineDraft}
        onDraft={setLineDraft}
        onApply={() => {
          const applied = positiveWhole(lineDraft);
          if (applied === null) {
            setLineFailure(wording.logs.invalidLines);
            return;
          }
          setLineFailure(null);
          setLines(applied);
        }}
        failure={lineFailure}
      />
      {embedding ? null : (
        <div className="acts">
          <button className="btn" type="button" onClick={demand.reload}>
            {wording.logs.read}
          </button>
        </div>
      )}
      <LogReading
        report={embedding ? local.report : demand.report}
        failure={embedding ? local.failure : demand.failure}
      />
    </Panel>
  );
}
