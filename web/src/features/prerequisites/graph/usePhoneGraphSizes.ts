/** Phone course and module node heights measured from their rendered roots. */
import { useCallback, useLayoutEffect, useState, type RefObject } from "react";
import { useMediaQuery } from "../../../shared/useMediaQuery";
import { PHONE_CONTENT_QUERY } from "../../../shared/viewport";

const EMPTY_HEIGHTS: ReadonlyMap<string, number> = new Map();

/**
 * Report the phone match and the measured course and module heights of the current content.
 *
 * `contentKey` identifies the rendered node content and owns the measurement map. A new key
 * starts an empty map. `onNodeHeight` keeps one identity for a content key, so every mounted
 * observer reconnects after a content change and republishes an equal height into the new map.
 */
export function usePhoneGraphSizes(contentKey: string): {
  phone: boolean;
  heights: ReadonlyMap<string, number>;
  onNodeHeight: (id: string, height: number) => void;
} {
  const phone = useMediaQuery(PHONE_CONTENT_QUERY);
  const [measurement, setMeasurement] = useState<{
    contentKey: string;
    heights: ReadonlyMap<string, number>;
  } | null>(null);
  const onNodeHeight = useCallback(
    (id: string, height: number) => {
      setMeasurement((current) => {
        if (current !== null && current.contentKey === contentKey) {
          if (current.heights.get(id) === height) return current;
          const heights = new Map(current.heights);
          heights.set(id, height);
          return { contentKey, heights };
        }
        return { contentKey, heights: new Map([[id, height]]) };
      });
    },
    [contentKey],
  );
  const heights =
    phone && measurement !== null && measurement.contentKey === contentKey
      ? measurement.heights
      : EMPTY_HEIGHTS;
  return { phone, heights, onNodeHeight };
}

/**
 * Report the border-box block size of one course or module root on the phone viewport.
 *
 * The observed element sits below the React Flow viewport transform, so the reported size is its
 * own CSS height rather than a zoomed bounding rectangle. The observer disconnects on a mode,
 * identity, callback or unmount change. Modern `ResizeObserver` support is required.
 */
export function useGraphNodeHeight(
  ref: RefObject<HTMLElement | null>,
  phone: boolean,
  id: string,
  onHeight: (id: string, height: number) => void,
): void {
  useLayoutEffect(() => {
    if (!phone) return;
    const element = ref.current;
    if (element === null) return;
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (entry === undefined) return;
      onHeight(id, Math.ceil(entry.borderBoxSize[0].blockSize));
    });
    observer.observe(element, { box: "border-box" });
    return () => observer.disconnect();
  }, [ref, phone, id, onHeight]);
}
