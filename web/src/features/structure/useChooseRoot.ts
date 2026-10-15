/** Loads an official root before atomically replacing the stored structure projection. */
import { useEffect, useRef, useState } from "react";
import { readStudyStructure } from "../../api/study-structure";
import type { ModuleSummary } from "../../api/types";
import { useProfileSelector } from "../../state/useProfileSelector";
import { applyStructure } from "./actions";
import {
  buildStructure,
  resolveStructure,
  NO_CONTENT,
  withUnplaced,
} from "./model";
import { emptyEdits } from "./state";

export function useChooseRoot(): {
  choose(module: ModuleSummary): Promise<boolean>;
  pending: string | null;
  error: Error | null;
} {
  const { store } = useProfileSelector((state) => state.structure);
  const operation = useRef<AbortController | null>(null);
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<Error | null>(null);
  useEffect(
    () => () => {
      operation.current?.abort();
      operation.current = null;
    },
    [],
  );
  return {
    pending,
    error,
    async choose(module) {
      operation.current?.abort();
      const controller = new AbortController();
      operation.current = controller;
      const profileId = store.getSnapshot().currentProfileId;
      setPending(module.group_id);
      setError(null);
      try {
        const report = await readStudyStructure(
          module.group_id,
          controller.signal,
        );
        if (
          controller.signal.aborted ||
          store.getSnapshot().currentProfileId !== profileId
        )
          return false;
        const root = resolveStructure(
          withUnplaced(buildStructure(report)),
          emptyEdits(),
          NO_CONTENT,
        );
        applyStructure(store, {
          rootGroupId: module.group_id,
          ...emptyEdits(),
          placedCourseIds: root.subtree.map((course) => course.group_id),
        });
        return true;
      } catch (caught) {
        if (
          controller.signal.aborted ||
          store.getSnapshot().currentProfileId !== profileId
        )
          return false;
        setError(caught instanceof Error ? caught : new Error(String(caught)));
        return false;
      } finally {
        if (operation.current === controller && !controller.signal.aborted) {
          operation.current = null;
          setPending(null);
        }
      }
    },
  };
}
