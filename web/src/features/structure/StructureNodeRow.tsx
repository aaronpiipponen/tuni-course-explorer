/** Expanded-by-default, user-collapsible Structure row with a drawer target. */
import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import type { ResolvedNode } from "./model";
import { useProfileSelector } from "../../state/useProfileSelector";
import { Disclosure } from "../../shared/Disclosure";
import {
  moduleName,
  formatCredits,
  sumCredits,
  nodeKindLabel,
} from "./presentation";
import { StructureCard } from "./StructureCard";
import { DOCUMENT } from "../../shared/icons";
import type { DisplayContents } from "./display";
import { useWording } from "../../shared/useWording";
import { uiText } from "../../shared/wording";

export function StructureNodeRow({
  resolved,
  courses,
  notes,
  depth,
  active,
  onOpen,
  children,
}: {
  resolved: ResolvedNode;
  courses: DisplayContents["courses"];
  notes: readonly string[];
  depth: number;
  active: boolean;
  onOpen: (resolved: ResolvedNode) => void;
  children?: React.ReactNode;
}) {
  const [open, setOpen] = useState(true);
  const transition = {
    duration: 0.45,
    ease: [0.22, 0.8, 0.2, 1] as const,
  };
  const language = useProfileSelector((state) => state.language).value;
  const { t } = useWording();
  const completed = new Set(
    useProfileSelector((state) => state.completedCourseIds).value,
  );
  const rowCourses = courses.map(({ course }) => course);
  const bucketCourses = new Map<string, (typeof rowCourses)[number]>();
  if (resolved.node.kind === "unplaced")
    for (const course of [...resolved.subtree, ...rowCourses])
      bucketCourses.set(course.group_id, course);
  const totals =
    resolved.node.kind === "unplaced"
      ? [...bucketCourses.values()]
      : resolved.subtree;
  const selectedCredits = sumCredits(totals),
    completedCredits = sumCredits(totals, (course) =>
      completed.has(course.group_id),
    );
  const title =
    resolved.node.kind === "unplaced"
      ? resolved.node.title!
      : moduleName(resolved.node.module!, language);
  const code = resolved.node.module?.code;
  return (
    <motion.section
      className={`snode${active ? " active" : ""}`}
      style={{ "--depth": depth } as React.CSSProperties}
      layout
      layoutId={
        resolved.node.module
          ? `structure-module-${resolved.node.module.group_id}`
          : undefined
      }
      initial={{ opacity: 0, height: 0, scale: 0.97 }}
      animate={{ opacity: 1, height: "auto", scale: 1 }}
      exit={{ opacity: 0, height: 0, scale: 0.97 }}
      transition={transition}
    >
      <div className="sh">
        <button
          className="chev"
          type="button"
          aria-label={t("{action} {name}", {
            action: t(open ? "Collapse" : "Expand"),
            name: title,
          })}
          aria-expanded={open}
          onClick={() => {
            setOpen((value) => !value);
          }}
        >
          <svg viewBox="0 0 16 16" aria-hidden="true">
            <path d="M4 6l4 4 4-4" />
          </svg>
        </button>
        <button
          className="shead-main"
          type="button"
          onClick={() => onOpen(resolved)}
        >
          <span className="sname">{title}</span>
          <i className="hair" />
          <span className="scnt">
            <b>{formatCredits(selectedCredits)}</b> |{" "}
            {uiText(language, "{value} cr", {
              value: formatCredits(completedCredits),
            })}
          </span>
          <span className="r2">
            {DOCUMENT}
            {code && <span className="scode">{code}</span>}
            <span className="skind">
              {nodeKindLabel(resolved.node, language)}
            </span>
            {resolved.added && <span className="tag r">{t("added")}</span>}
          </span>
        </button>
      </div>
      <Disclosure open={open} className="sbody">
        <div className="sin">
          <div className="sgrid">
            <AnimatePresence>
              {courses.map(({ course, added }) => (
                <motion.div
                  className="structure-course-motion"
                  key={course.group_id}
                  layout
                  layoutId={`structure-course-${course.group_id}`}
                  initial={{ opacity: 0, height: 0, scale: 0.97 }}
                  animate={{ opacity: 1, height: "auto", scale: 1 }}
                  exit={{ opacity: 0, height: 0, scale: 0.97 }}
                  transition={transition}
                >
                  <StructureCard
                    course={course}
                    completed={completed.has(course.group_id)}
                    added={added}
                  />
                </motion.div>
              ))}
            </AnimatePresence>
          </div>
          {notes.map((note, index) => (
            <p className="sempty" key={`${note}-${index}`}>
              {note}
            </p>
          ))}
          <AnimatePresence>{children}</AnimatePresence>
          {!courses.length &&
            !resolved.children.length &&
            !notes.length &&
            !children &&
            resolved.node.kind === "unplaced" && (
              <p className="sempty">{t("Nothing here yet.")}</p>
            )}
        </div>
      </Disclosure>
    </motion.section>
  );
}
