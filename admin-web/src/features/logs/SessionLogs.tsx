/**
 * The Session logs panel: one listed session's own server streams and its worker log.
 *
 * The session and the source come from the fixed vocabularies the listing and the source owner
 * define, and the selected pair is one of the listed receipts. A server stream and the keepalive
 * file read automatically, while the worker's own runner log is read only by the explicit Read
 * control. The panel renders the bounded read of its owning command and distinguishes a refusal, an
 * absent log, an available empty log and a log that holds lines.
 *
 * This module also owns the bounded-read presentation, the positive whole-line control, the
 * whole-count reading and the remote-stage predicate the sibling runtime panel shares, because the
 * two panels read the same bounded log shape of the same route.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { readSessionLog } from "../../api/logs";
import type {
  LogReadReport,
  LogSessionEntry,
  LogSource,
  StageName,
} from "../../api/types";
import { AutoMarker } from "../../shared/AutoMarker";
import { FailureNotice, Panel } from "../../shared/Panel";
import { Picker } from "../../shared/Picker";
import type { SessionAccess } from "../../shared/StagePanel";
import { useDemandRead } from "../../shared/useDemandRead";
import { usePanelRead } from "../../shared/usePanelRead";
import { wording } from "../../shared/wording";

/** The line count a log panel reads before the operator applies another one. */
export const DEFAULT_LOG_LINES = 200;

/** The two server-side streams every listed session holds. */
const SERVER_SOURCES: LogSource[] = ["server-stdout", "server-stderr"];

/** The two sources a remote worker session adds, its own runner log being the remote read. */
const REMOTE_SOURCES: LogSource[] = ["keepalive", "worker-runner"];

const REMOTE_SOURCE: LogSource = "worker-runner";

/** Report whether one stage's session keeps its log on the worker. */
export function remoteStage(stage: StageName): boolean {
  return stage === "translation" || stage === "inference";
}

/** Return the fixed source choices one stage offers. */
function sourcesFor(stage: StageName): LogSource[] {
  return remoteStage(stage)
    ? [...SERVER_SOURCES, ...REMOTE_SOURCES]
    : SERVER_SOURCES;
}

/** Render one bounded log read, or the state that distinguishes its outcomes. */
export function LogReading({
  report,
  failure,
}: {
  report: LogReadReport | null;
  failure: string | null;
}) {
  if (failure !== null) {
    return <FailureNotice text={failure} />;
  }
  if (report === null) {
    return <p className="note">{wording.logs.noRead}</p>;
  }
  if (!report.available) {
    return <p className="note">{wording.logs.unavailable}</p>;
  }
  if (report.text === null || report.text === "") {
    return <p className="note">{wording.logs.empty}</p>;
  }
  return <pre className="log-scroll">{report.text}</pre>;
}

/** Render one positive whole-line input with its Apply control. */
export function LogLineCount({
  draft,
  onDraft,
  onApply,
  failure,
}: {
  draft: string;
  onDraft: (value: string) => void;
  onApply: () => void;
  failure: string | null;
}) {
  return (
    <>
      <div className="lookup">
        <input
          aria-label={wording.logs.linesInput}
          value={draft}
          spellCheck={false}
          onChange={(event) => onDraft(event.target.value)}
        />
        <span className="unit">{wording.logs.linesUnit}</span>
        <button className="btn" type="button" onClick={onApply}>
          {wording.logs.apply}
        </button>
      </div>
      <FailureNotice text={failure} />
    </>
  );
}

/** Return one positive whole count, or null for anything else. */
export function positiveWhole(draft: string): number | null {
  const value = Number(draft.trim());
  return Number.isInteger(value) && value > 0 ? value : null;
}

/** Return the bounded read report of one selected session and source, or null for another one. */
function readingFor(
  report: LogReadReport | null,
  stage: StageName,
  sessionId: string,
  source: LogSource,
): LogReadReport | null {
  if (report === null) {
    return null;
  }
  if (
    report.stage !== stage ||
    report.session_id !== sessionId ||
    report.source !== source
  ) {
    return null;
  }
  return report;
}

/** Render the session log panel over one listed session of the shared inventory. */
export function SessionLogs({
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
  const [stage, setStage] = useState<StageName | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [source, setSource] = useState<LogSource>("server-stdout");
  const [lines, setLines] = useState(DEFAULT_LOG_LINES);
  const [lineDraft, setLineDraft] = useState(String(DEFAULT_LOG_LINES));
  const [lineFailure, setLineFailure] = useState<string | null>(null);
  const listed = useRef(false);

  useEffect(() => {
    if (listed.current || sessions.length === 0) {
      return;
    }
    listed.current = true;
    setStage(sessions[0].stage);
    setSessionId(sessions[0].session_id);
  }, [sessions]);

  useEffect(() => {
    if (
      stage === null ||
      sessionId === null ||
      sessionsLoading ||
      sessions.some(
        (entry) => entry.stage === stage && entry.session_id === sessionId,
      )
    ) {
      return;
    }
    setStage(null);
    setSessionId(null);
  }, [sessions, sessionsLoading, stage, sessionId]);

  const selected = stage !== null && sessionId !== null;
  const remote = source === REMOTE_SOURCE;
  const localEnabled = selected && !remote;
  const readingKey = `${stage ?? "none"}/${sessionId ?? "none"}/${source}/${lines}`;
  const readLocal = useCallback(
    (signal: AbortSignal, automatic: boolean): Promise<LogReadReport> => {
      if (stage === null || sessionId === null) {
        throw new Error("a session log read needs a selected session");
      }
      return readSessionLog(
        stage,
        sessionId,
        source,
        lines,
        session.csrfToken,
        signal,
        automatic,
      );
    },
    [stage, sessionId, source, lines, session.csrfToken],
  );
  const local = usePanelRead(readLocal, {
    pollSeconds: session.pollSeconds,
    enabled: localEnabled,
    onRefusal,
    failureTextValue: wording.readFailed,
  });
  const demand = useDemandRead(
    (signal: AbortSignal) => {
      if (stage === null || sessionId === null) {
        throw new Error("a session log read needs a selected session");
      }
      return readSessionLog(
        stage,
        sessionId,
        REMOTE_SOURCE,
        lines,
        session.csrfToken,
        signal,
      );
    },
    {
      identity: `${stage ?? "none"}/${sessionId ?? "none"}/${REMOTE_SOURCE}/${lines}`,
      onRefusal,
      failureTextValue: wording.readFailed,
    },
  );
  const reloadLocal = local.reload;
  // A change while the local read is already enabled reloads it. The hook alone reads when the
  // local source becomes enabled, including a first selection and a worker-to-server transition.
  const selectedKey = selected ? readingKey : null;
  const previousKey = useRef<string | null>(null);
  const previousLocalEnabled = useRef(false);
  useEffect(() => {
    const wasEnabled = previousLocalEnabled.current;
    const previous = previousKey.current;
    previousKey.current = selectedKey;
    previousLocalEnabled.current = localEnabled;
    if (
      !wasEnabled ||
      !localEnabled ||
      previous === null ||
      previous === selectedKey
    ) {
      return;
    }
    reloadLocal();
  }, [selectedKey, localEnabled, reloadLocal]);

  const choices = useMemo(
    () => (stage === null ? SERVER_SOURCES : sourcesFor(stage)),
    [stage],
  );
  const title = wording.logs.sessionLogs;
  const active = remote ? demand : local;
  const report =
    stage !== null && sessionId !== null
      ? remote
        ? demand.report
        : readingFor(local.report, stage, sessionId, source)
      : null;

  return (
    <Panel
      title={title}
      marker={
        <AutoMarker
          reading={active.loading}
          lastSuccess={active.lastSuccess}
          label={title}
          demand={remote}
        />
      }
    >
      <FailureNotice text={sessionsFailure} />
      {sessions.length === 0 ? (
        sessionsLoading || sessionsFailure !== null ? null : (
          <p className="note">{wording.logs.noSessions}</p>
        )
      ) : (
        <div className="lookup">
          <Picker
            label={wording.logs.sessionPicker}
            value={selected ? `${stage}/${sessionId}` : ""}
            options={sessions.map((entry) => ({
              value: `${entry.stage}/${entry.session_id}`,
              label: `${entry.stage} ${entry.session_id}`,
            }))}
            onChange={(next) => {
              const entry = sessions.find(
                (candidate) =>
                  `${candidate.stage}/${candidate.session_id}` === next,
              );
              if (entry === undefined) {
                return;
              }
              setStage(entry.stage);
              setSessionId(entry.session_id);
              if (
                !remoteStage(entry.stage) &&
                !SERVER_SOURCES.includes(source)
              ) {
                setSource("server-stdout");
              }
            }}
          />
          <Picker
            label={wording.logs.sourcePicker}
            value={source}
            options={choices.map((candidate) => ({
              value: candidate,
              label: candidate,
            }))}
            onChange={(next) => setSource(next as LogSource)}
          />
        </div>
      )}
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
      {remote && selected ? (
        <div className="acts">
          <button className="btn" type="button" onClick={demand.reload}>
            {wording.logs.read}
          </button>
        </div>
      ) : null}
      {selected ? (
        <LogReading
          report={report}
          failure={remote ? demand.failure : local.failure}
        />
      ) : null}
    </Panel>
  );
}
