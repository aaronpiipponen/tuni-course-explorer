/**
 * One mounted panel's automatic read loop.
 *
 * A panel reads immediately when it is enabled and the page is visible, then schedules its next read
 * after the current one completes plus the configured interval, so two reads never overlap and no
 * read runs while the panel is unmounted. The page's own visibility governs the loop: a hidden page
 * cancels the scheduled read and aborts one in flight without showing a failure, and the return to
 * visibility reads once immediately and resumes the ordinary loop. A refused admission reports its
 * status to the application and stops the loop, while any other failure renders in the panel with
 * its own failure text and schedules the next ordinary read. The automatic reads carry the loop's
 * own attribution, and the returned reload performs one explicit read that carries none. A caller
 * that receives its own report from an action installs it through ``apply`` without issuing a read.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { failureText, handleAdmissionFailure } from "../api/http";

/** The state one mounted panel renders. */
export interface PanelRead<T> {
  report: T | null;
  failure: string | null;
  lastSuccess: number | null;
  loading: boolean;
  reload: () => void;
}

interface PanelReadOptions {
  pollSeconds: number;
  enabled: boolean;
  onRefusal: (status: number) => void;
  failureTextValue: string;
}

/** Read one panel's command on its own loop and return its state and its explicit reload. */
export function usePanelRead<T>(
  read: (signal: AbortSignal, automatic: boolean) => Promise<T>,
  options: PanelReadOptions,
): PanelRead<T> & { apply: (report: T) => void } {
  const { pollSeconds, enabled, onRefusal, failureTextValue } = options;
  const [report, setReport] = useState<T | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [lastSuccess, setLastSuccess] = useState<number | null>(null);
  const [visible, setVisible] = useState(() => !document.hidden);
  const [loading, setLoading] = useState(enabled && !document.hidden);
  const [attempt, setAttempt] = useState(0);
  const reader = useRef(read);
  reader.current = read;
  const refusal = useRef(onRefusal);
  refusal.current = onRefusal;
  const failureValue = useRef(failureTextValue);
  failureValue.current = failureTextValue;
  // One reload that arrived while the hook could not read, consumed once it can.
  const pendingExplicit = useRef(false);

  useEffect(() => {
    const onVisibilityChange = (): void => setVisible(!document.hidden);
    document.addEventListener("visibilitychange", onVisibilityChange);
    return () =>
      document.removeEventListener("visibilitychange", onVisibilityChange);
  }, []);

  useEffect(() => {
    if (!enabled || !visible) {
      return;
    }
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const controller = new AbortController();

    const run = async (automatic: boolean): Promise<void> => {
      setLoading(true);
      try {
        const value = await reader.current(controller.signal, automatic);
        if (cancelled) {
          return;
        }
        setReport(value);
        setFailure(null);
        setLastSuccess(Date.now());
        setLoading(false);
        timer = setTimeout(() => void run(true), pollSeconds * 1000);
      } catch (error) {
        if (cancelled) {
          return;
        }
        setLoading(false);
        if (handleAdmissionFailure(error, refusal.current)) {
          return;
        }
        setFailure(failureText(error, failureValue.current));
        timer = setTimeout(() => void run(true), pollSeconds * 1000);
      }
    };

    // A reload that waited for a visible enabled hook keeps its explicit attribution, and takes
    // precedence over the visibility trigger so the return makes exactly one request.
    const explicit = pendingExplicit.current;
    pendingExplicit.current = false;
    void run(!explicit);

    return () => {
      cancelled = true;
      controller.abort();
      if (timer !== undefined) {
        clearTimeout(timer);
      }
    };
  }, [enabled, visible, pollSeconds, attempt, onRefusal, failureTextValue]);

  const reload = useCallback(() => {
    pendingExplicit.current = true;
    setAttempt((value) => value + 1);
  }, []);
  const apply = useCallback((value: T) => {
    setReport(value);
    setFailure(null);
    setLastSuccess(Date.now());
  }, []);
  return { report, failure, lastSuccess, loading, reload, apply };
}
