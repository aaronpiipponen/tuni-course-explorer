/** Structure root selection and composition of tree, browser edits and drawer. */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, LayoutGroup, motion } from "framer-motion";
import type { StudyStructureReport } from "../../api/types";
import { useProfileSelector } from "../../state/useProfileSelector";
import { ErrorNotice } from "../../shared/ErrorNotice";
import { PickerOverlay } from "../../shared/PickerOverlay";
import { useWording } from "../../shared/useWording";
import { uiText } from "../../shared/wording";
import { ModuleLookupBox } from "./ModuleLookupBox";
import { useChooseRoot } from "./useChooseRoot";
import { useStructureReport } from "./useStructureReport";
import {
  buildStructure,
  resolveStructure,
  indexResolved,
  NO_CONTENT,
  withUnplaced,
  type PlacedContent,
} from "./model";
import { displayContents } from "./display";
import { StructureNodeRow } from "./StructureNodeRow";
import { StructureDrawer } from "./StructureDrawer";
import { usePlacedContent } from "./usePlacedContent";
import { useCourseSummaries } from "../../shared/course/useCourseSummaries";
import { useStructureEditor } from "./useStructureEditor";
import { useNotice } from "./useNotice";
import { emptyEdits, type StructureEdits } from "./state";
import { applyStructure } from "./actions";
import { ResetStructureDialog } from "./ResetStructureDialog";

export function StructurePane() {
  const { value: rootGroupId } = useProfileSelector(
    (state) => state.structure.rootGroupId,
  );
  const { report, loading, error } = useStructureReport(rootGroupId);
  const { language, t } = useWording();
  const chooser = useChooseRoot();
  const [pickerOpen, setPickerOpen] = useState(false);
  const notice = useNotice();
  const closePicker = useCallback(() => setPickerOpen(false), []);
  const choose = (module: Parameters<typeof chooser.choose>[0]) => {
    void chooser.choose(module).then((success) => {
      if (success) {
        closePicker();
        notice.show((language) =>
          uiText(
            language,
            "Root changed: customisation discarded, completed courses retained",
          ),
        );
      }
    });
  };
  return (
    <main
      className="pane-content structure-pane"
      role="tabpanel"
      aria-label={t("Structure of studies")}
    >
      {!rootGroupId ? (
        <div className="prereq-empty">
          <p>
            {t(
              "Pick a programme or module to build your structure of studies.",
            )}
          </p>
          <button
            className="pill-btn"
            type="button"
            onClick={() => setPickerOpen(true)}
          >
            {t("Choose root")}
          </button>
        </div>
      ) : loading && !report ? (
        <div className="structure-skeleton" aria-label={t("Loading structure")}>
          {Array.from({ length: 6 }, (_, index) => (
            <i key={index} />
          ))}
        </div>
      ) : error ? (
        <ErrorNotice error={error} language={language} />
      ) : report ? (
        <StructureView
          key={rootGroupId}
          report={report}
          rootGroupId={rootGroupId}
          onChangeRoot={() => setPickerOpen(true)}
        />
      ) : null}
      {chooser.error && (
        <ErrorNotice error={chooser.error} language={language} />
      )}
      {notice.toast}
      <div className="structure-root-overlay">
        <PickerOverlay
          open={pickerOpen}
          onClose={closePicker}
          eyebrow={`// ${t("choose root")}`}
        >
          <ModuleLookupBox
            open={pickerOpen}
            pendingId={chooser.pending}
            onPick={(module) =>
              module.group_id === rootGroupId ? closePicker() : choose(module)
            }
          />
        </PickerOverlay>
      </div>
    </main>
  );
}

function StructureView({
  report,
  rootGroupId,
  onChangeRoot,
}: {
  report: StudyStructureReport;
  rootGroupId: string;
  onChangeRoot(): void;
}) {
  const { language, t } = useWording();
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
  const { value: placedIds } = useProfileSelector(
    (state) => state.structure.placedCourseIds,
  );
  const { store } = useProfileSelector((state) => state.structure);
  const edits = useMemo(
    () => ({ choices, coursePlacements, modulePlacements }),
    [choices, coursePlacements, modulePlacements],
  );
  const root = useMemo(
    () => withUnplaced(buildStructure(report, "r", language), language),
    [report, language],
  );
  const courseIds = Object.entries(coursePlacements)
    .filter(([, target]) => typeof target === "string")
    .map(([id]) => id);
  const moduleIds = Object.entries(modulePlacements)
    .filter(([, target]) => typeof target === "string")
    .map(([id]) => id);
  const placed = usePlacedContent(courseIds, moduleIds);
  const current = useMemo(
    () =>
      placed.loading || placed.error
        ? null
        : resolveStructure(root, edits, placed.content, language),
    [root, edits, placed.content, placed.loading, placed.error, language],
  );
  // While placed content loads, the last complete input is held and reprojected in the live language.
  const lastComplete = useRef<{
    report: StudyStructureReport;
    edits: StructureEdits;
    content: PlacedContent;
  } | null>(null);
  if (current)
    lastComplete.current = { report, edits, content: placed.content };
  const base =
    current ??
    (lastComplete.current
      ? resolveStructure(
          withUnplaced(
            buildStructure(lastComplete.current.report, "r", language),
            language,
          ),
          lastComplete.current.edits,
          lastComplete.current.content,
          language,
        )
      : resolveStructure(root, emptyEdits(), NO_CONTENT, language));
  const resolvedIndex = useMemo(() => indexResolved(base), [base]);
  const lastFreeIds = useRef<readonly string[]>([]);
  if (current)
    lastFreeIds.current = selected.filter(
      (id) => !base.subtree.some((course) => course.group_id === id),
    );
  const freeIds = placed.error ? [] : lastFreeIds.current;
  const freeContent = useCourseSummaries(freeIds);
  useEffect(() => {
    if (placed.loading || placed.error) return;
    const actual = base.subtree.map((course) => course.group_id);
    const current = [...placedIds].sort(),
      next = [...actual].sort();
    if (
      current.length !== next.length ||
      current.some((id, index) => id !== next[index])
    )
      applyStructure(store, { rootGroupId, ...edits, placedCourseIds: actual });
  }, [
    placed.loading,
    placed.error,
    base,
    placedIds,
    store,
    rootGroupId,
    edits,
  ]);
  const notice = useNotice();
  const moveTransition = {
    duration: 0.45,
    ease: [0.22, 0.8, 0.2, 1] as const,
  };
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const [resetOpen, setResetOpen] = useState(false);
  const resetOpener = useRef<HTMLButtonElement>(null);
  const active = activeKey
    ? (resolvedIndex.byKey.get(activeKey) ?? null)
    : null;
  const drawerResolved =
    active?.node.kind === "unplaced" &&
    !freeContent.loading &&
    !freeContent.error
      ? {
          ...active,
          courses: [
            ...active.courses,
            ...freeContent.courses
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
            ...freeContent.courses.filter(
              (course) =>
                !active.subtree.some(
                  (item) => item.group_id === course.group_id,
                ),
            ),
          ],
        }
      : active;
  const editor = useStructureEditor({
    rootGroupId,
    tree: root,
    resolved: base,
    edits,
    freeIds,
    content: placed.content,
    extend: placed.extend,
    notify: notice.show,
  });
  const open = activeKey !== null;
  useEffect(() => {
    document.body.classList.toggle("structure-drawer-open", open);
    return () => document.body.classList.remove("structure-drawer-open");
  }, [open]);
  const renderNode = (
    node: import("./model").ResolvedNode,
    depth: number,
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
          ...freeContent.courses.map((course) => ({
            course,
            added: false,
            owner: node.node,
          })),
        ]
      : display.courses;
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
      />
    );
  };
  const contentError = placed.error ?? freeContent.error;
  const refreshing = placed.loading || freeContent.loading;
  const [loadedOnce, setLoadedOnce] = useState(false);
  useEffect(() => {
    if (!refreshing) setLoadedOnce(true);
  }, [refreshing]);
  // Only the first load shows a skeleton tree. Subsequent refreshes reuse it and the scroll position.
  const contentLoading = !loadedOnce && refreshing;
  return (
    <>
      <div className={`structure-layout${open ? " with-drawer" : ""}`}>
        <div className="ctl">
          <motion.button
            className="pill-btn"
            type="button"
            layout="position"
            transition={moveTransition}
            onClick={onChangeRoot}
          >
            {t("Change root")}
          </motion.button>
          <motion.button
            className="pill-btn reset-all"
            type="button"
            layout="position"
            transition={moveTransition}
            ref={resetOpener}
            disabled={contentLoading || Boolean(contentError)}
            onClick={() => setResetOpen(true)}
          >
            {t("Reset all")}
          </motion.button>
        </div>
        <ResetStructureDialog
          open={resetOpen}
          onCancel={() => setResetOpen(false)}
          onReset={() => {
            editor.resetAll();
            setActiveKey(null);
            setResetOpen(false);
          }}
          returnFocus={() => resetOpener.current?.focus()}
        />
        {editor.error && (
          <ErrorNotice error={editor.error} language={language} />
        )}{" "}
        {contentError && (
          <ErrorNotice error={contentError} language={language} />
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
                <AnimatePresence>{renderNode(base, 0)}</AnimatePresence>
              </LayoutGroup>
            </div>
          )
        )}
        <StructureDrawer
          target={
            !contentLoading && !contentError && drawerResolved
              ? { resolved: drawerResolved }
              : null
          }
          editor={editor}
          onClose={() => setActiveKey(null)}
          index={resolvedIndex}
        />
      </div>
      {notice.toast}
    </>
  );
}
