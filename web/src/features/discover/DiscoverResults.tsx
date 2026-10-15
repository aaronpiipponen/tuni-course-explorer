/** Backend-ordered discovery result tiers with loading and empty states. */
import type { DiscoverState } from "./state";
import type {
  NextCoursesReport,
  SimilarityRecommendation,
} from "../../api/types";
import { ErrorNotice } from "../../shared/ErrorNotice";
import { useWording } from "../../shared/useWording";
import { DiscoverResultRow } from "./DiscoverResultRow";

export function DiscoverResults({
  next,
  similarity,
  list,
  loading,
  error,
  hasBasis,
}: {
  next: NextCoursesReport | null;
  similarity: readonly SimilarityRecommendation[];
  list: DiscoverState["list"];
  loading: boolean;
  error: Error | null;
  hasBasis: boolean;
}) {
  const { language, t } = useWording();
  if (!hasBasis) return null;
  if (loading)
    return (
      <div className="discover-loading" aria-live="polite">
        <p>
          {t(
            list === "recommended"
              ? "Calculating recommendations…"
              : "Calculating next courses…",
          )}
        </p>
        <div className="discover-skeleton-list" aria-hidden="true">
          {Array.from({ length: 6 }, (_, index) => (
            <div className="discover-skeleton" key={index} />
          ))}
        </div>
      </div>
    );
  if (error) return <ErrorNotice error={error} language={language} />;

  const nextRows = next?.results ?? [];
  const empty =
    list === "next" ? nextRows.length === 0 : similarity.length === 0;
  if (empty)
    return (
      <p className="discover-empty">{t("No course matches these options.")}</p>
    );

  return (
    <div className="discover-results">
      {list === "next" && nextRows.length > 0 && (
        <section aria-label={t("Next courses")}>
          <h2 className="discover-tier">
            // {t("next courses · {count}", { count: nextRows.length })}
          </h2>
          <div className="discover-result-list">
            {nextRows.map((result) => (
              <DiscoverResultRow
                key={result.course.group_id}
                kind="next"
                result={result}
              />
            ))}
          </div>
        </section>
      )}
      {list === "recommended" && similarity.length > 0 && (
        <section aria-label={t("Recommended for you")}>
          <h2 className="discover-tier">
            //{" "}
            {t("recommended for you · {count}", { count: similarity.length })}
          </h2>
          <div className="discover-result-list">
            {similarity.map((result) => (
              <DiscoverResultRow
                key={result.course.group_id}
                kind="similarity"
                result={result}
              />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
