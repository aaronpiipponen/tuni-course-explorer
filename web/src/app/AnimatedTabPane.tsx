/** Present one active feature pane and retain only exiting content for its transition. */
import { useState, type ReactNode } from "react";
import { motion, useIsPresent } from "framer-motion";
import type { TabId } from "../state/types";
import { useReducedMotion } from "../shared/useReducedMotion";
import { PaneSlideContext } from "./paneSlide";
import { tabSlideTransition, tabSlideVariants } from "./tabSlide";

/** Render one tab pane with directional enter and exit motion. */
export function AnimatedTabPane({
  tab,
  direction,
  children,
}: {
  tab: TabId;
  direction: -1 | 1;
  children: ReactNode;
}) {
  const isPresent = useIsPresent();
  const reducedMotion = useReducedMotion();
  const [animating, setAnimating] = useState(false);
  return (
    <motion.section
      data-tab={tab}
      className={isPresent ? "tab-pane" : "tab-pane exiting"}
      aria-hidden={!isPresent}
      inert={!isPresent}
      custom={direction}
      variants={tabSlideVariants(reducedMotion)}
      initial={reducedMotion ? false : "enter"}
      animate="centre"
      exit="exit"
      transition={tabSlideTransition(reducedMotion)}
      onAnimationStart={() => setAnimating(true)}
      onAnimationComplete={() => setAnimating(false)}
    >
      <PaneSlideContext.Provider value={!isPresent || animating}>
        {children}
      </PaneSlideContext.Provider>
    </motion.section>
  );
}
