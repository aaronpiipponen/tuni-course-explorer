/** Canonical basis chips and optionally expanded official course list. */
import { PickerOverlay } from "../../shared/PickerOverlay";
import { ErrorNotice } from "../../shared/ErrorNotice";
import { CourseListRow } from "../../shared/course/CourseListRow";
import { useCourseSummaries } from "../../shared/course/useCourseSummaries";
import { courseCredits, courseName } from "../../shared/course/presentation";
import { useWording } from "../../shared/useWording";

export function DiscoverBasis({
  basis,
  courseIds,
  expanded,
  onExpandedChange,
}: {
  basis: "completed" | "selected";
  courseIds: readonly string[];
  expanded: boolean;
  onExpandedChange: (expanded: boolean) => void;
}) {
  const { courses, loading, error } = useCourseSummaries(courseIds);
  const { language, t } = useWording();
  const basisLabel = t(
    basis === "completed" ? "Completed (basis)" : "Selected (basis)",
  );
  const totalCredits = courses.reduce(
    (total, course) => total + Number(course.credits_min),
    0,
  );

  if (!courseIds.length)
    return (
      <div className="discover-basis empty">
        <span className="eyebrow">
          {t("basis · {basis} · empty", { basis: basisLabel })}
        </span>
        <p>{t("Select or complete courses in any tab to get suggestions.")}</p>
      </div>
    );

  return (
    <section
      className="discover-basis"
      aria-label={t("{basis} course basis", { basis: basisLabel })}
    >
      <div className="discover-basis-summary">
        <span className="eyebrow">
          {t(
            courseIds.length === 1
              ? "basis · {basis} · {count} course"
              : "basis · {basis} · {count} courses",
            { basis: basisLabel, count: courseIds.length },
          )}
        </span>
        <div className="discover-chips">
          {courses.slice(0, 4).map((course) => (
            <span className="discover-chip" key={course.group_id}>
              <b>{course.code}</b> {courseName(course, language)}
            </span>
          ))}
          {courseIds.length > 4 && (
            <button
              type="button"
              className="discover-chip more"
              aria-expanded={expanded}
              onClick={() => onExpandedChange(!expanded)}
            >
              {t("+{count} more", { count: courseIds.length - 4 })}
            </button>
          )}
        </div>
      </div>
      {error && <ErrorNotice error={error} language={language} />}
      {!error && loading && (
        <p className="discover-basis-status">{t("Loading course details…")}</p>
      )}
      <PickerOverlay
        open={expanded}
        onClose={() => onExpandedChange(false)}
        eyebrow={`// ${t("basis {basis}", { basis: basisLabel })}`}
      >
        <p className="discover-total">
          {t(
            courseIds.length === 1
              ? "{total} cr total · {count} course"
              : "{total} cr total · {count} courses",
            { total: totalCredits, count: courseIds.length },
          )}
        </p>
        <div className="discover-basis-list">
          {courses.map((course) => (
            <CourseListRow
              course={course}
              trailing={courseCredits(course, language)}
              key={course.group_id}
            />
          ))}
        </div>
      </PickerOverlay>
    </section>
  );
}
