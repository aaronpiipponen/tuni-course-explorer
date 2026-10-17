/** Shared course card paired with report-owned next-course or similarity meters. */
import { motion } from "framer-motion";
import type {
  NextCourseResult,
  NextCoursesReport,
  SimilarityRecommendation,
} from "../../api/types";
import { CourseCard } from "../../shared/course/CourseCard";
import { useReducedMotion } from "../../shared/useReducedMotion";
import { useWording } from "../../shared/useWording";
import { DiscoverMeter } from "./DiscoverMeter";

export function DiscoverResultRow(
  props:
    | {
        kind: "next";
        result: NextCourseResult;
        mode: NextCoursesReport["mode"];
      }
    | {
        kind: "similarity";
        result: SimilarityRecommendation;
      },
) {
  const reducedMotion = useReducedMotion();
  const { t } = useWording();
  const { result } = props;
  const noCoverage = props.kind === "next" && props.mode === "all";
  const meters =
    props.kind === "next" ? (
      props.mode === "all" ? null : (
        <div className="discover-result-meters">
          {props.result.required_coverage !== null && (
            <DiscoverMeter
              label={t("Required")}
              value={props.result.required_coverage * 100}
            />
          )}
          {props.result.recommended_coverage !== null && (
            <DiscoverMeter
              label={t("Recommended")}
              value={props.result.recommended_coverage * 100}
            />
          )}
        </div>
      )
    ) : (
      <div className="discover-result-meters">
        <DiscoverMeter
          label={t("Similarity")}
          value={props.result.relatedness}
          title={
            props.result.uses_derived_text
              ? t("Teaching text includes derived translations")
              : undefined
          }
        />
      </div>
    );
  return (
    <motion.article
      className={`discover-result-row${props.kind === "next" ? " next-course" : ""}${noCoverage ? " no-coverage" : ""}`}
      layout={!reducedMotion}
      initial={reducedMotion ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={reducedMotion ? { duration: 0 } : { duration: 0.25 }}
      data-course-id={result.course.group_id}
    >
      <CourseCard
        course={result.course}
        tag={
          props.kind === "next" && props.result.depends_on_inferred
            ? t("inferred")
            : undefined
        }
      />
      {meters}
    </motion.article>
  );
}
