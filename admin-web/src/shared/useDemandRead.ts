/**
 * One explicit read a panel performs only when the operator asks for it.
 *
 * The read runs once per explicit reload and never on mount, on a timer or on an identity change.
 * A changed identity clears the result and aborts the read in flight, so a panel that selects
 * another source shows no text from the previous one. A refused admission is reported to the
 * application, and any other failure is rendered in the panel with its own failure text.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { failureText, handleAdmissionFailure } from "../api/http";
import type { PanelRead } from "./usePanelRead";

interface DemandReadOptions {
  /** The selection the read belongs to. A changed identity clears the result and aborts the read. */
  identity: string;
  onRefusal: (status: number) => void;
  failureTextValue: string;
}

/** Run one explicit read on demand and return its state and its reload. */
export function useDemandRead<T>(
  read: (signal: AbortSignal) => Promise<T>,
  options: DemandReadOptions,
): PanelRead<T> {
  const { identity, onRefusal, failureTextValue } = options;
  const [report, setReport] = useState<T | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [lastSuccess, setLastSuccess] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const reader = useRef(read);
  reader.current = read;
  const refusal = useRef(onRefusal);
  refusal.current = onRefusal;
  const failureTextValueRef = useRef(failureTextValue);
  failureTextValueRef.current = failureTextValue;
  const pending = useRef<AbortController | null>(null);

  const identityRef = useRef(identity);
  useEffect(() => {
    if (identityRef.current === identity) {
      return;
    }
    identityRef.current = identity;
    pending.current?.abort();
    pending.current = null;
    setReport(null);
    setFailure(null);
    setLastSuccess(null);
    setLoading(false);
  }, [identity]);

  useEffect(
    () => () => {
      pending.current?.abort();
      pending.current = null;
    },
    [],
  );

  const reload = useCallback((): void => {
    pending.current?.abort();
    const controller = new AbortController();
    pending.current = controller;
    setLoading(true);
    setFailure(null);
    void (async () => {
      try {
        const value = await reader.current(controller.signal);
        if (controller.signal.aborted) {
          return;
        }
        setReport(value);
        setLastSuccess(Date.now());
      } catch (error) {
        if (controller.signal.aborted) {
          return;
        }
        setFailure(failureText(error, failureTextValueRef.current));
        handleAdmissionFailure(error, refusal.current);
      } finally {
        if (pending.current === controller) {
          pending.current = null;
          setLoading(false);
        }
      }
    })();
  }, []);

  return { report, failure, lastSuccess, loading, reload };
}
