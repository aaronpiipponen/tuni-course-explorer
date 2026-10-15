/** Present one active feature pane and retain only exiting content for its transition. */
import type { ReactNode } from "react";
import { motion, useIsPresent } from "framer-motion";
import type { TabId } from "../state/types";

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
  return (
    <motion.section
      data-tab={tab}
      className={isPresent ? "tab-pane" : "tab-pane exiting"}
      aria-hidden={!isPresent}
      inert={!isPresent}
      variants={{
        enter: (travel: -1 | 1 = direction) => ({ x: `${travel * 100}vw` }),
        centre: { x: 0 },
        exit: (travel: -1 | 1 = direction) => ({ x: `${travel * -100}vw` }),
      }}
      initial="enter"
      animate="centre"
      exit="exit"
      transition={{ duration: 0.65, ease: [0.22, 0.8, 0.2, 1] }}
    >
      {children}
    </motion.section>
  );
}
