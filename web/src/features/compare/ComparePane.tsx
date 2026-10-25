/** Compare composition: persisted unique slots, transient requests and an accessible floating picker. */
import { useEffect, useRef, useState } from "react";
import type { CatalogueCourse } from "../../api/types";
import { useProfileSelector } from "../../state/useProfileSelector";
import { useAction } from "../../shared/useAction";
import { ErrorNotice } from "../../shared/ErrorNotice";
import { useWording } from "../../shared/useWording";
import { useCourseSummaries } from "../../shared/course/useCourseSummaries";
import { removeComparisonSlot, replaceComparisonSlot } from "./actions";
import { CompareSlot } from "./CompareSlot";
import { ComparePicker } from "./ComparePicker";
import { ComparisonResults } from "./ComparisonResults";
import { useComparison } from "./useComparison";
import { usePhoneTabsOnClose } from "../../shared/usePhoneTabsOnClose";

/** Render the comparison slots, picker and backend comparison result. */
export function ComparePane() {
  const { store, value: slots } = useProfileSelector(
    (state) => state.compare.slots,
  );
  const summaryA = useCourseSummaries(slots[0] ? [slots[0]] : []);
  const summaryB = useCourseSummaries(slots[1] ? [slots[1]] : []);
  const slotSummaries = [summaryA, summaryB] as const;
  const hydrationError = summaryA.error ?? summaryB.error;
  const { report, loading, error } = useComparison(slots);
  const { runAction, error: actionError } = useAction();
  const { language, t } = useWording();
  const [target, setTarget] = useState<0 | 1 | null>(null);
  usePhoneTabsOnClose(target !== null);
  const wrapperRefs = useRef<(HTMLDivElement | null)[]>([]);
  const opener = useRef<HTMLElement | null>(null);
  const pendingFocus = useRef<0 | 1 | null>(null);
  const openPicker = (slot: 0 | 1, element: HTMLElement) => {
    opener.current = element;
    setTarget(slot);
  };
  const closePicker = (restoreFocus = true) => {
    setTarget(null);
    if (restoreFocus) requestAnimationFrame(() => opener.current?.focus());
  };
  const pick = (course: CatalogueCourse) => {
    const current = target;
    if (current === null) return;
    runAction(() => replaceComparisonSlot(store, course.group_id, current));
    pendingFocus.current = current;
    closePicker(false);
  };
  useEffect(() => {
    if (pendingFocus.current === null) return;
    const slot = pendingFocus.current;
    const trigger =
      wrapperRefs.current[slot]?.querySelector<HTMLElement>(".course-card");
    if (trigger) {
      trigger.focus();
      pendingFocus.current = null;
    }
  }, [slotSummaries[0].courses, slotSummaries[1].courses, slots]);
  useEffect(() => {
    if (target === null) return;
    const outside = (event: PointerEvent) => {
      if (
        event.target instanceof Element &&
        event.target.closest(".language-control")
      )
        return;
      const picker = document.querySelector(".compare-picker-panel");
      const slotsElement = document.querySelector(".compare-slots");
      if (
        event.target instanceof Node &&
        !picker?.contains(event.target) &&
        !slotsElement?.contains(event.target)
      )
        closePicker(false);
    };
    const keydown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.stopPropagation();
        closePicker(true);
      }
      if (event.key === "ArrowLeft" || event.key === "ArrowRight")
        event.stopImmediatePropagation();
    };
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", keydown, true);
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("keydown", keydown, true);
    };
  }, [target]);
  return (
    <main
      className="pane-content compare-pane"
      role="tabpanel"
      aria-label={t("Compare")}
    >
      <div
        className="compare-main"
        data-picker-open={target !== null || undefined}
      >
        <div className="compare-slots" inert={target !== null}>
          {([0, 1] as const).map((slot) => {
            const id = slots[slot];
            const summary = slotSummaries[slot];
            const course = id
              ? (summary.courses.find((item) => item.group_id === id) ?? null)
              : null;
            return (
              <div
                key={slot}
                data-slot={slot}
                ref={(element) => {
                  wrapperRefs.current[slot] = element;
                }}
              >
                <CompareSlot
                  slot={slot}
                  occupied={id !== null}
                  course={course}
                  loading={id !== null && summary.loading && course === null}
                  targeted={target === slot}
                  onChoose={(element) => openPicker(slot, element)}
                  onRemove={() => {
                    runAction(() => removeComparisonSlot(store, slot));
                    setTarget(null);
                  }}
                />
              </div>
            );
          })}
        </div>
        <div className="compare-picker-anchor">
          <ComparePicker
            target={target}
            onClose={() => closePicker(true)}
            onPick={pick}
          />
        </div>
        {(hydrationError || error || actionError) && (
          <ErrorNotice
            error={hydrationError ?? error ?? actionError!}
            language={language}
          />
        )}
        <ComparisonResults report={report} loading={loading} />
      </div>
    </main>
  );
}
