/** One virtualized contiguous search tier with logical focus and interaction pinning. */
import {
  forwardRef,
  useCallback,
  useImperativeHandle,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { defaultRangeExtractor, useVirtualizer } from "@tanstack/react-virtual";
import type { KeyboardEvent, Ref } from "react";
import type { SearchMethod, UnifiedCourseSearchResult } from "../../api/types";
import { CourseCard } from "../../shared/course/CourseCard";

export type SearchTierListHandle = {
  focusCourse: (index: number, lastControl: boolean) => void;
  count: number;
};
export type SearchTierListProps = {
  method: SearchMethod;
  results: readonly UnifiedCourseSearchResult[];
  scrollElement: HTMLElement | null;
  onBoundaryFocus: (direction: -1 | 1) => boolean;
  ref?: Ref<SearchTierListHandle>;
};

function SearchTierListView({
  method,
  results,
  scrollElement,
  onBoundaryFocus,
  ref,
}: SearchTierListProps) {
  const listRef = useRef<HTMLDivElement>(null);
  const [listOffset, setListOffset] = useState(0);
  const [rowHeight, setRowHeight] = useState(38);
  const [focusedIndex, setFocusedIndex] = useState<number | null>(null);
  const [interactionIndex, setInteractionIndex] = useState<number | null>(null);
  const pendingFocus = useRef<{ index: number; lastControl: boolean } | null>(
    null,
  );
  const pinned = useMemo(
    () =>
      [focusedIndex, interactionIndex].filter(
        (value): value is number => value !== null,
      ),
    [focusedIndex, interactionIndex],
  );
  const rangeExtractor = useCallback(
    (range: Parameters<typeof defaultRangeExtractor>[0]) =>
      [...new Set([...defaultRangeExtractor(range), ...pinned])].sort(
        (left, right) => left - right,
      ),
    [pinned],
  );
  const virtualizer = useVirtualizer<HTMLElement, HTMLDivElement>({
    count: results.length,
    getScrollElement: () => scrollElement,
    estimateSize: () => rowHeight,
    getItemKey: (index) => results[index].course.group_id,
    overscan: 3,
    scrollMargin: listOffset,
    rangeExtractor,
    useFlushSync: false,
  });
  const virtualItems = virtualizer.getVirtualItems();
  const focusCourse = useCallback(
    (index: number, lastControl: boolean) => {
      pendingFocus.current = { index, lastControl };
      setFocusedIndex(index);
      virtualizer.scrollToIndex(index, { align: "auto" });
    },
    [virtualizer],
  );
  useImperativeHandle(ref, () => ({ focusCourse, count: results.length }), [
    focusCourse,
    results.length,
  ]);
  const observeGeometry = useCallback(() => {
    if (!scrollElement || !listRef.current) return;
    const paneRect = scrollElement.getBoundingClientRect();
    const listRect = listRef.current.getBoundingClientRect();
    const offset = listRect.top - paneRect.top + scrollElement.scrollTop;
    const card =
      listRef.current.querySelector<HTMLElement>(".course-card-shell");
    const measured = card
      ? Number.parseFloat(
          getComputedStyle(card).getPropertyValue("--course-row-height"),
        )
      : 38;
    setListOffset(offset);
    if (measured > 0 && measured !== rowHeight) {
      setRowHeight(measured);
      virtualizer.measure();
    }
  }, [scrollElement, rowHeight, virtualizer]);
  useLayoutEffect(() => {
    observeGeometry();
    if (!scrollElement) return;
    const observer = new ResizeObserver(observeGeometry);
    observer.observe(scrollElement);
    if (listRef.current) observer.observe(listRef.current);
    return () => observer.disconnect();
  }, [observeGeometry, scrollElement]);
  const focusBoundary = useCallback(
    (event: KeyboardEvent<HTMLDivElement>, index: number) => {
      const direction = event.shiftKey ? -1 : 1;
      const adjacent = index + direction;
      const controls =
        event.currentTarget.querySelectorAll<HTMLElement>("button, a[href]");
      const active = document.activeElement;
      const atBoundary = event.shiftKey
        ? controls.item(0) === active
        : controls.item(controls.length - 1) === active;
      if (event.key !== "Tab" || !atBoundary) return;
      if (adjacent < 0 || adjacent >= results.length) {
        setFocusedIndex(null);
        if (focusedIndex === index && onBoundaryFocus(direction as -1 | 1))
          event.preventDefault();
        return;
      }
      if (!virtualItems.some((item) => item.index === adjacent)) {
        event.preventDefault();
        focusCourse(adjacent, direction < 0);
      }
    },
    [results.length, virtualItems, focusedIndex, onBoundaryFocus, focusCourse],
  );
  const completePendingFocus = useCallback((element: HTMLDivElement | null) => {
    if (!element || !pendingFocus.current) return;
    const { index, lastControl } = pendingFocus.current;
    if (Number(element.dataset.index) !== index) return;
    const controls = element.querySelectorAll<HTMLElement>("button, a[href]");
    (lastControl
      ? controls.item(controls.length - 1)
      : controls.item(0)
    )?.focus();
    pendingFocus.current = null;
  }, []);

  return (
    <div
      className="list search-list search-virtual-list"
      role="list"
      ref={listRef}
      data-method={method}
      style={{ height: virtualizer.getTotalSize(), position: "relative" }}
    >
      {virtualItems.map((item) => {
        const result = results[item.index];
        return (
          <div
            key={item.key}
            ref={(element) => {
              virtualizer.measureElement(element);
              completePendingFocus(element);
            }}
            data-index={item.index}
            role="listitem"
            aria-posinset={item.index + 1}
            aria-setsize={results.length}
            className="search-virtual-row"
            data-course-id={result.course.group_id}
            style={{
              position: "absolute",
              top: 0,
              left: 0,
              right: 0,
              transform: `translateY(${item.start - listOffset}px)`,
            }}
            onFocus={() => setFocusedIndex(item.index)}
            onBlur={(event) => {
              if (
                !event.currentTarget.contains(
                  event.relatedTarget as Node | null,
                )
              )
                setFocusedIndex(null);
            }}
            onKeyDown={(event) => focusBoundary(event, item.index)}
          >
            <CourseCard
              course={result.course}
              matchSources={result.match_sources}
              isFirst={item.index === 0}
              isLast={item.index === results.length - 1}
              onInteractionChange={(active) =>
                setInteractionIndex(active ? item.index : null)
              }
            />
          </div>
        );
      })}
    </div>
  );
}

export const SearchTierList = forwardRef<
  SearchTierListHandle,
  Omit<SearchTierListProps, "ref">
>((props, ref) => <SearchTierListView {...props} ref={ref} />);
