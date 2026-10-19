/**
 * The Configuration panel: every key of one listed file, with a file-level Save.
 *
 * The file list reads automatically and starts with no file open. The open file reads automatically
 * while its drafts match the values the server reported, and polling stops while a key is edited or
 * a save runs. A save parses every changed draft before it posts anything, then saves the changed
 * keys one at a time in report order. The first refused key stops the sequence, which leaves the
 * unsaved drafts in place and reports the saved and unsaved counts rather than a complete success.
 * A value of one key that the operator has not edited follows the file, and the operator's own
 * edits stay untouched. Values live only in this mounted panel.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { failureText, handleAdmissionFailure } from "../../api/http";
import {
  readConfigurationFile,
  readConfigurationFiles,
  setConfigurationValue,
  WEB_CONFIGURATION_FILE,
} from "../../api/settings";
import type { JsonValue } from "../../api/types";
import { AutoMarker } from "../../shared/AutoMarker";
import { FailureNotice, Panel } from "../../shared/Panel";
import type { SessionAccess } from "../../shared/StagePanel";
import { usePanelRead } from "../../shared/usePanelRead";
import { wording } from "../../shared/wording";

/** One parsed draft: the JSON literal its key accepts and the value it decodes to. */
interface DraftValue {
  literal: string;
  value: JsonValue;
}

const filesRead = (signal: AbortSignal, automatic: boolean) =>
  readConfigurationFiles(signal, automatic);

/** Return one configuration value's editable text: a string's own contents, and JSON otherwise. */
function draftText(value: JsonValue): string {
  if (value === null) {
    return "";
  }
  return typeof value === "string" ? value : JSON.stringify(value);
}

/** Return the drafts of every key of one read file, in the order the file holds them. */
function draftsOf(values: Record<string, JsonValue>): Record<string, string> {
  const drafts: Record<string, string> = {};
  for (const key of Object.keys(values)) {
    drafts[key] = draftText(values[key]);
  }
  return drafts;
}

/** Return the drafts with every unedited key following the values the read reported. */
function refreshPristine(
  drafts: Record<string, string>,
  previous: Record<string, JsonValue>,
  values: Record<string, JsonValue>,
): Record<string, string> {
  const refreshed: Record<string, string> = { ...drafts };
  for (const key of Object.keys(values)) {
    const prior = previous[key];
    const current = refreshed[key];
    if (
      current !== undefined &&
      prior !== undefined &&
      current !== draftText(prior)
    ) {
      continue;
    }
    refreshed[key] = draftText(values[key]);
  }
  return refreshed;
}

/** Parse one changed draft into the literal its key accepts, or report it as unreadable. */
function parseDraft(stored: JsonValue, text: string): DraftValue | null {
  if (stored === null || typeof stored === "string") {
    return { literal: JSON.stringify(text), value: text };
  }
  try {
    const decoded: JsonValue = JSON.parse(text);
    return { literal: JSON.stringify(decoded), value: decoded };
  } catch (error) {
    if (!(error instanceof SyntaxError)) {
      throw error;
    }
    return null;
  }
}

/** Render the configuration panel. */
export function Configuration({
  session,
  onRefusal,
  webUpdate,
  onWebSaved,
}: {
  session: SessionAccess;
  onRefusal: (status: number) => void;
  webUpdate: { key: string; value: boolean } | null;
  onWebSaved: () => void;
}) {
  const detail = wording.settings;
  const [file, setFile] = useState<string | null>(null);
  const [draft, setDraft] = useState<Record<string, string> | null>(null);
  const [saved, setSaved] = useState<Record<string, JsonValue> | null>(null);
  const [loadedFile, setLoadedFile] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [summary, setSummary] = useState<string | null>(null);
  const savedRef = useRef<Record<string, JsonValue> | null>(null);

  useEffect(() => {
    savedRef.current = saved;
  }, [saved]);

  const files = usePanelRead(filesRead, {
    pollSeconds: session.pollSeconds,
    enabled: true,
    onRefusal,
    failureTextValue: wording.readFailed,
  });
  const changed = useMemo(() => {
    if (file === null || draft === null || saved === null) {
      return [];
    }
    return Object.keys(saved).filter(
      (key) => draft[key] !== draftText(saved[key]),
    );
  }, [file, draft, saved]);

  const readOpenFile = useCallback(
    (signal: AbortSignal, automatic: boolean) => {
      if (file === null) {
        throw new Error("a configuration read needs a selected file");
      }
      return readConfigurationFile(file, session.csrfToken, signal, automatic);
    },
    [file, session.csrfToken],
  );
  const openRead = usePanelRead(readOpenFile, {
    pollSeconds: session.pollSeconds,
    enabled: file !== null && changed.length === 0 && !pending,
    onRefusal,
    failureTextValue: wording.readFailed,
  });
  const reloadOpenFile = openRead.reload;
  const report = openRead.report;

  useEffect(() => {
    if (report === null || file === null || report.file !== file) {
      return;
    }
    const previous = savedRef.current;
    if (loadedFile !== file || previous === null) {
      setLoadedFile(file);
      setSaved(report.values);
      setDraft(draftsOf(report.values));
      setFailure(null);
      setSummary(null);
      return;
    }
    setSaved(report.values);
    setDraft((current) =>
      current === null
        ? draftsOf(report.values)
        : refreshPristine(current, previous, report.values),
    );
  }, [report, file, loadedFile]);

  const applied = useRef<{ key: string; value: boolean } | null>(null);
  useEffect(() => {
    if (webUpdate === null || applied.current === webUpdate) {
      return;
    }
    applied.current = webUpdate;
    const previous = savedRef.current;
    if (
      file !== WEB_CONFIGURATION_FILE ||
      previous === null ||
      previous[webUpdate.key] === undefined
    ) {
      return;
    }
    setSaved((current) =>
      current === null
        ? current
        : { ...current, [webUpdate.key]: webUpdate.value },
    );
    setDraft((current) => {
      if (
        current === null ||
        current[webUpdate.key] !== draftText(previous[webUpdate.key])
      ) {
        return current;
      }
      return { ...current, [webUpdate.key]: draftText(webUpdate.value) };
    });
  }, [webUpdate, file]);

  const onSelect = (name: string): void => {
    if (name === file) {
      return;
    }
    setFile(name);
    setDraft(null);
    setSaved(null);
    setLoadedFile(null);
    setFailure(null);
    setSummary(null);
    reloadOpenFile();
  };

  const onSave = async (): Promise<void> => {
    const currentFile = file;
    const currentDraft = draft;
    const currentSaved = saved;
    if (
      currentFile === null ||
      currentDraft === null ||
      currentSaved === null ||
      changed.length === 0
    ) {
      return;
    }
    const keys = changed;
    const parsed: Array<[string, DraftValue]> = [];
    for (const key of keys) {
      const decoded = parseDraft(currentSaved[key], currentDraft[key]);
      if (decoded === null) {
        setFailure(detail.invalidValue.replace("{key}", key));
        setSummary(null);
        return;
      }
      parsed.push([key, decoded]);
    }
    setPending(true);
    setFailure(null);
    setSummary(null);
    let written = 0;
    try {
      for (const [key, decoded] of parsed) {
        try {
          await setConfigurationValue(
            currentFile,
            key,
            decoded.literal,
            session.csrfToken,
          );
        } catch (error) {
          if (handleAdmissionFailure(error, onRefusal)) {
            return;
          }
          setFailure(failureText(error, wording.writeFailed));
          setSummary(
            detail.partialSave
              .replace("{saved}", String(written))
              .replace("{total}", String(keys.length)),
          );
          return;
        }
        written += 1;
        setSaved((current) =>
          current === null ? current : { ...current, [key]: decoded.value },
        );
        setDraft((current) =>
          current === null
            ? current
            : { ...current, [key]: draftText(decoded.value) },
        );
      }
      setSummary(detail.savedAll);
      if (currentFile === WEB_CONFIGURATION_FILE) {
        onWebSaved();
      }
    } finally {
      setPending(false);
    }
  };

  const listed = files.report?.files ?? [];
  return (
    <Panel
      title={detail.configuration}
      span={12}
      marker={
        <AutoMarker
          reading={openRead.loading}
          lastSuccess={openRead.lastSuccess}
          label={detail.configuration}
        />
      }
    >
      <FailureNotice text={files.failure} />
      <div className="cfgsplit">
        <nav className="cfglist">
          {listed.map((name) => (
            <button
              key={name}
              className={`cfgfile${name === file ? " on" : ""}`}
              type="button"
              disabled={pending}
              onClick={() => onSelect(name)}
            >
              {name}
            </button>
          ))}
        </nav>
        <div
          className={file === null ? "cfgdetail" : "cfgdetail cfgdetail-in"}
          key={file ?? "empty"}
        >
          {file === null ? (
            <p className="note">{detail.selectFile}</p>
          ) : (
            <>
              <div className="cfgdh">
                <h4>{file}</h4>
                <button
                  className="btn p xs"
                  type="button"
                  disabled={pending || changed.length === 0}
                  onClick={() => void onSave()}
                >
                  {detail.saveFile.replace("{file}", file)}
                </button>
              </div>
              <FailureNotice text={openRead.failure} />
              {saved === null
                ? null
                : Object.keys(saved).map((key, index) => (
                    <div
                      className="cfgrow cfgrow-in"
                      key={key}
                      style={{
                        animationDelay: `${Math.min(index, 12) * 14}ms`,
                      }}
                    >
                      <span className="k">{key}</span>
                      <span className="val">
                        <input
                          aria-label={key}
                          value={draft?.[key] ?? ""}
                          disabled={pending}
                          spellCheck={false}
                          onChange={(event) => {
                            setSummary(null);
                            setDraft((current) =>
                              current === null
                                ? current
                                : { ...current, [key]: event.target.value },
                            );
                          }}
                        />
                      </span>
                    </div>
                  ))}
              {summary === null ? null : <p className="note">{summary}</p>}
              <FailureNotice text={failure} />
              <p className="note">{detail.restartNote}</p>
            </>
          )}
        </div>
      </div>
    </Panel>
  );
}
