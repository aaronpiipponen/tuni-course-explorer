/** Ordered programme composition of the tree, picker, confirmations and drawer. */
import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, LayoutGroup } from "framer-motion";
import type {
  CatalogueModule,
  CourseSummary,
  ModuleSummary,
} from "../../api/types";
import { useProfileSelector } from "../../state/useProfileSelector";
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
import { ModuleVersionPicker } from "./ModuleVersionPicker";
import { displayContents } from "./display";
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
import type { PulledCourse } from "./edits";
import { useAction } from "../../shared/useAction";
import { usePlacedContent } from "./usePlacedContent";
import { useStructureEditor } from "./useStructureEditor";
import { useNotice } from "../../shared/useNotice";
import { usePhoneTabsOnClose } from "../../shared/usePhoneTabsOnClose";
import { SisuImportNotice } from "./SisuImportNotice";
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
  /** The courses the replacement programme pulls out of the nodes they are in now. */
  moves: readonly PulledCourse[];
  /** Localized node that displays the replacement programme now, when a visible node does. */
  moduleFrom?: (language: DisplayLanguage) => string;
};

/** One pending pull question of a reset, with the completion choice its answer already made. */
type PendingResetPull = {
  groupId: string;
  removeCompletedCourses: boolean;
  holder: ModuleSummary;
  moves: readonly PulledCourse[];
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
  // One confirmation lists the courses an addition pulls out of the nodes they are in now.
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
      selectionKey: contentSelectionKey,
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
    contentSelectionKey,
    programmeGroupIds,
    edits,
  ]);
  // A complete input is held only for its own serving dataset and selection identity.
  const [lastComplete, setLastComplete] = useState<{
    datasetIdentity: string;
    selectionKey: string;
    programmeGroupIds: readonly string[];
    edits: StructureEdits;
    content: PlacedContent;
  } | null>(null);
  useEffect(() => {
    if (completeInput) setLastComplete(completeInput);
  }, [completeInput]);
  const chosen =
    completeInput ??
    (lastComplete &&
    lastComplete.datasetIdentity === placed.datasetIdentity &&
    lastComplete.selectionKey === contentSelectionKey
      ? lastComplete
      : null);
  // The language projects the chosen input, so held same-identity content follows the live language.
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
  const drawerOpener = useRef<HTMLElement | null>(null);
  const active = activeKey
    ? (resolvedIndex.byKey.get(activeKey) ?? null)
    : null;
  // A node the structure does not hold, for example one an action removed, closes its drawer.
  useEffect(() => {
    if (activeKey !== null && !resolvedIndex.byKey.has(activeKey))
      setActiveKey(null);
  }, [activeKey, resolvedIndex]);
  const drawerResolved =
    active?.node.kind === "unplaced"
      ? {
          ...active,
          courses: [
            ...active.courses,
            ...freeCourses
              .filter(
                (course) =>
                  !active.courses.some(
                    (item) => item.course.group_id === course.group_id,
                  ),
              )
              .map((course) => ({ course, added: false })),
          ],
          subtree: [
            ...active.subtree,
            ...freeCourses.filter(
              (course) =>
                !active.subtree.some(
                  (item) => item.group_id === course.group_id,
                ),
            ),
          ],
        }
      : active;
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
    if (opener?.isConnected) opener.focus();
    else addRowHost.current?.querySelector("button")?.focus();
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
        // The replacement reads its report first, so the confirmation can name every course it pulls
        // and the place that holds it now.
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
   * through the pull question alone when the reset returns courses to it. A pull list that cannot be
   * read reports through the pane notice and opens nothing.
   */
  const openReset = (groupId: string) => {
    if (versionSelectionRequired) return;
    if (programmeHoldsCompletion(groupId)) {
      openConfirmation({
        operation: "reset",
        groupId,
        replacementGroupId: null,
        moduleVersions: null,
        moves: [],
      });
      return;
    }
    setAttempt("reset");
    void programmes.moves({ kind: "reset", groupId }).then((preview) => {
      if (!preview) return;
      if (preview.moves.length === 0) {
        openConfirmation({
          operation: "reset",
          groupId,
          replacementGroupId: null,
          moduleVersions: null,
          moves: [],
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
        if (preview.moves.length === 0) {
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
  /** Whether the programme holds a completed course in the displayed projection. */
  const programmeHoldsCompletion = (groupId: string): boolean => {
    const node = resolvedIndex.byKey.get(programmeKey(groupId));
    return (
      node !== undefined &&
      node.subtree.some((course) =>
        completedCourseIds.includes(course.group_id),
      )
    );
  };
  const returnConfirmationFocus = () => {
    focusOpener(confirmationOpener.current);
  };
  const closeDrawer = () => {
    setActiveKey(null);
    const opener = drawerOpener.current;
    drawerOpener.current = null;
    if (opener?.isConnected) requestAnimationFrame(() => opener.focus());
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
    const rowCourses = isUnplaced
      ? [
          ...display.courses,
          ...freeCourses.map((course) => ({
            course,
            added: false,
            owner: node.node,
          })),
        ]
      : display.courses;
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
  return (
    <main
      className="pane-content structure-pane"
      role="tabpanel"
      aria-label={t("Structure of studies")}
    >
      <div className={`structure-layout${open ? " with-drawer" : ""}`}>
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
            <div className="structure-tree">
              <LayoutGroup id="structure-items">
                <AnimatePresence>{rows}</AnimatePresence>
              </LayoutGroup>
            </div>
          )
        )}
        <StructureDrawer
          target={
            !contentLoading && !contentError && activeKey
              ? {
                  resolved: drawerResolved ?? base,
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
        hasCompletedCourses={
          confirmation !== null &&
          programmeHoldsCompletion(confirmation.groupId)
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
        hasCompletedCourses={
          confirmation !== null &&
          programmeHoldsCompletion(confirmation.groupId)
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
        hasCompletedCourses={
          confirmation !== null &&
          programmeHoldsCompletion(confirmation.groupId)
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
            ? { holder: resetPull.holder, moves: resetPull.moves }
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
    </main>
  );
}
