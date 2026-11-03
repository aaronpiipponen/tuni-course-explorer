/**
 * One transient course-card drag gesture over the structure tree.
 *
 * A pointer or touch contact becomes a drag after its own start threshold, follows the contact with
 * a lifted copy of the card, marks the insertion slot with a ghost and writes the accepted drop
 * through the caller's single editor operation. Measurements, listeners, timers and the scroll
 * frame are transient and never enter the saved profile.
 */
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
  type RefObject,
} from "react";
import {
  DRAG_BLOCKING_SELECTORS,
  OVERLAY_SELECTORS,
} from "../../shared/viewport";
import type { DisplayContents } from "./display";

/** One displayed holder and the courses it draws directly, in displayed order. */
export type CourseDragHolder = {
  key: string;
  courses: DisplayContents["courses"];
};
/** The holder and anchor an active drag would insert into. */
export type CourseDragTarget = {
  key: string;
  beforeCourseId: string | null;
};
/** One transient viewport rectangle of the lifted card. */
export type CourseDragRect = {
  left: number;
  top: number;
  width: number;
  height: number;
};
/** The lifted copy that follows the active contact. */
export type CourseDragLifted = {
  course: DisplayContents["courses"][number];
  left: number;
  top: number;
  width: number;
  height: number;
};
/**
 * The last accepted drop, kept for its holder's reveal until the next drop or an invalidation.
 *
 * `from` is the lifted card's viewport rectangle at release and is null once the destination has
 * taken the handoff. The sequence identifies that one handoff.
 */
export type CourseDragCompleted = {
  targetKey: string;
  sequence: number;
  courseId: string;
  from: CourseDragRect | null;
};
/** The drag state and handlers one structure row and pane read. */
export type CourseDrag = {
  activeCourseId: string | null;
  /** The course whose hold completed and shows its pickup cue, before any movement. */
  armedCourseId: string | null;
  target: CourseDragTarget | null;
  cardProps(courseId: string): {
    onPointerDownCapture: (event: ReactPointerEvent<HTMLDivElement>) => void;
  };
  lifted: CourseDragLifted | null;
  completedDrop: CourseDragCompleted | null;
  consumeDrop(sequence: number): void;
  /** The untransformed box the lifted card flies to, or null while it follows the contact. */
  settleTarget: CourseDragRect | null;
  /** Send the lifted card from the release rectangle into one destination slot. */
  settleDrop(slot: CourseDragRect): void;
};

/** The mouse hold in milliseconds that arms the drag. */
const MOUSE_HOLD_MS = 50;
/** The touch hold in milliseconds that separates a drag from a tap and a scroll. */
const TOUCH_HOLD_MS = 250;
/** The travel in pixels before the hold completes that cancels the press. */
const DRAG_START_TRAVEL = 8;
/** The travel in pixels after the hold that starts the drag. */
const ARMED_START_TRAVEL = 4;
/** The band in pixels at each pane edge where the active drag autoscrolls. */
const SCROLL_EDGE = 56;
/** The greatest autoscroll speed in pixels per second. */
const SCROLL_MAX_VELOCITY = 600;
/** The longest autoscroll frame in milliseconds. */
const SCROLL_MAX_FRAME_MS = 32;

type Contact = {
  courseId: string;
  card: HTMLElement;
  pointerId: number | null;
  touchId: number | null;
  startX: number;
  startY: number;
  x: number;
  y: number;
  offsetX: number;
  offsetY: number;
  width: number;
  height: number;
  active: boolean;
  /** The hold completed: the card shows its pickup cue and waits for movement. */
  armed: boolean;
  timer: number | null;
  pointerCleanup: (() => void) | null;
  touchMove: EventListener | null;
  touchEnd: EventListener | null;
  /** Each open holder grid's direct cells in displayed order, relative to its layout origin. */
  grids: Map<string, GridCard[]>;
  /** The contact coordinate at the lift, so a stationary hold arms no pane scroll. */
  liftedX: number;
  liftedY: number;
  scrollArmed: boolean;
};

/** One measured direct card of a holder grid in gesture-local layout coordinates. */
type GridCard = {
  id: string;
  left: number;
  top: number;
  width: number;
  height: number;
};

function distance(contact: Contact, x: number, y: number): number {
  return Math.hypot(x - contact.startX, y - contact.startY);
}

/** The static detached pose of the lifted card. It matches the held cue's pose, so the card
    continues from where the cue left it instead of jumping when the drag takes over. */
export const COURSE_DRAG_LIFT_Y = -1;
/** The scale of the lifted card's detached pose. */
export const COURSE_DRAG_LIFT_SCALE = 1.01;

/** Return the lifted card's transformed visual rectangle from its contact and captured size. */
function contactRect(contact: Contact): CourseDragRect {
  const width = contact.width * COURSE_DRAG_LIFT_SCALE;
  const height = contact.height * COURSE_DRAG_LIFT_SCALE;
  return {
    left: contact.x - contact.offsetX - (width - contact.width) / 2,
    top:
      contact.y -
      contact.offsetY +
      COURSE_DRAG_LIFT_Y -
      (height - contact.height) / 2,
    width,
    height,
  };
}

/** Return the layout point of one element relative to the page's layout origin. */
function layoutPoint(element: HTMLElement): { x: number; y: number } {
  let x = 0;
  let y = 0;
  let node: HTMLElement | null = element;
  while (node) {
    x += node.offsetLeft;
    y += node.offsetTop;
    node = node.offsetParent as HTMLElement | null;
  }
  return { x, y };
}

/**
 * Return one grid's direct course cells in displayed order, relative to its layout origin.
 *
 * The source cell stays in the logical arrangement and the preview ghost leaves it, so the
 * measurement is the arrangement the cards hold before the lift changes their flow.
 */
function measureGridCards(
  grid: HTMLElement,
  activeCourseId: string,
): GridCard[] {
  const ghost = Array.from(grid.children).find(
    (child): child is HTMLElement =>
      child instanceof HTMLElement &&
      child.classList.contains("structure-course-ghost"),
  );
  const source = Array.from(grid.children).find(
    (child): child is HTMLElement =>
      child instanceof HTMLElement &&
      child.dataset.structureCourse === activeCourseId,
  );
  const ghostDisplay = ghost?.style.display ?? "";
  const sourceDisplay = source?.style.display ?? "";
  const sourceVisibility = source?.style.visibility ?? "";
  if (ghost) ghost.style.display = "none";
  if (source) {
    source.style.display = "";
    source.style.visibility = "hidden";
  }
  try {
    const gridLayout = layoutPoint(grid);
    const cards: GridCard[] = [];
    for (const child of Array.from(grid.children)) {
      if (!(child instanceof HTMLElement) || child === ghost) continue;
      const id = child.dataset.structureCourse;
      if (!id || child.closest("[data-structure-grid]") !== grid) continue;
      const point = layoutPoint(child);
      cards.push({
        id,
        left: point.x - gridLayout.x,
        top: point.y - gridLayout.y,
        width: child.offsetWidth,
        height: child.offsetHeight,
      });
    }
    return cards;
  } finally {
    if (ghost) ghost.style.display = ghostDisplay;
    if (source) {
      source.style.display = sourceDisplay;
      source.style.visibility = sourceVisibility;
    }
  }
}

/** Return one grid's captured logical cells, capturing a newly revealed grid once. */
function gridCards(contact: Contact, grid: HTMLElement): GridCard[] {
  const key = grid.dataset.structureGrid ?? "";
  const captured = contact.grids.get(key);
  if (captured) return captured;
  const cards = measureGridCards(grid, contact.courseId);
  contact.grids.set(key, cards);
  return cards;
}

/** Return the positive intersection area of one viewport rectangle with another. */
function intersectionArea(
  rect: DOMRect | CourseDragRect,
  target: CourseDragRect,
) {
  const left = Math.max(rect.left, target.left);
  const right = Math.min(rect.left + rect.width, target.left + target.width);
  const top = Math.max(rect.top, target.top);
  const bottom = Math.min(rect.top + rect.height, target.top + target.height);
  return Math.max(0, right - left) * Math.max(0, bottom - top);
}

/** Return the course wrapper and identity one pointer or touch contact starts on. */
function eligibleContact(
  target: EventTarget | null,
  allowDrawers: boolean,
): { card: HTMLElement; courseId: string } | null {
  if (!(target instanceof Element)) return null;
  const trigger = target.closest(".tile-trigger");
  if (!trigger) return null;
  if (
    target.closest(
      ".tile-actions, button:not(.tile-trigger), a, input, textarea, select, [contenteditable], [role='slider']",
    )
  )
    return null;
  if (
    document.querySelector(
      allowDrawers ? DRAG_BLOCKING_SELECTORS : OVERLAY_SELECTORS.blocking,
    )
  )
    return null;
  const card = trigger.closest<HTMLElement>("[data-structure-course]");
  const courseId = card?.dataset.structureCourse;
  if (!card || !courseId) return null;
  return { card, courseId };
}

/**
 * Track one course drag and return its transient state with the handlers a course row spreads.
 *
 * `holders` lists the displayed programme, module and Unplaced holders in depth-first order.
 * `enabled` is false while the tree cannot write, `inputKey` identifies the exact hydrated input
 * the gesture started from, and `onDrop` is the single editor write. A changed input key, a
 * disabled surface and an unmount cancel the gesture without writing.
 */
export function useCourseDrag({
  treeRef,
  holders,
  enabled,
  inputKey,
  onDrop,
}: {
  treeRef: RefObject<HTMLDivElement | null>;
  holders: readonly CourseDragHolder[];
  enabled: boolean;
  inputKey: string;
  onDrop(
    courseId: string,
    targetKey: string,
    beforeCourseId: string | null,
  ): boolean;
}): CourseDrag {
  const [activeCourseId, setActiveCourseId] = useState<string | null>(null);
  const [armedCourseId, setArmedCourseId] = useState<string | null>(null);
  const [target, setTarget] = useState<CourseDragTarget | null>(null);
  const [lifted, setLifted] = useState<CourseDragLifted | null>(null);
  const [settleTarget, setSettleTarget] = useState<CourseDragRect | null>(null);
  const settleFallback = useRef<number | null>(null);
  const [completedDrop, setCompletedDrop] =
    useState<CourseDragCompleted | null>(null);
  const gesture = useRef<Contact | null>(null);
  const targetRef = useRef<CourseDragTarget | null>(null);
  // The holder whose collapsed header was targeted, kept for the append through its reveal.
  const collapsedAppend = useRef<string | null>(null);
  const holdersRef = useRef(holders);
  const enabledRef = useRef(enabled);
  const inputKeyRef = useRef(inputKey);
  const onDropRef = useRef(onDrop);
  const mounted = useRef(true);
  const suppressClick = useRef(false);
  const scrollFrame = useRef<number | null>(null);
  const bodyFrame = useRef<number | null>(null);
  const scrollPane = useRef<HTMLElement | null>(null);
  // One accepted drop's own input-key change follows the write, so it must not discard the handoff.
  const acceptedHandoff = useRef(false);
  holdersRef.current = holders;
  enabledRef.current = enabled;
  onDropRef.current = onDrop;

  const publishTarget = useCallback((next: CourseDragTarget | null) => {
    const previous = targetRef.current;
    if (previous === next) return;
    if (
      previous &&
      next &&
      previous.key === next.key &&
      previous.beforeCourseId === next.beforeCourseId
    )
      return;
    targetRef.current = next;
    setTarget(next);
  }, []);

  /** Discard the completed drop event and the lifted copy on an invalidated gesture. */
  const discardHandoff = useCallback(() => {
    setCompletedDrop(null);
    setLifted(null);
    setSettleTarget(null);
    if (settleFallback.current !== null) {
      window.clearTimeout(settleFallback.current);
      settleFallback.current = null;
    }
  }, []);

  const stopTouchListeners = useCallback((contact: Contact) => {
    if (contact.touchMove)
      document.removeEventListener("touchmove", contact.touchMove, true);
    if (contact.touchEnd) {
      document.removeEventListener("touchend", contact.touchEnd, true);
      document.removeEventListener("touchcancel", contact.touchEnd, true);
    }
    contact.touchMove = null;
    contact.touchEnd = null;
  }, []);

  const stopScroll = useCallback(() => {
    if (scrollFrame.current !== null) {
      cancelAnimationFrame(scrollFrame.current);
      scrollFrame.current = null;
    }
    scrollPane.current = null;
  }, []);

  const scheduleBodyClear = useCallback(() => {
    if (!document.body.classList.contains("course-dragging")) return;
    if (bodyFrame.current !== null) cancelAnimationFrame(bodyFrame.current);
    bodyFrame.current = requestAnimationFrame(() => {
      bodyFrame.current = null;
      document.body.classList.remove("course-dragging");
    });
  }, []);

  const clearGesture = useCallback(
    (immediate = false, preserveLifted = false) => {
      const contact = gesture.current;
      gesture.current = null;
      collapsedAppend.current = null;
      stopScroll();
      if (contact) {
        if (contact.timer !== null) window.clearTimeout(contact.timer);
        if (contact.pointerCleanup) contact.pointerCleanup();
        contact.pointerCleanup = null;
        stopTouchListeners(contact);
      }
      if (immediate) {
        if (bodyFrame.current !== null) {
          cancelAnimationFrame(bodyFrame.current);
          bodyFrame.current = null;
        }
        document.body.classList.remove("course-dragging");
      }
      if (!mounted.current) return;
      setArmedCourseId(null);
      setActiveCourseId(null);
      publishTarget(null);
      if (!preserveLifted) setLifted(null);
      if (!immediate) scheduleBodyClear();
    },
    [publishTarget, scheduleBodyClear, stopScroll, stopTouchListeners],
  );

  /**
   * Return the insertion anchor of one holder grid for the lifted card's rectangle.
   *
   * The grid's direct cells are its captured logical arrangement, translated through the grid's
   * live viewport origin. The cell of greatest positive overlap wins, an exact tie keeps the
   * current logical index or the earlier cell, and a rectangle that overlaps none takes the
   * nearest cell centre. A rectangle below the final logical row appends, whatever its horizontal
   * position. The chosen logical index converts to the same index in the source-excluded identity
   * list, where the end is the append.
   */
  const insertionAt = useCallback(
    (grid: HTMLElement, rect: CourseDragRect): string | null => {
      const contact = gesture.current;
      if (!contact) return null;
      const cards = gridCards(contact, grid);
      if (cards.length === 0) return null;
      const gridRect = grid.getBoundingClientRect();
      const finalBottom = Math.max(
        ...cards.map((card) => card.top + card.height),
      );
      if (rect.top > gridRect.top + finalBottom) return null;
      const viewportCard = (card: GridCard): CourseDragRect => ({
        left: gridRect.left + card.left,
        top: gridRect.top + card.top,
        width: card.width,
        height: card.height,
      });
      const current = targetRef.current;
      const remaining = cards
        .filter((card) => card.id !== contact.courseId)
        .map((card) => card.id);
      // The current slot is an index in the source-excluded list. The same index in the captured
      // source-included cells keeps that slot, and the end of the cells is the append.
      const currentIndex =
        current?.key === (grid.dataset.structureGrid ?? "")
          ? current.beforeCourseId === null
            ? cards.length
            : remaining.indexOf(current.beforeCourseId)
          : -1;
      let index = -1;
      let bestArea = 0;
      for (let position = 0; position < cards.length; position += 1) {
        const area = intersectionArea(viewportCard(cards[position]), rect);
        if (area > bestArea + 0.5) {
          bestArea = area;
          index = position;
        } else if (
          area > 0 &&
          Math.abs(area - bestArea) <= 0.5 &&
          position === currentIndex &&
          index !== currentIndex
        )
          index = position;
      }
      if (index < 0) {
        const centreX = rect.left + rect.width / 2;
        const centreY = rect.top + rect.height / 2;
        let nearest = Number.POSITIVE_INFINITY;
        for (let position = 0; position < cards.length; position += 1) {
          const card = cards[position];
          const distance = Math.hypot(
            gridRect.left + card.left + card.width / 2 - centreX,
            gridRect.top + card.top + card.height / 2 - centreY,
          );
          if (distance < nearest) {
            nearest = distance;
            index = position;
          }
        }
      }
      return remaining[index] ?? null;
    },
    [],
  );

  /** Return the displayed holder and slot of greatest positive overlap with the lifted card. */
  const hitTest = useCallback(
    (rect: CourseDragRect): CourseDragTarget | null => {
      const tree = treeRef.current;
      if (!tree) return null;
      const grids = new Map(
        [...tree.querySelectorAll<HTMLElement>("[data-structure-grid]")].map(
          (element) => [element.dataset.structureGrid ?? "", element],
        ),
      );
      const headers = new Map(
        [...tree.querySelectorAll<HTMLElement>("[data-structure-header]")].map(
          (element) => [element.dataset.structureHeader ?? "", element],
        ),
      );
      const list = holdersRef.current;
      let best: {
        key: string;
        area: number;
        grid: HTMLElement | null;
        header: boolean;
        open: boolean;
      } | null = null;
      for (const holder of list) {
        const key = holder.key;
        const grid = grids.get(key);
        const header = headers.get(key);
        // A collapsed holder draws no grid, so its row header is the append target and reveals
        // the body only while the preview names it.
        const gridOpen = grid
          ? grid.closest(".disclosure")?.classList.contains("open") === true
          : false;
        const gridArea =
          gridOpen && grid
            ? intersectionArea(grid.getBoundingClientRect(), rect)
            : 0;
        const headerArea = header
          ? intersectionArea(header.getBoundingClientRect(), rect)
          : 0;
        const area = gridArea + headerArea;
        if (area <= 0) continue;
        const current = targetRef.current;
        if (
          !best ||
          area > best.area + 0.5 ||
          (Math.abs(area - best.area) <= 0.5 && current?.key === key)
        )
          best = {
            key,
            area,
            grid: gridOpen && grid ? grid : null,
            header: headerArea > 0,
            open: gridOpen,
          };
      }
      if (!best) return null;
      // A collapsed header appends, and the same holder keeps that append through its reveal.
      if (!best.open && best.header) collapsedAppend.current = best.key;
      else if (collapsedAppend.current !== best.key)
        collapsedAppend.current = null;
      const keepsAppend = collapsedAppend.current === best.key && best.header;
      return {
        key: best.key,
        beforeCourseId:
          keepsAppend || !best.grid ? null : insertionAt(best.grid, rect),
      };
    },
    [insertionAt, treeRef],
  );

  const updateTarget = useCallback(
    (rect: CourseDragRect) => {
      publishTarget(hitTest(rect));
    },
    [hitTest, publishTarget],
  );

  const startScroll = useCallback(
    (pane: HTMLElement) => {
      stopScroll();
      scrollPane.current = pane;
      let last = performance.now();
      const step = (now: number) => {
        const contact = gesture.current;
        if (!contact?.active || scrollPane.current !== pane) {
          scrollFrame.current = null;
          return;
        }
        const delta = Math.min(SCROLL_MAX_FRAME_MS, Math.max(0, now - last));
        last = now;
        const rect = pane.getBoundingClientRect();
        let bottom = rect.bottom;
        const bar = document.querySelector<HTMLElement>(".phone-tabbar");
        if (bar && getComputedStyle(bar).display !== "none") {
          const barRect = bar.getBoundingClientRect();
          if (barRect.bottom > 0 && barRect.top < window.innerHeight)
            bottom = Math.min(bottom, barRect.top);
        }
        const { x, y } = contact;
        let velocity = 0;
        // The band starts inside the pane and saturates outward over adjacent chrome to the
        // viewport edge. The pane's own horizontal span bounds it.
        if (x >= rect.left && x <= rect.right) {
          if (y < rect.top + SCROLL_EDGE)
            velocity =
              -SCROLL_MAX_VELOCITY *
              Math.min(1, (rect.top + SCROLL_EDGE - y) / SCROLL_EDGE);
          else if (y > bottom - SCROLL_EDGE)
            velocity =
              SCROLL_MAX_VELOCITY *
              Math.min(1, (y - (bottom - SCROLL_EDGE)) / SCROLL_EDGE);
        }
        if (velocity !== 0) {
          const max = pane.scrollHeight - pane.clientHeight;
          const next = Math.max(
            0,
            Math.min(max, pane.scrollTop + (velocity * delta) / 1000),
          );
          if (next !== pane.scrollTop) {
            pane.scrollTop = next;
            if (gesture.current === contact) updateTarget(contactRect(contact));
          }
        }
        scrollFrame.current = requestAnimationFrame(step);
      };
      scrollFrame.current = requestAnimationFrame(step);
    },
    [stopScroll, updateTarget],
  );

  const activate = useCallback(
    (contact: Contact) => {
      if (gesture.current !== contact || contact.active) return;
      if (contact.timer !== null) {
        window.clearTimeout(contact.timer);
        contact.timer = null;
      }
      const item = holdersRef.current
        .flatMap((holder) => holder.courses)
        .find((entry) => entry.course.group_id === contact.courseId);
      if (!item) {
        clearGesture();
        return;
      }
      const rect = contact.card.getBoundingClientRect();
      contact.offsetX = contact.x - rect.left;
      contact.offsetY = contact.y - rect.top;
      contact.width = rect.width;
      contact.height = rect.height;
      contact.liftedX = contact.x;
      contact.liftedY = contact.y;
      contact.scrollArmed = false;
      contact.grids.clear();
      // The cards keep the arrangement they hold before the lift hides the source and the preview
      // inserts a ghost, so each logical cell stays fixed for the rest of the gesture.
      const tree = treeRef.current;
      if (tree)
        for (const grid of tree.querySelectorAll<HTMLElement>(
          "[data-structure-grid]",
        )) {
          const key = grid.dataset.structureGrid;
          if (
            key === undefined ||
            grid.closest(".disclosure")?.classList.contains("open") !== true
          )
            continue;
          contact.grids.set(key, measureGridCards(grid, contact.courseId));
        }
      contact.active = true;
      if (bodyFrame.current !== null) {
        cancelAnimationFrame(bodyFrame.current);
        bodyFrame.current = null;
      }
      document.body.classList.add("course-dragging");
      suppressClick.current = true;
      setArmedCourseId(null);
      setActiveCourseId(contact.courseId);
      setLifted({
        course: item,
        left: contact.x - contact.offsetX,
        top: contact.y - contact.offsetY,
        width: contact.width,
        height: contact.height,
      });
      updateTarget(contactRect(contact));
    },
    [clearGesture, treeRef, updateTarget],
  );

  /** Show the pickup cue after the hold, and start the drag on the first movement. */
  const beginHold = useCallback((contact: Contact, holdMs: number) => {
    contact.timer = window.setTimeout(() => {
      contact.timer = null;
      if (gesture.current === contact && !contact.active && !contact.armed) {
        contact.armed = true;
        setArmedCourseId(contact.courseId);
      }
    }, holdMs);
  }, []);

  const finish = useCallback(() => {
    const contact = gesture.current;
    if (!contact) return;
    const from = contact.active ? contactRect(contact) : null;
    const slot = contact.active ? targetRef.current : null;
    let accepted = false;
    if (
      slot &&
      onDropRef.current(contact.courseId, slot.key, slot.beforeCourseId)
    ) {
      // The input change of this accepted write arrives with the event and must not discard it.
      acceptedHandoff.current = true;
      accepted = true;
    }
    if (slot) {
      // A drop that keeps the card where it already is still flies back into its slot.
      setCompletedDrop((previous) => ({
        targetKey: slot.key,
        sequence: (previous?.sequence ?? 0) + 1,
        courseId: contact.courseId,
        from,
      }));
      if (settleFallback.current !== null)
        window.clearTimeout(settleFallback.current);
      settleFallback.current = window.setTimeout(() => {
        settleFallback.current = null;
        discardHandoff();
      }, 800);
    }
    // The lifted visual stays until the destination slot takes the rectangle over.
    clearGesture(false, accepted || slot !== null);
  }, [clearGesture, discardHandoff]);

  const updateContact = useCallback(
    (contact: Contact, x: number, y: number) => {
      contact.x = x;
      contact.y = y;
      setLifted((previous) =>
        previous
          ? {
              ...previous,
              left: x - contact.offsetX,
              top: y - contact.offsetY,
            }
          : previous,
      );
      updateTarget(contactRect(contact));
      // A stationary hold never scrolls. The first movement after the lift arms the one frame
      // loop, which then stays in force across edges and chrome until the gesture ends.
      if (
        !contact.scrollArmed &&
        (x !== contact.liftedX || y !== contact.liftedY)
      ) {
        const pane = contact.card.closest(".tab-pane");
        if (pane instanceof HTMLElement) {
          contact.scrollArmed = true;
          startScroll(pane);
        }
      }
    },
    [startScroll, updateTarget],
  );

  const startPointer = useCallback(
    (courseId: string, card: HTMLElement, event: PointerEvent) => {
      if (!enabledRef.current || gesture.current) return;
      if (event.pointerType === "touch" || event.button !== 0) return;
      discardHandoff();
      const contact: Contact = {
        courseId,
        card,
        pointerId: event.pointerId,
        touchId: null,
        startX: event.clientX,
        startY: event.clientY,
        x: event.clientX,
        y: event.clientY,
        offsetX: 0,
        offsetY: 0,
        width: 0,
        height: 0,
        active: false,
        armed: false,
        timer: null,
        pointerCleanup: null,
        touchMove: null,
        touchEnd: null,
        grids: new Map(),
        liftedX: event.clientX,
        liftedY: event.clientY,
        scrollArmed: false,
      };
      gesture.current = contact;
      const move = (native: PointerEvent) => {
        if (
          gesture.current !== contact ||
          native.pointerId !== contact.pointerId
        )
          return;
        if (!contact.active) {
          // The contact's own coordinate at the lift decides the captured offset, so drift inside
          // the hold tolerance changes no placement.
          contact.x = native.clientX;
          contact.y = native.clientY;
          const travelled = distance(contact, native.clientX, native.clientY);
          if (contact.armed) {
            if (travelled < ARMED_START_TRAVEL) return;
            activate(contact);
            if (!contact.active) return;
          } else if (travelled > DRAG_START_TRAVEL) {
            clearGesture();
            return;
          } else return;
        }
        native.preventDefault();
        updateContact(contact, native.clientX, native.clientY);
      };
      const up = (native: PointerEvent) => {
        if (
          gesture.current !== contact ||
          native.pointerId !== contact.pointerId
        )
          return;
        if (contact.active) finish();
        else clearGesture();
      };
      const cancelPointer = (native: PointerEvent) => {
        if (
          gesture.current !== contact ||
          native.pointerId !== contact.pointerId
        )
          return;
        clearGesture();
      };
      contact.pointerCleanup = () => {
        document.removeEventListener("pointermove", move, true);
        document.removeEventListener("pointerup", up, true);
        document.removeEventListener("pointercancel", cancelPointer, true);
      };
      document.addEventListener("pointermove", move, true);
      document.addEventListener("pointerup", up, true);
      document.addEventListener("pointercancel", cancelPointer, true);
      beginHold(contact, MOUSE_HOLD_MS);
    },
    [beginHold, clearGesture, discardHandoff, finish, updateContact],
  );

  const startTouch = useCallback(
    (event: TouchEvent) => {
      if (!enabledRef.current) return;
      if (gesture.current) {
        clearGesture();
        return;
      }
      if (event.touches.length !== 1) return;
      const touch = event.changedTouches[0];
      if (!touch) return;
      const eligible = eligibleContact(event.target, false);
      if (!eligible) return;
      discardHandoff();
      suppressClick.current = false;
      const contact: Contact = {
        courseId: eligible.courseId,
        card: eligible.card,
        pointerId: null,
        touchId: touch.identifier,
        startX: touch.clientX,
        startY: touch.clientY,
        x: touch.clientX,
        y: touch.clientY,
        offsetX: 0,
        offsetY: 0,
        width: 0,
        height: 0,
        active: false,
        armed: false,
        timer: null,
        pointerCleanup: null,
        touchMove: null,
        touchEnd: null,
        grids: new Map(),
        liftedX: touch.clientX,
        liftedY: touch.clientY,
        scrollArmed: false,
      };
      gesture.current = contact;
      const find = (list: TouchList): Touch | null => {
        for (let index = 0; index < list.length; index += 1)
          if (list[index].identifier === contact.touchId) return list[index];
        return null;
      };
      const move: EventListener = (nativeEvent) => {
        if (gesture.current !== contact) return;
        const native = nativeEvent as TouchEvent;
        const current = find(native.touches);
        if (!current || native.touches.length !== 1) {
          clearGesture();
          return;
        }
        if (!contact.active) {
          // The contact's own coordinate at the lift decides the captured offset, so drift inside
          // the hold tolerance changes no placement.
          contact.x = current.clientX;
          contact.y = current.clientY;
          const travelled = distance(contact, current.clientX, current.clientY);
          if (contact.armed) {
            if (travelled < ARMED_START_TRAVEL) return;
            activate(contact);
            if (!contact.active) return;
          } else if (travelled > DRAG_START_TRAVEL) {
            clearGesture();
            return;
          } else return;
        }
        native.preventDefault();
        updateContact(contact, current.clientX, current.clientY);
      };
      const end: EventListener = (nativeEvent) => {
        if (gesture.current !== contact) return;
        const native = nativeEvent as TouchEvent;
        const finished =
          native.type === "touchend" && find(native.changedTouches);
        if (contact.active && finished) finish();
        else clearGesture();
      };
      contact.touchMove = move;
      contact.touchEnd = end;
      // The lifted row hides the original target, so the contact's move and end ownership sits on
      // the document. The capture move listener can suppress native panning only after the lift.
      document.addEventListener("touchmove", move, {
        capture: true,
        passive: false,
      });
      document.addEventListener("touchend", end, true);
      document.addEventListener("touchcancel", end, true);
      beginHold(contact, TOUCH_HOLD_MS);
    },
    [beginHold, clearGesture, discardHandoff, finish, updateContact],
  );

  // The stable tree receives the touch start, and each contact's move and end listeners sit on
  // the document, so the lifted rendering never detaches their target.
  useEffect(() => {
    const tree = treeRef.current;
    if (!tree) return;
    tree.addEventListener("touchstart", startTouch, { passive: true });
    return () => tree.removeEventListener("touchstart", startTouch);
  }, [enabled, holders.length, inputKey, startTouch, treeRef]);

  useEffect(() => {
    const prevent = (event: Event) => {
      if (gesture.current?.active) event.preventDefault();
    };
    const click = (event: MouseEvent) => {
      if (!suppressClick.current || event.detail === 0) return;
      event.preventDefault();
      event.stopPropagation();
    };
    const pointerDown = () => {
      if (!gesture.current) suppressClick.current = false;
    };
    // A second contact cancels a touch drag anywhere in the document. The activation's click
    // suppression stays set, because the cancelled contact still produces a click.
    const touchStart = (event: TouchEvent) => {
      const contact = gesture.current;
      if (!contact) {
        suppressClick.current = false;
        return;
      }
      if (contact.touchId !== null && event.touches.length > 1) clearGesture();
    };
    document.addEventListener("contextmenu", prevent, true);
    document.addEventListener("click", click, true);
    document.addEventListener("pointerdown", pointerDown, true);
    document.addEventListener("touchstart", touchStart, {
      capture: true,
      passive: true,
    });
    return () => {
      document.removeEventListener("contextmenu", prevent, true);
      document.removeEventListener("click", click, true);
      document.removeEventListener("pointerdown", pointerDown, true);
      document.removeEventListener("touchstart", touchStart, true);
    };
  }, [clearGesture]);

  useEffect(() => {
    const keydown = (event: KeyboardEvent) => {
      if (event.key !== "Escape" || !gesture.current) return;
      event.preventDefault();
      clearGesture();
    };
    const blur = () => {
      if (gesture.current) clearGesture();
    };
    document.addEventListener("keydown", keydown, true);
    window.addEventListener("blur", blur);
    return () => {
      document.removeEventListener("keydown", keydown, true);
      window.removeEventListener("blur", blur);
    };
  }, [clearGesture]);

  useEffect(() => {
    if (!enabled && gesture.current) clearGesture();
    if (!enabled) discardHandoff();
  }, [clearGesture, discardHandoff, enabled]);

  useEffect(() => {
    if (inputKeyRef.current === inputKey) return;
    inputKeyRef.current = inputKey;
    if (gesture.current) clearGesture();
    // The accepted write's own input change carries the handoff. Any other input change discards
    // the completed event and its released geometry, which stops a settle in progress.
    if (acceptedHandoff.current) acceptedHandoff.current = false;
    else discardHandoff();
  }, [clearGesture, discardHandoff, inputKey]);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      clearGesture(true);
      if (settleFallback.current !== null) {
        window.clearTimeout(settleFallback.current);
        settleFallback.current = null;
      }
    };
  }, [clearGesture]);

  const cardProps = useCallback(
    (courseId: string) => ({
      onPointerDownCapture: (event: ReactPointerEvent<HTMLDivElement>) => {
        const eligible = eligibleContact(event.target, true);
        if (!eligible || eligible.courseId !== courseId) return;
        startPointer(courseId, eligible.card, event.nativeEvent);
      },
    }),
    [startPointer],
  );

  /** Mark one completed handoff as taken by its destination, preserving its disclosure metadata. */
  const consumeDrop = useCallback((sequence: number) => {
    setCompletedDrop((previous) =>
      previous && previous.sequence === sequence && previous.from !== null
        ? { ...previous, from: null }
        : previous,
    );
    setLifted(null);
    setSettleTarget(null);
    if (settleFallback.current !== null) {
      window.clearTimeout(settleFallback.current);
      settleFallback.current = null;
    }
  }, []);

  /** Send the lifted card from its release rectangle into the destination slot. */
  const settleDrop = useCallback((slot: CourseDragRect) => {
    setSettleTarget(slot);
  }, []);

  return {
    activeCourseId,
    armedCourseId,
    target,
    cardProps,
    lifted,
    completedDrop,
    consumeDrop,
    settleTarget,
    settleDrop,
  };
}
