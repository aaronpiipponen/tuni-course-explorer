/** Route result summary, persistent problem annotations and collapsible course rows. */
import { CourseListRow } from "../../../shared/course/CourseListRow";
import { useAction } from "../../../shared/useAction";
import { useFreeChoiceAdd } from "../../structure/useFreeChoiceAdd";
import { Disclosure } from "../../../shared/Disclosure";
import { ErrorNotice } from "../../../shared/ErrorNotice";
import { useWording } from "../../../shared/useWording";
import { uiText, type UiTextKey } from "../../../shared/wording";
import type { RouteSummary } from "./route";
import type { MinimumRouteSession } from "./useMinimumRoute";

const STATUS_KEYS: Record<RouteSummary["state"], UiTextKey> = {
  exact: "Exact minimum route",
  approximate: "Approximate route",
  approximation_failed: "No route found",
  unresolved: "Route unresolved",
  no_solution: "No route exists",
  shortfall: "Shortfall",
};
const TAG_KEYS: Record<RouteSummary["state"], UiTextKey> = {
  exact: "exact",
  approximate: "approximate",
  approximation_failed: "timeout",
  unresolved: "unresolved",
  no_solution: "no solution",
  shortfall: "shortfall",
};
function RouteTag({ state }: { state: RouteSummary["state"] }) {
  const { t } = useWording();
  const cls =
    state === "exact"
      ? "ok"
      : state === "approximate" || state === "shortfall"
        ? "warn"
        : state === "unresolved"
          ? "r"
          : "x";
  return <i className={`route-tag ${cls}`}>{t(TAG_KEYS[state])}</i>;
}
export function RoutePanel({
  view,
  route,
}: {
  view: RouteSummary | null;
  route: MinimumRouteSession;
}) {
  const freeChoice = useFreeChoiceAdd();
  const { runAction, error: actionError } = useAction();
  const { language, t } = useWording();
  const canExpand =
    view !== null &&
    ["exact", "approximate", "shortfall"].includes(view.state) &&
    view.rows.length > 0;
  const note =
    view?.state === "approximate"
      ? t("Not guaranteed to be the minimum.")
      : view?.state === "approximation_failed"
        ? t(
            "The exact search was too large and the approximation gave up. No route or total is available.",
          )
        : view?.state === "no_solution"
          ? t("No route meets every requirement. Blocked requirements:")
          : view?.state === "unresolved"
            ? t("Some requirements cannot be resolved:")
            : view?.state === "shortfall"
              ? t("A module rule is only partly met with active courses:")
              : null;
  return (
    <Disclosure
      open={route.calculating || view !== null || route.error !== null}
      className="route-panel"
    >
      <div className="route-panel-content">
        {(route.calculating || view !== null) && (
          <header className="route-head">
            <b className="route-total">
              {route.calculating ? (
                <>
                  <i className="route-spinner" />
                  {t("Calculating…")}
                </>
              ) : view !== null && view.newCredits !== null ? (
                t("{new} new · {full} full route", {
                  new: view.newCredits,
                  full: view.fullCredits ?? "",
                })
              ) : view !== null ? (
                t(STATUS_KEYS[view.state])
              ) : null}
            </b>
            {!route.calculating && view !== null && (
              <RouteTag state={view.state} />
            )}
            {!route.calculating && canExpand && (
              <button
                className="pill-btn route-expand"
                type="button"
                aria-expanded={route.expanded}
                aria-controls="route-course-list"
                onClick={() => route.setExpanded(!route.expanded)}
              >
                {t(route.expanded ? "Collapse" : "Expand")}
              </button>
            )}
          </header>
        )}
        {route.error && <ErrorNotice error={route.error} language={language} />}
        {view?.state === "exact" &&
          view.newCredits === uiText(language, "{value} cr", { value: 0 }) &&
          !route.calculating && (
            <p className="route-note">{t("Nothing new")}</p>
          )}
        {!route.calculating && note && <p className="route-note">{note}</p>}
        {!route.calculating &&
          view !== null &&
          ["no_solution", "unresolved", "approximation_failed"].includes(
            view.state,
          ) &&
          view.problems.length > 0 && (
            <ul className="route-problems">
              {view.problems.map((problem) => (
                <li
                  key={problem.identity}
                  data-occurrence-id={problem.occurrenceId}
                >
                  <b>{problem.title ?? problem.actionKey}</b>
                  <span>{problem.reason}</span>
                </li>
              ))}
            </ul>
          )}
        {!route.calculating && view?.state === "shortfall" && (
          <ul className="route-problems">
            {view.shortfalls.map((shortfall, index) => (
              <li key={`${shortfall.title}-${index}`}>
                <b>{shortfall.title}</b>
                <span>{shortfall.text}</span>
              </li>
            ))}
          </ul>
        )}
        {view !== null && (
          <Disclosure
            open={!route.calculating && route.expanded && canExpand}
            className="route-list-disclosure"
          >
            <div id="route-course-list" className="route-list">
              {view.rows.map((row, index) =>
                row.kind === "course" ? (
                  <div
                    className="route-row"
                    key={`${row.course.group_id}-${row.covered}-${index}`}
                  >
                    <CourseListRow
                      course={row.course}
                      trailing={row.covered ? t("done") : undefined}
                    />
                  </div>
                ) : (
                  <p className="route-opaque" key={`${row.key}-${index}`}>
                    {row.key} · {row.credits}
                  </p>
                ),
              )}
              {view.missingCourseIds.length > 0 && (
                <button
                  className="pill-btn route-add"
                  type="button"
                  onClick={() =>
                    runAction(() => freeChoice.add(view.missingCourseIds))
                  }
                >
                  {t("Add all missing courses to structure")}
                </button>
              )}
            </div>
          </Disclosure>
        )}
        {actionError && <ErrorNotice error={actionError} language={language} />}
      </div>
    </Disclosure>
  );
}
