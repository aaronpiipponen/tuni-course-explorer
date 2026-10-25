/** Drawer-local course/module/programme substring search and category controls. */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type {
  CatalogueCourse,
  CatalogueModule,
  CourseSummary,
  ModuleLookupGroup,
} from "../../api/types";
import { useReadCache } from "../../app/useReadCache";
import { useCourseLookup } from "../../shared/course/useCourseLookup";
import { useModuleLookup } from "./useModuleLookup";
import { courseCredits, courseName } from "../../shared/course/presentation";
import { readCachedCourseSummaries } from "../../shared/course/reads";
import { moduleName } from "./presentation";
import { ModuleVersionHandoff } from "./ModuleVersionHandoff";
import { ErrorNotice } from "../../shared/ErrorNotice";
import { LookupVirtualList } from "../../shared/LookupVirtualList";
import type { StructureNode } from "./model";
import { useProfileSelector } from "../../state/useProfileSelector";
import { useWording } from "../../shared/useWording";
import { useModuleVersionHandoff } from "./useModuleVersionHandoff";

type Filter = "all" | "course" | "module" | "programme";
const FILTER_KEYS = {
  all: "All",
  course: "Courses",
  module: "Modules",
  programme: "Programmes",
} as const;

/** One drawer course row's canonical identity. */
const courseKey = (course: CatalogueCourse) => course.group_id;

/** One drawer module group row's canonical identity. */
const groupKey = (row: ModuleLookupGroup) => row.group_id;
/** Render the drawer's course, module and programme search controls. */
export function DrawerSearch({
  node,
  open,
  onOpenChange,
  onAddCourse,
  onAddModule,
  pendingId,
}: {
  node: StructureNode;
  open: boolean;
  onOpenChange(open: boolean): void;
  onAddCourse(course: CourseSummary, node: StructureNode): void;
  onAddModule(module: CatalogueModule, node: StructureNode): void;
  pendingId: string | null;
}) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const [pickError, setPickError] = useState<Error | null>(null);
  const [busyCourseId, setBusyCourseId] = useState<string | null>(null);
  const [drawer, setDrawer] = useState<HTMLDivElement | null>(null);
  const host = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const cache = useReadCache();
  const courseRead = useRef<AbortController | null>(null);
  const nodeKey = useRef(node.key);
  nodeKey.current = node.key;
  const courses = useCourseLookup(
    open && (filter === "all" || filter === "course"),
    query,
    false,
  );
  const modules = useModuleLookup(
    open && (filter === "all" || filter === "module" || filter === "programme"),
    query,
  );
  const { store, value: language } = useProfileSelector(
    (state) => state.language,
  );
  const { t } = useWording();
  const close = useCallback(() => {
    setQuery("");
    onOpenChange(false);
  }, [onOpenChange]);
  useEffect(() => {
    setQuery("");
    setFilter("all");
    setPickError(null);
    courseRead.current?.abort();
    courseRead.current = null;
    setBusyCourseId(null);
    onOpenChange(false);
    return () => courseRead.current?.abort();
  }, [node.key, onOpenChange]);
  useEffect(() => {
    if (!open) return;
    const outside = (event: PointerEvent) => {
      if (event.target instanceof Node && !host.current?.contains(event.target))
        close();
    };
    const keys = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.stopPropagation();
        close();
      }
    };
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", keys, true);
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("keydown", keys, true);
    };
  }, [open, close]);
  const moduleList = modules.report?.results;
  const moduleResults = useMemo(
    () =>
      (moduleList ?? []).filter(
        (item) =>
          filter === "all" ||
          (filter === "programme"
            ? item.module_type === "DegreeProgramme"
            : item.module_type !== "DegreeProgramme"),
      ),
    [filter, moduleList],
  );
  const resetIdentity = `${open}-${query}-${language}-${filter}-${node.key}`;
  const showCourses = filter === "all" || filter === "course";
  const showModules =
    filter === "all" || filter === "module" || filter === "programme";
  /**
   * Resolve one explicit drawer course pick into its official summary, then add it.
   *
   * The read belongs to the profile and node that started it, so a changed target or profile
   * discards its settlement. A failed or missing summary reaches the ordinary error notice.
   */
  const chooseCourse = async (course: CatalogueCourse) => {
    if (busyCourseId !== null) return;
    const profileId = store.getSnapshot().currentProfileId;
    const startedAtKey = nodeKey.current;
    const controller = new AbortController();
    courseRead.current?.abort();
    courseRead.current = controller;
    setBusyCourseId(course.group_id);
    setPickError(null);
    try {
      const response = await readCachedCourseSummaries(
        cache,
        [course.group_id],
        controller.signal,
      );
      if (controller.signal.aborted) return;
      if (
        store.getSnapshot().currentProfileId !== profileId ||
        nodeKey.current !== startedAtKey
      )
        return;
      const summary = response.results.find(
        (item) => item.group_id === course.group_id,
      );
      if (!summary) throw new Error("Requested course summary is missing");
      onAddCourse(summary, node);
      close();
    } catch (caught) {
      if (!controller.signal.aborted)
        setPickError(
          caught instanceof Error ? caught : new Error(String(caught)),
        );
    } finally {
      if (courseRead.current === controller) {
        courseRead.current = null;
        setBusyCourseId(null);
      }
    }
  };
  const disabled = pendingId !== null || busyCourseId !== null;
  const chooseModule = (module: CatalogueModule) => {
    onAddModule(module, node);
    close();
  };
  const handoff = useModuleVersionHandoff(
    chooseModule,
    input,
    JSON.stringify([open, query, filter, node.key]),
  );
  return (
    <div className="dsrch" ref={host}>
      <div className="bar sm">
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <circle cx="11" cy="11" r="7" />
          <path d="m20 20-3.5-3.5" />
        </svg>
        <input
          ref={input}
          value={query}
          placeholder={t("Add a course, module or programme")}
          onFocus={() => onOpenChange(true)}
          onClick={() => onOpenChange(true)}
          onChange={(event) => {
            setQuery(event.target.value);
            onOpenChange(true);
          }}
          onKeyDown={(event) => {
            if (event.key === "Escape") close();
          }}
        />
      </div>
      <div
        className={`dres${open ? " open" : ""}`}
        ref={setDrawer}
        aria-hidden={!open}
        inert={!open}
      >
        <div className="seg dseg">
          {(["all", "course", "module", "programme"] as const).map((value) => (
            <button
              type="button"
              className={filter === value ? "on" : ""}
              key={value}
              onClick={() => setFilter(value)}
            >
              {t(FILTER_KEYS[value])}
            </button>
          ))}
        </div>
        {!query.trim() ? (
          <div className="dnote">
            {t("Type to search courses, modules and programmes.")}
          </div>
        ) : handoff.group ? (
          <ModuleVersionHandoff
            group={handoff.group}
            cancelRef={handoff.cancelRef}
            disabled={disabled}
            onCancel={handoff.cancel}
            onSelect={handoff.pick}
          />
        ) : (
          <>
            {pickError && <ErrorNotice error={pickError} language={language} />}
            {courses.error && showCourses && (
              <ErrorNotice error={courses.error} language={language} />
            )}{" "}
            {modules.error && showModules && (
              <ErrorNotice error={modules.error} language={language} />
            )}
            {courses.loading && showCourses && (
              <div
                className="course-lookup-skeletons"
                aria-label={t("Loading courses")}
              >
                <div className="course-lookup-skeleton" />
              </div>
            )}
            {modules.loading && showModules && (
              <div
                className="course-lookup-skeletons"
                aria-label={t("Loading modules")}
              >
                <div className="course-lookup-skeleton" />
              </div>
            )}
            {showCourses && !courses.loading && !courses.error && (
              <section className="tier eyebrow">
                <div>// {t("courses (heading)")}</div>
                {courses.report?.results.length ? (
                  <LookupVirtualList
                    items={courses.report.results}
                    getItemKey={courseKey}
                    className="plist"
                    resetKey={resetIdentity}
                    inputRef={input}
                    scrollElement={drawer}
                    renderRow={(course) => (
                      <button
                        className="prow"
                        type="button"
                        onClick={() => void chooseCourse(course)}
                        disabled={disabled}
                      >
                        <span className="code">{course.code}</span>
                        <span className="pn">
                          {courseName(course, language)}
                        </span>
                        <span className="cr">
                          {courseCredits(course, language)}
                        </span>
                        <span className="add">{t("+ add")}</span>
                      </button>
                    )}
                  />
                ) : (
                  <div className="dnote">{t("No matches.")}</div>
                )}
              </section>
            )}
            {showModules && !modules.loading && !modules.error && (
              <section className="tier eyebrow">
                {filter === "programme" ? (
                  <div>// {t("programmes")}</div>
                ) : (
                  <div>// {t("modules")}</div>
                )}
                {moduleResults.length ? (
                  <LookupVirtualList
                    items={moduleResults}
                    getItemKey={groupKey}
                    className="plist"
                    resetKey={resetIdentity}
                    inputRef={input}
                    scrollElement={drawer}
                    renderRow={(item) => (
                      <button
                        className="prow root-module-row"
                        type="button"
                        onClick={() => handoff.activate(item)}
                        disabled={disabled}
                      >
                        <span className="code">{item.code ?? ""}</span>
                        <span className="pn">{moduleName(item, language)}</span>
                      </button>
                    )}
                  />
                ) : (
                  <div className="dnote">{t("No matches.")}</div>
                )}
              </section>
            )}
          </>
        )}
      </div>
    </div>
  );
}
