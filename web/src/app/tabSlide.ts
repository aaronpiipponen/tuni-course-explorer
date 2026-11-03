/** The horizontal slide that a tab pane and the notices belonging to that tab share. */
/** The slide direction, -1 for left and 1 for right. */
export type TabDirection = -1 | 1;

const SLIDE_SECONDS = 0.65;
const SLIDE_EASE: [number, number, number, number] = [0.22, 0.8, 0.2, 1];

/** Return the variants that carry a pane and its notices one screen sideways. */
export function tabSlideVariants(reducedMotion: boolean) {
  return reducedMotion
    ? { enter: { x: 0 }, centre: { x: 0 }, exit: { x: 0 } }
    : {
        enter: (travel: TabDirection) => ({ x: `${travel * 100}vw` }),
        centre: { x: 0 },
        exit: (travel: TabDirection) => ({ x: `${travel * -100}vw` }),
      };
}

/** Return the timing of one tab slide, shared so a notice stays on its pane. */
export function tabSlideTransition(reducedMotion: boolean) {
  return reducedMotion
    ? { duration: 0 }
    : { duration: SLIDE_SECONDS, ease: SLIDE_EASE };
}
