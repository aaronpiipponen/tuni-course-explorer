/** Floating official substring picker using the shared course-card selection path. */
import type { CourseSummary } from "../../api/types";
import { useProfileSelector } from "../../state/useProfileSelector";
import { setComparePickerActiveOnly, setComparePickerQuery } from "./actions";
import { CourseLookupBox } from "../../shared/course/CourseLookupBox";
import { courseName } from "../../shared/course/presentation";
import { useWording } from "../../shared/useWording";

export function ComparePicker({
  target,
  onClose,
  onPick,
}: {
  target: 0 | 1 | null;
  onClose: () => void;
  onPick: (course: CourseSummary) => void;
}) {
  const open = target !== null;
  const { store, value: query } = useProfileSelector(
    (state) => state.compare.pickerQuery,
  );
  const { store: activityStore, value: activeOnly } = useProfileSelector(
    (state) => state.compare.pickerActiveOnly,
  );
  const { language, t } = useWording();
  return (
    <div
      className={`compare-picker-overlay${open ? " open" : ""}`}
      aria-hidden={!open}
      inert={!open}
    >
      <section
        className="compare-picker-panel"
        aria-label={t("Compare course picker")}
      >
        <div className="compare-picker-top">
          <span className="compare-eyebrow">
            // {t("choose course {slot}", { slot: target === 0 ? "A" : "B" })}
          </span>
          <button className="pill-btn" type="button" onClick={onClose}>
            {t("Close")}
          </button>
        </div>
        <CourseLookupBox
          open={open}
          query={query}
          onQuery={(value) => setComparePickerQuery(store, value)}
          activeOnly={activeOnly}
          onActiveOnly={(value) =>
            setComparePickerActiveOnly(activityStore, value)
          }
          pick={(course) => ({
            onPick: () => onPick(course),
            text: t("+ add"),
            ariaLabel: t("Add {code} {name} to comparison", {
              code: course.code,
              name: courseName(course, language),
            }),
          })}
        />
      </section>
    </div>
  );
}
