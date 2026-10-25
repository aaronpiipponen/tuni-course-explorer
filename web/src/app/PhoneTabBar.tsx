/** Phone bottom navigation over the served tabs plus the More sheet for the shared controls. */
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactElement,
} from "react";
import { AnimatePresence, motion } from "framer-motion";
import { effectiveTab, visibleTabs } from "./tabs";
import type { TabId } from "../state/types";
import { setActiveTab, useActiveTab } from "./sessionTab";
import { useAction } from "../shared/useAction";
import { useWording } from "../shared/useWording";
import { useWebFeatures } from "./useWebFeatures";
import { ErrorNotice } from "../shared/ErrorNotice";
import { ProfileButton } from "../features/profiles/ProfileButton";
import { LanguageSwitch } from "../shared/LanguageSwitch";
import { DOCS_REPOSITORY_URL } from "../features/docs/registry";
import {
  COMPARE_ICON,
  DISCOVER_ICON,
  GRAPH_ICON,
  MORE_ICON,
  SEARCH_ICON,
  STRUCTURE_ICON,
} from "../shared/icons";
import { AppFooter } from "./AppFooter";
import { useMediaQuery } from "../shared/useMediaQuery";
import { isUnhandledEscape } from "../shared/escape";
import { OVERLAY_SELECTORS, PHONE_SHELL_QUERY } from "../shared/viewport";
import {
  phoneTabsHideIsSuppressed,
  setPhoneTabsHidden,
} from "../shared/phoneTabs";
import { usePhoneTabsOnClose } from "../shared/usePhoneTabsOnClose";
import { useReducedMotion } from "../shared/useReducedMotion";

// A vertical scroll hides the bottom bar after this much travel, and reveals it on upward travel.
const PHONE_TABS_SCROLL_TRAVEL = 6;
const PHONE_TABS_SCROLL_QUIET_MS = 260;

/** Hide the phone bottom bar while a scroll surface moves down, and restore it at the top or on the way up. */
function usePhoneTabsAutoHide(activeTab: TabId) {
  const setHidden = useCallback((hidden: boolean) => {
    setPhoneTabsHidden(hidden);
  }, []);
  useEffect(() => {
    const media = window.matchMedia(PHONE_SHELL_QUERY);
    const lastTop = new WeakMap<Element, number>();
    let quietUntil = 0;
    const onScroll = (event: Event) => {
      if (!media.matches) {
        setHidden(false);
        return;
      }
      const target =
        event.target === document ? document.scrollingElement : event.target;
      if (!(target instanceof HTMLElement)) return;
      const top = Math.max(0, target.scrollTop);
      const previous = lastTop.get(target);
      lastTop.set(target, top);
      if (top <= 0) {
        setHidden(false);
        return;
      }
      if (previous === undefined) return;
      if (top > previous + PHONE_TABS_SCROLL_TRAVEL) {
        if (quietUntil > performance.now() || phoneTabsHideIsSuppressed())
          return;
        // Downward scrolling inside an overlay must not resize that overlay underneath the finger.
        if (
          target instanceof Element &&
          target.closest(OVERLAY_SELECTORS.phoneTabs)
        )
          return;
        // The card reveal scrolls a result under its open menu. The bar stays so the menu keeps the
        // place the reveal measured.
        if (document.querySelector(".course-menu")) return;
        setHidden(true);
        quietUntil = performance.now() + PHONE_TABS_SCROLL_QUIET_MS;
      } else if (top < previous - PHONE_TABS_SCROLL_TRAVEL) {
        setHidden(false);
        quietUntil = performance.now() + PHONE_TABS_SCROLL_QUIET_MS;
      }
    };
    const sync = () => {
      if (!media.matches) setHidden(false);
    };
    document.addEventListener("scroll", onScroll, true);
    media.addEventListener("change", sync);
    return () => {
      document.removeEventListener("scroll", onScroll, true);
      media.removeEventListener("change", sync);
      setHidden(false);
    };
  }, [setHidden]);
  useEffect(() => {
    setHidden(false);
  }, [activeTab, setHidden]);
}

const TAB_ICONS: Record<TabId, ReactElement> = {
  search: SEARCH_ICON,
  compare: COMPARE_ICON,
  prerequisites: GRAPH_ICON,
  discover: DISCOVER_ICON,
  structure: STRUCTURE_ICON,
};

/** Render the phone tab bar and its More sheet. */
export function PhoneTabBar({ openDocs }: { openDocs: () => void }) {
  const storedTab = useActiveTab();
  const { embeddings_enabled } = useWebFeatures();
  const activeTab = effectiveTab(storedTab, embeddings_enabled);
  const { runAction, error } = useAction();
  const { language, t } = useWording();
  const reducedMotion = useReducedMotion();
  usePhoneTabsAutoHide(activeTab);
  const [moreOpen, setMoreOpen] = useState(false);
  const phone = useMediaQuery(PHONE_SHELL_QUERY);
  usePhoneTabsOnClose(moreOpen);
  const moreButtonRef = useRef<HTMLButtonElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const closeMore = useCallback(() => {
    setMoreOpen(false);
    moreButtonRef.current?.focus();
  }, []);
  useEffect(() => {
    if (!phone) setMoreOpen(false);
  }, [phone]);
  useEffect(() => {
    if (!moreOpen) return;
    closeRef.current?.focus();
    const keydown = (event: KeyboardEvent) => {
      if (!isUnhandledEscape(event)) return;
      closeMore();
    };
    document.addEventListener("keydown", keydown);
    return () => document.removeEventListener("keydown", keydown);
  }, [moreOpen, closeMore]);
  return (
    <>
      <nav className="phone-tabbar" aria-label={t("Main navigation")}>
        {visibleTabs(embeddings_enabled).map((tab) => {
          const current = tab.id === activeTab;
          return (
            <button
              key={tab.id}
              type="button"
              className={current ? "phone-tab active" : "phone-tab"}
              aria-label={t(tab.labelKey)}
              aria-current={current ? "page" : undefined}
              onClick={() => {
                setMoreOpen(false);
                runAction(() => setActiveTab(tab.id));
              }}
            >
              {TAB_ICONS[tab.id]}
              <span>{t(tab.phoneLabelKey)}</span>
            </button>
          );
        })}
        <button
          ref={moreButtonRef}
          type="button"
          className="phone-tab"
          aria-expanded={moreOpen}
          onClick={() => setMoreOpen(!moreOpen)}
        >
          {MORE_ICON}
          <span>{t("More")}</span>
        </button>
      </nav>
      {error && (
        <div className="phone-tabbar-error">
          <ErrorNotice error={error} language={language} />
        </div>
      )}
      <AnimatePresence>
        {moreOpen && (
          <motion.div
            key="more-scrim"
            className="phone-more-scrim"
            aria-hidden="true"
            onClick={closeMore}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: reducedMotion ? 0 : 0.16 }}
          />
        )}
        {moreOpen && (
          <motion.section
            key="more-sheet"
            className="phone-more-sheet"
            role="dialog"
            aria-label={t("More")}
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 24 }}
            transition={{
              duration: reducedMotion ? 0 : 0.22,
              ease: [0.22, 0.8, 0.2, 1],
            }}
          >
            <header className="phone-more-head">
              <b>{t("More")}</b>
              <button
                ref={closeRef}
                className="pill-btn"
                type="button"
                onClick={closeMore}
              >
                {t("Close")}
              </button>
            </header>
            <div className="phone-more-row">
              <ProfileButton onClosedEscape={closeMore} />
            </div>
            <div className="phone-more-secondary">
              <div className="phone-more-secondary-inner">
                <div className="phone-more-row phone-more-utilities">
                  <LanguageSwitch />
                  <a
                    className="phone-more-docs"
                    href="/docs"
                    onClick={(event) => {
                      event.preventDefault();
                      closeMore();
                      openDocs();
                    }}
                  >
                    {t("Docs")}
                  </a>
                </div>
                <AppFooter repositoryUrl={DOCS_REPOSITORY_URL} />
              </div>
            </div>
          </motion.section>
        )}
      </AnimatePresence>
    </>
  );
}
