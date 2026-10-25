/** The shared test for an Escape key event that no nested layer has consumed. */
export function isUnhandledEscape(event: KeyboardEvent): boolean {
  return event.key === "Escape" && !event.defaultPrevented;
}
