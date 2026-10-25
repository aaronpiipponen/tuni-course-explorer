/** Present one active feature pane and retain only exiting content for its transition. */
import type { ReactNode } from "react";
import { motion, useIsPresent } from "framer-motion";
import type { TabId } from "../state/types";
import { useReducedMotion } from "../shared/useReducedMotion";

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
  return (
    <motion.section
      data-tab={tab}
      className={isPresent ? "tab-pane" : "tab-pane exiting"}
      aria-hidden={!isPresent}
      inert={!isPresent}
      variants={
        reducedMotion
          ? { enter: { x: 0 }, centre: { x: 0 }, exit: { x: 0 } }
          : {
              enter: (travel: -1 | 1 = direction) => ({
                x: `${travel * 100}vw`,
              }),
              centre: { x: 0 },
              exit: (travel: -1 | 1 = direction) => ({
                x: `${travel * -100}vw`,
              }),
            }
      }
      initial={reducedMotion ? false : "enter"}
      animate="centre"
      exit="exit"
      transition={
        reducedMotion
          ? { duration: 0 }
          : { duration: 0.65, ease: [0.22, 0.8, 0.2, 1] }
      }
    >
      {children}
    </motion.section>
  );
}
