/** Pointer-distance guards for course triggers and result lists that act on a click. */
import { useRef } from "react";
import type { MouseEvent, MouseEventHandler, PointerEventHandler } from "react";

function usePointerGuard<T extends HTMLElement>(): {
  onPointerDown: PointerEventHandler<T>;
  onPointerMove: PointerEventHandler<T>;
  onPointerCancel: PointerEventHandler<T>;
  consume: (event: MouseEvent<T>) => boolean;
} {
  const start = useRef<{ x: number; y: number } | null>(null);
  const moved = useRef(false);
  return {
    onPointerDown: (event) => {
      start.current = { x: event.clientX, y: event.clientY };
      moved.current = false;
    },
    onPointerMove: (event) => {
      const origin = start.current;
      if (!origin) return;
      if (Math.hypot(event.clientX - origin.x, event.clientY - origin.y) > 8)
        moved.current = true;
    },
    onPointerCancel: () => {
      if (start.current) moved.current = true;
      start.current = null;
    },
    consume: (event) => {
      // A click with detail 0 has no pointer origin, which includes native keyboard activation.
      if (event.detail === 0) return false;
      start.current = null;
      if (!moved.current) return false;
      moved.current = false;
      event.preventDefault();
      event.stopPropagation();
      return true;
    },
  };
}

/**
 * Return handlers that run `onTap` and suppress a pointer-origin click after movement.
 *
 * A canceled pointer counts as movement, so a scroll that starts on the trigger does not run
 * its click. A click that carries `detail` 0 has no pointer origin, native keyboard activation
 * included, and it runs `onTap` even after a canceled pointer.
 */
export function useTapGuard<T extends HTMLElement>(
  onTap: (event: MouseEvent<T>) => void,
): {
  onPointerDown: PointerEventHandler<T>;
  onPointerMove: PointerEventHandler<T>;
  onPointerCancel: PointerEventHandler<T>;
  onClick: MouseEventHandler<T>;
} {
  const guard = usePointerGuard<T>();
  return {
    onPointerDown: guard.onPointerDown,
    onPointerMove: guard.onPointerMove,
    onPointerCancel: guard.onPointerCancel,
    onClick: (event) => {
      if (guard.consume(event)) return;
      onTap(event);
    },
  };
}

/**
 * Return handlers for a container that suppress the pointer-origin click after movement.
 *
 * A click that carries `detail` 0 has no pointer origin, native keyboard activation included,
 * and it passes through to its own action.
 */
export function useTapGuardCapture<T extends HTMLElement>(): {
  onPointerDown: PointerEventHandler<T>;
  onPointerMove: PointerEventHandler<T>;
  onPointerCancel: PointerEventHandler<T>;
  onClickCapture: MouseEventHandler<T>;
} {
  const guard = usePointerGuard<T>();
  return {
    onPointerDown: guard.onPointerDown,
    onPointerMove: guard.onPointerMove,
    onPointerCancel: guard.onPointerCancel,
    onClickCapture: (event) => {
      guard.consume(event);
    },
  };
}
