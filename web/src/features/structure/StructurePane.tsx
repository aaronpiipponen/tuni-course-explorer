/** Ordered programme composition of the tree, picker, confirmations and drawer. */
import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, LayoutGroup } from "framer-motion";
import type { CourseSummary, ModuleSummary } from "../../api/types";
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
import { displayContents } from "./display";
import { moduleName } from "./presentation";
import {
  applyStructure,
  programmeForest,
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
import { useNotice } from "./useNotice";
import { SisuImportNotice } from "./SisuImportNotice";
import {
  resolveSisuImport,
  captureModuleIds,
  type SisuImportIssue,
} from "./sisu";
import type { DisplayLanguage } from "../../state/types";

type PickerMode = { kind: "add" } | { kind: "replace"; groupId: string };

type PendingConfirmation = {
  operation: "replace" | "reset" | "delete";
  groupId: string;
  replacementGroupId: string | null;
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

/**
 * Project the connected structure from the hydrated content, or null while content it needs is
 * absent.
 *
 * A missing programme report, a missing report of a placed module, and a missing summary of a
 * placed course are waiting states, so the pane holds the structure it drew last instead of
 * throwing or drawing an incomplete tree. The hydration owner requests exactly these identities.
 */
function projection(
  ids: readonly string[],
  edits: StructureEdits,
  content: PlacedContent,
  language: DisplayLanguage,
): ResolvedNode | null {
  const forest = programmeForest(ids, content, language);
  if (!forest) return null;
  const incomplete =
    Object.entries(edits.coursePlacements).some(
      ([id, target]) => typeof target === "string" && !content.courses.has(id),
    ) ||
    Object.entries(edits.modulePlacements).some(
      ([id, target]) => typeof target === "string" && !content.reports[id],
    );
  return incomplete ? null : resolveStructure(forest, edits, content, language);
}

const emptyProjection = (language: DisplayLanguage): ResolvedNode =>
  resolveStructure(
    buildProgrammeForest([], language),
    emptyEdits(),
    NO_CONTENT,
    language,
  );

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
    pending,
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
  );
  const [loadedOnce, setLoadedOnce] = useState(false);
  useEffect(() => {
    if (!placed.loading) setLoadedOnce(true);
  }, [placed.loading]);
  const [resolutionError, setResolutionError] = useState<Error | null>(null);
  const [importIssues, setImportIssues] = useState<
    readonly SisuImportIssue[] | null
  >(null);
  /**
   * Place one pending Sisu capture in a single write once its ordinary reads have settled.
   *
   * The captured hierarchy is resolved from the callback's own state, so a language or completion
   * change another tab made while the reads waited is kept. A failure leaves the pending record
   * untouched and shows its error instead of retrying an unchanged read.
   */
  useEffect(() => {
    if (!pending) return;
    if (placed.loading || placed.error) return;
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
    placed.loading,
    placed.error,
    placed.content,
    placed.unavailableCourseIds,
    placed.unavailableModuleIds,
    store,
  ]);
  // Only the first load shows a skeleton tree. A pending capture holds the tree until placement.
  const contentLoading = pending || (!loadedOnce && placed.loading);
  const contentError = placed.error ?? resolutionError;
  const current =
    contentLoading || contentError
      ? null
      : projection(programmeGroupIds, edits, placed.content, language);
  // While placed content loads, the last complete input is held and reprojected in the live language.
  const lastComplete = useRef<{
    programmeGroupIds: readonly string[];
    edits: StructureEdits;
    content: PlacedContent;
  } | null>(null);
  if (current)
    lastComplete.current = {
      programmeGroupIds,
      edits,
      content: placed.content,
    };
  const held = lastComplete.current
    ? projection(
        lastComplete.current.programmeGroupIds,
        lastComplete.current.edits,
        lastComplete.current.content,
        language,
      )
    : null;
  const base = current ?? held ?? emptyProjection(language);
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
  });
  useEffect(() => {
    if (contentLoading || contentError) return;
    applyStructure(store, (state) => {
      const structure = state.structure;
      // Content the hydrated snapshot lacks is a waiting state, not an empty tree.
      const resolved = projection(
        structure.programmeGroupIds,
        structure,
        placed.content,
        language,
      );
      if (!resolved) return null;
      const actual = resolved.subtree.map((course) => course.group_id);
      if (sameIdList(actual, structure.placedCourseIds)) return null;
      return {
        next: {
          programmeGroupIds: [...structure.programmeGroupIds],
          choices: structure.choices,
          coursePlacements: structure.coursePlacements,
          modulePlacements: structure.modulePlacements,
          placedCourseIds: actual,
        },
      };
    });
  }, [contentLoading, contentError, placed.content, store, language]);
  const [activeKey, setActiveKey] = useState<string | null>(null);
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
  useEffect(() => {
    document.body.classList.toggle("structure-drawer-open", open);
    return () => document.body.classList.remove("structure-drawer-open");
  }, [open]);
  const openPicker = (mode: PickerMode) => {
    setPicker(mode);
    setAttempt(null);
  };
  const closePicker = () => setPicker(null);
  const { runAction: runPick, error: pickError } = useAction();
  const openConfirmation = (next: PendingConfirmation) => {
    confirmationOpener.current =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    setConfirmation(next);
    setAttempt(null);
  };
  const pick = (module: ModuleSummary) =>
    runPick(() => {
      const groupId = module.group_id;
      if (picker?.kind === "replace") {
        // Choosing the programme already in that place keeps it and writes nothing.
        if (groupId === picker.groupId) {
          closePicker();
          return;
        }
        const target = picker.groupId;
        closePicker();
        // The replacement reads its report first, so the confirmation can name every course it pulls
        // and the place that holds it now.
        setAttempt("picker");
        void programmes
          .moves({
            kind: "replace",
            groupId: target,
            replacementGroupId: groupId,
          })
          .then((preview) => {
            if (!preview) return;
            openConfirmation({
              operation: "replace",
              groupId: target,
              replacementGroupId: groupId,
              moves: preview.moves,
              moduleFrom: preview.moduleFrom,
            });
          });
        return;
      }
      setAttempt("picker");
      void programmes.run({ kind: "add", groupId }).then((success) => {
        if (success) closePicker();
      });
    });
  const confirm = (removeCompletedCourses = false, pull = true) => {
    if (!confirmation) return;
    const operation: ProgrammeOperation | null =
      confirmation.operation === "replace"
        ? confirmation.replacementGroupId === null
          ? null
          : {
              kind: "replace",
              groupId: confirmation.groupId,
              replacementGroupId: confirmation.replacementGroupId,
            }
        : { kind: confirmation.operation, groupId: confirmation.groupId };
    if (!operation) return;
    setAttempt("confirm");
    void programmes
      .run(operation, removeCompletedCourses, pull)
      .then((success) => {
        if (success) setConfirmation(null);
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
    confirmationOpener.current =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    if (programmeHoldsCompletion(groupId)) {
      openConfirmation({
        operation: "reset",
        groupId,
        replacementGroupId: null,
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
          moves: [],
        });
        return;
      }
      askResetPull(groupId, false, preview);
    });
  };
  /** Answer the reset question, and continue to the pull question when the reset has one. */
  const answerReset = (removeCompletedCourses: boolean) => {
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
    const opener = confirmationOpener.current;
    if (opener?.isConnected) opener.focus();
    else addRowHost.current?.querySelector("button")?.focus();
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
        onOpen={() =>
          setActiveKey((current) =>
            current === node.node.key ? null : node.node.key,
          )
        }
        children={children.length ? children : undefined}
        programmeActions={
          directProgramme && groupId
            ? {
                onReplace: () => openPicker({ kind: "replace", groupId }),
                onReset: () => openReset(groupId),
                onDelete: () =>
                  openConfirmation({
                    operation: "delete",
                    groupId,
                    replacementGroupId: null,
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
        disabled={contentLoading || programmes.pending !== null}
      />
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
        {contentLoading ? (
          <div
            className="structure-skeleton"
            aria-label={t("Loading structure content")}
          >
            {Array.from({ length: 4 }, (_, index) => (
              <i key={index} />
            ))}
          </div>
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
          onClose={() => setActiveKey(null)}
          index={resolvedIndex}
          onResetProgramme={(groupId) => openReset(groupId)}
        />
      </div>
      {notice.toast}
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
        returnFocus={() => {
          const opener = moveOpener.current;
          if (opener?.isConnected) opener.focus();
          else addRowHost.current?.querySelector("button")?.focus();
        }}
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
          onClose={closePicker}
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
