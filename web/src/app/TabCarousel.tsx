/**
 * Animated cyclic carousel over the served tabs with touch swipe navigation, keyboard navigation
 * and inert offscreen panes.
 */
import {
  useEffect,
  useRef,
  useState,
  type ComponentType,
  type MouseEvent,
  type PointerEvent,
} from "react";
import { AnimatePresence } from "framer-motion";
import { setActiveTab, useActiveTab } from "./sessionTab";
import { effectiveTab, visibleTabs } from "./tabs";
import type { TabId } from "../state/types";
import { SearchPane } from "../features/search/SearchPane";
import { SearchSessionProvider } from "../features/search/SearchSession";
import { ComparePane } from "../features/compare/ComparePane";
import { PrerequisitesPane } from "../features/prerequisites/PrerequisitesPane";
import { DiscoverPane } from "../features/discover/DiscoverPane";
import { StructurePane } from "../features/structure/StructurePane";
import { useAction } from "../shared/useAction";
import { ErrorNotice } from "../shared/ErrorNotice";
import { useWording } from "../shared/useWording";
import { useWebFeatures } from "./useWebFeatures";
import { AnimatedTabPane } from "./AnimatedTabPane";
import { useMediaQuery } from "../shared/useMediaQuery";
import { OVERLAY_SELECTORS, PHONE_SHELL_QUERY } from "../shared/viewport";

const PANES: Record<TabId, ComponentType> = {
  search: SearchPane,
  compare: ComparePane,
  prerequisites: PrerequisitesPane,
  discover: DiscoverPane,
  structure: StructurePane,
};

// A touch gesture starts as a swipe only after this much travel and with this horizontal dominance.
const SWIPE_TRAVEL = 8;
const SWIPE_DOMINANCE = 1.5;
// A release travels this far to select the neighbouring tab.
const SWIPE_DISTANCE = 48;

type Swipe = {
  pointerId: number;
  startX: number;
  startY: number;
  horizontal: boolean;
};

/** Render the animated tab carousel and handle keyboard or touch navigation. */
export function TabCarousel() {
  const storedTab = useActiveTab();
  const { embeddings_enabled } = useWebFeatures();
  const activeTab = effectiveTab(storedTab, embeddings_enabled);
  const visible = visibleTabs(embeddings_enabled);
  const { runAction, error } = useAction();
  const { language, t } = useWording();
  const phone = useMediaQuery(PHONE_SHELL_QUERY);
  const active = visible.findIndex((tab) => tab.id === activeTab);
  const Pane = PANES[activeTab];
  const [presentation, setPresentation] = useState({
    tab: activeTab,
    direction: 1 as -1 | 1,
  });
  if (presentation.tab !== activeTab) {
    const previous = visible.findIndex(
      (tab) => tab.id === effectiveTab(presentation.tab, embeddings_enabled),
    );
    const displacement = (active - previous + visible.length) % visible.length;
    const shortest =
      displacement > visible.length / 2
        ? displacement - visible.length
        : displacement;
    setPresentation({ tab: activeTab, direction: shortest < 0 ? -1 : 1 });
  }
  const select = (index: number) =>
    runAction(() =>
      setActiveTab(visible[(index + visible.length) % visible.length].id),
    );
  const swipe = useRef<Swipe | null>(null);
  const committed = useRef(false);
  const releaseSwipe = (target: HTMLDivElement | null) => {
    const current = swipe.current;
    if (current?.horizontal && target?.hasPointerCapture(current.pointerId))
      target.releasePointerCapture(current.pointerId);
    swipe.current = null;
  };
  const startSwipe = (event: PointerEvent<HTMLDivElement>) => {
    committed.current = false;
    if (event.pointerType !== "touch") return;
    if (!phone) {
      releaseSwipe(event.currentTarget);
      return;
    }
    if (swipe.current) {
      releaseSwipe(event.currentTarget);
      return;
    }
    // The tracked touch owns the gesture, so a secondary contact starts nothing.
    if (!event.isPrimary) return;
    const target = event.target;
    if (
      target instanceof Element &&
      target.closest(OVERLAY_SELECTORS.swipeIgnore) !== null
    )
      return;
    if (document.querySelector(OVERLAY_SELECTORS.blocking)) return;
    swipe.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      horizontal: false,
    };
  };
  const moveSwipe = (event: PointerEvent<HTMLDivElement>) => {
    const current = swipe.current;
    if (!current || current.pointerId !== event.pointerId) return;
    if (!phone) {
      releaseSwipe(event.currentTarget);
      return;
    }
    if (current.horizontal) return;
    const dx = event.clientX - current.startX;
    const dy = event.clientY - current.startY;
    if (Math.max(Math.abs(dx), Math.abs(dy)) < SWIPE_TRAVEL) return;
    if (Math.abs(dx) < SWIPE_DOMINANCE * Math.abs(dy)) {
      releaseSwipe(event.currentTarget);
      return;
    }
    current.horizontal = true;
    event.currentTarget.setPointerCapture(event.pointerId);
  };
  const endSwipe = (event: PointerEvent<HTMLDivElement>) => {
    const current = swipe.current;
    if (!current || current.pointerId !== event.pointerId) return;
    const dx = event.clientX - current.startX;
    const dy = event.clientY - current.startY;
    const horizontal = current.horizontal;
    releaseSwipe(event.currentTarget);
    if (
      !horizontal ||
      !phone ||
      document.querySelector(OVERLAY_SELECTORS.blocking)
    )
      return;
    if (
      Math.abs(dx) < SWIPE_DISTANCE ||
      Math.abs(dx) < SWIPE_DOMINANCE * Math.abs(dy)
    )
      return;
    committed.current = true;
    select(active + (dx < 0 ? 1 : -1));
  };
  const cancelSwipe = (event: PointerEvent<HTMLDivElement>) => {
    if (swipe.current?.pointerId === event.pointerId)
      releaseSwipe(event.currentTarget);
  };
  // The release of a committed swipe produces a click on the painted pane, and it selects nothing.
  const suppressClick = (event: MouseEvent<HTMLDivElement>) => {
    if (!committed.current || event.detail === 0) return;
    committed.current = false;
    event.preventDefault();
    event.stopPropagation();
  };
  useEffect(() => {
    const keydown = (event: KeyboardEvent) => {
      if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
      const target = event.target;
      if (
        target instanceof HTMLElement &&
        (target.isContentEditable ||
          ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName))
      )
        return;
      if (document.querySelector('[role="menu"], [role="dialog"]')) return;
      event.preventDefault();
      select(active + (event.key === "ArrowRight" ? 1 : -1));
    };
    window.addEventListener("keydown", keydown);
    return () => window.removeEventListener("keydown", keydown);
  }, [active, visible]);
  return (
    <SearchSessionProvider>
      <section className="carousel-frame" aria-label={t("Course tools")}>
        <div className="carousel">
          <div
            className="carousel-window"
            onPointerDown={startSwipe}
            onPointerMove={moveSwipe}
            onPointerUp={endSwipe}
            onPointerCancel={cancelSwipe}
            // A descendant handing its implicit capture to this window keeps the tracked
            // gesture, so only this window's own capture loss cancels it.
            onLostPointerCapture={(event) => {
              if (event.target === event.currentTarget) cancelSwipe(event);
            }}
            onClickCapture={suppressClick}
          >
            <AnimatePresence initial={false} custom={presentation.direction}>
              <AnimatedTabPane
                key={activeTab}
                tab={activeTab}
                direction={presentation.direction}
              >
                <Pane />
              </AnimatedTabPane>
            </AnimatePresence>
          </div>
        </div>
        <button
          className="carousel-arrow previous"
          type="button"
          aria-label={t("Previous tab")}
          onClick={() => select(active - 1)}
        >
          <svg viewBox="0 0 16 16" aria-hidden="true">
            <path d="M10.15 3.70Q12 2.5 12.00 4.70L12.00 11.30Q12 13.5 10.15 12.30L5.35 9.20Q3.5 8 5.35 6.80Z" />
          </svg>
        </button>
        <button
          className="carousel-arrow next"
          type="button"
          aria-label={t("Next tab")}
          onClick={() => select(active + 1)}
        >
          <svg viewBox="0 0 16 16" aria-hidden="true">
            <path d="M5.85 3.70Q4 2.5 4.00 4.70L4.00 11.30Q4 13.5 5.85 12.30L10.65 9.20Q12.5 8 10.65 6.80Z" />
          </svg>
        </button>
        {error && <ErrorNotice error={error} language={language} />}
      </section>
    </SearchSessionProvider>
  );
}
