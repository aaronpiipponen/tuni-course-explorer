/** Shared course card paired with report-owned next-course or similarity meters. */
import { motion } from "framer-motion";
import type {
  NextCourseResult,
  SimilarityRecommendation,
} from "../../api/types";
import { CourseCard } from "../../shared/course/CourseCard";
import { useWording } from "../../shared/useWording";
import { DiscoverMeter } from "./DiscoverMeter";

export function DiscoverResultRow({
  result,
  kind,
}:
  | {
      kind: "next";
      result: NextCourseResult;
    }
  | {
      kind: "similarity";
      result: SimilarityRecommendation;
    }) {
  const { t } = useWording();
  const isNext = kind === "next";
  return (
    <motion.article
      className="discover-result-row"
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
      data-course-id={result.course.group_id}
    >
      <CourseCard
        course={result.course}
        tag={isNext && result.depends_on_inferred ? t("inferred") : undefined}
      />
      {isNext ? (
        <div className="discover-result-meters">
          <DiscoverMeter
            label={t("Required")}
            value={result.required_coverage * 100}
          />
          <DiscoverMeter
            label={t("Recommended")}
            value={result.recommended_coverage * 100}
          />
        </div>
      ) : (
        <div className="discover-result-meters">
          <DiscoverMeter
            label={t("Similarity")}
            value={result.relatedness}
            title={
              result.uses_derived_text
                ? t("Teaching text includes derived translations")
                : undefined
            }
          />
        </div>
      )}
    </motion.article>
  );
}
