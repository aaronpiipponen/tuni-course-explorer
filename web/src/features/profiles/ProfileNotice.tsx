/** Animated presentation wrapper for the transient notices of the profile menu. */
import { motion } from "framer-motion";
import type { ReactNode } from "react";
import { useReducedMotion } from "../../shared/useReducedMotion";

/** The lifetime of one profile notice, in milliseconds. */
export const PROFILE_NOTICE_MS = 5000;

/**
 * Draw one profile notice, animating its height and opacity around the supplied content.
 *
 * The wrapper owns presentation alone. It holds the content through the exit animation, and it
 * draws the content at once under the operating system's reduced-motion preference.
 */
export function ProfileNotice({ children }: { children: ReactNode }) {
  const reducedMotion = useReducedMotion();
  return (
    <motion.div
      className="profile-notice-motion"
      initial={reducedMotion ? false : { opacity: 0, height: 0 }}
      animate={{ opacity: 1, height: "auto" }}
      exit={{ opacity: 0, height: 0 }}
      transition={{
        duration: reducedMotion ? 0 : 0.3,
        ease: [0.22, 0.8, 0.2, 1],
      }}
    >
      {children}
    </motion.div>
  );
}
