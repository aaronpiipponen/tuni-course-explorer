/** Browser-owned structure edits, selection migration and user notices. */
import { useEffect, useRef, useState } from "react";
import type {
  CatalogueModule,
  CourseSummary,
  ModuleSummary,
} from "../../api/types";
import { DATASET_CHANGED_MESSAGE } from "../../app/cachedRead";
import { useReadCache } from "../../app/useReadCache";
import { useProfileSelector } from "../../state/useProfileSelector";
import { useAction } from "../../shared/useAction";
import {
  applyStructure,
  clearCourseOrder,
  programmeForest,
  resetCompletionChange,
  resetUnplaced,
  sameIdList,
  VERSION_CONFLICT,
  type StructureChange,
} from "./actions";
import {
  UNPLACED_KEY,
  type StructureEdits,
  type StructureState,
} from "./state";
import {
  courseHolders,
  indexResolved,
  nextChoices,
  officialHomes,
  resolveStructure,
  type PlacedContent,
  type ResolvedNode,
  type StructureNode,
  type StructureRuleItem,
} from "./model";
import {
  clearedScopePlacements,
  hasScopedEdits,
  restoreScopeContents,
  officialPulls,
  insideScope,
  officialPlacementTarget,
  placeCourse,
  placeModule,
  moveResetOptions,
  placeModuleWithCourses,
  removalPlacements,
  type PulledCourse,
  type PulledModule,
} from "./edits";
import { moduleName, nodeWordingKind, resolvedNodeLabel } from "./presentation";
import type {
  CourseMoveAnswer,
  CourseMoveRequest,
} from "./CourseMoveConfirmDialog";
import { toggleCompleted } from "../../state/course-actions";
import {
  courseSource,
  displayContents,
  holderCourses,
  moduleSource,
} from "./display";
import type { DisplayLanguage, ProfileState } from "../../state/types";
import { uiText } from "../../shared/wording";
import {
  forgetRemovedModuleVersions,
  moduleVersionKey,
} from "./moduleVersions";
import type { ExtraContent } from "./usePlacedContent";
import { readProspectiveStructure } from "./structureReads";

/** Find the official rule entry that renders one module, with the choice path that reaches it. */
function findRuleModule(
  root: StructureNode,
  moduleId: string,
): StructureRuleItem | null {
  const walk = (node: StructureNode): StructureRuleItem | null => {
    const entries =
      node.kind === "choice"
        ? node.options.flatMap((option) => option.entries)
        : node.entries;
    for (const entry of entries) {
      if (entry.kind !== "node") continue;
      if (entry.node.module?.group_id === moduleId && entry.origin)
        return { entry, origin: entry.origin };
      const nested = walk(entry.node);
      if (nested) return nested;
    }
    return null;
  };
  return walk(root);
}

/**
 * One module operation source: rendered content or a catalogue identity read before it applies.
 */
export type ModuleOperationSource =
  | { kind: "loaded"; module: ModuleSummary }
  | {
      kind: "read";
      module: CatalogueModule;
      prepare: (
        signal: AbortSignal,
        operationDatasetIdentity: string,
      ) => Promise<{
        module: ModuleSummary;
        content: PlacedContent;
        moduleVersions: Readonly<Record<string, string>>;
      }>;
    };

const asEdits = (state: StructureState): StructureEdits => ({
  choices: state.choices,
  coursePlacements: state.coursePlacements,
  modulePlacements: state.modulePlacements,
});

/**
 * Return an ordered programme list without one identity.
 *
 * A module the ordered list holds renders at the programme level, so placing it in a node takes it
 * out of that list and its entry resolves at the destination instead.
 */
const withoutProgrammeGroupId = (
  programmeGroupIds: readonly string[],
  id: string,
): string[] => programmeGroupIds.filter((programmeId) => programmeId !== id);

/**
 * Return the localized place a module source names.
 *
 * A source whose node is the forest wrapper places the module at the programme level, while every
 * other source is the programme or module node that displays the module.
 */
const modulePlaceText =
  (source: ResolvedNode) =>
  (language: DisplayLanguage): string =>
    source.node.kind === "group"
      ? uiText(language, "the programme list")
      : resolvedNodeLabel(source, language);

/** Return the structure editor operations and its pending selection state. */
export function useStructureEditor({
  resolved,
  edits,
  freeIds,
  content,
  extend,
  notify,
  confirmMoves,
  contentDatasetIdentity,
  contentSelectionKey,
  locked = false,
}: {
  resolved: ResolvedNode;
  edits: StructureEdits;
  freeIds: readonly string[];
  content: PlacedContent;
  extend(extra: ExtraContent): PlacedContent;
  notify(text: (language: DisplayLanguage) => string): void;
  confirmMoves(request: CourseMoveRequest): Promise<CourseMoveAnswer>;
  contentDatasetIdentity: string;
  /** The exact selections the supplied content answers. */
  contentSelectionKey: string;
  /** Whether a selection-required structure suspends every tree mutation. */
  locked?: boolean;
}) {
  const cache = useReadCache();
  const { store, value: completedCourseIds } = useProfileSelector(
    (state) => state.completedCourseIds,
  );
  const moduleOperation = useRef<AbortController | null>(null);
  const { runAction, error: actionError } = useAction();
  const [error, setError] = useState<Error | null>(null);
  const [pendingModuleId, setPendingModuleId] = useState<string | null>(null);
  useEffect(
    () => () => {
      moduleOperation.current?.abort();
      moduleOperation.current = null;
    },
    [],
  );
  const forestFor = (state: StructureState, ctx: PlacedContent) => {
    const forest = programmeForest(state.programmeGroupIds, ctx);
    if (!forest) throw new Error("Programme is unavailable");
    return forest;
  };
  const projectionFor = (state: StructureState, ctx: PlacedContent) =>
    indexResolved(resolveStructure(forestFor(state, ctx), state, ctx));
  /** The open profile's stored structure, read by the interfaces that compare without writing. */
  const storedStructure = (): StructureState => {
    const snapshot = store.getSnapshot();
    return snapshot.profiles[snapshot.currentProfileId].state.structure;
  };
  // A node-key action applies only while the latest forest holds its target.
  const requireNode = (
    state: StructureState,
    ctx: PlacedContent,
    key: string,
  ) => {
    if (!projectionFor(state, ctx).byKey.has(key))
      throw new Error("Structure target is unavailable");
  };
  const commit = (
    updateEdits: (current: StructureState) => StructureEdits,
    ctx: PlacedContent,
    removed: readonly string[] = [],
    nextProgrammes?: (current: StructureState) => string[],
    moduleVersions?: Readonly<Record<string, string>>,
    complete?: (
      state: ProfileState,
      change: StructureChange,
    ) => StructureChange,
  ) => {
    applyStructure(store, (state) => {
      const current = state.structure;
      const before = resolveStructure(forestFor(current, ctx), current, ctx);
      const programmeGroupIds = nextProgrammes
        ? nextProgrammes(current)
        : [...current.programmeGroupIds];
      const forest = forestFor({ ...current, programmeGroupIds }, ctx);
      const next = updateEdits(current);
      const projection = resolveStructure(forest, next, ctx);
      const change: StructureChange = {
        next: {
          programmeGroupIds,
          ...next,
          moduleVersions: forgetRemovedModuleVersions(
            moduleVersions ?? current.moduleVersions,
            before,
            projection,
          ),
          placedCourseIds: projection.subtree.map((course) => course.group_id),
          courseHolders: courseHolders(projection),
          courseOrder: [...current.courseOrder],
        },
        removedCourseIds: removed,
      };
      return complete ? complete(state, change) : change;
    });
  };
  const choose = (node: StructureNode, optionKey: string) =>
    runAction(() => {
      if (locked) return;
      commit((current) => {
        requireNode(current, content, node.key);
        return {
          ...asEdits(current),
          choices: nextChoices(current.choices, node, optionKey),
        };
      }, content);
      notify((messageLanguage) =>
        uiText(
          messageLanguage,
          (edits.choices[node.key]?.length ?? 0)
            ? "Selection changed"
            : "Selection made",
        ),
      );
    });
  const addCourse = (course: CourseSummary, node: StructureNode) =>
    runAction(() => {
      if (locked) return;
      const id = course.group_id;
      const index = indexResolved(resolved);
      const placed = index.courseAt.get(id);
      if (placed === index.byKey.get(node.key)) {
        notify((messageLanguage) =>
          uiText(
            messageLanguage,
            nodeWordingKind(node) === "programme"
              ? "Already in this programme"
              : "Already in this module",
          ),
        );
        return;
      }
      const ctx = extend({
        datasetIdentity: contentDatasetIdentity,
        courses: [course],
      });
      commit((current) => {
        requireNode(current, ctx, node.key);
        const forest = forestFor(current, ctx);
        const homes = officialHomes(forest, current, ctx);
        return {
          ...asEdits(current),
          coursePlacements: placeCourse(
            current,
            homes,
            id,
            officialPlacementTarget(
              forest,
              current,
              ctx,
              "coursePlacements",
              id,
              node.key,
            ),
          ).coursePlacements,
        };
      }, ctx);
    });
  /**
   * Prepare one module operation's records and the moves it authorizes, on the supplied state.
   *
   * An official selection extends the stored choices along the item's choice path first, so an
   * owner inside the selected option exists before the module is placed. The module source is the
   * visible node that renders the module, and `moveKey` names that source together with the node
   * key the module itself renders at and the pulled courses with the nodes they leave, so the write
   * compares the authorized moves against the latest state once. A module the ordered programme
   * list holds is taken out of that list as it is placed, so its entry resolves at the destination
   * node and not at the programme level. The node key the tree the choice extension has not reached
   * renders the module at decides whether the placement moves the module's whole current subtree or
   * takes its scope's official defaults. `pull` is whether that adoption moves the listed courses
   * into the module or leaves them where they are.
   */
  const modulePlacement = (
    current: StructureState,
    ctx: PlacedContent,
    module: ModuleSummary,
    targetKey: string,
    item: StructureRuleItem | null,
    pull = true,
    reset?: "keep" | "all",
  ): {
    edits: StructureEdits;
    moves: readonly PulledCourse[];
    moduleMoves: readonly PulledModule[];
    programmeIds: readonly string[];
    moduleFrom: ResolvedNode | null;
    resetMoves: readonly PulledCourse[];
    resetModuleMoves: readonly PulledModule[];
    resetProgrammeIds: readonly string[];
    resetOptions: "reset" | "reset-all" | "both" | undefined;
    sourceKey: string | null;
    destinationKey: string;
    moveKey: string;
  } => {
    const id = module.group_id;
    let choices = current.choices;
    if (item)
      for (const step of item.origin.choicePath)
        if (!(choices[step.node.key] ?? []).includes(step.optionKey))
          choices = nextChoices(choices, step.node, step.optionKey);
    const forest = forestFor(current, ctx);
    const edits = { ...asEdits(current), choices };
    const beforeTree = resolveStructure(forest, asEdits(current), ctx);
    const before = indexResolved(beforeTree);
    const candidate = indexResolved(resolveStructure(forest, edits, ctx));
    const held = candidate.moduleAt.get(id);
    if (held && insideScope(held.node.key, targetKey))
      throw new Error("A module cannot be added inside itself");
    if (!candidate.byKey.has(targetKey))
      throw new Error("Structure target is unavailable");
    // The module leaves the programme list as it is placed, so the destination placement renders
    // its entry instead of the reservation suppressing it.
    const afterForest = forestFor(
      {
        ...current,
        programmeGroupIds: withoutProgrammeGroupId(
          current.programmeGroupIds,
          id,
        ),
      },
      ctx,
    );
    const sourceNode = before.moduleAt.get(id)?.node ?? null;
    const placed = placeModuleWithCourses(
      afterForest,
      edits,
      ctx,
      id,
      targetKey,
      sourceNode,
      pull,
      reset,
    );
    // The reset lists read the moved module at its own new place, so the preview and the write
    // see one state. A clean official module needs no reset, a structural edit needs the restoring
    // reset, and completions need the destructive one.
    const movedIndex = indexResolved(
      resolveStructure(afterForest, placed.edits, ctx),
    );
    const destination = movedIndex.byKey.get(placed.destinationKey);
    if (!destination) throw new Error("Structure target is unavailable");
    const destinationNode: StructureNode = destination.node;
    const resetPulls =
      sourceNode === null
        ? null
        : officialPulls(afterForest, placed.edits, ctx, destinationNode);
    const resetOptions =
      sourceNode === null
        ? undefined
        : moveResetOptions(
            afterForest,
            placed.edits,
            ctx,
            movedIndex,
            destinationNode.key,
            completedCourseIds,
          );
    const source = moduleSource(beforeTree, id);
    // The forest wrapper is the programme level, so a top-level entry moves with its list place.
    const moduleFrom =
      source &&
      source.node.key !== targetKey &&
      (source.node.kind === "programme" ||
        source.node.kind === "module" ||
        source.node.kind === "group")
        ? source
        : null;
    const moveIds: [string, string | null][] = placed.moves.map((move) => [
      move.course.group_id,
      before.courseAt.get(move.course.group_id)?.node.key ?? null,
    ]);
    const moduleIds: [string, string | null][] = placed.moduleMoves.map(
      (move) => [
        move.module.group_id,
        before.moduleAt.get(move.module.group_id)?.node.key ?? null,
      ],
    );
    return {
      edits: placed.edits,
      moves: placed.moves,
      moduleMoves: placed.moduleMoves,
      programmeIds: placed.programmeIds,
      moduleFrom,
      resetMoves: resetPulls?.courses ?? [],
      resetModuleMoves: resetPulls?.modules ?? [],
      resetProgrammeIds: resetPulls?.programmeIds ?? [],
      resetOptions,
      sourceKey: sourceNode?.key ?? null,
      destinationKey: placed.destinationKey,
      moveKey: JSON.stringify([
        moduleFrom?.node.key ?? null,
        before.moduleAt.get(id)?.node.key ?? null,
        moveIds.sort((left, right) => (left[0] < right[0] ? -1 : 1)),
        moduleIds.sort((left, right) => (left[0] < right[0] ? -1 : 1)),
      ]),
    };
  };
  /**
   * Read the stored envelope and refuse a profile, programme list or selection that moved on.
   *
   * A profile that differs returns null. A different programme list raises the programmes message
   * and a different selection key raises the version-selection message.
   */
  const refreshModuleOperation = (
    profileId: string,
    programmes: readonly string[],
    baseSelectionKey: string,
  ): StructureState | null => {
    const latest = store.refreshFromStorage();
    if (latest.currentProfileId !== profileId) return null;
    const state = latest.profiles[profileId].state.structure;
    if (!sameIdList(state.programmeGroupIds, programmes))
      throw new Error("Structure programmes changed while adding a module");
    if (moduleVersionKey(state.moduleVersions) !== baseSelectionKey)
      throw new Error(
        "Structure version selection changed while adding a module",
      );
    return state;
  };
  /**
   * Confirm and apply one module operation on the latest structure.
   *
   * The saved envelope is read before the question and again after it, so a profile switch or a
   * different programme list fails the operation instead of writing to another profile or another
   * forest. The write recomputes the placement inside the store callback, and a move identity that
   * differs from the authorized one fails with `Structure moves changed while confirming a module`.
   */
  const finishModulePlacement = async (
    module: ModuleSummary,
    targetKey: string,
    item: StructureRuleItem | null,
    ctx: PlacedContent,
    controller: AbortController,
    profileId: string,
    programmes: readonly string[],
    operationDatasetIdentity: string,
    moduleVersions: Readonly<Record<string, string>>,
    baseSelectionKey: string,
  ): Promise<void> => {
    const state = refreshModuleOperation(
      profileId,
      programmes,
      baseSelectionKey,
    );
    if (!state) return;
    const stored = state.moduleVersions[module.group_id];
    if (stored !== undefined && stored !== module.sisu_module_id)
      throw new Error(VERSION_CONFLICT);
    if (item === null) {
      const target = projectionFor(state, ctx).byKey.get(targetKey);
      if (
        target &&
        displayContents(target).children.some(
          (child) => child.node.module?.group_id === module.group_id,
        )
      ) {
        notify((messageLanguage) =>
          uiText(
            messageLanguage,
            nodeWordingKind(target.node) === "programme"
              ? "Already in this programme"
              : "Already in this module",
          ),
        );
        return;
      }
    }
    const preview = modulePlacement(state, ctx, module, targetKey, item);
    const source = preview.moduleFrom;
    let pulls = true;
    let reset: "keep" | "all" | undefined;
    if (source || preview.moves.length > 0 || preview.moduleMoves.length > 0) {
      const answer = await confirmMoves({
        holder: module,
        moves: preview.moves,
        moduleMoves: preview.moduleMoves,
        moduleFrom: source ? modulePlaceText(source) : undefined,
        resetOptions: preview.resetOptions,
      });
      if (answer === false) return;
      pulls = answer !== "keep";
      if (answer === "reset" || answer === "reset-all")
        reset = answer === "reset" ? "keep" : "all";
    }
    // A reset returns the module's own official courses from the nodes that render them.
    if (
      reset !== undefined &&
      (preview.resetMoves.length > 0 || preview.resetModuleMoves.length > 0)
    ) {
      const answer = await confirmMoves({
        holder: module,
        moves: preview.resetMoves,
        moduleMoves: preview.resetModuleMoves,
      });
      if (answer === false) return;
      pulls = answer !== "keep";
    }
    if (controller.signal.aborted) return;
    if (!refreshModuleOperation(profileId, programmes, baseSelectionKey))
      return;
    const latestContent = extend({
      datasetIdentity: operationDatasetIdentity,
      reports: ctx.reports,
      moduleVersions,
    });
    let applied: readonly PulledCourse[] = [];
    let resetKeys: { heldKey: string; restoredKey: string } | null = null;
    commit(
      (current) => {
        if (!sameIdList(current.programmeGroupIds, programmes))
          throw new Error("Structure programmes changed while adding a module");
        const placement = modulePlacement(
          current,
          latestContent,
          module,
          targetKey,
          item,
          pulls,
          reset,
        );
        if (placement.moveKey !== preview.moveKey)
          throw new Error("Structure moves changed while confirming a module");
        if (reset !== undefined && placement.sourceKey !== null)
          resetKeys = {
            heldKey: placement.sourceKey,
            restoredKey: placement.destinationKey,
          };
        applied = placement.moves;
        return placement.edits;
      },
      latestContent,
      [],
      (current) => {
        const pulled = new Set(pulls ? preview.programmeIds : []);
        if (reset !== undefined)
          for (const id of preview.resetProgrammeIds) pulled.add(id);
        return current.programmeGroupIds.filter(
          (id) => id !== module.group_id && !pulled.has(id),
        );
      },
      moduleVersions,
      reset === "all"
        ? (state, change) =>
            resetKeys === null
              ? change
              : resetCompletionChange(
                  state,
                  resetKeys.heldKey,
                  latestContent,
                  change,
                  resetKeys.restoredKey,
                )
        : undefined,
    );
    notify((messageLanguage) => {
      // A kept course stays where it is, so only a pulled one is reported as moved.
      const moved =
        pulls && applied.length
          ? ` · ${uiText(
              messageLanguage,
              applied.length === 1
                ? "{count} course moved here"
                : "{count} courses moved here",
              { count: applied.length },
            )}`
          : "";
      return `${uiText(messageLanguage, "Added {name}", {
        name: moduleName(module, messageLanguage),
      })}${moved}`;
    });
  };
  /**
   * Run one module operation through the shared abort, pending, error and cleanup lifecycle.
   *
   * The profile identity and the ordered programme list are captured before any read, so the
   * operation compares its confirmation against the state it started from. `prepare` returns the
   * placed content the operation reads into, and its failures reach the editor error state.
   */
  const runModuleOperation = (
    source: ModuleOperationSource,
    targetKey: string,
    item: StructureRuleItem | null,
  ): Promise<void> => {
    moduleOperation.current?.abort();
    const controller = new AbortController();
    moduleOperation.current = controller;
    const snapshot = store.getSnapshot();
    const profileId = snapshot.currentProfileId;
    const programmes =
      snapshot.profiles[profileId].state.structure.programmeGroupIds;
    const operationDatasetIdentity = cache.getDatasetIdentity();
    const baseSelectionKey = contentSelectionKey;
    setPendingModuleId(source.module.group_id);
    setError(null);
    return (async () => {
      try {
        let module: ModuleSummary;
        let ctx: PlacedContent;
        let moduleVersions: Readonly<Record<string, string>>;
        if (source.kind === "read") {
          const prepared = await source.prepare(
            controller.signal,
            operationDatasetIdentity,
          );
          if (controller.signal.aborted) return;
          module = prepared.module;
          ctx = prepared.content;
          moduleVersions = prepared.moduleVersions;
        } else {
          if (contentDatasetIdentity !== cache.getDatasetIdentity())
            throw new Error(DATASET_CHANGED_MESSAGE);
          const state = refreshModuleOperation(
            profileId,
            programmes,
            baseSelectionKey,
          );
          if (!state) return;
          const stored = state.moduleVersions[source.module.group_id];
          if (stored !== undefined && stored !== source.module.sisu_module_id)
            throw new Error(VERSION_CONFLICT);
          module = source.module;
          ctx = content;
          moduleVersions = {
            ...state.moduleVersions,
            [source.module.group_id]: source.module.sisu_module_id,
          };
        }
        await finishModulePlacement(
          module,
          targetKey,
          item,
          ctx,
          controller,
          profileId,
          programmes,
          operationDatasetIdentity,
          moduleVersions,
          baseSelectionKey,
        );
      } catch (caught) {
        if (
          controller.signal.aborted ||
          store.getSnapshot().currentProfileId !== profileId
        )
          return;
        setError(caught instanceof Error ? caught : new Error(String(caught)));
      } finally {
        if (
          moduleOperation.current === controller &&
          !controller.signal.aborted
        ) {
          moduleOperation.current = null;
          setPendingModuleId(null);
        }
      }
    })();
  };
  /**
   * Add one searched module to a node, reading every report its prospective request needs.
   *
   * The prospective module-version map holds the stored map plus the picked exact id. A different
   * stored identity refuses the operation. The read covers every programme, placed module and
   * candidate, so each root uses the selected nested version.
   */
  const addModule = (module: CatalogueModule, node: StructureNode): void => {
    if (locked) return;
    // A module the target node's own rule names, in an option included, is selected at that
    // official place. Every other module is placed into the target node: one the tree renders
    // elsewhere moves there with its whole structure, and one it does not render adopts its
    // official contents.
    const official = findRuleModule(node, module.group_id);
    if (official?.entry.kind === "node" && official.entry.node.module) {
      void selectRuleModule(official.entry.node.module, official);
      return;
    }
    void runModuleOperation(
      {
        kind: "read",
        module,
        prepare: async (signal, operationDatasetIdentity) => {
          const snapshot = store.refreshFromStorage();
          const state = snapshot.profiles[snapshot.currentProfileId].state;
          const stored = state.structure.moduleVersions[module.group_id];
          if (stored !== undefined && stored !== module.sisu_module_id)
            throw new Error(VERSION_CONFLICT);
          const moduleVersions = {
            ...state.structure.moduleVersions,
            [module.group_id]: module.sisu_module_id,
          };
          const prospective = await readProspectiveStructure({
            cache,
            content,
            contentDatasetIdentity,
            contentSelectionKey,
            extend,
            state: state.structure,
            groupId: module.group_id,
            moduleVersions,
            operationDatasetIdentity,
            signal,
          });
          return {
            module: prospective.report.root.module,
            content: prospective.content,
            moduleVersions,
          };
        },
      },
      node.key,
      null,
    );
  };
  const deselectRuleCourse = (
    course: CourseSummary,
    removeCompletion: boolean,
  ) =>
    runAction(() => {
      if (locked) return;
      if (freeIds.includes(course.group_id)) {
        if (completedCourseIds.includes(course.group_id) && !removeCompletion)
          return;
        commit(asEdits, content, [course.group_id]);
        return;
      }
      commit(
        (current) => ({
          ...asEdits(current),
          coursePlacements: placeCourse(
            current,
            officialHomes(forestFor(current, content), current, content),
            course.group_id,
            null,
          ).coursePlacements,
        }),
        content,
        removeCompletion ? [course.group_id] : [],
      );
    });
  const placeRuleCourse = (course: CourseSummary, item: StructureRuleItem) => {
    commit((current) => {
      let choices = current.choices;
      for (const step of item.origin.choicePath)
        if (!(choices[step.node.key] ?? []).includes(step.optionKey))
          choices = nextChoices(choices, step.node, step.optionKey);
      // An option can nest a choice, so the owner of a row inside one exists only after the
      // path's options are chosen. The target is checked against that selected state.
      const selected = { ...current, choices };
      requireNode(selected, content, item.origin.ownerKey);
      const forest = forestFor(selected, content);
      const next = { ...asEdits(selected), choices };
      return placeCourse(
        next,
        officialHomes(forest, selected, content),
        course.group_id,
        officialPlacementTarget(
          forest,
          next,
          content,
          "coursePlacements",
          course.group_id,
          item.origin.ownerKey,
        ),
      );
    }, content);
  };
  const selectRuleCourse = (course: CourseSummary, item: StructureRuleItem) =>
    runAction(() => {
      if (locked) return;
      placeRuleCourse(course, item);
    });
  // `item` is given only when the course must first be selected into this rule.
  const toggleRuleCourseCompleted = (
    course: CourseSummary,
    item: StructureRuleItem | null,
  ) =>
    runAction(() => {
      if (locked) return;
      if (item) placeRuleCourse(course, item);
      toggleCompleted(store, course.group_id);
    });
  /**
   * Select one official module option, confirming the module move and every course it pulls first.
   */
  const selectRuleModule = (
    module: ModuleSummary,
    item: StructureRuleItem,
  ): Promise<void> => {
    if (locked) return Promise.resolve();
    return runModuleOperation(
      { kind: "loaded", module },
      item.origin.ownerKey,
      item,
    );
  };
  /**
   * Remove one module from the structure.
   *
   * A completed course it held moves to Unplaced studies and keeps its completion. The identities
   * in `removedCourseIds` are the destructive choice: they leave both course sets and the tree
   * together with the module.
   */
  const deselectRuleModule = (
    module: ModuleSummary,
    removedCourseIds: readonly string[] = [],
  ) =>
    runAction(() => {
      if (locked) return;
      commit(
        (current) => {
          const forest = forestFor(current, content);
          const next = placeModule(
            current,
            officialHomes(forest, current, content),
            module.group_id,
            null,
          );
          // The courses this module held follow the ordinary removal outcome, so no stale place
          // keeps them out of a node a later addition gives them.
          const held = indexResolved(
            resolveStructure(forest, current, content),
          ).moduleAt.get(module.group_id);
          const courses = held?.subtree.map((course) => course.group_id) ?? [];
          const dropped = new Set(removedCourseIds);
          return {
            choices: next.choices,
            modulePlacements: next.modulePlacements,
            coursePlacements: {
              ...next.coursePlacements,
              ...removalPlacements(courses, completedCourseIds),
              ...Object.fromEntries(
                courses.filter((id) => dropped.has(id)).map((id) => [id, null]),
              ),
            },
          };
        },
        content,
        removedCourseIds,
      );
    });
  // Name of the other node a course is placed in, or null when the move needs no confirmation.
  // Unplaced studies holds unplaced items by definition, so leaving it is not a move between
  // official owners.
  const courseHome = (
    courseId: string,
    targetKey: string,
    language: DisplayLanguage,
  ): string | null => {
    const at = indexResolved(resolved).courseAt.get(courseId);
    if (!at || at.node.key === targetKey || at.node.kind === "unplaced")
      return null;
    const holder = courseSource(resolved, courseId);
    if (!holder) throw new Error("Structure target is unavailable");
    return resolvedNodeLabel(holder, language);
  };
  /**
   * Whether one node's current contents differ from the contents its own place draws for it.
   *
   * The open profile's structure is read from the store and its forest derived, so a choice, an
   * addition, a move out of an official home or a deselection inside that scope is compared
   * against the scope's own official defaults in its own place, which is the rendering the holder
   * shows when an addition first places it. A record that leaves the rendered contents unchanged
   * is not a difference. A displayed card order that differs from the unranked order the same
   * scope draws without saved ranks is a difference as well, while a rank list that changes no
   * displayed sequence is not. It reads and derives only.
   */
  const hasNodeEdits = (node: StructureNode): boolean => {
    const current = storedStructure();
    const forest = forestFor(current, content);
    return hasScopedEdits(
      forest,
      asEdits(current),
      content,
      node.key,
      current.courseOrder,
    );
  };
  /**
   * The courses one reset returns to its scope from the nodes that render them.
   *
   * The reset returns every course whose official home is inside that scope and which another node
   * renders, so an interface can ask about them before the write and keep them where they are.
   */
  const resetPulls = (node: StructureNode) => {
    const current = storedStructure();
    const pulls = officialPulls(
      forestFor(current, content),
      asEdits(current),
      content,
      node,
    );
    return { moves: pulls.courses, moduleMoves: pulls.modules };
  };
  /**
   * Reset one node to its official contents.
   *
   * The scoped edits and the completion clearing both derive from the same latest profile state
   * read inside the write callback, so an edit another tab saved while a confirmation waited is
   * seen. `removeCompletedCourses` is the destructive `Reset all` choice, which clears exactly the
   * completions the affected subtree held before the reset and reaches the completion owner in
   * every state, including a scope that holds no edit. `pull` is whether the reset returns the
   * courses `resetPulls` lists. A kept course holds its place. Unplaced studies clears
   * the places it owns and offers no such choice. The write forgets the version entries of the
   * groups the reset removes, while the reset holder and every other rendered group keep theirs.
   */
  const resetNode = (
    node: StructureNode,
    removeCompletedCourses = false,
    pull = true,
  ) =>
    runAction(() => {
      if (locked) return;
      if (node.kind === "unplaced") {
        resetUnplaced(store, content);
        notify((messageLanguage) =>
          uiText(messageLanguage, "Unplaced studies reset"),
        );
        return;
      }
      applyStructure(store, (state) => {
        const current = state.structure;
        const forest = forestFor(current, content);
        requireNode(current, content, node.key);
        const before = resolveStructure(forest, current, content);
        const beforeIndex = indexResolved(before);
        const { edits: scoped } = restoreScopeContents(
          forest,
          current,
          content,
          node,
          pull,
        );
        const affected = beforeIndex.byKey.get(node.key);
        if (!affected) throw new Error("Structure target is unavailable");
        // A course this node showed does not fall back into another node it leaves alone.
        const kept = clearedScopePlacements(
          affected,
          forest,
          scoped,
          content,
          (key) => key === UNPLACED_KEY || insideScope(node.key, key),
          state.completedCourseIds,
        );
        const edits: StructureEdits = {
          ...scoped,
          coursePlacements: { ...scoped.coursePlacements, ...kept },
        };
        const projection = resolveStructure(forest, edits, content);
        // The reset scope's cards, and the cards the reset restores into it, lose their ranks.
        const orderCleared = new Set(
          affected.subtree.map((course) => course.group_id),
        );
        for (const [id, at] of indexResolved(projection).courseAt)
          if (insideScope(node.key, at.node.key)) orderCleared.add(id);
        const ordinary: StructureChange = {
          next: {
            programmeGroupIds: [...current.programmeGroupIds],
            ...edits,
            moduleVersions: forgetRemovedModuleVersions(
              current.moduleVersions,
              before,
              projection,
            ),
            placedCourseIds: projection.subtree.map(
              (course) => course.group_id,
            ),
            courseHolders: courseHolders(projection),
            courseOrder: clearCourseOrder(current.courseOrder, orderCleared),
          },
        };
        return removeCompletedCourses
          ? resetCompletionChange(state, node.key, content, ordinary)
          : ordinary;
      });
      notify((messageLanguage) =>
        uiText(
          messageLanguage,
          nodeWordingKind(node) === "programme"
            ? "Programme reset to its official contents"
            : "Module reset to its official contents",
        ),
      );
    });
  /**
   * Move or reorder one displayed course with one atomic structure write.
   *
   * `targetKey` is a displayed programme, module or Unplaced studies holder. A null
   * `beforeCourseId` appends to that holder's direct course grid. The destination's displayed
   * sequence becomes the saved rank of its cards, and a rank of no other holder is derived. The
   * write returns true after it lands and false for an invalid, unchanged or failed operation.
   */
  const dropCourse = (
    courseId: string,
    targetKey: string,
    beforeCourseId: string | null,
  ): boolean => {
    let applied = false;
    let wrote = false;
    runAction(() => {
      if (locked) return;
      applyStructure(store, (state) => {
        const current = state.structure;
        const forest = forestFor(current, content);
        const projection = resolveStructure(forest, current, content);
        const index = indexResolved(projection);
        const selected = new Set(state.selectedCourseIds);
        const target = index.byKey.get(targetKey);
        if (
          !target ||
          !["programme", "module", "unplaced"].includes(target.node.kind) ||
          target.node.transparent
        )
          return null;
        const placed = index.courseAt.get(courseId);
        // The displayed holder is the grid the user sees, not the inner choice or transparent
        // rule that owns the course, so a reorder inside one grid never becomes a placement.
        const source =
          courseSource(projection, courseId) ??
          (selected.has(courseId) ? index.byKey.get(UNPLACED_KEY) : undefined);
        if (!source) return null;
        if (placed === undefined && !content.courses.has(courseId)) return null;
        // The loose list is every selected course the tree does not place anywhere.
        const loose = state.selectedCourseIds.flatMap((id) => {
          if (projection.subtree.some((course) => course.group_id === id))
            return [];
          const course = content.courses.get(id);
          return course ? [course] : [];
        });
        const ordered = (holder: ResolvedNode) =>
          holderCourses(
            holder,
            displayContents(holder).courses,
            loose,
            current.courseOrder,
          );
        const currentIds = ordered(target).map((item) => item.course.group_id);
        const destination = currentIds.filter((id) => id !== courseId);
        if (beforeCourseId !== null) {
          const at = destination.indexOf(beforeCourseId);
          if (at < 0) return null;
          destination.splice(at, 0, courseId);
        } else destination.push(courseId);
        const sameHolder = source.node.key === targetKey;
        if (
          sameHolder &&
          destination.join("\u0000") === currentIds.join("\u0000")
        )
          return null;
        const edits = sameHolder
          ? asEdits(current)
          : {
              ...asEdits(current),
              coursePlacements: placeCourse(
                current,
                officialHomes(forest, current, content),
                courseId,
                officialPlacementTarget(
                  forest,
                  current,
                  content,
                  "coursePlacements",
                  courseId,
                  targetKey,
                ),
              ).coursePlacements,
            };
        const finalProjection = resolveStructure(forest, edits, content);
        if (
          !sameHolder &&
          !indexResolved(finalProjection).courseAt.has(courseId) &&
          !(
            edits.coursePlacements[courseId] === UNPLACED_KEY &&
            selected.has(courseId)
          )
        )
          return null;
        const destinationSet = new Set(destination);
        const anchor = current.courseOrder.findIndex((id) =>
          destinationSet.has(id),
        );
        const remaining = current.courseOrder.filter(
          (id) => !destinationSet.has(id),
        );
        const insertAt =
          anchor < 0
            ? remaining.length
            : current.courseOrder
                .slice(0, anchor)
                .filter((id) => !destinationSet.has(id)).length;
        const courseOrder = [
          ...remaining.slice(0, insertAt),
          ...destination,
          ...remaining.slice(insertAt),
        ];
        wrote = true;
        return {
          next: {
            programmeGroupIds: [...current.programmeGroupIds],
            ...edits,
            moduleVersions: { ...current.moduleVersions },
            placedCourseIds: finalProjection.subtree.map(
              (course) => course.group_id,
            ),
            courseHolders: courseHolders(finalProjection),
            courseOrder,
          },
        };
      });
      applied = wrote;
    });
    return applied;
  };
  return {
    choose,
    addCourse,
    addModule,
    selectRuleCourse,
    toggleRuleCourseCompleted,
    deselectRuleCourse,
    selectRuleModule,
    deselectRuleModule,
    courseHome,
    hasNodeEdits,
    resetPulls,
    resetNode,
    dropCourse,
    pendingModuleId,
    error: error ?? actionError,
  };
}
