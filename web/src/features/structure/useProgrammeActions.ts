/** Programme picker lifecycle: read one official report, confirm its course moves, then operate. */
import { useEffect, useRef, useState } from "react";
import { readStudyStructure } from "../../api/study-structure";
import type {
  CourseSummary,
  ModuleSummary,
  StudyStructureReport,
} from "../../api/types";
import { useProfileSelector } from "../../state/useProfileSelector";
import {
  changeProgrammes,
  displayedPlace,
  programmeMoves,
  sameIdList,
  type ProgrammeOperation,
} from "./actions";
import type {
  CourseMoveAnswer,
  CourseMoveRequest,
} from "./CourseMoveConfirmDialog";
import type { PulledCourse } from "./edits";
import type { PlacedContent } from "./model";
import type { StructureState } from "./state";
import type { DisplayLanguage } from "../../state/types";

/** The courses a holder addition, replacement or reset moves, for its confirmation. */
export type ProgrammeMovePreview = {
  /** The holder the operation adds, replaces or resets. */
  holder: ModuleSummary;
  moves: readonly PulledCourse[];
  /** Localized node that displays the operation's holder now, when a visible node does. */
  moduleFrom?: (language: DisplayLanguage) => string;
};

function pendingId(operation: ProgrammeOperation): string {
  return operation.kind === "replace"
    ? operation.replacementGroupId
    : operation.groupId;
}

export function useProgrammeActions(
  content: PlacedContent,
  extend: (extra: {
    courses?: readonly CourseSummary[];
    reports?: Readonly<Record<string, StudyStructureReport>>;
  }) => PlacedContent,
  confirmMoves: (request: CourseMoveRequest) => Promise<CourseMoveAnswer>,
): {
  run(
    operation: ProgrammeOperation,
    removeCompletedCourses?: boolean,
    pull?: boolean,
  ): Promise<boolean>;
  moves(operation: ProgrammeOperation): Promise<ProgrammeMovePreview | null>;
  pending: string | null;
  error: Error | null;
} {
  const { store } = useProfileSelector(
    (state) => state.structure.programmeGroupIds,
  );
  const operationRef = useRef<AbortController | null>(null);
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<Error | null>(null);
  useEffect(
    () => () => {
      operationRef.current?.abort();
      operationRef.current = null;
    },
    [],
  );
  const start = (operation: ProgrammeOperation) => {
    operationRef.current?.abort();
    const controller = new AbortController();
    operationRef.current = controller;
    const snapshot = store.getSnapshot();
    const profileId = snapshot.currentProfileId;
    setPending(pendingId(operation));
    setError(null);
    return {
      controller,
      profileId,
      programmes:
        snapshot.profiles[profileId].state.structure.programmeGroupIds,
    };
  };
  /** Refresh the saved envelope and refuse a profile or programme list that moved on. */
  const refreshed = (profileId: string, programmes: readonly string[]) => {
    const latest = store.refreshFromStorage();
    if (latest.currentProfileId !== profileId) return null;
    const state = latest.profiles[latest.currentProfileId].state;
    if (!sameIdList(state.structure.programmeGroupIds, programmes)) return null;
    return state.structure;
  };
  const finish = (controller: AbortController) => {
    if (operationRef.current === controller && !controller.signal.aborted) {
      operationRef.current = null;
      setPending(null);
    }
  };
  const fail = (
    caught: unknown,
    controller: AbortController,
    profileId: string,
  ) => {
    if (
      controller.signal.aborted ||
      store.getSnapshot().currentProfileId !== profileId
    )
      return;
    setError(caught instanceof Error ? caught : new Error(String(caught)));
  };
  /** Read the report of one picked programme into the supplied content when it is absent. */
  const withReport = async (
    operation: ProgrammeOperation,
    controller: AbortController,
  ): Promise<PlacedContent> => {
    const id = pendingId(operation);
    if (content.reports[id]) return content;
    const report = await readStudyStructure(id, controller.signal);
    if (controller.signal.aborted)
      throw new Error("Programme read was cancelled");
    return extend({ reports: { [id]: report } });
  };
  /** Read what one addition or replacement moves out of the supplied state. */
  const preview = (
    state: StructureState,
    operation: ProgrammeOperation,
    ctx: PlacedContent,
  ): ProgrammeMovePreview => ({
    holder: ctx.reports[pendingId(operation)]!.root.module,
    moves: programmeMoves(state, operation, ctx),
    moduleFrom: displayedPlace(state, ctx, pendingId(operation)),
  });
  return {
    pending,
    error,
    async moves(operation) {
      const { controller, profileId, programmes } = start(operation);
      try {
        const state = refreshed(profileId, programmes);
        if (!state) return null;
        const ctx = await withReport(operation, controller);
        return preview(state, operation, ctx);
      } catch (caught) {
        fail(caught, controller, profileId);
        return null;
      } finally {
        finish(controller);
      }
    },
    async run(operation, removeCompletedCourses = false, pull = true) {
      const { controller, profileId, programmes } = start(operation);
      try {
        let ctx = content;
        let pulls = pull;
        if (operation.kind === "add" || operation.kind === "replace") {
          ctx = await withReport(operation, controller);
          const state = refreshed(profileId, programmes);
          if (!state) return false;
          if (operation.kind === "add") {
            const request = preview(state, operation, ctx);
            // One confirmation covers the programme move and every course it pulls.
            if (request.moduleFrom !== undefined || request.moves.length > 0) {
              const answer = await confirmMoves({
                holder: request.holder,
                moves: request.moves,
                moduleFrom: request.moduleFrom,
              });
              if (answer === false) return false;
              pulls = answer !== "keep";
            }
            if (controller.signal.aborted) return false;
            if (!refreshed(profileId, programmes)) return false;
          }
        }
        changeProgrammes(store, operation, ctx, removeCompletedCourses, pulls);
        return true;
      } catch (caught) {
        fail(caught, controller, profileId);
        return false;
      } finally {
        finish(controller);
      }
    },
  };
}
