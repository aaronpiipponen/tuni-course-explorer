/** Five backend-ordered comparison meters and the backend-authored verdict label. */
import type {
  CourseComparisonReport,
  ComparisonVerdict,
} from "../../api/types";
import type { UiTextKey } from "../../shared/wording";
import { useWording } from "../../shared/useWording";
import { ComparisonMeter } from "./ComparisonMeter";

const VERDICT_KEYS: Record<ComparisonVerdict, UiTextKey> = {
  heavily_overlapping: "Heavily overlapping",
  partly_overlapping: "Partly overlapping",
  same_area_different_content: "Same area, different content",
  loosely_related: "Loosely related",
  unrelated: "Unrelated",
};

/** Render backend-ordered comparison measurements and the verdict. */
export function ComparisonResults({
  report,
  loading,
}: {
  report: CourseComparisonReport | null;
  loading: boolean;
}) {
  const { t } = useWording();
  const a = report?.course_a.code ?? "A";
  const b = report?.course_b.code ?? "B";
  const rows = [
    [
      "overall",
      t("Overall relatedness"),
      t("whole course"),
      report ? report.meters.overall_relatedness : null,
    ],
    [
      "content",
      t("Content similarity"),
      t("content vs content"),
      report ? report.meters.content_similarity : null,
    ],
    [
      "outcomes",
      t("Learning-outcome similarity"),
      t("outcomes vs outcomes"),
      report ? report.meters.learning_outcome_similarity : null,
    ],
    [
      "a-in-b",
      t("Overlap: {a} in {b}", { a, b }),
      t("how much of A has a match in B"),
      report ? report.meters.overlap.a_in_b : null,
    ],
    [
      "b-in-a",
      t("Overlap: {b} in {a}", { a, b }),
      t("how much of B has a match in A"),
      report ? report.meters.overlap.b_in_a : null,
    ],
  ] as const;
  const verdict = report
    ? report.verdict === null
      ? t("not available")
      : t(VERDICT_KEYS[report.verdict])
    : loading
      ? t("Comparing courses…")
      : t("Select two courses to compare");
  return (
    <>
      <div className="compare-verdict">
        <strong>{verdict}</strong>
        <span className="compare-analysis">
          {t("Course information analysis, not official equivalence.")}
          {report?.uses_derived_text ? ` ${t("Includes derived text.")}` : ""}
        </span>
      </div>
      <div className="comparison-meters">
        {rows.map(([id, label, description, value]) => (
          <ComparisonMeter
            key={id}
            label={label}
            description={description}
            value={value}
            pending={!report}
            loading={loading}
          />
        ))}
      </div>
    </>
  );
}
