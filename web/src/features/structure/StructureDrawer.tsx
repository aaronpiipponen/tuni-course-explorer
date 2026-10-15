/** Persistent animated drawer for choices, search, contents, removal and reset. */
import { useEffect, useRef, useState } from "react";
import type { CourseSummary } from "../../api/types";
import type { DisplayLanguage } from "../../state/types";
import { useProfileSelector } from "../../state/useProfileSelector";
import {
  moduleName,
  nodeKindLabel,
  sumCredits,
  formatCredits,
} from "./presentation";
import {
  indexResolved,
  type ResolvedNode,
  type StructureNode,
  type StructureRuleItem,
} from "./model";
import { displayContents } from "./display";
import { DrawerSearch } from "./DrawerSearch";
import { DrawerOptionRow } from "./DrawerOptionRow";
import { CompletedCourseDeselectDialog } from "./CompletedCourseDeselectDialog";
import { MoveConfirmDialog } from "./MoveConfirmDialog";
import { CLOSE } from "../../shared/icons";
import { useWording } from "../../shared/useWording";

type Editor = {
  choose(node: StructureNode, optionKey: string): void;
  addCourse(course: CourseSummary, node: StructureNode): void;
  addModule(
    module: import("../../api/types").ModuleSummary,
    node: StructureNode,
  ): void;
  selectRuleCourse(course: CourseSummary, item: StructureRuleItem): void;
  toggleRuleCourseCompleted(
    course: CourseSummary,
    item: StructureRuleItem | null,
  ): void;
  deselectRuleCourse(course: CourseSummary, removeCompletion: boolean): void;
  selectRuleModule(
    module: import("../../api/types").ModuleSummary,
    item: StructureRuleItem,
  ): void;
  deselectRuleModule(module: import("../../api/types").ModuleSummary): void;
  courseHome(
    courseId: string,
    targetKey: string,
    language: DisplayLanguage,
  ): string | null;
  moduleHome(
    moduleId: string,
    targetKey: string,
    language: DisplayLanguage,
  ): string | null;
  resetNode(node: StructureNode): void;
  pendingModuleId: string | null;
};

export function StructureDrawer({
  target,
  index,
  editor,
  onClose,
}: {
  target: { resolved: ResolvedNode } | null;
  index: ReturnType<typeof indexResolved>;
  editor: Editor;
  onClose(): void;
}) {
  const lastTarget = useRef(target);
  // The pending move formatters run from a stored callback. Read the editor current at
  // evaluation time so a language switch or reprojection is not answered from the click-time one.
  const editorRef = useRef(editor);
  editorRef.current = editor;
  const [searchOpen, setSearchOpen] = useState(false);
  const [pendingCompletedCourse, setPendingCompletedCourse] =
    useState<CourseSummary | null>(null);
  const completedDeselectOpener = useRef<HTMLElement | null>(null);
  const [pendingMove, setPendingMove] = useState<{
    name: (language: DisplayLanguage) => string;
    place: (language: DisplayLanguage) => string | null;
    run(): void;
  } | null>(null);
  const moveOpener = useRef<HTMLElement | null>(null);
  useEffect(() => {
    if (target) lastTarget.current = target;
  }, [target]);
  const displayed = target ?? lastTarget.current;
  useEffect(() => {
    if (!target) {
      setPendingCompletedCourse(null);
      setPendingMove(null);
    }
  }, [target]);
  const { language, t } = useWording();
  const completed = new Set(
    useProfileSelector((state) => state.completedCourseIds).value,
  );
  const resolved =
    displayed && "resolved" in displayed ? displayed.resolved : null;
  const node = resolved?.node;
  useEffect(() => {
    if (!node || !["programme", "module", "unplaced"].includes(node.kind))
      setSearchOpen(false);
  }, [node?.key]);
  const title =
    node?.kind === "choice" || node?.kind === "unplaced"
      ? node.title
      : node?.module
        ? moduleName(node.module, language)
        : "";
  const displayedContents = resolved ? displayContents(resolved) : null;
  const courses =
    displayedContents?.courses
      .filter((item) => item.added || node?.kind === "unplaced")
      .map(({ course }) => course) ?? [];
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
  const deselectCourse = (course: CourseSummary) => {
    if (completed.has(course.group_id)) {
      completedDeselectOpener.current =
        document.activeElement instanceof HTMLElement
          ? document.activeElement
          : null;
      setPendingCompletedCourse(course);
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
                  courses={selectedRowCourses(selectedRows, resolved)}
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
                  const rowOption = {
                    key: `${option.key}:${entry.kind === "course" ? entry.key : entry.node.key}`,
                    entries: [entry],
                  };
                  return (
                    <DrawerOptionRow
                      key={rowOption.key}
                      option={rowOption}
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
                          if (selected)
                            editor.deselectRuleModule(entry.node.module);
                          else if (node) {
                            const module = entry.node.module;
                            const origin = originFor(entry);
                            confirmMove(
                              (displayLanguage) =>
                                moduleName(module, displayLanguage),
                              (displayLanguage) =>
                                editorRef.current.moduleHome(
                                  module.group_id,
                                  origin.ownerKey,
                                  displayLanguage,
                                ),
                              () =>
                                editor.selectRuleModule(module, {
                                  entry,
                                  origin,
                                }),
                            );
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
    ...(courses.length
      ? [
          <section className="tier eyebrow" key="courses">
            <div>
              <CreditSummary courses={courses} completed={completed} />
            </div>
            <div className="plist vis">
              {courses.map((course) => (
                <DrawerOptionRow
                  key={course.group_id}
                  option={{
                    key: course.group_id,
                    entries: [{ kind: "course", key: course.group_id, course }],
                  }}
                  selected
                  language={language}
                  completion={{
                    completed: completed.has(course.group_id),
                    onToggle: () =>
                      editor.toggleRuleCourseCompleted(course, null),
                  }}
                  onChoose={() => deselectCourse(course)}
                />
              ))}
            </div>
          </section>,
        ]
      : []),
    ...(children.length
      ? [
          <section className="tier eyebrow" key="modules">
            <div>
              <CreditSummary
                courses={children.flatMap((child) => child.subtree)}
                completed={completed}
              />
            </div>
            <div className="plist vis">
              {children.map((child) => (
                <DrawerOptionRow
                  key={child.node.key}
                  option={{
                    key: child.node.key,
                    entries: [{ kind: "node", node: child.node }],
                  }}
                  selected
                  language={language}
                  onChoose={() =>
                    child.node.module &&
                    editor.deselectRuleModule(child.node.module)
                  }
                />
              ))}
            </div>
          </section>,
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
        onTransitionEnd={(event) => {
          if (
            !target &&
            event.target === event.currentTarget &&
            event.propertyName === "transform"
          )
            lastTarget.current = null;
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
            className="dx"
            type="button"
            aria-label={t("Close drawer")}
            onClick={onClose}
          >
            {CLOSE}
          </button>
        </header>
        <div className="db">
          <div className="dsum">
            <span>
              <b>{node?.rule}</b>
            </span>
            <CreditSummary courses={summaryCourses} completed={completed} />
          </div>
          {node && ["programme", "module", "unplaced"].includes(node.kind) && (
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
                confirmMove(
                  (displayLanguage) => moduleName(module, displayLanguage),
                  (displayLanguage) =>
                    editorRef.current.moduleHome(
                      module.group_id,
                      to.key,
                      displayLanguage,
                    ),
                  () => editor.addModule(module, to),
                )
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
                  : t("This module is empty.")}
              </div>
            )}
            {node && (
              <div className="dfoot">
                <button
                  className="pill-btn"
                  type="button"
                  onClick={() => editor.resetNode(node)}
                >
                  {t(
                    node.kind === "programme"
                      ? "Reset this degree"
                      : "Reset this module",
                  )}
                </button>
              </div>
            )}
          </div>
        </div>
      </aside>
      <MoveConfirmDialog
        open={pendingMove !== null}
        name={pendingMove ? pendingMove.name(language) : ""}
        place={pendingMove ? (pendingMove.place(language) ?? "") : ""}
        onCancel={() => setPendingMove(null)}
        onMove={() => {
          pendingMove?.run();
          setPendingMove(null);
        }}
        returnFocus={() => moveOpener.current?.focus()}
      />
      <CompletedCourseDeselectDialog
        open={pendingCompletedCourse !== null}
        courseCode={pendingCompletedCourse?.code ?? ""}
        onCancel={() => setPendingCompletedCourse(null)}
        onKeepLoose={() => {
          if (pendingCompletedCourse)
            editor.deselectRuleCourse(pendingCompletedCourse, false);
          setPendingCompletedCourse(null);
        }}
        onRemove={() => {
          if (pendingCompletedCourse)
            editor.deselectRuleCourse(pendingCompletedCourse, true);
          setPendingCompletedCourse(null);
        }}
        returnFocus={() => completedDeselectOpener.current?.focus()}
      />
    </>
  );
}

function selectedRowCourses(
  selectedRows: readonly {
    option: import("./model").StructureOption;
    entry: import("./model").StructureEntry;
  }[],
  resolved: ResolvedNode | null,
): CourseSummary[] {
  const courses = new Map<string, CourseSummary>();
  const findNode = (
    node: ResolvedNode,
    key: string,
  ): ResolvedNode | undefined => {
    if (node.node.key === key) return node;
    for (const child of node.children) {
      const found = findNode(child, key);
      if (found) return found;
    }
    return undefined;
  };
  for (const { entry } of selectedRows) {
    if (entry.kind === "course")
      courses.set(entry.course.group_id, entry.course);
    else if (entry.kind === "node" && resolved) {
      findNode(resolved, entry.node.key)?.subtree.forEach((course) =>
        courses.set(course.group_id, course),
      );
    }
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
