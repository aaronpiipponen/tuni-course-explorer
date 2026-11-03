/** Ordered programme composition of the tree, picker, confirmations and drawer. */
import { createPortal } from "react-dom";
import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, LayoutGroup } from "framer-motion";
import type {
  CatalogueModule,
  CourseSummary,
  ModuleSummary,
} from "../../api/types";
import { useProfileSelector } from "../../state/useProfileSelector";
import { useCurrentProfileId } from "../../state/useCurrentProfile";
import { ErrorNotice } from "../../shared/ErrorNotice";
import { PickerOverlay } from "../../shared/PickerOverlay";
import { useWording } from "../../shared/useWording";
import { ModuleLookupBox } from "./ModuleLookupBox";
import {
  useProgrammeActions,
  type ProgrammeMovePreview,
} from "./useProgrammeActions";
import { AddProgrammeRow } from "./AddProgrammeRow";
import { ModuleRemoveDialog } from "./ModuleRemoveDialog";
import { ProgrammeConfirmDialog } from "./ProgrammeConfirmDialog";
import { StructureDrawer } from "./StructureDrawer";
import { StructureNodeRow } from "./StructureNodeRow";
import { StructureCard } from "./StructureCard";
import { ModuleVersionPicker } from "./ModuleVersionPicker";
import {
  displayedHolders,
  displayContents,
  holderCourses,
  unplacedTarget,
} from "./display";
import {
  COURSE_DRAG_LIFT_SCALE,
  COURSE_DRAG_LIFT_Y,
  useCourseDrag,
} from "./useCourseDrag";
import { moduleName } from "./presentation";
import { moduleVersionKey } from "./moduleVersions";
import {
  VERSION_CONFLICT,
  applyStructure,
  sameIdList,
  type ProgrammeOperation,
} from "./actions";
import {
  buildProgrammeForest,
  courseHolders,
  indexResolved,
  programmeKey,
  resolveStructure,
  NO_CONTENT,
  type PlacedContent,
  type ResolvedNode,
} from "./model";
import { emptyEdits, type StructureEdits } from "./state";
import {
  CourseMoveConfirmDialog,
  useCourseMoveConfirm,
  type CourseMoveAnswer,
  type CourseMoveRequest,
} from "./CourseMoveConfirmDialog";
import type { PulledCourse, PulledModule } from "./edits";
import { scopeHoldsCompletion } from "./edits";
import { useAction } from "../../shared/useAction";
import { usePlacedContent } from "./usePlacedContent";
import { useStructureEditor } from "./useStructureEditor";
import { useNotice } from "../../shared/useNotice";
import { usePhoneTabsOnClose } from "../../shared/usePhoneTabsOnClose";
import { HelpLink, HelpTip, type HelpSection } from "../../shared/HelpTip";
import { SisuImportNotice } from "./SisuImportNotice";
import { forgetUnplacedReveal, settleUnplacedReveal } from "./reveal";
import { ProfileTransfer } from "../profiles/ProfileTransfer";
import {
  resolveSisuImport,
  captureModuleIds,
  sisuImportBlocked,
  type SisuImportIssue,
} from "./sisu";
import type { DisplayLanguage } from "../../state/types";

type PickerMode = { kind: "add" } | { kind: "replace"; groupId: string };

type PendingConfirmation = {
  operation: "replace" | "reset" | "delete";
  groupId: string;
  replacementGroupId: string | null;
  /** The exact selections the replacement's reports were read under. */
  moduleVersions: Readonly<Record<string, string>> | null;
  /** The courses the replacement programme pulls out of the nodes they are in. */
  moves: readonly PulledCourse[];
  /** The highest-level official modules the replacement pulls with everything they hold. */
  moduleMoves: readonly PulledModule[];
  /** Localized node that displays the replacement programme, when a visible node does. */
  moduleFrom?: (language: DisplayLanguage) => string;
};

/** One pending pull question of a reset, with the completion choice its answer already made. */
type PendingResetPull = {
  groupId: string;
  removeCompletedCourses: boolean;
  holder: ModuleSummary;
  moves: readonly PulledCourse[];
  moduleMoves: readonly PulledModule[];
};

function stringPlacements(placements: Record<string, string | null>): string[] {
  return Object.entries(placements)
    .filter(([, target]) => typeof target === "string")
    .map(([id]) => id);
}

function dedupe(ids: readonly string[]): string[] {
  return [...new Set(ids)];
}

const emptyProjection = (language: DisplayLanguage): ResolvedNode =>
  resolveStructure(
    buildProgrammeForest([], language),
    emptyEdits(),
    NO_CONTENT,
    language,
  );

/** Render the Structure of studies tree, picker, confirmations and drawer. */
export function StructurePane() {
  const { store, value: programmeGroupIds } = useProfileSelector(
    (state) => state.structure.programmeGroupIds,
  );
  const { value: choices } = useProfileSelector(
    (state) => state.structure.choices,
  );
  const { value: coursePlacements } = useProfileSelector(
    (state) => state.structure.coursePlacements,
  );
  const { value: modulePlacements } = useProfileSelector(
    (state) => state.structure.modulePlacements,
  );
  const { value: moduleVersions } = useProfileSelector(
    (state) => state.structure.moduleVersions,
  );
  const { value: courseOrder } = useProfileSelector(
    (state) => state.structure.courseOrder,
  );
  const { value: selected } = useProfileSelector(
    (state) => state.selectedCourseIds,
  );
  const { value: completedCourseIds } = useProfileSelector(
    (state) => state.completedCourseIds,
  );
  const { value: pendingSisuImport } = useProfileSelector(
    (state) => state.pendingSisuImport,
  );
  const pending = pendingSisuImport !== null;
  // A restored profile can hold a waiting capture beside saved edits, which placement leaves alone.
  const { value: importBlocked } = useProfileSelector((state) =>
    sisuImportBlocked(state),
  );
  // A capture can hold a module the official rule does not name, which needs its own report.
  const capturedModuleIds = useMemo(
    () => (pendingSisuImport ? captureModuleIds(pendingSisuImport) : []),
    [pendingSisuImport],
  );
  const { language, t } = useWording();
  const notice = useNotice();
  const [picker, setPicker] = useState<PickerMode | null>(null);
  const [confirmation, setConfirmation] = useState<PendingConfirmation | null>(
    null,
  );
  const [resetPull, setResetPull] = useState<PendingResetPull | null>(null);
  // The surface the last operation started from, so each surface shows only its own failure.
  const [attempt, setAttempt] = useState<"picker" | "confirm" | "reset" | null>(
    null,
  );
  const addRowHost = useRef<HTMLDivElement>(null);
  const treeRef = useRef<HTMLDivElement>(null);
  const confirmationOpener = useRef<HTMLElement | null>(null);
  const pickerOpener = useRef<HTMLElement | null>(null);
  const edits = useMemo(
    () => ({ choices, coursePlacements, modulePlacements }),
    [choices, coursePlacements, modulePlacements],
  );
  // One hydration owner loads every report and summary the tree needs, programmes included.
  const placed = usePlacedContent(
    useMemo(
      () => dedupe([...selected, ...stringPlacements(coursePlacements)]),
      [selected, coursePlacements],
    ),
    useMemo(
      () =>
        dedupe([
          ...programmeGroupIds,
          ...stringPlacements(modulePlacements),
          ...capturedModuleIds,
        ]),
      [programmeGroupIds, modulePlacements, capturedModuleIds],
    ),
    moduleVersions,
    pending,
  );
  const contentSelectionKey = useMemo(
    () => moduleVersionKey(moduleVersions),
    [moduleVersions],
  );
  // One confirmation lists the courses an addition pulls out of the nodes they are in.
  const moveConfirm = useCourseMoveConfirm();
  const moveOpener = useRef<HTMLElement | null>(null);
  const confirmMoves = (
    request: CourseMoveRequest,
  ): Promise<CourseMoveAnswer> => {
    moveOpener.current =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    return moveConfirm.confirm(request);
  };
  const programmes = useProgrammeActions(
    placed.content,
    placed.extend,
    confirmMoves,
    placed.datasetIdentity,
    contentSelectionKey,
  );
  const [loadedOnce, setLoadedOnce] = useState(false);
  useEffect(() => {
    if (!placed.loading) setLoadedOnce(true);
  }, [placed.loading]);
  const [resolutionError, setResolutionError] = useState<Error | null>(null);
  const [importIssues, setImportIssues] = useState<
    readonly SisuImportIssue[] | null
  >(null);
  // Only the first load shows a skeleton tree. A pending capture holds the tree until placement.
  const contentLoading = pending || (!loadedOnce && placed.loading);
  const contentError = placed.error ?? resolutionError;
  // A notice that links Unplaced studies can arrive before the tree or its content, so the
  // request waits here until the row exists.
  useEffect(() => {
    if (contentLoading || contentError) return;
    settleUnplacedReveal(treeRef.current);
  }, [contentLoading, contentError]);
  useEffect(() => () => forgetUnplacedReveal(), []);
  // One display input is complete when every programme report and every string placement it
  // references exists, except a root the server still needs an explicit version for. Completeness
  // is checked by identity before any forest is built.
  const completeInput = useMemo(() => {
    if (contentLoading || contentError) return null;
    const required = new Set(placed.versionSelectionRequiredIds);
    if (
      programmeGroupIds.some(
        (id) => !required.has(id) && !placed.content.reports[id],
      )
    )
      return null;
    if (
      stringPlacements(edits.modulePlacements).some(
        (id) => !required.has(id) && !placed.content.reports[id],
      )
    )
      return null;
    if (
      Object.entries(edits.coursePlacements).some(
        ([id, target]) =>
          typeof target === "string" && !placed.content.courses.has(id),
      )
    )
      return null;
    return {
      datasetIdentity: placed.datasetIdentity,
      programmeGroupIds,
      edits,
      content: placed.content,
    };
  }, [
    contentLoading,
    contentError,
    placed.datasetIdentity,
    placed.content,
    placed.versionSelectionRequiredIds,
    programmeGroupIds,
    edits,
  ]);
  // A complete input is held across a changed selection, so a chosen module or version keeps the
  // previous forest on screen while its reports load. Only a dataset or profile change drops it.
  const currentProfileId = useCurrentProfileId();
  const [lastComplete, setLastComplete] = useState<{
    profileId: string;
    datasetIdentity: string;
    programmeGroupIds: readonly string[];
    edits: StructureEdits;
    content: PlacedContent;
  } | null>(null);
  useEffect(() => {
    if (!completeInput) return;
    setLastComplete({
      profileId: currentProfileId,
      datasetIdentity: completeInput.datasetIdentity,
      programmeGroupIds: completeInput.programmeGroupIds,
      edits: completeInput.edits,
      content: completeInput.content,
    });
  }, [completeInput, currentProfileId]);
  const chosen =
    completeInput ??
    (lastComplete &&
    lastComplete.profileId === currentProfileId &&
    lastComplete.datasetIdentity === placed.datasetIdentity
      ? lastComplete
      : null);
  // The language projects the chosen input, so held content follows the live language.
  const chosenProjection = useMemo(
    () =>
      chosen
        ? resolveStructure(
            buildProgrammeForest(
              chosen.programmeGroupIds.flatMap((id) => {
                const report = chosen.content.reports[id];
                return report ? [report] : [];
              }),
              language,
            ),
            chosen.edits,
            chosen.content,
            language,
          )
        : null,
    [chosen, language],
  );
  const holders = useMemo(
    () => (chosenProjection ? courseHolders(chosenProjection) : null),
    [chosenProjection],
  );
  useEffect(() => {
    if (!holders) return;
    const snapshot = store.getSnapshot();
    const current =
      snapshot.profiles[snapshot.currentProfileId].state.structure
        .courseHolders;
    if (JSON.stringify(current ?? {}) === JSON.stringify(holders)) return;
    store.updateCurrent((state) => ({
      ...state,
      structure: { ...state.structure, courseHolders: holders },
    }));
  }, [holders, store]);
  const base = chosenProjection ?? emptyProjection(language);
  // Root groups needing a version come from the server's own settlement, while nested groups come
  // from selected, unsuppressed references in the resolved projection. This one gate suspends
  // pending placement, reconciliation and editing, and keeps the required pickers reachable. A
  // reference the stored edits remove renders nothing, so it needs no selection and asks for none.
  const selectionRequiredGroups = useMemo(
    () =>
      dedupe([
        ...placed.versionSelectionRequiredIds,
        ...(pending ? [] : base.versionSelectionRequiredIds),
      ]),
    [
      placed.versionSelectionRequiredIds,
      base.versionSelectionRequiredIds,
      pending,
    ],
  );
  const versionSelectionRequired = selectionRequiredGroups.length > 0;
  /**
   * Place one pending Sisu capture in a single write once its ordinary reads have settled, no
   * required root or nested group needs an explicit version, and the profile holds no saved
   * structure edit beside the capture.
   *
   * The captured hierarchy is resolved from the callback's own state, so a language or completion
   * change another tab made while the reads waited is kept. A failure leaves the pending record
   * untouched and shows its error instead of retrying an unchanged read.
   */
  useEffect(() => {
    if (!pending) return;
    if (importBlocked) return;
    if (placed.loading || placed.error) return;
    if (versionSelectionRequired) return;
    const profileId = store.getSnapshot().currentProfileId;
    if (store.refreshFromStorage().currentProfileId !== profileId) return;
    let issues: readonly SisuImportIssue[] = [];
    let applied = false;
    try {
      applyStructure(store, (state) => {
        const result = resolveSisuImport(state, placed.content, {
          courseIds: placed.unavailableCourseIds,
          moduleIds: placed.unavailableModuleIds,
        });
        if (!result) return null;
        issues = result.issues;
        applied = true;
        return result.change;
      });
    } catch (caught) {
      setResolutionError(
        caught instanceof Error ? caught : new Error(String(caught)),
      );
      return;
    }
    if (!applied) return;
    setResolutionError(null);
    // A placement that left nothing out shows no notice at all.
    setImportIssues(issues.length > 0 ? issues : null);
  }, [
    pending,
    importBlocked,
    placed.loading,
    placed.error,
    placed.content,
    placed.unavailableCourseIds,
    placed.unavailableModuleIds,
    versionSelectionRequired,
    store,
  ]);
  const resolvedIndex = useMemo(() => indexResolved(base), [base]);
  const freeIds = useMemo(
    () =>
      selected.filter(
        (id) => !base.subtree.some((course) => course.group_id === id),
      ),
    [selected, base],
  );
  const freeCourses = useMemo(
    () =>
      freeIds
        .map((id) => placed.content.courses.get(id))
        .filter((course): course is CourseSummary => course !== undefined),
    [freeIds, placed.content],
  );
  const editor = useStructureEditor({
    resolved: base,
    edits,
    freeIds,
    content: placed.content,
    extend: placed.extend,
    notify: notice.show,
    confirmMoves,
    contentDatasetIdentity: placed.datasetIdentity,
    contentSelectionKey,
    locked: selectionRequiredGroups.length > 0,
  });
  // The displayed holders and their direct courses are read once for hit testing and for drawing,
  // with the saved rank applied after the free Unplaced summaries merge in.
  const dragHolders = useMemo(
    () =>
      displayedHolders(base).map((holder) => ({
        key: holder.key,
        courses: holderCourses(
          holder.node,
          holder.courses,
          freeCourses,
          courseOrder,
        ),
      })),
    [base, courseOrder, freeCourses],
  );
  const holderCourseMap = useMemo(
    () => new Map(dragHolders.map((holder) => [holder.key, holder.courses])),
    [dragHolders],
  );
  const dragInputKey = useMemo(
    () =>
      JSON.stringify([
        placed.datasetIdentity,
        contentSelectionKey,
        programmeGroupIds,
        choices,
        coursePlacements,
        modulePlacements,
        moduleVersions,
        courseOrder,
        selected,
        pendingSisuImport,
        selectionRequiredGroups,
        programmes.pending,
        editor.pendingModuleId,
      ]),
    [
      placed.datasetIdentity,
      contentSelectionKey,
      programmeGroupIds,
      choices,
      coursePlacements,
      modulePlacements,
      moduleVersions,
      courseOrder,
      selected,
      pendingSisuImport,
      selectionRequiredGroups,
      programmes.pending,
      editor.pendingModuleId,
    ],
  );
  const drag = useCourseDrag({
    treeRef,
    holders: dragHolders,
    enabled:
      completeInput !== null &&
      !contentLoading &&
      !contentError &&
      !pending &&
      !versionSelectionRequired &&
      programmes.pending === null &&
      editor.pendingModuleId === null,
    inputKey: dragInputKey,
    onDrop: editor.dropCourse,
  });
  const renderedStructureKey = useMemo(
    () =>
      JSON.stringify([
        programmeGroupIds,
        choices,
        coursePlacements,
        modulePlacements,
        contentSelectionKey,
      ]),
    [
      programmeGroupIds,
      choices,
      coursePlacements,
      modulePlacements,
      contentSelectionKey,
    ],
  );
  useEffect(() => {
    // Only a current complete projection supplies placed identities, never the held fallback.
    if (!completeInput || !chosenProjection) return;
    // A root that still needs an explicit version owns no reconciled subtree yet.
    if (selectionRequiredGroups.length > 0) return;
    const renderedKey = renderedStructureKey;
    const placedCourseIds = chosenProjection.subtree.map(
      (course) => course.group_id,
    );
    applyStructure(store, (state) => {
      if (state.pendingSisuImport !== null) return null;
      const structure = state.structure;
      const latestKey = JSON.stringify([
        structure.programmeGroupIds,
        structure.choices,
        structure.coursePlacements,
        structure.modulePlacements,
        moduleVersionKey(structure.moduleVersions),
      ]);
      if (latestKey !== renderedKey) return null;
      if (sameIdList(placedCourseIds, structure.placedCourseIds)) return null;
      return {
        next: {
          programmeGroupIds: [...structure.programmeGroupIds],
          choices: structure.choices,
          coursePlacements: structure.coursePlacements,
          modulePlacements: structure.modulePlacements,
          moduleVersions: { ...structure.moduleVersions },
          placedCourseIds,
          courseOrder: [...structure.courseOrder],
        },
      };
    });
  }, [
    chosenProjection,
    completeInput,
    renderedStructureKey,
    selectionRequiredGroups,
    store,
  ]);
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const [helpOpen, setHelpOpen] = useState(false);
  const drawerOpener = useRef<HTMLElement | null>(null);
  // The last node the drawer showed under its own key, held across an unfinished projection.
  const lastDrawer = useRef<{ key: string; resolved: ResolvedNode } | null>(
    null,
  );
  const active = activeKey
    ? (resolvedIndex.byKey.get(activeKey) ?? null)
    : null;
  // A selection write restarts hydration, so the projection is briefly unfinished. A node a
  // complete projection no longer holds, for example one an action removed, closes its drawer.
  useEffect(() => {
    if (
      activeKey !== null &&
      chosen !== null &&
      !resolvedIndex.byKey.has(activeKey)
    )
      setActiveKey(null);
  }, [activeKey, chosen, resolvedIndex]);
  const drawerResolved =
    active?.node.kind === "unplaced"
      ? unplacedTarget(active, freeCourses)
      : active;
  if (activeKey && drawerResolved)
    lastDrawer.current = { key: activeKey, resolved: drawerResolved };
  const heldDrawer =
    activeKey && lastDrawer.current?.key === activeKey
      ? lastDrawer.current.resolved
      : null;
  const shownDrawerResolved = drawerResolved ?? heldDrawer;
  const programmeIdsByKey = useMemo(
    () => new Map(programmeGroupIds.map((id) => [programmeKey(id), id])),
    [programmeGroupIds],
  );
  const open = activeKey !== null;
  usePhoneTabsOnClose(open);
  useEffect(() => {
    document.body.classList.toggle("structure-drawer-open", open);
    return () => document.body.classList.remove("structure-drawer-open");
  }, [open]);
  const openPicker = (mode: PickerMode) => {
    if (versionSelectionRequired) return;
    pickerOpener.current =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    setPicker(mode);
    setAttempt(null);
  };
  /** Focus a connected opener, or the first Add programme button when it has left the document. */
  const focusOpener = (opener: HTMLElement | null) => {
    if (opener?.isConnected) opener.focus({ preventScroll: true });
    else
      addRowHost.current
        ?.querySelector("button")
        ?.focus({ preventScroll: true });
  };
  const closePicker = (restoreFocus = true) => {
    const opener = pickerOpener.current;
    pickerOpener.current = null;
    setPicker(null);
    if (!restoreFocus) return;
    requestAnimationFrame(() => focusOpener(opener));
  };
  const { runAction: runPick, error: pickError } = useAction();
  const openConfirmation = (
    next: PendingConfirmation,
    opener: HTMLElement | null = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null,
  ) => {
    confirmationOpener.current = opener;
    setConfirmation(next);
    setAttempt(null);
  };
  const selectVersion = (groupId: string, module: CatalogueModule) =>
    runPick(() => {
      // One picker selection owns its entry, and every other saved value stays untouched.
      store.updateCurrent((state) => ({
        ...state,
        structure: {
          ...state.structure,
          moduleVersions: {
            ...state.structure.moduleVersions,
            [groupId]: module.sisu_module_id,
          },
        },
      }));
    });
  const pick = (module: CatalogueModule) =>
    runPick(() => {
      if (versionSelectionRequired) return;
      const groupId = module.group_id;
      if (picker?.kind === "replace") {
        // Choosing the programme already in that place keeps an equal version and writes nothing.
        if (groupId === picker.groupId) {
          const snapshot = store.getSnapshot();
          const current =
            snapshot.profiles[snapshot.currentProfileId].state.structure;
          const stored = current.moduleVersions[groupId];
          if (stored !== undefined) {
            if (stored === module.sisu_module_id) {
              closePicker();
              return;
            }
            throw new Error(VERSION_CONFLICT);
          }
          const report = placed.content.reports[groupId];
          // An equal hydrated version closes without installing a map entry, and missing content
          // raises `Programme is unavailable`.
          if (report === undefined) throw new Error("Programme is unavailable");
          if (report.root.module.sisu_module_id !== module.sisu_module_id)
            throw new Error(VERSION_CONFLICT);
          closePicker();
          return;
        }
        const target = picker.groupId;
        const opener = pickerOpener.current;
        closePicker(false);
        // The replacement reads its report first, so the confirmation can name every course it
        // pulls and the place that holds it.
        setAttempt("picker");
        void programmes
          .moves({
            kind: "replace",
            groupId: target,
            replacementGroupId: groupId,
            versionId: module.sisu_module_id,
          })
          .then((preview) => {
            if (!preview) {
              // The restore waits one frame so the closed picker has committed before focus moves.
              requestAnimationFrame(() => focusOpener(opener));
              return;
            }
            openConfirmation(
              {
                operation: "replace",
                groupId: target,
                replacementGroupId: groupId,
                moduleVersions: preview.moduleVersions,
                moves: preview.moves,
                moduleMoves: preview.moduleMoves,
                moduleFrom: preview.moduleFrom,
              },
              opener,
            );
          });
        return;
      }
      setAttempt("picker");
      void programmes
        .run({
          kind: "add",
          groupId,
          versionId: module.sisu_module_id,
        })
        .then((success) => {
          if (success) closePicker();
        });
    });
  const confirm = (removeCompletedCourses = false, pull = true) => {
    if (!confirmation || versionSelectionRequired) return;
    const operation: ProgrammeOperation | null =
      confirmation.operation === "replace"
        ? confirmation.replacementGroupId === null
          ? null
          : {
              kind: "replace",
              groupId: confirmation.groupId,
              replacementGroupId: confirmation.replacementGroupId,
              versionId: "",
            }
        : { kind: confirmation.operation, groupId: confirmation.groupId };
    if (!operation) return;
    if (operation.kind === "replace") {
      const versionId =
        confirmation.moduleVersions?.[operation.replacementGroupId];
      if (versionId === undefined) return;
      operation.versionId = versionId;
    }
    setAttempt("confirm");
    void programmes
      .run(
        operation,
        removeCompletedCourses,
        pull,
        confirmation.moduleVersions ?? undefined,
      )
      .then((success) => {
        if (!success) return;
        // A replaced or deleted programme leaves the tree, so its row trigger cannot hold focus.
        if (operation.kind !== "reset") confirmationOpener.current = null;
        setConfirmation(null);
      });
  };
  /** Ask about the courses one reset returns, then run it with the answered mode. */
  const askResetPull = (
    groupId: string,
    removeCompletedCourses: boolean,
    preview: ProgrammeMovePreview,
  ) => {
    setResetPull({
      groupId,
      removeCompletedCourses,
      holder: preview.holder,
      moves: preview.moves,
      moduleMoves: preview.moduleMoves,
    });
  };
  const answerResetPull = (answer: CourseMoveAnswer) => {
    if (versionSelectionRequired) return;
    const pending = resetPull;
    if (!pending) return;
    if (answer === false) {
      setResetPull(null);
      return;
    }
    setAttempt("confirm");
    void programmes
      .run(
        { kind: "reset", groupId: pending.groupId },
        pending.removeCompletedCourses,
        answer !== "keep",
      )
      .then((success) => {
        if (success) setResetPull(null);
      });
  };
  /**
   * Open the confirmation of one programme reset.
   *
   * The reset always asks. A scope that holds a completion asks first, and one that holds none asks
   * through the pull question alone when the reset returns courses to it. A pull list that cannot
   * be read reports through the pane notice and opens nothing.
   */
  const openReset = (groupId: string) => {
    if (versionSelectionRequired) return;
    if (
      scopeHoldsCompletion(
        resolvedIndex,
        programmeKey(groupId),
        completedCourseIds,
      )
    ) {
      openConfirmation({
        operation: "reset",
        groupId,
        replacementGroupId: null,
        moduleVersions: null,
        moves: [],
        moduleMoves: [],
      });
      return;
    }
    setAttempt("reset");
    void programmes.moves({ kind: "reset", groupId }).then((preview) => {
      if (!preview) return;
      if (preview.moves.length === 0 && preview.moduleMoves.length === 0) {
        openConfirmation({
          operation: "reset",
          groupId,
          replacementGroupId: null,
          moduleVersions: null,
          moves: [],
          moduleMoves: [],
        });
        return;
      }
      askResetPull(groupId, false, preview);
    });
  };
  /** Answer the reset question, and continue to the pull question when the reset has one. */
  const answerReset = (removeCompletedCourses: boolean) => {
    if (versionSelectionRequired) return;
    const pending = confirmation?.operation === "reset" ? confirmation : null;
    if (!pending) return;
    setAttempt("reset");
    void programmes
      .moves({ kind: "reset", groupId: pending.groupId })
      .then((preview) => {
        if (!preview) return;
        if (preview.moves.length === 0 && preview.moduleMoves.length === 0) {
          confirm(removeCompletedCourses);
          return;
        }
        setConfirmation(null);
        askResetPull(pending.groupId, removeCompletedCourses, preview);
      });
  };
  const confirmationName = (groupId: string): string => {
    const module = placed.content.reports[groupId]?.root.module;
    return module ? moduleName(module, language) : groupId;
  };
  const returnConfirmationFocus = () => {
    focusOpener(confirmationOpener.current);
  };
  const closeDrawer = () => {
    setActiveKey(null);
    const opener = drawerOpener.current;
    drawerOpener.current = null;
    if (opener?.isConnected)
      requestAnimationFrame(() => opener.focus({ preventScroll: true }));
  };
  const toggleDrawer = (key: string) => {
    if (activeKey === key) {
      closeDrawer();
      return;
    }
    drawerOpener.current =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    setActiveKey(key);
  };
  const renderNode = (
    node: ResolvedNode,
    depth: number,
    directProgramme = false,
  ): React.ReactNode => {
    const display = displayContents(node);
    const children = display.children.map((child) =>
      renderNode(child, node.node.transparent ? depth : depth + 1),
    );
    if (node.node.transparent) return children;
    const isUnplaced = node.node.kind === "unplaced";
    const rowCourses = holderCourseMap.get(node.node.key) ?? display.courses;
    const groupId = isUnplaced ? null : (node.node.module?.group_id ?? null);
    return (
      <StructureNodeRow
        key={node.node.key}
        resolved={node}
        courses={rowCourses}
        notes={display.notes}
        depth={depth}
        active={activeKey === node.node.key}
        onOpen={() => toggleDrawer(node.node.key)}
        drag={drag}
        children={children.length ? children : undefined}
        programmeActions={
          directProgramme && groupId && !versionSelectionRequired
            ? {
                onReplace: () => openPicker({ kind: "replace", groupId }),
                onReset: () => openReset(groupId),
                onDelete: () =>
                  openConfirmation({
                    operation: "delete",
                    groupId,
                    replacementGroupId: null,
                    moduleVersions: null,
                    moves: [],
                    moduleMoves: [],
                  }),
              }
            : undefined
        }
      />
    );
  };
  // The Add row sits between the last programme and the global Unplaced studies row.
  const rootContents = displayContents(base);
  const rows = rootContents.children.map((child) =>
    renderNode(child, 0, child.node.kind !== "unplaced"),
  );
  const unplacedIndex = rootContents.children.findIndex(
    (child) => child.node.kind === "unplaced",
  );
  rows.splice(
    unplacedIndex < 0 ? rows.length : unplacedIndex,
    0,
    <div className="add-programme-slot" key="add-programme" ref={addRowHost}>
      <AddProgrammeRow
        onAdd={() => openPicker({ kind: "add" })}
        disabled={
          contentLoading ||
          programmes.pending !== null ||
          versionSelectionRequired
        }
      />
      {programmeGroupIds.length === 0 && (
        <div className="structure-empty-import">
          <ProfileTransfer store={store} importOnly />
        </div>
      )}
    </div>,
  );
  const help: readonly HelpSection[] = [
    {
      heading: t("structure"),
      items: [
        {
          term: (
            <HelpLink href="/docs#guide-structure/adding-a-programme">
              {t("Add programme")}
            </HelpLink>
          ),
          text: t(
            "Add a degree programme or module by name or code. Choose an exact version when several are offered. Open a module row to choose alternatives or add courses through its drawer.",
          ),
        },
        {
          term: (
            <HelpLink href="/docs#guide-structure/unplaced-studies">
              {t("Unplaced studies")}
            </HelpLink>
          ),
          text: t(
            "Holds selected courses with no place in a programme or module. Add a course here from its course menu, then place it where you want it. A course appears in one place and its completion is shared across tabs.",
          ),
        },
      ],
    },
    {
      heading: t("editing"),
      items: [
        {
          term: (
            <HelpLink href="/docs#guide-structure-edit/dragging-courses-and-card-order">
              {t("Dragging courses")}
            </HelpLink>
          ),
          text: t(
            "On desktop, drag a course card to move or reorder it. On a touch screen, hold until the card lifts, then drag. The outline marks the drop position. Hold near the top or bottom to scroll. Dropping asks no confirmation, and a completed course keeps its completion.",
          ),
        },
        {
          term: (
            <HelpLink href="/docs#guide-structure-edit/resetting-a-part">
              {t("Reset programme")}
            </HelpLink>
          ),
          text: t(
            "The programme menu and the module drawer restore official content through a confirmation. Reset preserves completed courses. Reset all also clears completions held by the affected part. Read the confirmation before resetting, replacing or deleting a part.",
          ),
        },
        {
          term: (
            <HelpLink href="/docs#guide-profiles">
              {t("Profiles and import")}
            </HelpLink>
          ),
          text: t(
            "Your programmes, choices, placements and card order are saved in this browser's profile. Use the profile panel to export or import a plan. With no programme added, the import area is also shown below Add programme.",
          ),
        },
      ],
    },
  ];
  return (
    <main
      className="pane-content structure-pane"
      role="tabpanel"
      aria-label={t("Structure of studies")}
    >
      <div
        className={`structure-layout${open ? " with-drawer" : ""}${helpOpen ? " with-help" : ""}`}
      >
        <div className="structure-help-row">
          <HelpTip
            title={t("Structure of studies")}
            explain="Explain structure of studies"
            sections={help}
            onOpenChange={setHelpOpen}
            keepOpenOnOutside={(target) =>
              target instanceof Element &&
              target.closest(".structure-tree") !== null
            }
          />
        </div>
        {contentError && (
          <ErrorNotice error={contentError} language={language} />
        )}
        <AnimatePresence>
          {importIssues && (
            <SisuImportNotice
              issues={importIssues}
              onDismiss={() => setImportIssues(null)}
            />
          )}
        </AnimatePresence>
        {editor.error && (
          <ErrorNotice error={editor.error} language={language} />
        )}
        {(attempt === "picker" || attempt === "reset") && programmes.error && (
          <ErrorNotice error={programmes.error} language={language} />
        )}
        {importBlocked && (
          <p className="error-notice" role="status">
            {t(
              "Sisu import paused to preserve saved edits. Your profile is unchanged.",
            )}
          </p>
        )}
        {!contentError &&
          !placed.loading &&
          !importBlocked &&
          versionSelectionRequired &&
          selectionRequiredGroups.map((groupId) => (
            <ModuleVersionPicker
              key={groupId}
              groupId={groupId}
              disabled={
                programmes.pending !== null || editor.pendingModuleId !== null
              }
              onSelect={(module) => selectVersion(groupId, module)}
            />
          ))}
        {contentLoading ? (
          importBlocked ? null : (
            <div
              className="structure-skeleton"
              aria-label={t("Loading structure content")}
            >
              {Array.from({ length: 4 }, (_, index) => (
                <i key={index} />
              ))}
            </div>
          )
        ) : (
          !contentError && (
            <div className="structure-tree" ref={treeRef}>
              <LayoutGroup id="structure-items">
                <AnimatePresence>{rows}</AnimatePresence>
              </LayoutGroup>
            </div>
          )
        )}
        <StructureDrawer
          target={
            !contentLoading && !contentError && activeKey && shownDrawerResolved
              ? {
                  resolved: shownDrawerResolved,
                  programmeId: programmeIdsByKey.get(activeKey) ?? null,
                }
              : null
          }
          editor={editor}
          onClose={closeDrawer}
          index={resolvedIndex}
          onResetProgramme={(groupId) => openReset(groupId)}
        />
      </div>
      {pickError && <ErrorNotice error={pickError} language={language} />}
      <ProgrammeConfirmDialog
        operation={confirmation?.operation === "replace" ? "replace" : null}
        name={confirmation ? confirmationName(confirmation.groupId) : ""}
        replacementName={
          confirmation?.replacementGroupId
            ? confirmationName(confirmation.replacementGroupId)
            : ""
        }
        moduleFrom={confirmation?.moduleFrom}
        moves={confirmation?.moves ?? []}
        moduleMoves={confirmation?.moduleMoves ?? []}
        hasCompletedCourses={
          confirmation !== null &&
          scopeHoldsCompletion(
            resolvedIndex,
            programmeKey(confirmation.groupId),
            completedCourseIds,
          )
        }
        busy={programmes.pending !== null}
        error={attempt === "confirm" ? programmes.error : null}
        onCancel={() => setConfirmation(null)}
        onConfirm={(pull) => confirm(false, pull)}
        returnFocus={returnConfirmationFocus}
      />
      <ModuleRemoveDialog
        open={confirmation?.operation === "reset"}
        operation="reset"
        holderKind="programme"
        name={confirmation ? confirmationName(confirmation.groupId) : ""}
        hasEdits={false}
        hasCompletedCourses={
          confirmation !== null &&
          scopeHoldsCompletion(
            resolvedIndex,
            programmeKey(confirmation.groupId),
            completedCourseIds,
          )
        }
        busy={programmes.pending !== null}
        error={attempt === "confirm" ? programmes.error : null}
        onCancel={() => setConfirmation(null)}
        onKeep={() => answerReset(false)}
        onRemove={() => answerReset(true)}
        returnFocus={returnConfirmationFocus}
      />
      <ModuleRemoveDialog
        open={confirmation?.operation === "delete"}
        operation="remove"
        holderKind="programme"
        name={confirmation ? confirmationName(confirmation.groupId) : ""}
        hasEdits={false}
        hasCompletedCourses={
          confirmation !== null &&
          scopeHoldsCompletion(
            resolvedIndex,
            programmeKey(confirmation.groupId),
            completedCourseIds,
          )
        }
        busy={programmes.pending !== null}
        error={attempt === "confirm" ? programmes.error : null}
        onCancel={() => setConfirmation(null)}
        onKeep={() => confirm()}
        onRemove={() => confirm(true)}
        returnFocus={returnConfirmationFocus}
      />
      <CourseMoveConfirmDialog
        request={moveConfirm.request}
        onAnswer={moveConfirm.answer}
        returnFocus={() => focusOpener(moveOpener.current)}
      />
      <CourseMoveConfirmDialog
        request={
          resetPull
            ? {
                holder: resetPull.holder,
                moves: resetPull.moves,
                moduleMoves: resetPull.moduleMoves,
              }
            : null
        }
        busy={programmes.pending !== null}
        error={attempt === "confirm" ? programmes.error : null}
        onAnswer={answerResetPull}
        returnFocus={returnConfirmationFocus}
      />
      <div className="structure-root-overlay">
        {/* The picker anchors to the visible tab area, not to the scrolled tree content. */}
        <PickerOverlay
          open={picker !== null}
          onClose={() => closePicker()}
          eyebrow={`// ${t("Choose programme")}`}
          anchorClassName="structure-root-anchor"
        >
          <ModuleLookupBox
            open={picker !== null}
            pendingId={programmes.pending}
            onPick={pick}
          />
        </PickerOverlay>
      </div>
      {drag.lifted &&
        createPortal(
          <div
            className="structure-course-lifted structure-tree"
            style={{
              ...(drag.settleTarget ?? drag.lifted),
              transform: drag.settleTarget
                ? "none"
                : `translateY(${COURSE_DRAG_LIFT_Y}px) scale(${COURSE_DRAG_LIFT_SCALE})`,
              transformOrigin: "center",
              transition: drag.settleTarget
                ? "left 0.3s cubic-bezier(0.22, 0.8, 0.2, 1), top 0.3s cubic-bezier(0.22, 0.8, 0.2, 1), width 0.3s cubic-bezier(0.22, 0.8, 0.2, 1), height 0.3s cubic-bezier(0.22, 0.8, 0.2, 1), transform 0.3s cubic-bezier(0.22, 0.8, 0.2, 1)"
                : undefined,
            }}
            aria-hidden="true"
            inert
          >
            <StructureCard
              course={drag.lifted.course.course}
              completed={completedCourseIds.includes(
                drag.lifted.course.course.group_id,
              )}
              added={drag.lifted.course.added}
            />
          </div>,
          document.body,
        )}
    </main>
  );
}
