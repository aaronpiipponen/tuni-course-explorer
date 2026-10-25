/** Programme picker lifecycle: read one official report, confirm its course moves, then operate. */
import { useEffect, useRef, useState } from "react";
import type { ModuleSummary } from "../../api/types";
import { useReadCache } from "../../app/useReadCache";
import { useProfileSelector } from "../../state/useProfileSelector";
import {
  VERSION_CONFLICT,
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
import { moduleVersionKey } from "./moduleVersions";
import type { ExtraContent } from "./usePlacedContent";
import { readProspectiveStructure } from "./structureReads";
import type { DisplayLanguage } from "../../state/types";

/** The courses a holder addition, replacement or reset moves, for its confirmation. */
export type ProgrammeMovePreview = {
  /** The holder the operation adds, replaces or resets. */
  holder: ModuleSummary;
  moves: readonly PulledCourse[];
  /** The exact selections the preview's reports were read under. */
  moduleVersions: Readonly<Record<string, string>>;
  /** Localized node that displays the operation's holder now, when a visible node does. */
  moduleFrom?: (language: DisplayLanguage) => string;
};

function pendingId(operation: ProgrammeOperation): string {
  return operation.kind === "replace"
    ? operation.replacementGroupId
    : operation.groupId;
}

function asError(caught: unknown): Error {
  return caught instanceof Error ? caught : new Error(String(caught));
}

/** Return the programme picker lifecycle and its operations. */
export function useProgrammeActions(
  content: PlacedContent,
  extend: (extra: ExtraContent) => PlacedContent,
  confirmMoves: (request: CourseMoveRequest) => Promise<CourseMoveAnswer>,
  contentDatasetIdentity: string,
  contentSelectionKey: string,
): {
  run(
    operation: ProgrammeOperation,
    removeCompletedCourses?: boolean,
    pull?: boolean,
    confirmedVersions?: Readonly<Record<string, string>>,
  ): Promise<boolean>;
  moves(operation: ProgrammeOperation): Promise<ProgrammeMovePreview | null>;
  pending: string | null;
  error: Error | null;
} {
  const cache = useReadCache();
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
      operationDatasetIdentity: cache.getDatasetIdentity(),
      baseSelectionKey: contentSelectionKey,
    };
  };
  /** Refresh the saved envelope and refuse a profile, programme list or selection that moved on. */
  const refreshed = (
    profileId: string,
    programmes: readonly string[],
    baseSelectionKey: string,
  ) => {
    const latest = store.refreshFromStorage();
    if (latest.currentProfileId !== profileId) return null;
    const state = latest.profiles[latest.currentProfileId].state;
    if (!sameIdList(state.structure.programmeGroupIds, programmes)) return null;
    if (moduleVersionKey(state.structure.moduleVersions) !== baseSelectionKey)
      return null;
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
    setError(asError(caught));
  };
  /** The prospective map of one operation over the latest stored selections. */
  const prospectiveVersions = (
    state: StructureState,
    operation: ProgrammeOperation,
  ): Readonly<Record<string, string>> => {
    if (operation.kind !== "add" && operation.kind !== "replace")
      return state.moduleVersions;
    const groupId = pendingId(operation);
    const stored = state.moduleVersions[groupId];
    if (stored !== undefined && stored !== operation.versionId)
      throw new Error(VERSION_CONFLICT);
    return { ...state.moduleVersions, [groupId]: operation.versionId };
  };
  /**
   * Read every report one operation's move preview and write need under its prospective map.
   *
   * The shared prospective read reuses the supplied content only for matching dataset, selection
   * and requested roots, and otherwise reads the whole requested set.
   */
  const withReport = async (
    state: StructureState,
    operation: ProgrammeOperation,
    controller: AbortController,
    operationDatasetIdentity: string,
    moduleVersions: Readonly<Record<string, string>>,
  ): Promise<PlacedContent> => {
    const prospective = await readProspectiveStructure({
      cache,
      content,
      contentDatasetIdentity,
      contentSelectionKey,
      extend,
      state,
      groupId: pendingId(operation),
      moduleVersions,
      operationDatasetIdentity,
      signal: controller.signal,
    });
    return prospective.content;
  };
  /** Read what one addition or replacement moves out of the supplied state. */
  const preview = (
    state: StructureState,
    operation: ProgrammeOperation,
    ctx: PlacedContent,
    moduleVersions: Readonly<Record<string, string>>,
  ): ProgrammeMovePreview => {
    const report = ctx.reports[pendingId(operation)];
    if (!report) throw new Error("Programme is unavailable");
    return {
      holder: report.root.module,
      moves: programmeMoves(state, operation, ctx),
      moduleVersions,
      moduleFrom: displayedPlace(state, ctx, pendingId(operation)),
    };
  };
  return {
    pending,
    error,
    async moves(operation) {
      const {
        controller,
        profileId,
        programmes,
        operationDatasetIdentity,
        baseSelectionKey,
      } = start(operation);
      try {
        const state = refreshed(profileId, programmes, baseSelectionKey);
        if (!state) return null;
        const moduleVersions = prospectiveVersions(state, operation);
        const ctx = await withReport(
          state,
          operation,
          controller,
          operationDatasetIdentity,
          moduleVersions,
        );
        return preview(state, operation, ctx, moduleVersions);
      } catch (caught) {
        fail(caught, controller, profileId);
        return null;
      } finally {
        finish(controller);
      }
    },
    async run(
      operation,
      removeCompletedCourses = false,
      pull = true,
      confirmedVersions,
    ) {
      const {
        controller,
        profileId,
        programmes,
        operationDatasetIdentity,
        baseSelectionKey,
      } = start(operation);
      try {
        let state = refreshed(profileId, programmes, baseSelectionKey);
        if (!state) return false;
        let moduleVersions = prospectiveVersions(state, operation);
        if (
          confirmedVersions !== undefined &&
          moduleVersionKey(confirmedVersions) !==
            moduleVersionKey(moduleVersions)
        )
          return false;
        let ctx = content;
        let pulls = pull;
        if (operation.kind === "add" || operation.kind === "replace") {
          ctx = await withReport(
            state,
            operation,
            controller,
            operationDatasetIdentity,
            moduleVersions,
          );
          const current = refreshed(profileId, programmes, baseSelectionKey);
          if (!current) return false;
          state = current;
          moduleVersions = prospectiveVersions(state, operation);
          if (
            confirmedVersions !== undefined &&
            moduleVersionKey(confirmedVersions) !==
              moduleVersionKey(moduleVersions)
          )
            return false;
          if (operation.kind === "add") {
            const request = preview(state, operation, ctx, moduleVersions);
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
            if (!refreshed(profileId, programmes, baseSelectionKey))
              return false;
          }
        }
        changeProgrammes(
          store,
          operation,
          ctx,
          removeCompletedCourses,
          pulls,
          moduleVersions,
        );
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
