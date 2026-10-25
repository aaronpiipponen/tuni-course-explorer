/**
 * The two width breakpoints of the phone layout.
 *
 * `PHONE_SHELL_QUERY` selects the phone shell. `PHONE_CONTENT_QUERY` selects the phone layout
 * of the tab content: the prerequisite drawing and its pane, the Search and Discover panes, and
 * the course card, tile and list row.
 */
export const PHONE_SHELL_QUERY = "(max-width: 760px)";
/**
 * The tab-content breakpoint that selects the phone layout of the prerequisite, Search and
 * Discover panes and the course card, tile and list row.
 */
export const PHONE_CONTENT_QUERY = "(max-width: 680px)";

const OVERLAY_COMMON =
  '.route-stack, .sdrawer, .help-drawer, .root-picker, .compare-picker-overlay, .profile-menu, [role="dialog"], [role="menu"]';

/**
 * The overlay vocabulary of the phone shell.
 *
 * `swipeIgnore` marks the surfaces that keep a touch gesture away from the tab ring, `phoneTabs`
 * adds the bottom-bar sheets and the course sheet to that set for the bar's own overlay checks,
 * and `blocking` is the open-state selection that stops a swipe.
 */
export const OVERLAY_SELECTORS = {
  swipeIgnore: `${OVERLAY_COMMON}, button:not(.course-card):not(.discover-result-row):not(.tile-trigger), a, input, textarea, select, [contenteditable], [role="slider"], .graph-panel, .root-picker-scrim`,
  phoneTabs: `${OVERLAY_COMMON}, .phone-sheet, .phone-more-sheet, .course-menu`,
  blocking:
    '.sdrawer.open, .help-drawer[data-state="open"], .root-picker.open, .compare-picker-overlay.open, [role="dialog"], [role="menu"]',
} as const;
