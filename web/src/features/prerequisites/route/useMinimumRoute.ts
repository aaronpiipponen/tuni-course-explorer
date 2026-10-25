/**
 * Explicit transient minimum-route ownership: only `find` starts one disposable worker.
 *
 * The held graph supplies the native structure, its dataset identity and the configured allocation
 * limit. A successful outcome joins the shared read cache. The visible route stays transient and
 * every input, readiness, report, pane or dataset change discards it.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import type {
  PrerequisiteGraphReport,
  PrerequisitePath,
} from "../../../api/types";
import { useReadCache } from "../../../app/useReadCache";
import { withLiveInputs } from "../../../solver/structure";
import type { usePrerequisiteInputs } from "../usePrerequisiteInputs";
import { calculateRouteInWorker } from "./workerClient";

/** The visible minimum route and its explicit operations. */
export type MinimumRouteSession = {
  result: PrerequisitePath | null;
  calculating: boolean;
  error: Error | null;
  expanded: boolean;
  find: () => void;
  clear: () => void;
  setExpanded: (expanded: boolean) => void;
};

type RouteState = {
  key: string;
  report: PrerequisiteGraphReport;
  result: PrerequisitePath | null;
  calculating: boolean;
  error: Error | null;
  expanded: boolean;
};

/** Return the transient minimum route session of one held graph. */
export function useMinimumRoute(
  inputs: ReturnType<typeof usePrerequisiteInputs>,
  report: PrerequisiteGraphReport | null,
  graphReady: boolean,
): MinimumRouteSession {
  const { request, key, active } = inputs;
  const cache = useReadCache();
  const controller = useRef<AbortController | null>(null);
  const routeKey =
    active && graphReady && report !== null && request !== null
      ? JSON.stringify([
          "minimum-route",
          report.dataset_identity,
          inputs.graphKey,
          key,
          report.max_compact_nodes,
        ])
      : null;
  const currentKey = useRef<string | null>(routeKey);
  currentKey.current = routeKey;
  const currentReport = useRef(report);
  currentReport.current = report;
  const [state, setState] = useState<RouteState | null>(null);
  const discard = useCallback(() => {
    controller.current?.abort();
    controller.current = null;
    setState(null);
  }, []);
  useEffect(() => {
    discard();
    return discard;
  }, [routeKey, report, discard]);
  const find = useCallback(() => {
    if (routeKey === null || request === null || report === null) return;
    const identity = report.dataset_identity;
    if (cache.getDatasetIdentity() !== identity) return;
    controller.current?.abort();
    const cached = cache.get<PrerequisitePath>(routeKey);
    if (cached !== undefined) {
      controller.current = null;
      setState({
        key: routeKey,
        report,
        result: cached,
        calculating: false,
        error: null,
        expanded: false,
      });
      return;
    }
    const pendingController = new AbortController();
    controller.current = pendingController;
    const initiatingKey = routeKey;
    const initiatingReport = report;
    const solverRequest = {
      operation: "route" as const,
      ...withLiveInputs(report.solver, request),
      max_compact_nodes: report.max_compact_nodes,
    };
    setState({
      key: initiatingKey,
      report: initiatingReport,
      result: null,
      calculating: true,
      error: null,
      expanded: false,
    });
    calculateRouteInWorker(solverRequest, pendingController.signal).then(
      (result) => {
        if (
          pendingController.signal.aborted ||
          controller.current !== pendingController ||
          currentKey.current !== initiatingKey ||
          currentReport.current !== initiatingReport ||
          cache.getDatasetIdentity() !== identity
        )
          return;
        cache.put(identity, initiatingKey, result);
        setState({
          key: initiatingKey,
          report: initiatingReport,
          result,
          calculating: false,
          error: null,
          expanded: false,
        });
      },
      (caught: unknown) => {
        if (
          pendingController.signal.aborted ||
          controller.current !== pendingController ||
          currentKey.current !== initiatingKey ||
          currentReport.current !== initiatingReport
        )
          return;
        setState({
          key: initiatingKey,
          report: initiatingReport,
          result: null,
          calculating: false,
          error: caught instanceof Error ? caught : new Error(String(caught)),
          expanded: false,
        });
      },
    );
  }, [routeKey, request, report, cache]);
  const setExpanded = useCallback(
    (expanded: boolean) =>
      setState((current) =>
        current === null ? null : { ...current, expanded },
      ),
    [],
  );
  // Withhold a result whose inputs, report or cache identity have moved on.
  const current =
    routeKey !== null &&
    report !== null &&
    cache.getDatasetIdentity() === report.dataset_identity &&
    state !== null &&
    state.key === routeKey &&
    state.report === report
      ? state
      : null;
  return {
    result: current?.result ?? null,
    calculating: current?.calculating ?? false,
    error: current?.error ?? null,
    expanded: current?.expanded ?? false,
    find,
    clear: discard,
    setExpanded,
  };
}
