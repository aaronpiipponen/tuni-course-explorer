/** Hide or restore the phone bottom bar around scrolling and explicit dismissals. */
const HIDDEN_CLASS = "phone-tabs-hidden";
let restoredAt = 0;

/** Hide or show the phone bottom bar. */
export function setPhoneTabsHidden(hidden: boolean): void {
  document.body.classList.toggle(HIDDEN_CLASS, hidden);
}

/** Restore the phone bottom bar after an action that dismisses a surface. */
export function showPhoneTabs(): void {
  setPhoneTabsHidden(false);
  // A following scroll-to-focus must not immediately hide the bar again.
  restoredAt = performance.now() + 500;
}

/** Return whether the bar's restore window suppresses a hide. */
export function phoneTabsHideIsSuppressed(): boolean {
  return performance.now() < restoredAt;
}
