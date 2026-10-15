/** Compare composition: persisted unique slots, transient requests and an accessible floating picker. */
import { useEffect, useRef, useState } from "react";
import type { CourseSummary } from "../../api/types";
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

export function ComparePane() {
  const { store, value: slots } = useProfileSelector(
    (state) => state.compare.slots,
  );
  const {
    courses,
    loading: hydrationLoading,
    error: hydrationError,
  } = useCourseSummaries(slots.filter((id): id is string => id !== null));
  const { report, loading, error } = useComparison(slots);
  const { runAction, error: actionError } = useAction();
  const { language, t } = useWording();
  const [target, setTarget] = useState<0 | 1 | null>(null);
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
  const pick = (course: CourseSummary) => {
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
  }, [courses, slots]);
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
  const summaries = new Map(courses.map((course) => [course.group_id, course]));
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
                  course={id ? (summaries.get(id) ?? null) : null}
                  loading={
                    id !== null && hydrationLoading && !summaries.has(id)
                  }
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
