/** One measured, keyboard-navigable virtual window over a lookup surface's complete result list. */
import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { defaultRangeExtractor, useVirtualizer } from "@tanstack/react-virtual";
import type {
  FocusEvent,
  HTMLAttributes,
  KeyboardEvent,
  ReactNode,
  RefObject,
} from "react";

const ROW_ESTIMATE = 44;
const OVERSCAN = 3;

const estimateRow = () => ROW_ESTIMATE;

type FocusTarget = { key: string; direction: -1 | 1 };

/**
 * Render every item's row through a measured virtual window.
 *
 * The outer element is the scroll owner unless `scrollElement` supplies an external one, in which
 * case the list is a full-height spacer inside that element and each list measures its own offset.
 * Endpoint rows and the focused row stay mounted, so Tab enters and leaves the list in native DOM
 * order while Tab, Shift+Tab, the arrow keys, Home and End move between logical rows. A surface
 * that supplies `inputRef` gets focus back in that field when a focused row disappears, and a
 * surface with no query field omits it.
 */
export function LookupVirtualList<T>({
  items,
  getItemKey,
  renderRow,
  className,
  resetKey,
  inputRef,
  scrollElement,
  containerProps,
}: {
  items: readonly T[];
  getItemKey(item: T): string;
  renderRow(item: T): ReactNode;
  className: string;
  resetKey: string;
  inputRef?: RefObject<HTMLInputElement | null>;
  scrollElement?: HTMLElement | null;
  containerProps?: HTMLAttributes<HTMLDivElement>;
}) {
  const listRef = useRef<HTMLDivElement>(null);
  const pending = useRef<FocusTarget | null>(null);
  const ownedFocus = useRef(false);
  const previousKeys = useRef<readonly string[]>([]);
  const [focusedKey, setFocusedKey] = useState<string | null>(null);
  const [scrollMargin, setScrollMargin] = useState(0);
  const keys = useMemo(() => items.map(getItemKey), [items, getItemKey]);
  const indexByKey = useMemo(
    () => new Map(keys.map((key, index) => [key, index])),
    [keys],
  );
  const focusedIndex =
    focusedKey === null ? -1 : (indexByKey.get(focusedKey) ?? -1);
  const offset = scrollElement ? scrollMargin : 0;
  const rangeExtractor = useCallback(
    (range: Parameters<typeof defaultRangeExtractor>[0]) => {
      const pinned = [0, items.length - 1, focusedIndex].filter(
        (index) => index >= 0 && index < items.length,
      );
      return [...new Set([...defaultRangeExtractor(range), ...pinned])].sort(
        (left, right) => left - right,
      );
    },
    [focusedIndex, items.length],
  );
  // A stable key reader and scroll owner let the virtualizer keep its measured index map across a
  // scroll render.
  const itemKey = useCallback((index: number) => keys[index], [keys]);
  const scrollOwner = useCallback(
    () => scrollElement ?? listRef.current,
    [scrollElement],
  );
  const virtualizer = useVirtualizer<HTMLElement, HTMLDivElement>({
    count: items.length,
    getScrollElement: scrollOwner,
    getItemKey: itemKey,
    estimateSize: estimateRow,
    overscan: OVERSCAN,
    scrollMargin: offset,
    rangeExtractor,
    useFlushSync: false,
  });
  const virtualItems = virtualizer.getVirtualItems();
  const buttonAt = useCallback(
    (index: number) =>
      listRef.current?.querySelector<HTMLButtonElement>(
        `.lookup-virtual-row[data-index="${index}"] button`,
      ) ?? null,
    [],
  );
  const isDisabled = useCallback(
    (index: number) => buttonAt(index)?.disabled ?? false,
    [buttonAt],
  );
  const firstEnabled = useCallback(
    (direction: -1 | 1) => {
      for (
        let index = direction > 0 ? 0 : items.length - 1;
        index >= 0 && index < items.length;
        index += direction
      )
        if (!isDisabled(index)) return index;
      return null;
    },
    [isDisabled, items.length],
  );
  const adjacentEnabled = useCallback(
    (index: number, direction: -1 | 1) => {
      for (
        let candidate = index + direction;
        candidate >= 0 && candidate < items.length;
        candidate += direction
      )
        if (!isDisabled(candidate)) return candidate;
      return null;
    },
    [isDisabled, items.length],
  );
  /**
   * Scroll the focused row into the visible part of its scroll owner.
   *
   * A measured row start and end is an offset in the owner's scroll coordinates because the
   * measurement includes `scrollMargin`, so both bounds compare against `scrollTop` directly
   * and the absolute offset stays clamped to the owner.
   */
  const scrollRowIntoView = useCallback(
    (index: number) => {
      const owner = scrollElement ?? listRef.current;
      if (!owner) return;
      // Read fresh measurements so a row measured since the last render scrolls by its own size.
      virtualizer.getVirtualItems();
      const item = virtualizer.measurementsCache[index];
      if (!item) return;
      if (item.start < owner.scrollTop) {
        virtualizer.scrollToOffset(item.start, { align: "start" });
      } else if (item.end > owner.scrollTop + owner.clientHeight) {
        virtualizer.scrollToOffset(item.end - owner.clientHeight, {
          align: "start",
        });
      }
    },
    [scrollElement, virtualizer],
  );
  const requestFocus = useCallback(
    (index: number, direction: -1 | 1) => {
      const key = keys[index];
      if (key === undefined) return;
      pending.current = { key, direction };
      setFocusedKey(key);
      scrollRowIntoView(index);
    },
    [keys, scrollRowIntoView],
  );
  useLayoutEffect(() => {
    const waiting = pending.current;
    if (waiting === null) return;
    const index = indexByKey.get(waiting.key);
    if (index === undefined) {
      pending.current = null;
      return;
    }
    const button = buttonAt(index);
    if (button === null) return;
    if (button.disabled) {
      const next = adjacentEnabled(index, waiting.direction);
      if (next === null) {
        pending.current = null;
        return;
      }
      pending.current = { key: keys[next], direction: waiting.direction };
      setFocusedKey(keys[next]);
      scrollRowIntoView(next);
      return;
    }
    pending.current = null;
    button.focus();
  });
  const observeGeometry = useCallback(() => {
    const owner = scrollElement;
    const list = listRef.current;
    if (!owner || !list) return;
    const ownerRect = owner.getBoundingClientRect();
    const listRect = list.getBoundingClientRect();
    const next = listRect.top - ownerRect.top + owner.scrollTop;
    setScrollMargin((previous) =>
      Math.abs(previous - next) < 0.5 ? previous : next,
    );
  }, [scrollElement]);
  useLayoutEffect(() => {
    const owner = scrollElement;
    const list = listRef.current;
    if (!owner || !list) return;
    observeGeometry();
    const observer = new ResizeObserver(observeGeometry);
    observer.observe(owner);
    observer.observe(list);
    return () => observer.disconnect();
  }, [items, observeGeometry, resetKey, scrollElement]);
  useEffect(() => {
    pending.current = null;
    setFocusedKey(null);
    const owner = scrollElement ?? listRef.current;
    if (owner) owner.scrollTop = 0;
  }, [resetKey, scrollElement]);
  useEffect(() => {
    const keysChanged = keys !== previousKeys.current;
    previousKeys.current = keys;
    if (!keysChanged || focusedKey === null || indexByKey.has(focusedKey))
      return;
    pending.current = null;
    setFocusedKey(null);
    if (ownedFocus.current) {
      ownedFocus.current = false;
      inputRef?.current?.focus();
    }
  }, [focusedKey, indexByKey, inputRef, keys]);
  useEffect(
    () => () => {
      pending.current = null;
    },
    [],
  );
  const handleFocus = (index: number) => {
    ownedFocus.current = true;
    setFocusedKey(keys[index]);
    if (index === 0 || index === items.length - 1) scrollRowIntoView(index);
  };
  const handleBlur = (event: FocusEvent<HTMLDivElement>) => {
    if (event.currentTarget.contains(event.relatedTarget as Node | null))
      return;
    ownedFocus.current = false;
    setFocusedKey(null);
  };
  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const target =
      event.target instanceof Element
        ? event.target.closest<HTMLElement>(".lookup-virtual-row")
        : null;
    if (!target || !event.currentTarget.contains(target)) return;
    const index = Number(target.dataset.index);
    if (!Number.isInteger(index)) return;
    if (event.key === "Home" || event.key === "End") {
      const direction = event.key === "Home" ? 1 : -1;
      const next = firstEnabled(direction);
      event.preventDefault();
      event.stopPropagation();
      if (next !== null) requestFocus(next, direction);
      return;
    }
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      const direction = event.key === "ArrowDown" ? 1 : -1;
      const next = adjacentEnabled(index, direction);
      event.preventDefault();
      event.stopPropagation();
      if (next !== null) requestFocus(next, direction);
      return;
    }
    if (event.key !== "Tab") return;
    const direction = event.shiftKey ? -1 : 1;
    const next = adjacentEnabled(index, direction);
    if (next === null) return;
    event.preventDefault();
    event.stopPropagation();
    requestFocus(next, direction);
  };
  return (
    <div
      {...containerProps}
      ref={listRef}
      className={`${className} lookup-virtual-list`}
      role="list"
      onBlur={handleBlur}
      onKeyDown={handleKeyDown}
    >
      <div
        className="lookup-virtual-spacer"
        style={{
          height: Math.max(0, virtualizer.getTotalSize() - offset),
        }}
      >
        {virtualItems.map((item) => (
          <div
            key={item.key}
            ref={(node) => {
              virtualizer.measureElement(node);
            }}
            data-index={item.index}
            data-key={keys[item.index]}
            role="listitem"
            aria-posinset={item.index + 1}
            aria-setsize={items.length}
            className="lookup-virtual-row"
            style={{
              transform: `translateY(${item.start - offset}px)`,
            }}
            onFocus={() => handleFocus(item.index)}
          >
            {renderRow(items[item.index])}
          </div>
        ))}
      </div>
    </div>
  );
}
