/** Atomic browser structure projection, scoped programme operations and Unplaced studies reset. */
import type { BrowserStore } from "../../state/store";
import type {
  CourseId,
  DisplayLanguage,
  ProfileState,
} from "../../state/types";
import type { StudyStructureReport } from "../../api/types";
import type { StructureEdits, StructureState } from "./state";
import { UNPLACED_KEY } from "./state";
import type { SisuPlan } from "./sisu";
import {
  buildProgrammeForest,
  courseHolders,
  indexResolved,
  officialHomes,
  programmeKey,
  resolveStructure,
  type PlacedContent,
  type StructureNode,
} from "./model";
import {
  clearedScopePlacements,
  holderPulls,
  insideScope,
  moveScope,
  replacedScopeHomes,
  officialPulls,
  moveResetOptions,
  resetMoved,
  resetScope,
  restoreScopeContents,
  type PulledCourse,
  type PulledModule,
} from "./edits";
import { moduleSource } from "./display";
import { resolvedNodeLabel } from "./presentation";
import { forgetRemovedModuleVersions } from "./moduleVersions";

/** One complete next structure and its accompanying selection and completion removals. */
export type StructureChange = {
  next: StructureState;
  /** Course identities removed from both selection and completion. */
  removedCourseIds?: readonly CourseId[];
  /** Course identities removed from selection unless they are completed. */
  discardUncompletedCourseIds?: readonly CourseId[];
  /** A supplied value replaces the pending Sisu hierarchy. An omitted field leaves it in place. */
  pendingSisuImport?: SisuPlan | null;
};

/** One programme list operation: add, replace, reset or delete the programme with `groupId`. */
export type ProgrammeOperation =
  | { kind: "add"; groupId: string; versionId: string }
  | {
      kind: "replace";
      groupId: string;
      replacementGroupId: string;
      versionId: string;
    }
  | { kind: "reset" | "delete"; groupId: string };

/** The refusal message of a module version that differs from the stored one. */
export const VERSION_CONFLICT =
  "Another version of this module is already selected";

/** One operation's next programme list, edits, card order, pulled courses and discards. */
type ProgrammeOutcome = {
  programmeGroupIds: string[];
  edits: StructureEdits;
  courseOrder: string[];
  moves: readonly PulledCourse[];
  moduleMoves: readonly PulledModule[];
  /** The courses a reset of the moved holder returns from the nodes that render them. */
  resetMoves: readonly PulledCourse[];
  /** The highest-level official modules a reset of the moved holder returns. */
  resetModuleMoves: readonly PulledModule[];
  /** The pulled module identities the ordered programme list renders. */
  resetProgrammeIds: readonly string[];
  /** The moved holder's scope before and after the operation, for a destructive reset. */
  resetHeldKey: string | null;
  resetRestoredKey: string | null;
  /** The reset actions the move offers beside Move, from the moved module's own state. */
  moveOptions: "reset" | "reset-all" | "both" | undefined;
  discards: readonly CourseId[];
};

/** Return the saved order without the listed identities, keeping every other rank as it is. */
export function clearCourseOrder(
  order: readonly string[],
  ids: Iterable<string>,
): string[] {
  const cleared = new Set(ids);
  return order.filter((id) => !cleared.has(id));
}

/** Return whether two id lists hold the same ids in the same order. */
export function sameIdList(
  left: readonly string[],
  right: readonly string[],
): boolean {
  return (
    left.length === right.length &&
    left.every((id, index) => id === right[index])
  );
}

/**
 * Build the ordered forest from the reports the supplied content holds.
 *
 * A report the content lacks returns `null`, so a caller can wait for hydration or refuse the
 * operation instead of projecting an incomplete structure.
 */
export function programmeForest(
  ids: readonly string[],
  content: PlacedContent,
  language: DisplayLanguage = "en",
): StructureNode | null {
  const reports: StudyStructureReport[] = [];
  for (const id of ids) {
    const report = content.reports[id];
    if (!report) return null;
    reports.push(report);
  }
  return buildProgrammeForest(reports, language);
}

/**
 * Return the localized node that displays one identity in the supplied state, when a visible node
 * does.
 *
 * A direct Unplaced studies holder is not a place a move names, because that node holds unplaced
 * items by definition.
 */
export function displayedPlace(
  state: StructureState,
  content: PlacedContent,
  groupId: string,
): ((language: DisplayLanguage) => string) | undefined {
  const forest = programmeForest(state.programmeGroupIds, content);
  if (!forest) return undefined;
  const source = moduleSource(
    resolveStructure(forest, state, content),
    groupId,
  );
  return source &&
    (source.node.kind === "programme" || source.node.kind === "module")
    ? (language) => resolvedNodeLabel(source, language)
    : undefined;
}

/** The node the supplied state renders one module identity at, or null when it renders none. */
function holderNode(
  forest: StructureNode,
  state: StructureState,
  content: PlacedContent,
  moduleId: string,
): StructureNode | null {
  return (
    indexResolved(resolveStructure(forest, state, content)).moduleAt.get(
      moduleId,
    )?.node ?? null
  );
}

/**
 * Return edits without the placement one promoted identity holds.
 *
 * A promoted programme renders from the ordered list, so its module placement map has no entry for
 * that identity.
 */
function withoutPlacement(
  edits: StructureEdits,
  moduleId: string,
): StructureEdits {
  const modulePlacements = { ...edits.modulePlacements };
  delete modulePlacements[moduleId];
  return { ...edits, modulePlacements };
}

/**
 * Return one programme operation's next list and edits, or throw a visible failure.
 *
 * `moves` names the courses the operation pulls into a holder it adds, each with the node it sits
 * in, so an interface can confirm the moves before it writes. `pull` is whether the operation
 * moves those courses: a kept course stays in the node that renders it.
 */
function programmeOutcome(
  state: StructureState,
  operation: ProgrammeOperation,
  content: PlacedContent,
  completedCourseIds: readonly string[],
  pull: boolean,
  reset?: "keep" | "all",
): ProgrammeOutcome {
  const edits: StructureEdits = {
    choices: state.choices,
    coursePlacements: state.coursePlacements,
    modulePlacements: state.modulePlacements,
  };
  if (operation.kind === "add") {
    if (state.programmeGroupIds.includes(operation.groupId))
      throw new Error("Programme is already added");
    const before = programmeForest(state.programmeGroupIds, content);
    const source = before
      ? holderNode(before, state, content, operation.groupId)
      : null;
    const programmeGroupIds = [...state.programmeGroupIds, operation.groupId];
    // The ordered list renders this identity, so it keeps no placement record of its own. A
    // record, a removal record included, would suppress the added top-level entry. A programme the
    // tree already displays moves to the list with its whole current subtree and the place it
    // leaves keeps no record, while one the tree does not display renders only after this addition
    // and so takes its scope's official defaults rather than any record that scope carries.
    const edited = withoutPlacement(edits, operation.groupId);
    const after = programmeForest(programmeGroupIds, content);
    if (!after) throw new Error("Programme is unavailable");
    const holder = indexResolved(
      resolveStructure(after, edited, content),
    ).byKey.get(programmeKey(operation.groupId));
    if (!holder) throw new Error("Programme is unavailable");
    const moved =
      source === null
        ? edited
        : moveScope(edited, content, source, holder.node);
    const pulls = holderPulls(
      after,
      moved,
      holder.node,
      content,
      source !== null,
      pull,
    );
    // The reset lists read the moved holder at its new place, so the preview and the write see
    // one state.
    const movedIndex = indexResolved(
      resolveStructure(after, pulls.edits, content),
    );
    const moveOptions =
      source === null
        ? undefined
        : moveResetOptions(
            after,
            pulls.edits,
            content,
            movedIndex,
            holder.node.key,
            completedCourseIds,
          );
    const resetPulls =
      source === null
        ? null
        : officialPulls(after, pulls.edits, content, holder.node);
    const resetEdits =
      reset !== undefined && source !== null
        ? resetMoved(after, pulls.edits, content, holder.node, reset, pull)
        : null;
    const dropped = new Set([
      ...pulls.programmeIds,
      ...(resetEdits?.programmeIds ?? []),
    ]);
    return {
      programmeGroupIds: programmeGroupIds.filter((id) => !dropped.has(id)),
      edits: resetEdits?.edits ?? pulls.edits,
      courseOrder: [...state.courseOrder],
      moves: pulls.moves,
      moduleMoves: pulls.moduleMoves,
      resetMoves: resetPulls?.courses ?? [],
      resetModuleMoves: resetPulls?.modules ?? [],
      resetProgrammeIds: resetPulls?.programmeIds ?? [],
      resetHeldKey: source === null ? null : source.key,
      resetRestoredKey: source === null ? null : holder.node.key,
      moveOptions,
      discards: [],
    };
  }
  if (!state.programmeGroupIds.includes(operation.groupId))
    throw new Error("Programme is unavailable");
  const before = programmeForest(state.programmeGroupIds, content);
  if (!before) throw new Error("Programme is unavailable");
  const affected = indexResolved(
    resolveStructure(before, state, content),
  ).byKey.get(programmeKey(operation.groupId));
  if (!affected) throw new Error("Programme is unavailable");
  const clearedKey = programmeKey(operation.groupId);
  const homes = officialHomes(before, state, content);
  let programmeGroupIds: string[];
  let replacementKey: string | null = null;
  let replacementId: string | null = null;
  let source: StructureNode | null = null;
  if (operation.kind === "replace") {
    if (
      operation.replacementGroupId !== operation.groupId &&
      state.programmeGroupIds.includes(operation.replacementGroupId)
    )
      throw new Error("Programme is already added");
    programmeGroupIds = state.programmeGroupIds.map((id) =>
      id === operation.groupId ? operation.replacementGroupId : id,
    );
    replacementKey = programmeKey(operation.replacementGroupId);
    replacementId = operation.replacementGroupId;
    source = holderNode(before, state, content, operation.replacementGroupId);
  } else if (operation.kind === "reset") {
    programmeGroupIds = [...state.programmeGroupIds];
  } else {
    programmeGroupIds = state.programmeGroupIds.filter(
      (id) => id !== operation.groupId,
    );
  }
  let after = programmeForest(programmeGroupIds, content);
  if (!after) throw new Error("Programme is unavailable");
  // The replacement renders from the ordered list after this operation, so it keeps no placement
  // record of its own: a record, a removal record included, would suppress the top-level entry the
  // list renders at the replaced position.
  const edited =
    replacementId === null ? edits : withoutPlacement(edits, replacementId);
  const keepExternalPlacements =
    operation.kind === "delete" || operation.kind === "replace";
  let scoped = resetScope(edited, homes, clearedKey, keepExternalPlacements);
  let moves: readonly PulledCourse[] = [];
  let moduleMoves: readonly PulledModule[] = [];
  if (operation.kind === "reset") {
    const restored = restoreScopeContents(
      before,
      edited,
      content,
      affected.node,
      pull,
    );
    scoped = restored.edits;
    moves = restored.pulls.courses;
    moduleMoves = restored.pulls.modules;
    if (pull && restored.pulls.programmeIds.length > 0) {
      programmeGroupIds = programmeGroupIds.filter(
        (id) => !restored.pulls.programmeIds.includes(id),
      );
      const reduced = programmeForest(programmeGroupIds, content);
      if (!reduced) throw new Error("Programme is unavailable");
      after = reduced;
    }
  }
  if (replacementKey) {
    const holder = indexResolved(
      resolveStructure(after, edited, content),
    ).byKey.get(replacementKey);
    if (!holder) throw new Error("Programme is unavailable");
    if (source !== null) {
      // The replacement programme moves to the top-level key with its whole current subtree, so its
      // records travel before the replaced scope takes them away and the replaced programme's own
      // records clear around them. An identity the replaced programme names inside that subtree
      // keeps its removal and its places with it.
      scoped = resetScope(
        moveScope(edited, content, source, holder.node),
        replacedScopeHomes(homes, source.key),
        clearedKey,
        true,
      );
    }
    // A replacement programme the tree already displays keeps its own contents, and one it does not
    // display renders only after this operation, so its scope takes its official defaults.
    const pulls = holderPulls(
      after,
      scoped,
      holder.node,
      content,
      source !== null,
      pull,
    );
    scoped = pulls.edits;
    moves = pulls.moves;
    moduleMoves = pulls.moduleMoves;
    // A pulled module that the ordered list renders leaves that list, so its own official place
    // inside the replacement renders it with the contents this operation moves there.
    if (pulls.programmeIds.length > 0) {
      programmeGroupIds = programmeGroupIds.filter(
        (id) => !pulls.programmeIds.includes(id),
      );
      const reduced = programmeForest(programmeGroupIds, content);
      if (!reduced) throw new Error("Programme is unavailable");
      after = reduced;
    }
  }
  // A holder the action leaves alone does not take over a course the named programme held.
  const replacements = clearedScopePlacements(
    affected,
    after,
    scoped,
    content,
    (key) =>
      key === UNPLACED_KEY ||
      insideScope(clearedKey, key) ||
      (replacementKey !== null && insideScope(replacementKey, key)),
    completedCourseIds,
  );
  const finalEdits: StructureEdits = {
    ...scoped,
    coursePlacements: { ...scoped.coursePlacements, ...replacements },
  };
  // The named scope's cards lose their ranks. A replacement subtree that travels intact keeps the
  // relative order of its courses, and every other saved rank stays as it was.
  const projection = resolveStructure(after, finalEdits, content);
  const cleared = new Set(affected.subtree.map((course) => course.group_id));
  if (operation.kind === "reset")
    for (const [id, node] of indexResolved(projection).courseAt)
      if (insideScope(clearedKey, node.node.key)) cleared.add(id);
  if (operation.kind === "replace" && source !== null) {
    const kept = indexResolved(
      resolveStructure(before, state, content),
    ).byKey.get(source.key);
    for (const course of kept?.subtree ?? []) cleared.delete(course.group_id);
  }
  return {
    programmeGroupIds,
    edits: finalEdits,
    courseOrder: clearCourseOrder(state.courseOrder, cleared),
    moves,
    moduleMoves,
    resetMoves: [],
    resetModuleMoves: [],
    resetProgrammeIds: [],
    resetHeldKey: null,
    resetRestoredKey: null,
    moveOptions: undefined,
    discards: affected.subtree.map((course) => course.group_id),
  };
}

/**
 * Return the courses one programme operation would pull into a holder it adds or restores.
 *
 * It reads the same outcome the write applies, so an interface can confirm the moves first and a
 * cancelled confirmation writes nothing. A reset returns the courses whose official home is inside
 * the reset scope and which the nodes outside it render.
 */
export function programmeMoves(
  state: StructureState,
  operation: ProgrammeOperation,
  content: PlacedContent,
  completedCourseIds: readonly string[] = [],
): {
  moves: readonly PulledCourse[];
  moduleMoves: readonly PulledModule[];
  resetMoves: readonly PulledCourse[];
  resetModuleMoves: readonly PulledModule[];
  resetProgrammeIds: readonly string[];
  moveOptions: "reset" | "reset-all" | "both" | undefined;
} {
  if (operation.kind === "delete")
    return {
      moves: [],
      moduleMoves: [],
      resetMoves: [],
      resetModuleMoves: [],
      resetProgrammeIds: [],
      moveOptions: undefined,
    };
  const forest = programmeForest(state.programmeGroupIds, content);
  if (!forest) throw new Error("Programme is unavailable");
  if (operation.kind === "reset") {
    const affected = indexResolved(
      resolveStructure(forest, state, content),
    ).byKey.get(programmeKey(operation.groupId));
    if (!affected) throw new Error("Programme is unavailable");
    const pulls = officialPulls(forest, state, content, affected.node);
    return {
      moves: pulls.courses,
      moduleMoves: pulls.modules,
      resetMoves: [],
      resetModuleMoves: [],
      resetProgrammeIds: pulls.programmeIds,
      moveOptions: undefined,
    };
  }
  const outcome = programmeOutcome(
    state,
    operation,
    content,
    completedCourseIds,
    true,
  );
  return {
    moves: outcome.moves,
    moduleMoves: outcome.moduleMoves,
    resetMoves: outcome.resetMoves,
    resetModuleMoves: outcome.resetModuleMoves,
    resetProgrammeIds: outcome.resetProgrammeIds,
    moveOptions: outcome.moveOptions,
  };
}

/**
 * Apply one structure change to the latest stored envelope.
 *
 * The callback reads the current profile state and returns the complete next structure, or
 * `null` for a change that writes nothing. The ordered selection and completion migration runs
 * once on the returned structure, so a course the next structure does not place leaves the
 * selection unless it is completed or explicitly removed.
 */
export function applyStructure(
  store: BrowserStore,
  change: (state: ProfileState) => StructureChange | null,
): void {
  store.updateCurrent((state) => {
    const result = change(state);
    if (result === null) return state;
    const { next } = result;
    const previous = state.structure.placedCourseIds;
    const completed = new Set(state.completedCourseIds);
    const keep = new Set(next.placedCourseIds);
    const dropped = new Set(
      previous.filter((id) => !keep.has(id) && !completed.has(id)),
    );
    for (const id of result.discardUncompletedCourseIds ?? [])
      if (!completed.has(id)) dropped.add(id);
    const explicitlyRemoved = new Set(result.removedCourseIds ?? []);
    const selected = state.selectedCourseIds.filter(
      (id) => !dropped.has(id) && !explicitlyRemoved.has(id),
    );
    const seen = new Set(selected);
    for (const id of next.placedCourseIds)
      if (!seen.has(id)) {
        seen.add(id);
        selected.push(id);
      }
    // The order names selected courses only, so an identity that leaves every set with the
    // selection migration leaves the order in the same write.
    const chosen = new Set(selected);
    return {
      ...state,
      selectedCourseIds: selected,
      completedCourseIds: state.completedCourseIds.filter(
        (id) => !explicitlyRemoved.has(id),
      ),
      structure: {
        programmeGroupIds: [...next.programmeGroupIds],
        choices: next.choices,
        coursePlacements: next.coursePlacements,
        modulePlacements: next.modulePlacements,
        moduleVersions: { ...next.moduleVersions },
        placedCourseIds: [...next.placedCourseIds],
        courseHolders: next.courseHolders ?? state.structure.courseHolders,
        courseOrder: next.courseOrder.filter((id) => chosen.has(id)),
      },
      pendingSisuImport:
        result.pendingSisuImport === undefined
          ? state.pendingSisuImport
          : result.pendingSisuImport,
    };
  });
}

/**
 * Add the destructive reset outcome to one prepared ordinary reset.
 *
 * `Reset all` clears exactly the completions the affected resolved subtree held immediately
 * before the write. A completed course that the restored content places inside the scope keeps
 * its restored place and loses its completion, so a required official course comes back selected
 * and uncompleted. A completed course the reset discards keeps no restored place: the ordinary
 * reset would leave it loose in Unplaced studies, so its place is cleared too. A completed
 * identity the scope only mentions but another holder actually owns is never touched.
 * `restoredKey` names the scope the ordinary change renders, which a moved module reads as its
 * destination while the held identities still come from the scope it leaves.
 */
export function resetCompletionChange(
  state: ProfileState,
  scopeKey: string,
  content: PlacedContent,
  ordinary: StructureChange,
  restoredKey: string = scopeKey,
): StructureChange {
  const before = programmeForest(state.structure.programmeGroupIds, content);
  if (!before) throw new Error("Programme is unavailable");
  const affected = indexResolved(
    resolveStructure(before, state.structure, content),
  ).byKey.get(scopeKey);
  if (!affected) throw new Error("Structure target is unavailable");
  const held = new Set(affected.subtree.map((course) => course.group_id));
  const removedCompleted = state.completedCourseIds.filter((id) =>
    held.has(id),
  );
  const candidate = programmeForest(ordinary.next.programmeGroupIds, content);
  if (!candidate) throw new Error("Programme is unavailable");
  const edits: StructureEdits = {
    choices: ordinary.next.choices,
    coursePlacements: { ...ordinary.next.coursePlacements },
    modulePlacements: ordinary.next.modulePlacements,
  };
  // The restored placement is read from the ordinary reset, so a discarded completion cannot
  // fall back into an untouched holder.
  const restoredAt = indexResolved(
    resolveStructure(candidate, edits, content),
  ).courseAt;
  for (const id of removedCompleted) {
    const at = restoredAt.get(id);
    if (!at || !insideScope(restoredKey, at.node.key))
      edits.coursePlacements[id] = null;
  }
  const projection = resolveStructure(candidate, edits, content);
  return {
    ...ordinary,
    next: {
      programmeGroupIds: ordinary.next.programmeGroupIds,
      ...edits,
      moduleVersions: ordinary.next.moduleVersions,
      placedCourseIds: projection.subtree.map((course) => course.group_id),
      courseHolders: courseHolders(projection),
      courseOrder: ordinary.next.courseOrder,
    },
    removedCourseIds: removedCompleted,
  };
}

/**
 * Apply one programme operation to the latest stored structure.
 *
 * Add appends a programme. Replace, Reset and Delete act on the one named programme: that
 * programme's customisation is cleared, its rendered courses are discarded while uncompleted,
 * and every completion stays completed and selected at its next official place or, with no
 * official place left, loose under Unplaced studies. A missing programme or a report the
 * supplied content lacks raises `Programme is unavailable`.
 *
 * `removeCompletedCourses` is the destructive choice for the two entry points that offer one: a
 * delete drops the affected programme's completed courses from both course sets and the tree as
 * the completed-course removal does, and a reset clears the completions the affected programme
 * holds immediately before the write. Discrimination follows the operation kind, so an ordinary
 * reset and every delete without the flag write the ordinary change.
 *
 * `pull` is whether a reset returns the courses its scope's official content holds in another node.
 * A kept course stays there, and the addition and replacement paths read the flag the same way.
 *
 * `moduleVersions` is the prospective selection the operation's reports were read under. It
 * defaults to the stored map, a picked identity is added to it, and any entry that disagrees
 * with the stored map refuses the write instead of replacing a stored selection. The
 * write forgets the version entries of the groups the operation removes from the rendered tree, so
 * a removed programme or module can be added again with another explicit version.
 */
export function changeProgrammes(
  store: BrowserStore,
  operation: ProgrammeOperation,
  content: PlacedContent,
  removeCompletedCourses = false,
  pull = true,
  moduleVersions?: Readonly<Record<string, string>>,
  reset?: "keep" | "all",
): void {
  applyStructure(store, (state) => {
    const latestVersions = state.structure.moduleVersions;
    const baseVersions = moduleVersions ?? latestVersions;
    let selectedVersions = baseVersions;
    const beforeForest = programmeForest(
      state.structure.programmeGroupIds,
      content,
    );
    if (!beforeForest) throw new Error("Programme is unavailable");
    const before = resolveStructure(beforeForest, state.structure, content);
    if (operation.kind === "add" || operation.kind === "replace") {
      const groupId =
        operation.kind === "add"
          ? operation.groupId
          : operation.replacementGroupId;
      for (const [group, version] of Object.entries(baseVersions)) {
        const stored = latestVersions[group];
        if (stored !== undefined && stored !== version)
          throw new Error(VERSION_CONFLICT);
      }
      const stored = latestVersions[groupId];
      if (stored !== undefined && stored !== operation.versionId)
        throw new Error(VERSION_CONFLICT);
      selectedVersions = { ...baseVersions, [groupId]: operation.versionId };
    }
    const outcome = programmeOutcome(
      { ...state.structure, moduleVersions: selectedVersions },
      operation,
      content,
      state.completedCourseIds,
      pull,
      reset,
    );
    const after = programmeForest(outcome.programmeGroupIds, content);
    if (!after) throw new Error("Programme is unavailable");
    const removedCompleted =
      operation.kind === "delete" && removeCompletedCourses
        ? outcome.discards.filter((id) => state.completedCourseIds.includes(id))
        : [];
    const coursePlacements = { ...outcome.edits.coursePlacements };
    for (const id of removedCompleted) coursePlacements[id] = null;
    const edits: StructureEdits = {
      choices: outcome.edits.choices,
      coursePlacements,
      modulePlacements: outcome.edits.modulePlacements,
    };
    const projection = resolveStructure(after, edits, content);
    const ordinary: StructureChange = {
      next: {
        programmeGroupIds: outcome.programmeGroupIds,
        ...edits,
        moduleVersions: forgetRemovedModuleVersions(
          selectedVersions,
          before,
          projection,
        ),
        placedCourseIds: projection.subtree.map((course) => course.group_id),
        courseHolders: courseHolders(projection),
        courseOrder: outcome.courseOrder,
      },
      discardUncompletedCourseIds: outcome.discards,
      removedCourseIds: removedCompleted,
    };
    if (operation.kind === "reset" && removeCompletedCourses)
      return resetCompletionChange(
        state,
        programmeKey(operation.groupId),
        content,
        ordinary,
      );
    if (
      reset === "all" &&
      outcome.resetHeldKey !== null &&
      outcome.resetRestoredKey !== null
    )
      return resetCompletionChange(
        state,
        outcome.resetHeldKey,
        content,
        ordinary,
        outcome.resetRestoredKey,
      );
    return ordinary;
  });
}

/**
 * Clear every choice and placement the global Unplaced studies bucket owns.
 *
 * The write forgets the version entries of the groups the reset removes from the rendered tree and
 * keeps every other selection.
 */
export function resetUnplaced(
  store: BrowserStore,
  content: PlacedContent,
): void {
  applyStructure(store, (state) => {
    const edits = state.structure;
    const tree = programmeForest(edits.programmeGroupIds, content);
    if (!tree) throw new Error("Programme is unavailable");
    const resolved = resolveStructure(tree, edits, content);
    const bucket = indexResolved(resolved).byKey.get(UNPLACED_KEY);
    const discard = [
      ...(bucket?.subtree.map((course) => course.group_id) ?? []),
      ...state.selectedCourseIds.filter(
        (id) => !resolved.subtree.some((course) => course.group_id === id),
      ),
    ];
    const homes = officialHomes(tree, edits, content);
    const resetPlacements = (placements: Record<string, string | null>) => {
      const retained: Record<string, string | null> = {};
      for (const [id, target] of Object.entries(placements)) {
        if (target === null) {
          if (
            (homes.get(id) ?? []).some(
              (home) => !insideScope(UNPLACED_KEY, home),
            )
          )
            retained[id] = null;
          continue;
        }
        if (!insideScope(UNPLACED_KEY, target)) retained[id] = target;
        else if (
          (homes.get(id) ?? []).some((home) => !insideScope(UNPLACED_KEY, home))
        )
          retained[id] = null;
      }
      return retained;
    };
    const next: StructureEdits = {
      choices: Object.fromEntries(
        Object.entries(edits.choices).filter(
          ([key]) => !insideScope(UNPLACED_KEY, key),
        ),
      ),
      coursePlacements: resetPlacements(edits.coursePlacements),
      modulePlacements: resetPlacements(edits.modulePlacements),
    };
    const projection = resolveStructure(tree, next, content);
    return {
      next: {
        programmeGroupIds: [...edits.programmeGroupIds],
        ...next,
        moduleVersions: forgetRemovedModuleVersions(
          edits.moduleVersions,
          resolved,
          projection,
        ),
        placedCourseIds: projection.subtree.map((course) => course.group_id),
        courseHolders: courseHolders(projection),
        courseOrder: clearCourseOrder(edits.courseOrder, discard),
      },
      discardUncompletedCourseIds: discard,
    };
  });
}
