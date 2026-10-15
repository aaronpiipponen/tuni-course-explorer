/** Browser-owned structure edits, selection migration and user notices. */
import { useEffect, useRef, useState } from "react";
import type { CourseSummary, ModuleSummary } from "../../api/types";
import { readStudyStructure } from "../../api/study-structure";
import { useProfileSelector } from "../../state/useProfileSelector";
import { useAction } from "../../shared/useAction";
import { applyStructure, resetUnplaced } from "./actions";
import { emptyEdits, UNPLACED_KEY, type StructureEdits } from "./state";
import {
  indexResolved,
  nextChoices,
  officialHomes,
  resolveStructure,
  NO_CONTENT,
  type PlacedContent,
  type ResolvedNode,
  type StructureNode,
  type StructureRuleItem,
} from "./model";
import {
  placeCourse,
  placeModule,
  placeModuleWithCourses,
  resetScope,
} from "./edits";
import { moduleName } from "./presentation";
import { toggleCompleted } from "../../state/course-actions";
import { displayContents } from "./display";
import type { DisplayLanguage } from "../../state/types";
import { uiText } from "../../shared/wording";

export function useStructureEditor({
  rootGroupId,
  tree,
  resolved,
  edits,
  freeIds,
  content,
  extend,
  notify,
}: {
  rootGroupId: string;
  tree: StructureNode;
  resolved: ResolvedNode;
  edits: StructureEdits;
  freeIds: readonly string[];
  content: PlacedContent;
  extend(extra: {
    courses?: readonly CourseSummary[];
    reports?: Readonly<
      Record<string, import("../../api/types").StudyStructureReport>
    >;
  }): PlacedContent;
  notify(text: (language: DisplayLanguage) => string): void;
}) {
  const { store } = useProfileSelector((state) => state.structure);
  const moduleOperation = useRef<AbortController | null>(null);
  const completedCourseIds = useProfileSelector(
    (state) => state.completedCourseIds,
  ).value;
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
  const commit = (
    next: StructureEdits,
    ctx: PlacedContent,
    removed: readonly string[] = [],
  ) => {
    const projection = resolveStructure(tree, next, ctx);
    applyStructure(
      store,
      {
        rootGroupId,
        ...next,
        placedCourseIds: projection.subtree.map((course) => course.group_id),
      },
      removed,
    );
  };
  const choose = (node: StructureNode, optionKey: string) =>
    runAction(() => {
      const next = nextChoices(edits.choices, node, optionKey);
      if (next === edits.choices) return;
      commit({ ...edits, choices: next }, content);
      notify((messageLanguage) =>
        uiText(
          messageLanguage,
          (edits.choices[node.key]?.length ?? 0)
            ? "Selection changed: completed courses kept, other courses dropped"
            : "Selection made",
        ),
      );
    });
  const addCourse = (course: CourseSummary, node: StructureNode) =>
    runAction(() => {
      const id = course.group_id;
      const index = indexResolved(resolved);
      const placed = index.courseAt.get(id);
      if (placed === index.byKey.get(node.key)) {
        notify((messageLanguage) =>
          uiText(messageLanguage, "Already in this module"),
        );
        return;
      }
      const ctx = extend({ courses: [course] });
      const homes = officialHomes(tree, edits, ctx);
      const next = {
        ...edits,
        coursePlacements: placeCourse(edits, homes, id, node.key)
          .coursePlacements,
      };
      commit(next, ctx);
    });
  const addModule = async (module: ModuleSummary, node: StructureNode) => {
    const id = module.group_id;
    const currentIndex = indexResolved(resolved);
    const current = currentIndex.moduleAt.get(id);
    if (
      current &&
      (node.key === current.node.key ||
        node.key.startsWith(`${current.node.key}/`))
    ) {
      setError(new Error("A module cannot be added inside itself"));
      return;
    }
    const target = currentIndex.byKey.get(node.key);
    if (
      target &&
      displayContents(target).children.some(
        (child) => child.node.module?.group_id === id,
      )
    ) {
      notify((messageLanguage) =>
        uiText(messageLanguage, "Already in this module"),
      );
      return;
    }
    moduleOperation.current?.abort();
    const controller = new AbortController();
    moduleOperation.current = controller;
    const profileId = store.getSnapshot().currentProfileId;
    setPendingModuleId(id);
    setError(null);
    try {
      const report = await readStudyStructure(id, controller.signal);
      if (
        controller.signal.aborted ||
        store.getSnapshot().currentProfileId !== profileId
      )
        return;
      const ctx = extend({ reports: { [id]: report } });
      const snapshot = store.getSnapshot();
      const state = snapshot.profiles[snapshot.currentProfileId].state;
      const currentEdits = state.structure;
      if (currentEdits.rootGroupId !== rootGroupId)
        throw new Error("Structure root changed while adding a module");
      const currentResolved = resolveStructure(tree, currentEdits, ctx);
      const currentIndex = indexResolved(currentResolved);
      const currentModule = currentIndex.moduleAt.get(id);
      if (
        currentModule &&
        (node.key === currentModule.node.key ||
          node.key.startsWith(`${currentModule.node.key}/`))
      )
        throw new Error("A module cannot be added inside itself");
      const actualTarget = currentIndex.byKey.get(node.key);
      if (
        actualTarget &&
        displayContents(actualTarget).children.some(
          (child) => child.node.module?.group_id === id,
        )
      ) {
        notify((messageLanguage) =>
          uiText(messageLanguage, "Already in this module"),
        );
        return;
      }
      const { edits: placed, movedCourseCount } = placeModuleWithCourses(
        tree,
        currentEdits,
        ctx,
        id,
        node.key,
        currentEdits.placedCourseIds,
      );
      const next = {
        ...placed,
      };
      notify((messageLanguage) => {
        const moved = movedCourseCount
          ? ` · ${uiText(
              messageLanguage,
              movedCourseCount === 1
                ? "{count} course moved here"
                : "{count} courses moved here",
              { count: movedCourseCount },
            )}`
          : "";
        return `${uiText(messageLanguage, "Added {name}", {
          name: moduleName(module, messageLanguage),
        })}${moved}`;
      });
      commit(next, ctx);
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
  };
  const deselectRuleCourse = (
    course: CourseSummary,
    removeCompletion: boolean,
  ) =>
    runAction(() => {
      if (freeIds.includes(course.group_id)) {
        if (completedCourseIds.includes(course.group_id) && !removeCompletion)
          return;
        commit(edits, content, [course.group_id]);
        return;
      }
      const homes = officialHomes(tree, edits, content);
      commit(
        {
          ...edits,
          coursePlacements: placeCourse(edits, homes, course.group_id, null)
            .coursePlacements,
        },
        content,
        removeCompletion ? [course.group_id] : [],
      );
    });
  const placeRuleCourse = (course: CourseSummary, item: StructureRuleItem) => {
    let choices = edits.choices;
    for (const step of item.origin.choicePath)
      if (!(choices[step.node.key] ?? []).includes(step.optionKey))
        choices = nextChoices(choices, step.node, step.optionKey);
    const homes = officialHomes(tree, edits, content);
    const nextEdits = placeCourse(
      { ...edits, choices },
      homes,
      course.group_id,
      item.origin.ownerKey,
    );
    commit(nextEdits, content);
  };
  const selectRuleCourse = (course: CourseSummary, item: StructureRuleItem) =>
    runAction(() => placeRuleCourse(course, item));
  // `item` is given only when the course must first be selected into this rule.
  const toggleRuleCourseCompleted = (
    course: CourseSummary,
    item: StructureRuleItem | null,
  ) =>
    runAction(() => {
      if (item) placeRuleCourse(course, item);
      toggleCompleted(store, course.group_id);
    });
  const selectRuleModule = (module: ModuleSummary, item: StructureRuleItem) =>
    runAction(() => {
      let choices = edits.choices;
      for (const step of item.origin.choicePath)
        if (!(choices[step.node.key] ?? []).includes(step.optionKey))
          choices = nextChoices(choices, step.node, step.optionKey);
      const { edits: next } = placeModuleWithCourses(
        tree,
        { ...edits, choices },
        content,
        module.group_id,
        item.origin.ownerKey,
        resolved.subtree.map((course) => course.group_id),
      );
      commit(next, content);
    });
  const deselectRuleModule = (module: ModuleSummary) =>
    runAction(() => {
      const homes = officialHomes(tree, edits, content);
      commit(
        {
          ...edits,
          modulePlacements: placeModule(edits, homes, module.group_id, null)
            .modulePlacements,
        },
        content,
      );
    });
  // Name of the other node a course/module is placed in, or null if it is not placed
  // elsewhere than `targetKey`.
  const courseHome = (
    courseId: string,
    targetKey: string,
    language: DisplayLanguage,
  ): string | null => {
    const at = indexResolved(resolved).courseAt.get(courseId);
    if (at) return at.node.key === targetKey ? null : nodeLabel(at, language);
    return freeIds.includes(courseId) && targetKey !== UNPLACED_KEY
      ? uiText(language, "Unplaced studies")
      : null;
  };
  const moduleHome = (
    moduleId: string,
    targetKey: string,
    language: DisplayLanguage,
  ): string | null => {
    const at = indexResolved(resolved).moduleAt.get(moduleId);
    return at && at.node.key !== targetKey ? nodeLabel(at, language) : null;
  };
  const resetNode = (node: StructureNode) =>
    runAction(() => {
      if (node.kind === "unplaced") {
        resetUnplaced(store, tree, content);
        notify((messageLanguage) =>
          uiText(messageLanguage, "Unplaced studies reset"),
        );
        return;
      }
      commit(
        resetScope(edits, officialHomes(tree, edits, content), node.key),
        content,
      );
      notify((messageLanguage) =>
        uiText(messageLanguage, "Module reset to its official contents"),
      );
    });
  const resetAll = () =>
    runAction(() => {
      const projection = resolveStructure(tree, emptyEdits(), NO_CONTENT);
      applyStructure(
        store,
        {
          rootGroupId,
          ...emptyEdits(),
          placedCourseIds: projection.subtree.map((course) => course.group_id),
        },
        [],
        freeIds,
      );
      notify((messageLanguage) =>
        uiText(messageLanguage, "Reset to the official structure"),
      );
    });
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
    moduleHome,
    resetNode,
    resetAll,
    pendingModuleId,
    error: error ?? actionError,
  };
}

function nodeLabel(node: ResolvedNode, language: DisplayLanguage): string {
  return node.node.module
    ? moduleName(node.node.module, language)
    : (node.node.title ?? uiText(language, "Choice"));
}
