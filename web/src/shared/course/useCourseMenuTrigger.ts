/** One tap, open-state and reveal lifecycle shared by the course card, tile and list row. */
import { useEffect, useRef } from "react";
import type { ComponentPropsWithoutRef } from "react";
import { useReducedMotion } from "../useReducedMotion";
import { showPhoneTabs } from "../phoneTabs";
import { revealCourseCard } from "./revealCourseCard";
import { useTapGuard } from "./useTapGuard";

/**
 * Return the shared menu trigger handlers for one course surface.
 *
 * A tap on an open menu, or on one that was open at pointer-down, closes it. Otherwise the menu
 * opens and, when the surface names a reveal target, the shared reveal runs on the next frame.
 * Closing runs the reveal cleanup, restores the phone tab bar and calls `onOpenChange`.
 */
export function useCourseMenuTrigger(options: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  phone: boolean;
  /** The element the shared reveal centres, or null when this open needs no reveal. */
  getRevealTarget: (trigger: HTMLButtonElement) => HTMLElement | null;
  /** The scroll container the reveal uses instead of the nearest scrollable ancestor. */
  getRevealContainer?: (trigger: HTMLButtonElement) => HTMLElement | null;
  /** Called after the menu mounts and before the reveal, for a caller that moves its own surface. */
  onMenuOpen?: (target: HTMLElement, menu: HTMLElement) => void;
}): {
  tap: Pick<
    ComponentPropsWithoutRef<"button">,
    "onClick" | "onPointerDown" | "onPointerMove" | "onPointerCancel"
  >;
  changeOpen: (open: boolean) => void;
} {
  const {
    open,
    onOpenChange,
    phone,
    getRevealTarget,
    getRevealContainer,
    onMenuOpen,
  } = options;
  const reducedMotion = useReducedMotion();
  const revealCleanup = useRef<(() => void) | null>(null);
  const menuWasOpen = useRef(false);
  const changeOpen = (next: boolean) => {
    if (!next) {
      revealCleanup.current?.();
      revealCleanup.current = null;
      if (phone) showPhoneTabs();
    }
    onOpenChange(next);
  };
  const tap = useTapGuard<HTMLButtonElement>((event) => {
    if (open || menuWasOpen.current) {
      menuWasOpen.current = false;
      changeOpen(false);
      return;
    }
    menuWasOpen.current = false;
    const trigger = event.currentTarget;
    const target = getRevealTarget(trigger);
    onOpenChange(true);
    if (!target) return;
    requestAnimationFrame(() => {
      if (!target.isConnected) return;
      const menu = document.querySelector<HTMLElement>(".course-menu");
      if (!menu) return;
      onMenuOpen?.(target, menu);
      revealCleanup.current?.();
      revealCleanup.current = revealCourseCard(
        target,
        reducedMotion,
        menu.getBoundingClientRect().top,
        getRevealContainer?.(trigger),
      );
    });
  });
  useEffect(
    () => () => {
      revealCleanup.current?.();
    },
    [],
  );
  return {
    tap: {
      onClick: tap.onClick,
      onPointerDown: (event) => {
        menuWasOpen.current = open;
        tap.onPointerDown(event);
      },
      onPointerMove: tap.onPointerMove,
      onPointerCancel: tap.onPointerCancel,
    },
    changeOpen,
  };
}
