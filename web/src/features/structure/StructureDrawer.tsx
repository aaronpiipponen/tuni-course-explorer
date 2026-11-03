/** Persistent animated drawer for choices, search, contents, removal and reset. */
import {
  useContext,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import { AnimatePresence, motion } from "framer-motion";
import { PaneSlideContext } from "../../app/paneSlide";
import type {
  CatalogueModule,
  CourseSummary,
  ModuleSummary,
} from "../../api/types";
import type { DisplayLanguage } from "../../state/types";
import { useProfileSelector } from "../../state/useProfileSelector";
import {
  moduleName,
  nodeKindLabel,
  nodeWordingKind,
  sumCredits,
  formatCredits,
} from "./presentation";
import {
  indexResolved,
  type ResolvedNode,
  type StructureNode,
  type StructureRuleItem,
} from "./model";
import { displayContents, orderCourses } from "./display";
import { DrawerSearch } from "./DrawerSearch";
import { DrawerOptionRow } from "./DrawerOptionRow";
import { CompletedCourseDeselectDialog } from "./CompletedCourseDeselectDialog";
import { ModuleRemoveDialog } from "./ModuleRemoveDialog";
import { ConfirmDialog } from "../../shared/ConfirmDialog";
import {
  CourseMoveConfirmDialog,
  useCourseMoveConfirm,
} from "./CourseMoveConfirmDialog";
import type { PulledCourse, PulledModule } from "./edits";
import { scopeHoldsCompletion } from "./edits";
import { useReducedMotion } from "../../shared/useReducedMotion";
import { useWording } from "../../shared/useWording";
import { useMediaQuery } from "../../shared/useMediaQuery";
import { PHONE_SHELL_QUERY } from "../../shared/viewport";

type DrawerTarget = { resolved: ResolvedNode; programmeId: string | null };

type Editor = {
  choose(node: StructureNode, optionKey: string): void;
  addCourse(course: CourseSummary, node: StructureNode): void;
  addModule(module: CatalogueModule, node: StructureNode): void;
  selectRuleCourse(course: CourseSummary, item: StructureRuleItem): void;
  toggleRuleCourseCompleted(
    course: CourseSummary,
    item: StructureRuleItem | null,
  ): void;
  deselectRuleCourse(course: CourseSummary, removeCompletion: boolean): void;
  selectRuleModule(
    module: import("../../api/types").ModuleSummary,
    item: StructureRuleItem,
  ): Promise<void>;
  deselectRuleModule(
    module: import("../../api/types").ModuleSummary,
    removedCourseIds?: readonly string[],
  ): void;
  courseHome(
    courseId: string,
    targetKey: string,
    language: DisplayLanguage,
  ): string | null;
  /** Whether one node's current contents differ from the contents its own place draws for it. */
  hasNodeEdits(node: StructureNode): boolean;
  /** The courses one reset returns to its scope from the nodes that render them. */
  resetPulls(node: StructureNode): {
    moves: readonly PulledCourse[];
    moduleMoves: readonly PulledModule[];
  };
  resetNode(
    node: StructureNode,
    removeCompletedCourses?: boolean,
    pull?: boolean,
  ): void;
  pendingModuleId: string | null;
};

/** Render the structure drawer for choices, search, contents, removal and reset. */
export function StructureDrawer({
  target,
  index,
  editor,
  onClose,
  onResetProgramme,
}: {
  target: DrawerTarget | null;
  index: ReturnType<typeof indexResolved>;
  editor: Editor;
  onClose(): void;
  onResetProgramme(groupId: string): void;
}) {
  // The displayed closing target is state, so the closed drawer rerenders when it clears.
  const [lastTarget, setLastTarget] = useState<DrawerTarget | null>(null);
  const reducedMotion = useReducedMotion();
  const paneSliding = useContext(PaneSlideContext);
  const still = reducedMotion || paneSliding;
  // The pending move formatters run from a stored callback. Read the current editor at
  // evaluation time so a language switch or reprojection is not answered from the click-time one.
  const editorRef = useRef(editor);
  editorRef.current = editor;
  const [searchOpen, setSearchOpen] = useState(false);
  const [pendingCompletedCourse, setPendingCompletedCourse] = useState<{
    course: CourseSummary;
    /** Whether the course sits under Unplaced studies, where keeping it loose changes nothing. */
    unplaced: boolean;
  } | null>(null);
  const completedDeselectOpener = useRef<HTMLElement | null>(null);
  const [pendingModuleRemove, setPendingModuleRemove] = useState<{
    module: ModuleSummary;
    /** Whether the module holds changes to its official content. */
    hasEdits: boolean;
  } | null>(null);
  const moduleRemoveOpener = useRef<HTMLElement | null>(null);
  const [pendingModuleReset, setPendingModuleReset] = useState<{
    node: StructureNode;
    /** The courses and modules that reset returns to the scope from other nodes. */
    pulls: {
      moves: readonly PulledCourse[];
      moduleMoves: readonly PulledModule[];
    };
  } | null>(null);
  const moduleResetOpener = useRef<HTMLElement | null>(null);
  // The pull question of a reset, whose answer is the mode the reset writes.
  const resetPull = useCourseMoveConfirm();
  const [pendingMove, setPendingMove] = useState<{
    name: (language: DisplayLanguage) => string;
    place: (language: DisplayLanguage) => string | null;
    run(): void;
  } | null>(null);
  const moveOpener = useRef<HTMLElement | null>(null);
  useEffect(() => {
    if (target) setLastTarget(target);
  }, [target]);
  useLayoutEffect(() => {
    // A suppressed transform transition never fires transitionend, so retained content clears
    // from the preference itself, including a preference change during the close.
    if (reducedMotion && !target) setLastTarget(null);
  }, [reducedMotion, target]);
  const displayed = target ?? (reducedMotion ? null : lastTarget);
  useEffect(() => {
    if (!target) {
      setPendingCompletedCourse(null);
      setPendingModuleRemove(null);
      setPendingModuleReset(null);
      setPendingMove(null);
      resetPull.answer(false);
    }
  }, [target]);
  const { language, t } = useWording();
  const phoneSheet = useMediaQuery(PHONE_SHELL_QUERY);
  const sheetRef = useRef<HTMLElement>(null);
  const completedCourseIds = useProfileSelector(
    (state) => state.completedCourseIds,
  ).value;
  const completed = new Set(completedCourseIds);
  const courseOrder = useProfileSelector(
    (state) => state.structure.courseOrder,
  ).value;
  const resolved =
    displayed && "resolved" in displayed ? displayed.resolved : null;
  const programmeId =
    displayed && "resolved" in displayed ? displayed.programmeId : null;
  const node = resolved?.node;
  const transition = {
    duration: reducedMotion ? 0 : 0.45,
    ease: [0.22, 0.8, 0.2, 1] as const,
  };
  useEffect(() => {
    // A different drawer starts with its own search closed.
    setSearchOpen(false);
  }, [node?.key]);
  useEffect(() => {
    if (!target) return;
    const keys = (event: KeyboardEvent) => {
      if (event.key !== "Escape" || searchOpen) return;
      if (document.querySelector('[role="dialog"], .root-picker.open')) return;
      event.stopPropagation();
      onClose();
    };
    document.addEventListener("keydown", keys, true);
    return () => document.removeEventListener("keydown", keys, true);
  }, [target, searchOpen, onClose]);
  useEffect(() => {
    if (!target || !phoneSheet) return;
    // The phone drawer is a sheet over the shell, so an outside press dismisses it, while the
    // desktop side panel leaves the tree beside it interactive.
    const outside = (event: PointerEvent) => {
      if (
        !(event.target instanceof Node) ||
        sheetRef.current?.contains(event.target) ||
        document.querySelector(
          '[role="dialog"], [role="menu"], .root-picker.open, .root-picker-scrim.open',
        )
      )
        return;
      onClose();
    };
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, [target, phoneSheet, onClose]);
  const title =
    node?.kind === "choice" || node?.kind === "unplaced"
      ? node.title
      : node?.module
        ? moduleName(node.module, language)
        : "";
  const displayedContents = resolved ? displayContents(resolved) : null;
  const courses = displayedContents
    ? orderCourses(
        displayedContents.courses.filter(
          (item) => item.added || node?.kind === "unplaced",
        ),
        courseOrder,
      ).map(({ course }) => course)
    : [];
  const summaryCourses = resolved?.subtree ?? [];
  const children =
    displayedContents?.children.filter((child) => child.added) ?? [];
  const notes = displayedContents?.notes ?? [];
  const flattenOptionEntries = (
    entries: import("./model").StructureEntry[],
  ): import("./model").StructureEntry[] =>
    entries.flatMap((entry) =>
      entry.kind === "node" && entry.node.transparent
        ? flattenOptionEntries(entry.node.entries)
        : entry.kind === "node" && entry.node.kind === "choice"
          ? []
          : [entry],
    );
  const originFor = (entry: import("./model").StructureEntry) => {
    if ((entry.kind !== "course" && entry.kind !== "node") || !entry.origin)
      throw new Error("Structure rule entry is missing its source origin");
    return entry.origin;
  };
  const isSelected = (entry: import("./model").StructureEntry) => {
    if (entry.kind !== "course" && entry.kind !== "node") return false;
    const origin = originFor(entry);
    const pathChosen = origin.choicePath.every((step) =>
      index.byKey
        .get(step.node.key)
        ?.chosen.some((option) => option.key === step.optionKey),
    );
    if (!pathChosen) return false;
    return entry.kind === "course"
      ? index.courseAt.get(entry.course.group_id)?.node.key === origin.ownerKey
      : !!entry.node.module &&
          index.moduleAt.get(entry.node.module.group_id)?.node.key ===
            entry.node.key;
  };
  // Runs `move` immediately, or after confirmation when the item is placed in another node.
  const confirmMove = (
    name: (language: DisplayLanguage) => string,
    place: (language: DisplayLanguage) => string | null,
    move: () => void,
  ) => {
    if (place(language) === null) {
      move();
      return;
    }
    moveOpener.current =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    setPendingMove({ name, place, run: move });
  };
  /** The identities of the courses one module renders, for its removal outcome. */
  const moduleCourseIds = (module: ModuleSummary) =>
    (index.moduleAt.get(module.group_id)?.subtree ?? []).map(
      (course) => course.group_id,
    );
  const completedInside = (module: ModuleSummary) =>
    moduleCourseIds(module).filter((id) => completed.has(id));
  /**
   * Remove one module. A module whose current contents differ from the contents its own place
   * draws for it with its own official defaults, or that holds completed courses, asks first, so
   * the choice that also removes completions is one click. A module whose placement gives it its
   * own official contents, a pulled course included, and that holds no completed course goes at
   * once.
   */
  const removeModule = (module: ModuleSummary) => {
    // Both callers resolve the module from the displayed structure, so its node is present.
    const held = index.moduleAt.get(module.group_id)!;
    const hasEdits = editor.hasNodeEdits(held.node);
    if (!hasEdits && completedInside(module).length === 0) {
      editor.deselectRuleModule(module);
      return;
    }
    moduleRemoveOpener.current =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    setPendingModuleRemove({ module, hasEdits });
  };
  /**
   * Reset the node whose drawer footer was activated.
   *
   * A top-level programme resets through the row menu's reset question and Unplaced studies
   * resets the places it holds. Another programme or module asks through the shared reset question
   * when its scope holds a completion or its pull list is empty. A scope with no completion and a
   * non-empty pull list asks through the pull question of the courses the reset returns to it.
   */
  const requestReset = (target: StructureNode) => {
    if (programmeId !== null) {
      onResetProgramme(programmeId);
      return;
    }
    if (target.kind === "unplaced") {
      editor.resetNode(target);
      return;
    }
    const pulls = editorRef.current.resetPulls(target);
    moduleResetOpener.current =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    if (
      scopeHoldsCompletion(index, target.key, completedCourseIds) ||
      (pulls.moves.length === 0 && pulls.moduleMoves.length === 0)
    ) {
      setPendingModuleReset({ node: target, pulls });
      return;
    }
    askResetPull(target, false, pulls);
  };
  /** Ask about the courses one reset returns, then reset with the answered mode. */
  const askResetPull = (
    target: StructureNode,
    removeCompletedCourses: boolean,
    pulls: {
      moves: readonly PulledCourse[];
      moduleMoves: readonly PulledModule[];
    },
  ) => {
    // The drawer target is a displayed programme or module, so it carries its own module identity.
    const holder = target.module!;
    void resetPull
      .confirm({ holder, moves: pulls.moves, moduleMoves: pulls.moduleMoves })
      .then((answer) =>
        answer === false
          ? undefined
          : editorRef.current.resetNode(
              target,
              removeCompletedCourses,
              answer !== "keep",
            ),
      );
  };
  /** Answer the reset question, and continue to the pull question when the reset has one. */
  const answerReset = (removeCompletedCourses: boolean) => {
    const pending = pendingModuleReset;
    setPendingModuleReset(null);
    if (!pending) return;
    if (
      pending.pulls.moves.length === 0 &&
      pending.pulls.moduleMoves.length === 0
    ) {
      editorRef.current.resetNode(pending.node, removeCompletedCourses);
      return;
    }
    askResetPull(pending.node, removeCompletedCourses, pending.pulls);
  };
  const deselectCourse = (course: CourseSummary, unplaced = false) => {
    if (completed.has(course.group_id)) {
      completedDeselectOpener.current =
        document.activeElement instanceof HTMLElement
          ? document.activeElement
          : null;
      setPendingCompletedCourse({ course, unplaced });
    } else editor.deselectRuleCourse(course, false);
  };
  const contentSections = [
    ...(node?.kind === "choice"
      ? []
      : (node?.ruleGroups.map((group) => {
          const rows = group.options.flatMap((option) =>
            flattenOptionEntries(option.entries).map((entry) => ({
              option,
              entry,
            })),
          );
          const selectedRows = rows.filter(({ entry }) => isSelected(entry));
          return (
            <section
              className="tier eyebrow rule-group-section"
              key={group.key}
            >
              <div className="rule-group-heading">
                <span>{group.rule}</span>
                <CreditSummary
                  courses={selectedRowCourses(selectedRows, index)}
                  completed={completed}
                />
              </div>
              <div className="plist vis">
                {rows.map(({ option, entry }) => {
                  if (entry.kind === "note")
                    return (
                      <div className="dnote" key={`${option.key}:${entry.key}`}>
                        {entry.text}
                      </div>
                    );
                  const rowKey = `${option.key}:${entry.kind === "course" ? entry.key : entry.node.key}`;
                  return (
                    <DrawerOptionRow
                      key={rowKey}
                      entry={entry}
                      selected={isSelected(entry)}
                      language={language}
                      completion={
                        entry.kind === "course"
                          ? {
                              completed: completed.has(entry.course.group_id),
                              onToggle: () => {
                                const item =
                                  completed.has(entry.course.group_id) ||
                                  isSelected(entry)
                                    ? null
                                    : { entry, origin: originFor(entry) };
                                const toggle = () =>
                                  editor.toggleRuleCourseCompleted(
                                    entry.course,
                                    item,
                                  );
                                if (item)
                                  confirmMove(
                                    () => entry.course.code,
                                    (displayLanguage) =>
                                      editorRef.current.courseHome(
                                        entry.course.group_id,
                                        item.origin.ownerKey,
                                        displayLanguage,
                                      ),
                                    toggle,
                                  );
                                else toggle();
                              },
                            }
                          : undefined
                      }
                      onChoose={() => {
                        const selected = isSelected(entry);
                        if (entry.kind === "course") {
                          if (selected) deselectCourse(entry.course);
                          else if (node) {
                            const origin = originFor(entry);
                            confirmMove(
                              () => entry.course.code,
                              (displayLanguage) =>
                                editorRef.current.courseHome(
                                  entry.course.group_id,
                                  origin.ownerKey,
                                  displayLanguage,
                                ),
                              () =>
                                editor.selectRuleCourse(entry.course, {
                                  entry,
                                  origin,
                                }),
                            );
                          }
                        } else if (entry.kind === "node" && entry.node.module) {
                          if (selected) removeModule(entry.node.module);
                          else if (node) {
                            const module = entry.node.module;
                            void editor.selectRuleModule(module, {
                              entry,
                              origin: originFor(entry),
                            });
                          }
                        }
                      }}
                    />
                  );
                })}
              </div>
            </section>
          );
        }) ?? [])),
    ...(node && node.kind !== "choice"
      ? [
          <motion.div
            className="drawer-section-motion"
            key="courses"
            layout={still ? false : "position"}
            initial={false}
            animate={{
              opacity: courses.length ? 1 : 0,
              height: courses.length ? "auto" : 0,
            }}
            transition={transition}
          >
            <section className="tier eyebrow">
              <div>
                <CreditSummary courses={courses} completed={completed} />
              </div>
              <div className="plist vis">
                <AnimatePresence initial={false}>
                  {courses.map((course) => (
                    <motion.div
                      className="drawer-course-motion"
                      key={course.group_id}
                      layout={still ? false : "position"}
                      initial={
                        reducedMotion ? false : { opacity: 0, height: 0 }
                      }
                      animate={{ opacity: 1, height: "auto" }}
                      exit={{ opacity: 0, height: 0 }}
                      transition={transition}
                    >
                      <DrawerOptionRow
                        entry={{
                          kind: "course",
                          key: course.group_id,
                          course,
                        }}
                        selected
                        language={language}
                        completion={{
                          completed: completed.has(course.group_id),
                          onToggle: () =>
                            editor.toggleRuleCourseCompleted(course, null),
                        }}
                        onChoose={() =>
                          deselectCourse(course, node?.kind === "unplaced")
                        }
                      />
                    </motion.div>
                  ))}
                </AnimatePresence>
              </div>
            </section>
          </motion.div>,
        ]
      : []),
    ...(node && node.kind !== "choice"
      ? [
          <motion.div
            className="drawer-section-motion"
            key="modules"
            layout={still ? false : "position"}
            initial={false}
            animate={{
              opacity: children.length ? 1 : 0,
              height: children.length ? "auto" : 0,
            }}
            transition={transition}
          >
            <section className="tier eyebrow">
              <div>
                <CreditSummary
                  courses={children.flatMap((child) => child.subtree)}
                  completed={completed}
                />
              </div>
              <div className="plist vis">
                <AnimatePresence initial={false}>
                  {children.map((child) => (
                    <motion.div
                      className="drawer-course-motion"
                      key={child.node.key}
                      layout={still ? false : "position"}
                      initial={
                        reducedMotion ? false : { opacity: 0, height: 0 }
                      }
                      animate={{ opacity: 1, height: "auto" }}
                      exit={{ opacity: 0, height: 0 }}
                      transition={transition}
                    >
                      <DrawerOptionRow
                        entry={{ kind: "node", node: child.node }}
                        selected
                        language={language}
                        onChoose={() =>
                          child.node.module && removeModule(child.node.module)
                        }
                      />
                    </motion.div>
                  ))}
                </AnimatePresence>
              </div>
            </section>
          </motion.div>,
        ]
      : []),
  ];
  const noContents =
    !courses.length &&
    !children.length &&
    !notes.length &&
    !(node?.ruleGroups.length ?? 0);
  return (
    <>
      <aside
        className={`sdrawer${target ? " open" : ""}`}
        aria-hidden={!target}
        inert={!target}
        ref={sheetRef}
        onTransitionEnd={(event) => {
          if (
            !target &&
            event.target === event.currentTarget &&
            event.propertyName === "transform"
          )
            setLastTarget(null);
        }}
      >
        <AnimatePresence mode="wait">
          {displayed && (
            <motion.div
              key={displayed.resolved.node.key}
              className="sdrawer-content"
              initial={{ opacity: 0, y: reducedMotion ? 0 : 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{
                duration: reducedMotion ? 0 : 0.26,
                ease: transition.ease,
              }}
            >
              <header className="dh">
                <div>
                  <span className="dt">{title}</span>
                  <span className="dc">
                    {node
                      ? `${node.module?.code ?? ""}${node.module?.code ? " · " : ""}${nodeKindLabel(node, language)}`
                      : ""}
                  </span>
                </div>
                <button
                  className="pill-btn"
                  type="button"
                  aria-label={t("Close drawer")}
                  onClick={onClose}
                >
                  {t("Close")}
                </button>
              </header>
              <div className="db thin-scrollbar">
                <div className="dsum">
                  <span>
                    <b>{node?.rule}</b>
                  </span>
                  <CreditSummary
                    courses={summaryCourses}
                    completed={completed}
                  />
                </div>
                {node &&
                  ["programme", "module", "unplaced"].includes(node.kind) && (
                    <DrawerSearch
                      node={node}
                      open={searchOpen}
                      onOpenChange={setSearchOpen}
                      onAddCourse={(course, to) =>
                        confirmMove(
                          () => course.code,
                          (displayLanguage) =>
                            editorRef.current.courseHome(
                              course.group_id,
                              to.key,
                              displayLanguage,
                            ),
                          () => editor.addCourse(course, to),
                        )
                      }
                      onAddModule={(module, to) =>
                        void editor.addModule(module, to)
                      }
                      pendingId={editor.pendingModuleId}
                    />
                  )}
                <div className={`dlist${searchOpen ? " dim" : ""}`}>
                  {contentSections}
                  {notes.map((note, index) => (
                    <div className="dnote" key={`${note}-${index}`}>
                      {note}
                    </div>
                  ))}
                  {noContents && (
                    <div className="dnote">
                      {node?.kind === "choice" && !resolved?.chosen.length
                        ? t("No option selected yet.")
                        : t(
                            node && nodeWordingKind(node) === "programme"
                              ? "This programme is empty."
                              : "This module is empty.",
                          )}
                    </div>
                  )}
                  {node && (
                    <div className="dfoot">
                      <button
                        className="pill-btn"
                        type="button"
                        onClick={() => requestReset(node)}
                      >
                        {t(
                          nodeWordingKind(node) === "programme"
                            ? "Reset programme"
                            : "Reset this module",
                        )}
                      </button>
                    </div>
                  )}
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </aside>
      <ConfirmDialog
        open={pendingMove !== null}
        title={t("Move here?")}
        description={t("{name} is already in {place}. Move it here?", {
          name: pendingMove ? pendingMove.name(language) : "",
          place: pendingMove ? (pendingMove.place(language) ?? "") : "",
        })}
        confirmLabel={t("Move")}
        onCancel={() => setPendingMove(null)}
        onConfirm={() => {
          pendingMove?.run();
          setPendingMove(null);
        }}
        returnFocus={() => moveOpener.current?.focus({ preventScroll: true })}
      />
      <ModuleRemoveDialog
        open={pendingModuleRemove !== null}
        operation="remove"
        holderKind={
          pendingModuleRemove
            ? nodeWordingKind({
                kind: "module",
                module: pendingModuleRemove.module,
              })
            : "module"
        }
        name={
          pendingModuleRemove
            ? moduleName(pendingModuleRemove.module, language)
            : ""
        }
        hasEdits={pendingModuleRemove?.hasEdits ?? false}
        hasCompletedCourses={
          pendingModuleRemove !== null &&
          completedInside(pendingModuleRemove.module).length > 0
        }
        onCancel={() => setPendingModuleRemove(null)}
        onKeep={() => {
          if (pendingModuleRemove)
            editor.deselectRuleModule(pendingModuleRemove.module);
          setPendingModuleRemove(null);
        }}
        onRemove={() => {
          if (pendingModuleRemove)
            editor.deselectRuleModule(
              pendingModuleRemove.module,
              completedInside(pendingModuleRemove.module),
            );
          setPendingModuleRemove(null);
        }}
        returnFocus={() =>
          moduleRemoveOpener.current?.focus({ preventScroll: true })
        }
      />
      <ModuleRemoveDialog
        open={pendingModuleReset !== null}
        operation="reset"
        holderKind={
          pendingModuleReset
            ? nodeWordingKind(pendingModuleReset.node)
            : "module"
        }
        hasEdits={false}
        name={
          pendingModuleReset?.node.module
            ? moduleName(pendingModuleReset.node.module, language)
            : ""
        }
        hasCompletedCourses={
          pendingModuleReset !== null &&
          scopeHoldsCompletion(
            index,
            pendingModuleReset.node.key,
            completedCourseIds,
          )
        }
        onCancel={() => setPendingModuleReset(null)}
        onKeep={() => answerReset(false)}
        onRemove={() => answerReset(true)}
        returnFocus={() =>
          moduleResetOpener.current?.focus({ preventScroll: true })
        }
      />
      <CourseMoveConfirmDialog
        request={resetPull.request}
        onAnswer={resetPull.answer}
        returnFocus={() =>
          moduleResetOpener.current?.focus({ preventScroll: true })
        }
      />
      <CompletedCourseDeselectDialog
        open={pendingCompletedCourse !== null}
        courseCode={pendingCompletedCourse?.course.code ?? ""}
        unplaced={pendingCompletedCourse?.unplaced ?? false}
        onCancel={() => setPendingCompletedCourse(null)}
        onKeepLoose={() => {
          if (pendingCompletedCourse)
            editor.deselectRuleCourse(pendingCompletedCourse.course, false);
          setPendingCompletedCourse(null);
        }}
        onRemove={() => {
          if (pendingCompletedCourse)
            editor.deselectRuleCourse(pendingCompletedCourse.course, true);
          setPendingCompletedCourse(null);
        }}
        returnFocus={() =>
          completedDeselectOpener.current?.focus({ preventScroll: true })
        }
      />
    </>
  );
}

function selectedRowCourses(
  selectedRows: readonly {
    option: import("./model").StructureOption;
    entry: import("./model").StructureEntry;
  }[],
  index: ReturnType<typeof indexResolved>,
): CourseSummary[] {
  const courses = new Map<string, CourseSummary>();
  for (const { entry } of selectedRows) {
    if (entry.kind === "course")
      courses.set(entry.course.group_id, entry.course);
    else if (entry.kind === "node")
      for (const course of index.byKey.get(entry.node.key)?.subtree ?? [])
        courses.set(course.group_id, course);
  }
  return [...courses.values()];
}

function CreditSummary({
  courses,
  completed,
}: {
  courses: readonly CourseSummary[];
  completed: ReadonlySet<string>;
}) {
  const { t } = useWording();
  return (
    <span className="credit-summary">
      <b>{formatCredits(sumCredits(courses))}</b> {t("selected")} |{" "}
      <b>
        {formatCredits(
          sumCredits(courses, (course) => completed.has(course.group_id)),
        )}
      </b>{" "}
      {t("completed")} {t("cr")}
    </span>
  );
}
