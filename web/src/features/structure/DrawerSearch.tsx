/** Drawer-local course/module/programme substring search and category controls. */
import { useCallback, useEffect, useRef, useState } from "react";
import type { CourseSummary, ModuleSummary } from "../../api/types";
import { useCourseLookup } from "../../shared/course/useCourseLookup";
import { useModuleLookup } from "./useModuleLookup";
import { courseCredits, courseName } from "../../shared/course/presentation";
import { moduleName } from "./presentation";
import { ErrorNotice } from "../../shared/ErrorNotice";
import type { StructureNode } from "./model";
import { useProfileSelector } from "../../state/useProfileSelector";
import { useWording } from "../../shared/useWording";

type Filter = "all" | "course" | "module" | "programme";
const FILTER_KEYS = {
  all: "All",
  course: "Courses",
  module: "Modules",
  programme: "Programmes",
} as const;
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
  onAddModule(module: ModuleSummary, node: StructureNode): void;
  pendingId: string | null;
}) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const host = useRef<HTMLDivElement>(null);
  const courses = useCourseLookup(
    open && (filter === "all" || filter === "course"),
    query,
    false,
  );
  const modules = useModuleLookup(
    open && (filter === "all" || filter === "module" || filter === "programme"),
    query,
  );
  const language = useProfileSelector((state) => state.language).value;
  const { t } = useWording();
  const close = useCallback(() => {
    setQuery("");
    onOpenChange(false);
  }, [onOpenChange]);
  useEffect(() => {
    setQuery("");
    setFilter("all");
    onOpenChange(false);
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
  const moduleResults = (modules.report?.results ?? []).filter(
    (item) =>
      filter === "all" ||
      (filter === "programme"
        ? item.module_type === "DegreeProgramme"
        : item.module_type !== "DegreeProgramme"),
  );
  const showCourses = filter === "all" || filter === "course";
  const showModules =
    filter === "all" || filter === "module" || filter === "programme";
  const chooseCourse = (course: CourseSummary) => {
    onAddCourse(course, node);
    close();
  };
  const chooseModule = (module: ModuleSummary) => {
    onAddModule(module, node);
    close();
  };
  return (
    <div className="dsrch" ref={host}>
      <div className="bar sm">
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <circle cx="11" cy="11" r="7" />
          <path d="m20 20-3.5-3.5" />
        </svg>
        <input
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
      <div className={`dres${open ? " open" : ""}`} aria-hidden={!open}>
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
        ) : (
          <>
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
                  <div className="plist">
                    {courses.report.results.map((course) => (
                      <button
                        className="prow"
                        key={course.group_id}
                        type="button"
                        onClick={() => chooseCourse(course)}
                        disabled={pendingId !== null}
                      >
                        <span className="code">{course.code}</span>
                        <span className="pn">
                          {courseName(course, language)}
                        </span>
                        <span className="cr">
                          {courseCredits(course, language)}
                        </span>
                      </button>
                    ))}
                  </div>
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
                  <div className="plist">
                    {moduleResults.map((item) => (
                      <button
                        className="prow"
                        key={item.group_id}
                        type="button"
                        onClick={() => chooseModule(item)}
                        disabled={pendingId !== null}
                      >
                        <span className="code">{item.code ?? ""}</span>
                        <span className="pn">{moduleName(item, language)}</span>
                        <span className="cr">
                          {t(
                            item.module_type === "DegreeProgramme"
                              ? "programme"
                              : "module",
                          )}
                        </span>
                        {pendingId === item.group_id && (
                          <span>{t("adding…")}</span>
                        )}
                      </button>
                    ))}
                  </div>
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
