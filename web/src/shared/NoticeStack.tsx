/** Render one tab's notices and lift them above bottom overlays and menus. */
import {
  useCallback,
  useContext,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import {
  AnimatePresence,
  animate,
  motion,
  useIsPresent,
  useMotionValue,
} from "framer-motion";
import type { TabDirection } from "../app/tabSlide";
import { tabSlideTransition, tabSlideVariants } from "../app/tabSlide";
import type { DisplayLanguage, TabId } from "../state/types";
import { NoticeListContext, type Notice } from "./noticeContext";
import { useAction } from "./useAction";
import { useMediaQuery } from "./useMediaQuery";
import { useReducedMotion } from "./useReducedMotion";
import { ErrorNotice } from "./ErrorNotice";
import { useWording } from "./useWording";
import { phoneSurfaceIsClosing } from "./phoneMotion";
import { PHONE_CONTENT_QUERY, PHONE_SHELL_QUERY } from "./viewport";

/** The overlays anchored at the bottom that the notice stack rises above on the phone shell. */
const RAISED_OVERLAYS =
  '.course-menu, .programme-menu, .profile-menu, .phone-sheet, .phone-more-sheet, [role="menu"]';

/** The route and member result panel, which holds the bottom strip of the phone content layout. */
const RESULT_STACK_SELECTOR = ".route-stack";

/** The gap between the notice and the menu or sheet it rises above. */
const OVERLAY_GAP = 8;

/** The minimum-route control, which holds the bottom strip of the phone content layout. */
const ROUTEBOX_SELECTOR = ".routebox";

/** The gap between the notice and the minimum-route control it rises above. */
const ROUTEBOX_GAP = 16;

/** The overlays the notice stack stays above on the z axis, and the modal panels beside it. */
const MODAL_OVERLAYS =
  '.dialog-panel, .help-drawer[data-state="open"], .root-picker.open, .compare-picker-overlay.open';

const OVER_Z = 50;
const ABOVE_SCRIM_Z = 40;
const BASE_Z = 30;

/**
 * The top edge an overlay rests at. A bottom sheet animates its entrance with a transform, so its
 * measured top moves while its laid-out place is already final.
 */
function restingTop(element: HTMLElement): number {
  return element.matches(".phone-sheet, .phone-more-sheet")
    ? element.offsetTop
    : element.getBoundingClientRect().top;
}

/** Whether a modal surface covers nearly the whole window. */
function fullScreen(element: HTMLElement): boolean {
  const box = element.getBoundingClientRect();
  return (
    box.width >= window.innerWidth * 0.9 &&
    box.height >= window.innerHeight * 0.9
  );
}

/** One notice row that steps from one message to the next. */
function NoticeRow({
  notice,
  language,
  reducedMotion,
  runAction,
}: {
  notice: Notice;
  language: DisplayLanguage;
  reducedMotion: boolean;
  runAction(action: () => void): void;
}) {
  const text = notice.text(language);
  const [displayed, setDisplayed] = useState(text);
  const link = notice.link;
  const linkLabel = link?.label(language) ?? "";
  const linkAt = linkLabel ? displayed.indexOf(linkLabel) : -1;
  const toast = useRef<HTMLDivElement>(null);
  const words = useMotionValue(1);
  const run = useRef(0);

  useLayoutEffect(() => {
    if (displayed === text) return;
    const element = toast.current;
    if (!element || reducedMotion) {
      setDisplayed(text);
      return;
    }
    const id = ++run.current;
    const before = element.getBoundingClientRect();
    // Hold the pill at its old box while the old words fade, so the border cannot cross them.
    element.style.width = `${before.width}px`;
    element.style.height = `${before.height}px`;
    void (async () => {
      await animate(words, 0, { duration: 0.08 });
      if (run.current !== id) return;
      setDisplayed(text);
      // Let the changed words commit and lay out, then read the box they need without painting its
      // jump.
      await new Promise<void>((resolve) =>
        requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
      );
      const node = toast.current;
      if (!node || run.current !== id) return;
      node.style.width = "";
      node.style.height = "";
      const after = node.getBoundingClientRect();
      node.style.width = `${before.width}px`;
      node.style.height = `${before.height}px`;
      // The box moves only while no words are visible, so no text is ever cut or overlapped. A
      // pixel-to-pixel transition is used because a natural width cannot be transitioned.
      node.style.transition =
        "width 0.18s cubic-bezier(0.22, 0.8, 0.2, 1), height 0.18s cubic-bezier(0.22, 0.8, 0.2, 1)";
      void node.getBoundingClientRect();
      node.style.width = `${after.width}px`;
      node.style.height = `${after.height}px`;
      await new Promise<void>((resolve) => window.setTimeout(resolve, 200));
      if (run.current !== id) return;
      node.style.transition = "";
      node.style.width = "";
      node.style.height = "";
      await animate(words, 1, { duration: 0.1 });
    })();
  }, [displayed, reducedMotion, text, words]);

  return (
    <motion.div
      className="toast-motion"
      initial={reducedMotion ? false : { opacity: 0, y: 8, height: 0 }}
      animate={{ opacity: 1, y: 0, height: "auto" }}
      exit={{ opacity: 0, y: 8, height: 0 }}
      transition={{
        duration: reducedMotion ? 0 : 0.25,
        ease: [0.22, 0.8, 0.2, 1],
      }}
    >
      <div className="toast" role="status" ref={toast}>
        <div className="toast-text">
          <motion.span className="toast-words" style={{ opacity: words }}>
            {link && linkAt >= 0 ? (
              <>
                {displayed.slice(0, linkAt)}
                <button
                  className="toast-action toast-link"
                  type="button"
                  onClick={() => runAction(link.run)}
                >
                  {linkLabel}
                </button>
                {displayed.slice(linkAt + linkLabel.length)}
              </>
            ) : (
              displayed
            )}
          </motion.span>
          {notice.action && (
            <button
              className="toast-action"
              type="button"
              onClick={() => runAction(notice.action!.run)}
            >
              {notice.action.label(language)}
            </button>
          )}
        </div>
      </div>
    </motion.div>
  );
}

/** Render one tab's notices with their enter and leave motion and their overlay placement. */
export function NoticeStack({
  tab,
  direction,
}: {
  tab: TabId;
  /** The slide of the tab that owns the notices, which the stack rides along. */
  direction?: TabDirection;
}) {
  const notices = useContext(NoticeListContext).filter(
    (notice) => notice.tab === tab,
  );
  const { language } = useWording();
  const { runAction, error } = useAction();
  const reducedMotion = useReducedMotion();
  const phone = useMediaQuery(PHONE_SHELL_QUERY);
  const phoneContent = useMediaQuery(PHONE_CONTENT_QUERY);
  const isPresent = useIsPresent();
  // A stack outside a tab slide (a standalone mount) has no slide to ride.
  const sliding = direction !== undefined;
  const [animating, setAnimating] = useState(false);
  // The measurement reads this during its timers, after the leaving render may have committed.
  const present = useRef(isPresent);
  present.current = isPresent;
  const [placement, setPlacement] = useState<{
    bottom: number | null;
    z: number;
  }>({ bottom: null, z: BASE_Z });
  // The last top of every surface the placement follows, and when one of them last moved. A moving
  // edge is followed frame by frame. A surface that appears or leaves hands over through the one
  // shared transition.
  const tops = useRef(new Map<HTMLElement, number>());
  const lastMove = useRef(0);
  const stack = useRef<HTMLDivElement>(null);

  const measure = useCallback(() => {
    // A stack leaving with its tab keeps the place it had, even when the control that reserved
    // that space has already gone with the pane.
    if (!present.current) return;
    // A surface that is folding away stops holding the notice, and the notice descends in step
    // with it.
    const lifts: number[] = [];
    // The route control and the route result belong to their tab's pane, which may still be
    // sliding out while another tab's stack is on screen.
    const pane = document.querySelector(`.tab-pane[data-tab="${tab}"]`);
    // A result that is folding away has released its space at the start of the fold. The control
    // underneath takes over at once, so the notice starts down with the fold rather than after it.
    const resultClosing = pane
      ? pane.querySelector(".route-panel.closing") !== null
      : false;
    const elements = [
      ...(phone && !phoneSurfaceIsClosing()
        ? [...document.querySelectorAll<HTMLElement>(RAISED_OVERLAYS)].filter(
            (element) => element.getAttribute("data-state") !== "closed",
          )
        : []),
      ...(phoneContent && pane && !resultClosing
        ? [...pane.querySelectorAll<HTMLElement>(RESULT_STACK_SELECTOR)]
        : []),
      ...(phoneContent && pane
        ? [...pane.querySelectorAll<HTMLElement>(ROUTEBOX_SELECTOR)]
        : []),
    ].filter((element) => element.isConnected);
    for (const element of elements)
      lifts.push(
        window.innerHeight -
          restingTop(element) +
          (element.matches(ROUTEBOX_SELECTOR) ? ROUTEBOX_GAP : OVERLAY_GAP),
      );
    // Only the outermost surfaces hold the notice up. A menu inside a sheet is already cleared
    // by that sheet.
    const outermost = elements.filter(
      (element) =>
        element.parentElement?.closest(
          `${RAISED_OVERLAYS}, ${RESULT_STACK_SELECTOR}, ${ROUTEBOX_SELECTOR}`,
        ) === null,
    );
    // An edge that moved belongs to a surface animating its own size, and the notice rides it. The
    // short memory keeps a second measurement in the same frame from dropping the tracking, and a
    // surface that appeared or left produces no moving edge at all.
    const now = performance.now();
    let moved = false;
    const nextTops = new Map<HTMLElement, number>();
    for (const element of outermost) {
      const top = restingTop(element);
      const previous = tops.current.get(element);
      if (previous !== undefined && Math.abs(previous - top) > 1) moved = true;
      nextTops.set(element, top);
    }
    tops.current = nextTops;
    if (moved) lastMove.current = now;
    if (stack.current) {
      const following =
        phone && outermost.length > 0 && now - lastMove.current < 200;
      if (following) stack.current.setAttribute("data-tracking", "true");
      else stack.current.removeAttribute("data-tracking");
    }
    const bottom = lifts.length > 0 ? Math.max(0, ...lifts) : null;
    const modals = [
      ...document.querySelectorAll<HTMLElement>(MODAL_OVERLAYS),
    ].filter((element) => element.isConnected);
    const over =
      modals.some(
        (element) =>
          element.matches(".root-picker.open, .compare-picker-overlay.open") ||
          element.matches('.help-drawer[data-state="open"]'),
      ) || false;
    const full = modals.some(fullScreen);
    // A phone overlay carries its own scrim, so the notice rises above that scrim too instead of
    // dimming behind it.
    const raised = phone && (lifts.length > 0 || modals.length > 0);
    const z =
      over || full
        ? OVER_Z
        : modals.length > 0 || raised
          ? ABOVE_SCRIM_Z
          : BASE_Z;
    setPlacement((current) =>
      current.bottom === bottom && current.z === z ? current : { bottom, z },
    );
  }, [phone, phoneContent, tab]);

  // A notice arrives in the same commit as the control that reserves its space, so the placement
  // is resolved before that notice is painted instead of moving it one frame later.
  useLayoutEffect(() => {
    measure();
  });

  useEffect(() => {
    // With no notice on screen there is nothing to place, and the observer would only read layout
    // on every change the page makes.
    if (notices.length === 0) return;
    // A sheet or menu animates into place over a few frames, so the measurement follows it until
    // the overlay settles instead of reading one interim edge.
    let frame = 0;
    let until = 0;
    const tick = () => {
      measure();
      frame = performance.now() < until ? requestAnimationFrame(tick) : 0;
    };
    const follow = () => {
      until = performance.now() + 450;
      if (frame === 0) frame = requestAnimationFrame(tick);
    };
    follow();
    const observer = new MutationObserver(follow);
    observer.observe(document.body, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ["class", "data-state"],
    });
    window.addEventListener("resize", follow);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", follow);
      if (frame !== 0) cancelAnimationFrame(frame);
    };
  }, [measure, notices.length]);

  return (
    <>
      <motion.div
        ref={stack}
        className="toast-stack"
        variants={sliding ? tabSlideVariants(reducedMotion) : undefined}
        custom={direction}
        initial={sliding ? "enter" : false}
        animate={sliding ? "centre" : undefined}
        exit={sliding ? "exit" : undefined}
        transition={sliding ? tabSlideTransition(reducedMotion) : undefined}
        // A stack leaving with its tab is as unreachable as the pane that is leaving.
        // A stack sliding with its tab keeps its place: a control that appears or leaves with the
        // pane must not glide it vertically while the pane travels sideways.
        data-sliding={isPresent && !animating ? undefined : true}
        onAnimationStart={() => setAnimating(true)}
        onAnimationComplete={() => setAnimating(false)}
        inert={!isPresent}
        aria-hidden={isPresent ? undefined : true}
        style={{
          ...(placement.bottom === null
            ? {}
            : { bottom: `${placement.bottom}px` }),
          zIndex: placement.z,
        }}
      >
        <AnimatePresence>
          {notices.map((notice) => (
            <NoticeRow
              key={notice.id}
              notice={notice}
              language={language}
              reducedMotion={reducedMotion}
              runAction={runAction}
            />
          ))}
        </AnimatePresence>
      </motion.div>
      {error && <ErrorNotice error={error} language={language} />}
    </>
  );
}
