/** Drawing-size refusal while preserving the explicit route operation. */
import type { PrerequisiteGraphReport } from "../../../api/types";
import { useWording } from "../../../shared/useWording";
import type { RouteSummary } from "./route";
import { RouteControl } from "./RouteControl";
import { RoutePanel } from "./RoutePanel";
import type { MinimumRouteSession } from "./useMinimumRoute";

export function RefusedGraph({
  report,
  route,
  summary,
  graphLoading,
}: {
  report: PrerequisiteGraphReport;
  route: MinimumRouteSession;
  summary: RouteSummary | null;
  graphLoading: boolean;
}) {
  const { language, t } = useWording();
  const locale = language === "fi" ? "fi-FI" : "en-US";
  return (
    <div className="graph-stage">
      <RouteControl
        route={route}
        disabled={graphLoading || route.calculating}
      />
      <div className="graph-panel graph-refusal-panel">
        <div className="graph-refusal-body">
          <section className="graph-refusal" role="status">
            <b>{t("This prerequisite tree is too large to draw.")}</b>
            <p>
              <b>
                {t("{elements} elements, limit {limit}.", {
                  elements: report.drawing.element_count.toLocaleString(locale),
                  limit: report.drawing.limit?.toLocaleString(locale) ?? "—",
                })}
              </b>
            </p>
            <p className="graph-refusal-tip">
              {t(
                "Tip: turn off Recommended or Inferred, or turn on Active only, to shrink the graph.",
              )}
            </p>
          </section>
        </div>
      </div>
      <div className="route-stack">
        <RoutePanel view={summary} route={route} />
      </div>
    </div>
  );
}
