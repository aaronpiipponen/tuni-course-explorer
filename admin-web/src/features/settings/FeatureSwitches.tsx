/**
 * The Feature switches panel: the two serving switches of this site's web file.
 *
 * Each switch writes its own key of `config/web.toml` through the same configuration client the
 * editor uses, and it shows the written position only after the command acknowledged it. A refused
 * write keeps the value the file holds. A value the file does not report as a boolean renders as
 * unknown rather than as an unchecked switch. The saved value reaches the serving process when that
 * process builds its settings again, so the panel states the rebuild and restart that applies it.
 */
import { useEffect, useRef, useState } from "react";
import { failureText, handleAdmissionFailure } from "../../api/http";
import {
  readConfigurationFile,
  setConfigurationValue,
  WEB_CONFIGURATION_FILE,
} from "../../api/settings";
import { AutoMarker } from "../../shared/AutoMarker";
import { FailureNotice, Panel } from "../../shared/Panel";
import type { SessionAccess } from "../../shared/StagePanel";
import { Switch } from "../../shared/Switch";
import { usePanelRead } from "../../shared/usePanelRead";
import { wording } from "../../shared/wording";

/** The two feature switches of the site, in the order the web file lists them. */
const SWITCHES = [
  {
    key: "WEB_INFERENCE_ENABLED",
    label: wording.settings.inferenceFeatures,
    detail: wording.settings.inferenceDetail,
  },
  {
    key: "WEB_EMBEDDINGS_ENABLED",
    label: wording.settings.embeddingFeatures,
    detail: wording.settings.embeddingDetail,
  },
];

/** Render the feature switches panel. */
export function FeatureSwitches({
  session,
  onRefusal,
  revision,
  onSaved,
}: {
  session: SessionAccess;
  onRefusal: (status: number) => void;
  revision: number;
  onSaved: (key: string, value: boolean) => void;
}) {
  const detail = wording.settings;
  const [writing, setWriting] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [acknowledged, setAcknowledged] = useState<{
    key: string;
    value: boolean;
  } | null>(null);
  const panel = usePanelRead(
    (signal: AbortSignal, automatic: boolean) =>
      readConfigurationFile(
        WEB_CONFIGURATION_FILE,
        session.csrfToken,
        signal,
        automatic,
      ),
    {
      pollSeconds: session.pollSeconds,
      enabled: writing === null,
      onRefusal,
      failureTextValue: wording.readFailed,
    },
  );
  const reload = panel.reload;
  const seenRevision = useRef(revision);
  useEffect(() => {
    if (seenRevision.current === revision) {
      return;
    }
    seenRevision.current = revision;
    reload();
  }, [revision, reload]);
  const seenReport = useRef(panel.report);
  useEffect(() => {
    if (seenReport.current === panel.report) {
      return;
    }
    seenReport.current = panel.report;
    setAcknowledged(null);
  }, [panel.report]);

  const onToggle = async (key: string, current: boolean): Promise<void> => {
    const next = !current;
    setWriting(key);
    setFailure(null);
    try {
      await setConfigurationValue(
        WEB_CONFIGURATION_FILE,
        key,
        JSON.stringify(next),
        session.csrfToken,
      );
      setAcknowledged({ key, value: next });
      onSaved(key, next);
    } catch (error) {
      if (handleAdmissionFailure(error, onRefusal)) {
        return;
      }
      setFailure(failureText(error, wording.writeFailed));
    } finally {
      setWriting(null);
    }
  };

  const values = panel.report?.values;
  return (
    <Panel
      title={detail.featureSwitches}
      marker={
        <AutoMarker
          reading={panel.loading}
          lastSuccess={panel.lastSuccess}
          label={detail.featureSwitches}
        />
      }
    >
      <FailureNotice text={panel.failure} />
      <FailureNotice text={failure} />
      <div className="rows two">
        {SWITCHES.map((entry) => {
          const reported = values?.[entry.key];
          const known = typeof reported === "boolean" ? reported : null;
          const value =
            acknowledged?.key === entry.key ? acknowledged.value : known;
          return (
            <div className="swline" key={entry.key}>
              <div>
                <div>{entry.label}</div>
                <div className="note">{entry.detail}</div>
              </div>
              {value === null ? (
                <p className="note" role="status">
                  {wording.unknown}
                </p>
              ) : (
                <Switch
                  label={entry.label}
                  checked={value}
                  disabled={writing !== null}
                  onChange={() => void onToggle(entry.key, value)}
                />
              )}
            </div>
          );
        })}
      </div>
    </Panel>
  );
}
