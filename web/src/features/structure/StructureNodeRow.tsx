/** Expanded-by-default, user-collapsible Structure row with a drawer target and drag slots. */
import {
  useContext,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import { AnimatePresence, motion, useIsPresent } from "framer-motion";
import type { ResolvedNode } from "./model";
import { useProfileSelector } from "../../state/useProfileSelector";
import { Disclosure } from "../../shared/Disclosure";
import { PaneSlideContext } from "../../app/paneSlide";
import { useReducedMotion } from "../../shared/useReducedMotion";
import {
  moduleName,
  formatCredits,
  sumCredits,
  nodeKindLabel,
} from "./presentation";
import { StructureCard } from "./StructureCard";
import { ProgrammeMenu } from "./ProgrammeMenu";
import { DOCUMENT } from "../../shared/icons";
import type { DisplayContents } from "./display";
import type { CourseDrag } from "./useCourseDrag";
import { useWording } from "../../shared/useWording";
import { uiText } from "../../shared/wording";

/** Render one collapsible Structure node row. */
export function StructureNodeRow({
  resolved,
  courses,
  notes,
  depth,
  active,
  onOpen,
  children,
  programmeActions,
  drag,
}: {
  resolved: ResolvedNode;
  courses: DisplayContents["courses"];
  notes: readonly string[];
  depth: number;
  active: boolean;
  onOpen: (resolved: ResolvedNode) => void;
  children?: React.ReactNode;
  /** The pane's one transient course drag. */
  drag: CourseDrag;
  /** Present on a direct top-level programme row only. */
  programmeActions?: {
    onReplace(): void;
    onReset(): void;
    onDelete(): void;
  };
}) {
  const [open, setOpen] = useState(true);
  // A targeted collapsed holder reveals its body for the preview alone, so a cancel or a move to
  // another holder restores the user's own disclosure state without a saved copy.
  const dragTargeted =
    drag.activeCourseId !== null && drag.target?.key === resolved.node.key;
  // The accepted handoff keeps its destination open until the row takes the visible rectangle.
  const dragHandoff =
    drag.completedDrop?.targetKey === resolved.node.key &&
    drag.completedDrop.from !== null;
  const expanded = open || dragTargeted || dragHandoff;
  const gridRef = useRef<HTMLDivElement>(null);
  // Layout animation pauses for the drag teardown, so a cancelled or in-place drop never replays
  // the preview projection on the cards that did not move.
  const dragActive = drag.activeCourseId !== null;
  const [layoutAnimation, setLayoutAnimation] = useState(true);
  // The empty note waits for the last card's exit, so the row never snaps from a card to the note.
  const [emptyReady, setEmptyReady] = useState(true);
  useLayoutEffect(() => {
    if (dragActive) {
      setLayoutAnimation(true);
      return;
    }
    setLayoutAnimation(false);
    const frame = requestAnimationFrame(() => setLayoutAnimation(true));
    return () => cancelAnimationFrame(frame);
  }, [dragActive]);
  const settleTimer = useRef<number | null>(null);
  useLayoutEffect(() => {
    if (drag.completedDrop?.targetKey === resolved.node.key) setOpen(true);
  }, [drag.completedDrop, resolved.node.key]);
  useEffect(
    () => () => {
      if (settleTimer.current !== null)
        window.clearTimeout(settleTimer.current);
    },
    [],
  );
  const reducedMotion = useReducedMotion();
  const paneSliding = useContext(PaneSlideContext);
  const still = reducedMotion || paneSliding;
  const transition = {
    duration: still ? 0 : 0.45,
    ease: [0.22, 0.8, 0.2, 1] as const,
  };
  // A row that grows from nothing or leaves the tree clips its content, so its own title cannot
  // paint over the rows below while the box opens or collapses. The entry clip ends with the
  // row's own opening transition, and the exit clip lasts while AnimatePresence removes the row.
  const present = useIsPresent();
  const [entering, setEntering] = useState(!still);
  useEffect(() => {
    if (!entering) return;
    const timer = window.setTimeout(
      () => setEntering(false),
      transition.duration * 1000 + 50,
    );
    return () => window.clearTimeout(timer);
  }, [entering, transition.duration]);
  const clipping = entering || !present;
  const language = useProfileSelector((state) => state.language).value;
  const { t } = useWording();
  const handoff = drag.completedDrop;
  const handoffFrom = handoff?.from ?? null;
  const handoffCourseId = handoff?.courseId ?? null;
  const handoffSequence = handoff?.sequence ?? 0;
  const holdsHandoffCourse =
    handoffCourseId !== null &&
    courses.some(({ course }) => course.group_id === handoffCourseId);
  const consumeDrop = drag.consumeDrop;
  useLayoutEffect(() => {
    if (handoffFrom === null || handoffCourseId === null) return;
    if (!holdsHandoffCourse || !expanded) return;
    let frame = 0;
    let cancelled = false;
    let previous: DOMRect | null = null;
    let stableFrames = 0;
    const destination = () => {
      const grid = gridRef.current;
      if (!grid) return null;
      return (
        Array.from(
          grid.querySelectorAll<HTMLElement>("[data-structure-course]"),
        ).find(
          (candidate) => candidate.dataset.structureCourse === handoffCourseId,
        ) ?? null
      );
    };
    const begin = (slot: DOMRect) => {
      drag.settleDrop({
        left: slot.left,
        top: slot.top,
        width: slot.width,
        height: slot.height,
      });
      if (reducedMotion) {
        consumeDrop(handoffSequence);
        return;
      }
      // The destination card stays hidden behind the flying lifted copy until the flight ends.
      if (settleTimer.current !== null)
        window.clearTimeout(settleTimer.current);
      settleTimer.current = window.setTimeout(() => {
        settleTimer.current = null;
        consumeDrop(handoffSequence);
      }, 320);
    };
    const tick = () => {
      if (cancelled) return;
      const element = destination();
      if (!element) {
        frame = requestAnimationFrame(tick);
        return;
      }
      const slot = element.getBoundingClientRect();
      if (slot.width === 0 || slot.height === 0) {
        previous = null;
        stableFrames = 0;
        frame = requestAnimationFrame(tick);
        return;
      }
      // The surrounding layout keeps moving after the write, so the handoff starts once the
      // destination holds one measured slot for two frames.
      stableFrames =
        previous !== null &&
        Math.abs(previous.left - slot.left) < 1 &&
        Math.abs(previous.top - slot.top) < 1
          ? stableFrames + 1
          : 0;
      previous = slot;
      if (stableFrames >= 2) {
        begin(slot);
        return;
      }
      frame = requestAnimationFrame(tick);
    };
    if (reducedMotion) {
      const element = destination();
      if (!element) return;
      begin(element.getBoundingClientRect());
      return;
    }
    tick();
    return () => {
      cancelled = true;
      if (frame !== 0) cancelAnimationFrame(frame);
    };
  }, [
    consumeDrop,
    expanded,
    handoffCourseId,
    handoffFrom,
    handoffSequence,
    holdsHandoffCourse,
    reducedMotion,
    drag.settleDrop,
  ]);
  const completed = new Set(
    useProfileSelector((state) => state.completedCourseIds).value,
  );
  const rowCourses = courses.map(({ course }) => course);
  // A card that appeared since the previous render enters without a layout animation, so it never
  // slides in from a measured position it never had. The set updates after the commit, which keeps
  // the new card out of the layout pass that mounts it.
  const renderedCards = useRef<Set<string>>(new Set());
  const freshCards = new Set(
    courses
      .map(({ course }) => course.group_id)
      .filter((id) => !renderedCards.current.has(id)),
  );
  useEffect(() => {
    renderedCards.current = new Set(
      courses.map(({ course }) => course.group_id),
    );
  }, [courses]);
  useEffect(() => {
    if (courses.length > 0) setEmptyReady(false);
  }, [courses.length]);
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
  const creditSummary = (
    <>
      <b>{formatCredits(selectedCredits)}</b> |{" "}
      {uiText(language, "{value} cr", {
        value: formatCredits(completedCredits),
      })}
    </>
  );
  const ghost = (
    <div
      className="structure-course-ghost"
      key="structure-course-ghost"
      aria-hidden="true"
      style={
        {
          "--drag-ghost-width": `${drag.lifted?.width ?? 0}px`,
          "--drag-ghost-height": `${drag.lifted?.height ?? 0}px`,
        } as React.CSSProperties
      }
    />
  );
  return (
    <motion.section
      className={`snode${active ? " active" : ""}${clipping ? " is-clipping" : ""}`}
      style={{ "--depth": depth } as React.CSSProperties}
      data-structure-holder={resolved.node.key}
      data-structure-unplaced={
        resolved.node.kind === "unplaced" ? "" : undefined
      }
      layout={still ? false : "position"}
      layoutId={
        still
          ? undefined
          : resolved.node.module
            ? `structure-module-${resolved.node.module.group_id}`
            : undefined
      }
      initial={still ? false : { opacity: 0, height: 0, scale: 0.97 }}
      animate={{ opacity: 1, height: "auto", scale: 1 }}
      // The row's own top spacing collapses with its height, so removing the node leaves no
      // leftover step after the glide.
      exit={{ opacity: 0, height: 0, marginTop: 0, scale: 0.97 }}
      transition={transition}
    >
      <div className="sh" data-structure-header={resolved.node.key}>
        <button
          className="chev"
          type="button"
          aria-label={t("{action} {name}", {
            action: t(expanded ? "Collapse" : "Expand"),
            name: title,
          })}
          aria-expanded={expanded}
          onClick={() => {
            setOpen((value) => !value);
          }}
        >
          <svg viewBox="0 0 16 16" aria-hidden="true">
            <path d="M4 6l4 4 4-4" />
          </svg>
        </button>
        <div className="shead-main">
          <button
            className="shead-open"
            type="button"
            onClick={() => onOpen(resolved)}
          >
            <span className="sname">{title}</span>
            <span className="r2">
              {DOCUMENT}
              {code && <span className="scode">{code}</span>}
              <span className="skind">
                {nodeKindLabel(resolved.node, language)}
              </span>
              <span className="scnt-inline">{creditSummary}</span>
              {resolved.added && <span className="tag r">{t("added")}</span>}
            </span>
          </button>
          {programmeActions ? (
            <ProgrammeMenu name={title} {...programmeActions} />
          ) : (
            <i className="hair" />
          )}
          <span className="scnt">{creditSummary}</span>
        </div>
      </div>
      <Disclosure open={expanded} className="sbody">
        <div className="sin">
          <div
            className="sgrid"
            ref={gridRef}
            data-structure-grid={resolved.node.key}
            style={
              // A source-only holder reserves the hidden source's height, while other empty
              // holders are reached through their headers.
              drag.activeCourseId !== null &&
              courses.some(
                ({ course }) => course.group_id === drag.activeCourseId,
              ) &&
              !courses.some(
                ({ course }) => course.group_id !== drag.activeCourseId,
              ) &&
              drag.lifted
                ? { minHeight: drag.lifted.height }
                : undefined
            }
          >
            <AnimatePresence
              onExitComplete={() => {
                if (!courses.length) setEmptyReady(true);
              }}
            >
              {courses.flatMap(({ course, added }) => {
                const lifted = drag.activeCourseId === course.group_id;
                const armed = drag.armedCourseId === course.group_id;
                const receiving =
                  handoffCourseId === course.group_id && handoffFrom !== null;
                const card = (
                  <motion.div
                    className={`structure-course-slot${armed ? " is-armed" : ""}`}
                    key={course.group_id}
                    data-structure-course={course.group_id}
                    style={lifted ? { display: "none" } : undefined}
                    initial={
                      reducedMotion || receiving ? false : { opacity: 0 }
                    }
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    transition={{ duration: reducedMotion ? 0 : 0.3 }}
                  >
                    <motion.div
                      className={`structure-course-motion${receiving ? " is-receiving" : ""}`}
                      {...(lifted ? {} : drag.cardProps(course.group_id))}
                      exit={still ? { opacity: 0 } : { opacity: 0, height: 0 }}
                      transition={{ duration: still ? 0 : 0.3 }}
                      layout={
                        !still &&
                        !lifted &&
                        !receiving &&
                        layoutAnimation &&
                        !entering &&
                        !freshCards.has(course.group_id)
                      }
                      layoutId={
                        still ||
                        lifted ||
                        receiving ||
                        entering ||
                        freshCards.has(course.group_id)
                          ? undefined
                          : `structure-course-${resolved.node.key}-${course.group_id}`
                      }
                    >
                      <StructureCard
                        course={course}
                        completed={completed.has(course.group_id)}
                        added={
                          resolved.node.kind === "unplaced" ? false : added
                        }
                      />
                    </motion.div>
                  </motion.div>
                );
                if (
                  dragTargeted &&
                  drag.target?.beforeCourseId === course.group_id
                )
                  return [ghost, card];
                return [card];
              })}
              {dragTargeted && drag.target?.beforeCourseId === null && ghost}
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
            resolved.node.kind === "unplaced" &&
            emptyReady && (
              <motion.div
                initial={still ? false : { opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                transition={{ duration: still ? 0 : 0.25 }}
                style={{ overflow: "hidden" }}
              >
                <p className="sempty">{t("Nothing here yet.")}</p>
              </motion.div>
            )}
        </div>
      </Disclosure>
    </motion.section>
  );
}
