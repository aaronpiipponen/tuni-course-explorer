/** One official hydrated comparison slot with persistent replace/remove controls. */
import type { CourseSummary } from "../../api/types";
import { useWording } from "../../shared/useWording";
import { CourseCard } from "../../shared/course/CourseCard";

export function CompareSlot({
  slot,
  occupied,
  course,
  loading,
  targeted,
  onChoose,
  onRemove,
}: {
  slot: 0 | 1;
  occupied: boolean;
  course: CourseSummary | null;
  loading: boolean;
  targeted: boolean;
  onChoose: (element: HTMLElement) => void;
  onRemove: () => void;
}) {
  const { t } = useWording();
  const letter = slot === 0 ? "A" : "B";
  return occupied ? (
    <section
      className={`compare-slot-card${targeted ? " target" : ""}`}
      aria-label={t("Course {slot}", { slot: letter })}
    >
      <div className="compare-slot-actions">
        <button
          className="pill-btn"
          type="button"
          onClick={(event) => onChoose(event.currentTarget)}
        >
          {t("Replace")}
        </button>
        <button className="pill-btn danger" type="button" onClick={onRemove}>
          {t("Remove")}
        </button>
      </div>
      {loading ? (
        <div
          className="compare-slot-skeleton"
          aria-label={t("Loading course {slot}", { slot: letter })}
        />
      ) : course ? (
        <CourseCard course={course} />
      ) : (
        <p className="compare-slot-unavailable">
          {t("Course details unavailable")}
        </p>
      )}
    </section>
  ) : (
    <button
      className={`compare-slot-empty${targeted ? " target" : ""}`}
      type="button"
      aria-label={t("Choose course {slot}", { slot: letter })}
      onClick={(event) => onChoose(event.currentTarget)}
    >
      <b aria-hidden="true">+</b>
      {t("Course {slot}", { slot: letter })}
    </button>
  );
}
