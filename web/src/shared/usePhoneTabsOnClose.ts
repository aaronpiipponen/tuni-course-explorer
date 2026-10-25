/** Restore the phone bottom bar once an overlay that was open has closed. */
import { useEffect, useRef } from "react";
import { showPhoneTabs } from "./phoneTabs";

/**
 * Restore the phone bottom bar when `open` changes from true to false.
 *
 * The first render restores nothing.
 */
export function usePhoneTabsOnClose(open: boolean): void {
  const wasOpen = useRef(open);
  useEffect(() => {
    if (wasOpen.current && !open) showPhoneTabs();
    wasOpen.current = open;
  }, [open]);
}
