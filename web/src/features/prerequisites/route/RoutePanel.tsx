/** Route result summary, persistent problem annotations and collapsible course rows. */
import { useEffect, useRef, useState } from "react";
import { CourseListRow } from "../../../shared/course/CourseListRow";
import { useAction } from "../../../shared/useAction";
import { useFreeChoiceAdd } from "../../structure/useFreeChoiceAdd";
import { Disclosure } from "../../../shared/Disclosure";
import { ErrorNotice } from "../../../shared/ErrorNotice";
import { useWording } from "../../../shared/useWording";
import { uiText, type UiTextKey } from "../../../shared/wording";
import type { RouteSummary } from "./route";
import type { MinimumRouteSession } from "./useMinimumRoute";

// A result with no total states its reason as the top line.
const HEADER_KEYS: Record<RouteSummary["state"], UiTextKey> = {
  exact: "Exact minimum route",
  approximate: "Approximate route",
  approximation_failed:
    "The exact search was too large and the approximation gave up.",
  unresolved: "Some requirements cannot be resolved:",
  no_solution: "No route meets every requirement.",
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
/** How long a discarded route stays painted while its panel fades and collapses. */
const RETENTION_MS = 650;
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
/** Render one route result with its problems and course rows. */
export function RoutePanel({
  view,
  route,
  sheetCollapse,
  sheetExit,
}: {
  view: RouteSummary | null;
  route: MinimumRouteSession;
  /** Fold the open phone sheet onto its compact strip and resolve once it has settled. */
  sheetCollapse?: () => Promise<void>;
  /** Fold the open phone sheet away entirely and resolve once it has settled. */
  sheetExit?: () => Promise<void>;
}) {
  const freeChoice = useFreeChoiceAdd();
  const { runAction, error: actionError } = useAction();
  const { language, t } = useWording();
  // Add-all and a changed basis discard the session at once. The last route stays painted while
  // the disclosure collapses, so the panel animates out with its rows instead of vanishing.
  const [retained, setRetained] = useState<RouteSummary | null>(null);
  const [retainedExpanded, setRetainedExpanded] = useState(false);
  // An action that needs the settled screen waits for the fold that the leaving route starts.
  const pendingAfterFold = useRef<(() => void) | null>(null);
  useEffect(() => {
    if (view !== null) {
      setRetained(view);
      setRetainedExpanded(route.expanded);
      return;
    }
    if (route.calculating || route.error !== null) {
      setRetained(null);
      setRetainedExpanded(false);
      return;
    }
    if (retained === null) return;
    // An open phone sheet folds away as one motion, then the route it showed is dropped.
    if (retainedExpanded && sheetExit) {
      let cancelled = false;
      void sheetExit().then(() => {
        if (cancelled) return;
        setRetained(null);
        setRetainedExpanded(false);
        const queued = pendingAfterFold.current;
        pendingAfterFold.current = null;
        queued?.();
      });
      return () => {
        cancelled = true;
      };
    }
    setRetainedExpanded(false);
    const timer = window.setTimeout(() => {
      setRetained(null);
      setRetainedExpanded(false);
      const queued = pendingAfterFold.current;
      pendingAfterFold.current = null;
      queued?.();
    }, RETENTION_MS);
    return () => window.clearTimeout(timer);
  }, [
    view,
    route.expanded,
    route.calculating,
    route.error,
    retained,
    retainedExpanded,
    sheetExit,
  ]);
  const shownView = view ?? retained;
  const expanded = view !== null ? route.expanded : retainedExpanded;
  const closing = view === null && retained !== null;
  // The open sheet stays painted while it folds away, so its content keeps its place.
  const visible =
    route.calculating ||
    view !== null ||
    route.error !== null ||
    (closing && retainedExpanded);
  const canExpand =
    shownView !== null &&
    ["exact", "approximate", "shortfall"].includes(shownView.state) &&
    shownView.rows.length > 0;
  /** Collapse the list, and on the phone the sheet folds before the layout switches. */
  const collapseRoute = () => {
    if (!sheetCollapse) {
      route.setExpanded(false);
      return;
    }
    void sheetCollapse().then(() => route.setExpanded(false));
  };
  const note =
    shownView?.state === "approximate"
      ? t("Not guaranteed to be the minimum.")
      : shownView?.state === "approximation_failed"
        ? t("No route or total is available.")
        : shownView?.state === "no_solution"
          ? t("Blocked requirements:")
          : shownView?.state === "shortfall"
            ? t("A module rule is only partly met with active courses:")
            : null;
  return (
    <Disclosure
      open={visible}
      className={`route-panel${expanded ? " expanded" : ""}${closing ? " closing" : ""}`}
    >
      <div className="route-panel-content">
        {(route.calculating || shownView !== null) && (
          <header className="route-head">
            <b className="route-total">
              {route.calculating ? (
                <>
                  <i className="route-spinner" />
                  {t("Calculating…")}
                </>
              ) : shownView !== null && shownView.newCredits !== null ? (
                t("{new} new · {full} full route", {
                  new: shownView.newCredits,
                  full: shownView.fullCredits ?? "",
                })
              ) : shownView !== null ? (
                t(HEADER_KEYS[shownView.state])
              ) : null}
            </b>
            {!route.calculating && shownView !== null && (
              <RouteTag state={shownView.state} />
            )}
            {!route.calculating && canExpand && (
              <button
                className="pill-btn route-expand"
                type="button"
                aria-expanded={expanded}
                aria-controls="route-course-list"
                onClick={() =>
                  expanded ? collapseRoute() : route.setExpanded(true)
                }
              >
                {t(expanded ? "Collapse" : "Expand")}
              </button>
            )}
            <button
              className="pill-btn route-clear"
              type="button"
              aria-label={t("Clear minimum route")}
              onClick={() => route.clear()}
            >
              {t("Clear")}
            </button>
          </header>
        )}
        {route.error && (
          <div className="route-error">
            <ErrorNotice error={route.error} language={language} />
            {!route.calculating && view === null && (
              <button
                className="pill-btn route-clear"
                type="button"
                aria-label={t("Clear minimum route")}
                onClick={() => route.clear()}
              >
                {t("Clear")}
              </button>
            )}
          </div>
        )}
        {shownView?.state === "exact" &&
          shownView.newCredits ===
            uiText(language, "{value} cr", { value: 0 }) &&
          !route.calculating && (
            <p className="route-note">{t("Nothing new")}</p>
          )}
        {!route.calculating && note && <p className="route-note">{note}</p>}
        {!route.calculating &&
          shownView !== null &&
          ["no_solution", "unresolved", "approximation_failed"].includes(
            shownView.state,
          ) &&
          shownView.problems.length > 0 && (
            <ul className="route-problems">
              {shownView.problems.map((problem) => (
                <li key={problem.identity} data-node-id={problem.nodeId}>
                  <b>{problem.title ?? problem.nodeId}</b>
                  {problem.reason !== null && <span>{problem.reason}</span>}
                </li>
              ))}
            </ul>
          )}
        {!route.calculating && shownView?.state === "shortfall" && (
          <ul className="route-problems">
            {shownView.shortfalls.map((shortfall, index) => (
              <li key={`${shortfall.title}-${index}`}>
                <b>{shortfall.title}</b>
                <span>{shortfall.text}</span>
              </li>
            ))}
          </ul>
        )}
        {shownView !== null && (
          <Disclosure
            open={!route.calculating && expanded && canExpand}
            className="route-list-disclosure"
            clipClassName="thin-scrollbar"
          >
            <div id="route-course-list" className="route-list">
              {shownView.rows.map((row, index) =>
                row.kind === "course" ? (
                  <div
                    className="route-row"
                    key={`${row.course.group_id}-${row.covered}-${index}`}
                  >
                    <CourseListRow
                      course={row.course}
                      reveal
                      hideCredits
                      showMarkers
                    />
                  </div>
                ) : (
                  <p className="route-opaque" key={`${row.key}-${index}`}>
                    {row.key} · {row.credits}
                  </p>
                ),
              )}
            </div>
          </Disclosure>
        )}
        {!route.calculating &&
          expanded &&
          canExpand &&
          shownView !== null &&
          shownView.missingCourseIds.length > 0 && (
            <div className="route-foot">
              <button
                className="pill-btn route-add"
                type="button"
                disabled={closing}
                onClick={() => {
                  const addAll = () =>
                    runAction(() => freeChoice.add(shownView.missingCourseIds));
                  // The route's own basis is gone once the missing courses are added, so it
                  // always closes and collapses rather than staying on screen. The add lands
                  // after the phone sheet has folded, so its notice opens on a settled screen.
                  if (expanded && sheetExit) {
                    pendingAfterFold.current = addAll;
                    route.clear();
                    return;
                  }
                  addAll();
                  route.clear();
                }}
              >
                {t("Add all missing courses to structure")}
              </button>
            </div>
          )}
        {actionError && <ErrorNotice error={actionError} language={language} />}
      </div>
    </Disclosure>
  );
}
