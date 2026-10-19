/**
 * The Usage panel: the recorded course-exploration requests of one applied window.
 *
 * The applied window reads automatically through the fixed usage report, which prunes the records
 * past the configured retention. The panel shows the window bounds, the request total and the mean
 * duration, and one row per returned route. It reports no administration command count and no
 * invented mean for a window that holds no request.
 */
import { useEffect, useRef, useState } from "react";
import { readUsage } from "../../api/logs";
import { AutoMarker } from "../../shared/AutoMarker";
import { count, moment, shortDuration } from "../../shared/format";
import { DataTable, FailureNotice, Panel, Row, Rows } from "../../shared/Panel";
import type { SessionAccess } from "../../shared/StagePanel";
import { usePanelRead } from "../../shared/usePanelRead";
import { wording } from "../../shared/wording";
import { positiveWhole } from "./SessionLogs";

/** The window the usage panel reads before the operator applies another one. */
const DEFAULT_USAGE_HOURS = 24;

/** Render the usage panel. */
export function Usage({
  session,
  onRefusal,
}: {
  session: SessionAccess;
  onRefusal: (status: number) => void;
}) {
  const detail = wording.logs;
  const [hours, setHours] = useState(DEFAULT_USAGE_HOURS);
  const [draft, setDraft] = useState(String(DEFAULT_USAGE_HOURS));
  const [inputFailure, setInputFailure] = useState<string | null>(null);
  const panel = usePanelRead(
    (signal: AbortSignal, automatic: boolean) =>
      readUsage(hours, session.csrfToken, signal, automatic),
    {
      pollSeconds: session.pollSeconds,
      enabled: true,
      onRefusal,
      failureTextValue: wording.readFailed,
    },
  );
  const reload = panel.reload;
  const seenHours = useRef(hours);
  useEffect(() => {
    if (seenHours.current === hours) {
      return;
    }
    seenHours.current = hours;
    reload();
  }, [hours, reload]);

  const report = panel.report;
  return (
    <Panel
      title={detail.usage}
      span={12}
      marker={
        <AutoMarker
          reading={panel.loading}
          lastSuccess={panel.lastSuccess}
          label={detail.usage}
        />
      }
    >
      <div className="lookup">
        <input
          aria-label={detail.hoursInput}
          value={draft}
          spellCheck={false}
          onChange={(event) => setDraft(event.target.value)}
        />
        <span className="unit">{detail.hoursUnit}</span>
        <button
          className="btn"
          type="button"
          onClick={() => {
            const applied = positiveWhole(draft);
            if (applied === null) {
              setInputFailure(detail.invalidHours);
              return;
            }
            setInputFailure(null);
            setHours(applied);
          }}
        >
          {detail.apply}
        </button>
      </div>
      <FailureNotice text={inputFailure} />
      <FailureNotice text={panel.failure} />
      {report === null ? null : (
        <>
          <Rows>
            <Row
              label={detail.window}
              value={detail.windowRange
                .replace("{start}", moment(report.window_start))
                .replace("{end}", moment(report.window_end))}
            />
            <Row label={detail.requests} value={count(report.requests)} />
            <Row
              label={detail.mean}
              value={
                report.mean_duration_seconds === null
                  ? wording.unknown
                  : shortDuration(report.mean_duration_seconds)
              }
            />
          </Rows>
          {report.routes.length === 0 ? (
            <p className="note">{detail.noWindow}</p>
          ) : (
            <DataTable
              head={[detail.route, detail.requests, detail.mean]}
              rows={report.routes.map((route) => [
                <code key="route">{route.route}</code>,
                count(route.requests),
                shortDuration(route.mean_duration_seconds),
              ])}
              align={["", "r", "r"]}
            />
          )}
        </>
      )}
    </Panel>
  );
}
