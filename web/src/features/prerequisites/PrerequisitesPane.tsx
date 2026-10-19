/** Prerequisite graph controls, explicit route session and root/member overlays. */
import { useCallback, useMemo, useRef, useState } from "react";
import { useProfileSelector } from "../../state/useProfileSelector";
import { useCourseSummaries } from "../../shared/course/useCourseSummaries";
import { courseName } from "../../shared/course/presentation";
import { ActivitySwitch } from "../../shared/ActivitySwitch";
import { TwoOptionSwitch } from "../../shared/TwoOptionSwitch";
import { ToggleChip } from "../../shared/ToggleChip";
import { HelpTip, type HelpSection } from "../../shared/HelpTip";
import { ErrorNotice } from "../../shared/ErrorNotice";
import { useAction } from "../../shared/useAction";
import { useWording } from "../../shared/useWording";
import { useWebFeatures } from "../../app/useWebFeatures";
import {
  setIncludeInferred,
  setIncludeRecommended,
  setPrerequisitesActiveOnly,
  setPrerequisitesBasis,
} from "./actions";
import { RootBox } from "./RootBox";
import { usePrerequisiteInputs } from "./usePrerequisiteInputs";
import { usePrerequisiteReport } from "./usePrerequisiteReport";
import { PrerequisiteGraph } from "./graph/PrerequisiteGraph";
import { buildRouteSummary } from "./route/route";
import { useMinimumRoute } from "./route/useMinimumRoute";
import { RefusedGraph } from "./route/RefusedGraph";
import "./prerequisites.css";

export function PrerequisitesPane() {
  const { value: rootId } = useProfileSelector(
    (state) => state.prerequisites.rootCourseId,
  );
  const { store: activityStore, value: activeOnly } = useProfileSelector(
    (state) => state.prerequisites.activeOnly,
  );
  const { store: basisStore, value: basis } = useProfileSelector(
    (state) => state.prerequisites.basis,
  );
  const { store: recommendedStore, value: includeRecommended } =
    useProfileSelector((state) => state.prerequisites.includeRecommended);
  const { store: inferredStore, value: includeInferred } = useProfileSelector(
    (state) => state.prerequisites.includeInferred,
  );
  const { language, t } = useWording();
  const { inference_enabled } = useWebFeatures();
  const { courses: roots, error: rootError } = useCourseSummaries(
    rootId ? [rootId] : [],
  );
  const inputs = usePrerequisiteInputs();
  const {
    report,
    loading: graphLoading,
    error,
  } = usePrerequisiteReport(inputs);
  const route = useMinimumRoute(inputs);
  const summary = useMemo(
    () =>
      report && route.result
        ? buildRouteSummary(report, route.result, language)
        : null,
    [report, route.result, language],
  );
  const { runAction, error: actionError } = useAction();
  const [rootOpen, setRootOpen] = useState(false);
  const recenter = useRef<(() => void) | null>(null);
  const closeRoot = useCallback(() => setRootOpen(false), []);
  const root = roots[0];
  const help: readonly HelpSection[] = [
    {
      heading: t("options"),
      items: [
        {
          term: t("Completed / Selected"),
          text: t(
            "Which of your courses count as covered when the route is worked out: only the ones you marked completed, or everything you have selected.",
          ),
        },
        {
          term: t("Recommended"),
          text: t(
            "Also shows recommended prerequisites, drawn apart from the required ones. They count in the minimum route while this is on.",
          ),
        },
        {
          term: t("Active only"),
          text: t(
            "Leaves inactive courses out of the graph and the route. Selected or completed inactive courses and the opened root are shown. Turn it off to include them.",
          ),
        },
        ...(inference_enabled
          ? [
              {
                term: t("Inferred"),
                text: t(
                  "Also shows prerequisites found by analysis rather than listed in the official data. They are marked as inferred.",
                ),
              },
            ]
          : []),
      ],
    },
    {
      heading: t("minimum route"),
      items: [
        {
          term: t("Find minimum route"),
          text: t(
            "Click to calculate one temporary cheapest route through your completed or selected courses. It is not saved anywhere, changing the selected course, the basis, the scope or your course sets clears it back to the normal graph, and clicking it again clears it.",
          ),
        },
      ],
    },
  ];
  return (
    <main
      className="pane-content prereq-pane"
      role="tabpanel"
      aria-label={t("Prerequisites")}
    >
      <div className="prereq-controls">
        <span title={t("Counts as covered")}>
          <TwoOptionSwitch
            labels={[t("Completed (basis)"), t("Selected (basis)")]}
            firstSelected={basis === "completed"}
            onChange={(completed) =>
              runAction(() =>
                setPrerequisitesBasis(
                  basisStore,
                  completed ? "completed" : "selected",
                ),
              )
            }
            ariaLabel={t("Route basis")}
          />
        </span>
        <ToggleChip
          label={t("Recommended")}
          on={includeRecommended}
          onChange={(value) =>
            runAction(() => setIncludeRecommended(recommendedStore, value))
          }
        />
        <ActivitySwitch
          activeOnly={activeOnly}
          onChange={(value) =>
            runAction(() => setPrerequisitesActiveOnly(activityStore, value))
          }
        />
        {inference_enabled && (
          <ToggleChip
            label={t("Inferred")}
            on={includeInferred}
            onChange={(value) =>
              runAction(() => setIncludeInferred(inferredStore, value))
            }
          />
        )}
        <HelpTip sections={help} />
        <div className="root-chip">
          {root && (
            <b>
              {root.code} {courseName(root, language)}
            </b>
          )}
          <button
            className="pill-btn"
            type="button"
            onClick={() => setRootOpen(true)}
          >
            {t("Change")}
          </button>
          {rootId && (
            <button
              className="pill-btn"
              type="button"
              onClick={() => report?.drawing.allowed && recenter.current?.()}
              disabled={report?.drawing.allowed === false}
            >
              {t("Recenter")}
            </button>
          )}
        </div>
      </div>
      {actionError && <ErrorNotice error={actionError} language={language} />}
      {rootError && <ErrorNotice error={rootError} language={language} />}
      <div className="prereq-stage">
        {!rootId ? (
          <div className="prereq-empty">
            <p>{t("Pick a course to open its prerequisite graph.")}</p>
            <button
              className="pill-btn"
              type="button"
              onClick={() => setRootOpen(true)}
            >
              {t("Choose course")}
            </button>
          </div>
        ) : graphLoading && !report ? (
          <div
            className="graph-skeleton"
            aria-label={t("Loading prerequisite graph")}
          >
            {Array.from({ length: 8 }, (_, index) => (
              <i key={index} />
            ))}
          </div>
        ) : error ? (
          <ErrorNotice error={error} language={language} />
        ) : report ? (
          report.drawing.allowed ? (
            <PrerequisiteGraph
              report={report}
              recenterRef={recenter}
              route={route}
              summary={summary}
              graphLoading={graphLoading}
            />
          ) : (
            <RefusedGraph
              report={report}
              route={route}
              summary={summary}
              graphLoading={graphLoading}
            />
          )
        ) : null}
        <RootBox open={rootOpen} onClose={closeRoot} />
      </div>
    </main>
  );
}
