/** Explicit transient minimum-route ownership: only `find` starts one request. */
import { useCallback, useEffect, useRef, useState } from "react";
import { readMinimumRoute } from "../../../api/minimum-route";
import type { PrerequisitePath } from "../../../api/types";
import type { usePrerequisiteInputs } from "../usePrerequisiteInputs";

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
  result: PrerequisitePath | null;
  calculating: boolean;
  error: Error | null;
  expanded: boolean;
};

export function useMinimumRoute(
  inputs: ReturnType<typeof usePrerequisiteInputs>,
): MinimumRouteSession {
  const { request, key, active } = inputs;
  const controller = useRef<AbortController | null>(null);
  const currentKey = useRef(key);
  currentKey.current = key;
  const [state, setState] = useState<RouteState>({
    key,
    result: null,
    calculating: false,
    error: null,
    expanded: false,
  });
  const discard = useCallback(() => {
    controller.current?.abort();
    controller.current = null;
    setState((current) =>
      current.key === currentKey.current &&
      current.result === null &&
      !current.calculating &&
      current.error === null &&
      !current.expanded
        ? current
        : {
            key: currentKey.current,
            result: null,
            calculating: false,
            error: null,
            expanded: false,
          },
    );
  }, []);
  useEffect(() => {
    discard();
    return discard;
  }, [key, active, discard]);
  const find = useCallback(() => {
    if (!request || !active) return;
    controller.current?.abort();
    const pendingController = new AbortController();
    controller.current = pendingController;
    const initiatingKey = key;
    setState({
      key: initiatingKey,
      result: null,
      calculating: true,
      error: null,
      expanded: false,
    });
    readMinimumRoute(request, pendingController.signal).then(
      (result) => {
        if (
          pendingController.signal.aborted ||
          controller.current !== pendingController ||
          currentKey.current !== initiatingKey
        )
          return;
        setState({
          key: initiatingKey,
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
          currentKey.current !== initiatingKey
        )
          return;
        setState({
          key: initiatingKey,
          result: null,
          calculating: false,
          error: caught instanceof Error ? caught : new Error(String(caught)),
          expanded: false,
        });
      },
    );
  }, [request, key, active]);
  const setExpanded = useCallback(
    (expanded: boolean) => setState((current) => ({ ...current, expanded })),
    [],
  );
  // Withhold a result whose inputs or pane have moved on, before effect cleanup runs.
  const current =
    active && request !== null && state.key === key ? state : null;
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
