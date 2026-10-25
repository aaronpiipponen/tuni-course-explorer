/** Shared course card paired with report-owned next-course or similarity meters. */
import { useId } from "react";
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

/** Render one next-course or similarity discovery result. */
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
  const metersId = useId();
  const noCoverage = props.kind === "next" && props.mode === "all";
  const meters =
    props.kind === "next" ? (
      props.mode === "all" ? null : (
        <span className="discover-result-meters" id={metersId}>
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
        </span>
      )
    ) : (
      <span className="discover-result-meters" id={metersId}>
        <DiscoverMeter
          label={t("Similarity")}
          value={props.result.relatedness}
          title={
            props.result.uses_derived_text
              ? t("Teaching text includes derived translations")
              : undefined
          }
        />
      </span>
    );
  return (
    <CourseCard
      course={result.course}
      cardClassName="compact-result-card"
      tag={
        props.kind === "next" && props.result.depends_on_inferred
          ? t("inferred")
          : undefined
      }
      renderTrigger={(triggerProps) => (
        <motion.button
          {...triggerProps}
          className={`discover-result-row${props.kind === "next" ? " next-course" : ""}${noCoverage ? " no-coverage" : ""}`}
          layout={!reducedMotion}
          initial={reducedMotion ? false : { opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={reducedMotion ? { duration: 0 } : { duration: 0.25 }}
          data-course-id={result.course.group_id}
          aria-describedby={meters ? metersId : undefined}
        >
          <span className={triggerProps.className}>
            {triggerProps.children}
          </span>
          {meters}
        </motion.button>
      )}
    />
  );
}
