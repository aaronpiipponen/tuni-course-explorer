/** Prerequisite graph controls, explicit route session and root/member overlays. */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
import { useMediaQuery } from "../../shared/useMediaQuery";
import { PHONE_CONTENT_QUERY } from "../../shared/viewport";
import { SLIDERS_ICON, SWAP_ICON } from "../../shared/icons";
import { PhoneSheet } from "../../shared/PhoneSheet";
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
import { evaluateGraphNodeStates } from "./graph/localState";
import { buildRouteSummary } from "./route/route";
import { useMinimumRoute } from "./route/useMinimumRoute";
import { RefusedGraph } from "./route/RefusedGraph";
import "./prerequisites.css";

/** Render the Prerequisites tab controls, its root picker and its graph. */
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
  const phone = useMediaQuery(PHONE_CONTENT_QUERY);
  const { courses: roots, error: rootError } = useCourseSummaries(
    rootId ? [rootId] : [],
  );
  const inputs = usePrerequisiteInputs();
  const {
    report,
    loading: graphLoading,
    error,
    ready,
  } = usePrerequisiteReport(inputs);
  const route = useMinimumRoute(inputs, report, ready);
  const nodeStates = useMemo(
    () =>
      report && inputs.request
        ? evaluateGraphNodeStates(report, inputs.request)
        : [],
    [report, inputs.key],
  );
  const summary = useMemo(
    () =>
      report && route.result
        ? buildRouteSummary(report, route.result, language)
        : null,
    [report, route.result, language],
  );
  const { runAction, error: actionError } = useAction();
  const [rootOpen, setRootOpen] = useState(false);
  const [optionsOpen, setOptionsOpen] = useState(false);
  useEffect(() => {
    // A width change closes the sheet without focusing its hidden trigger.
    if (!phone) setOptionsOpen(false);
  }, [phone]);
  const recenter = useRef<(() => void) | null>(null);
  const optionsTrigger = useRef<HTMLButtonElement>(null);
  const closeRoot = useCallback(() => setRootOpen(false), []);
  const closeOptions = useCallback(() => {
    setOptionsOpen(false);
    optionsTrigger.current?.focus();
  }, []);
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
            "Also shows recommended prerequisites and includes them in the minimum route.",
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
                  "Also shows prerequisites found by analysis rather than listed in the official data. They are marked as inferred, and a connection is dashed only when all its relationships are inferred.",
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
  const inferredToggle = inference_enabled ? (
    <ToggleChip
      label={t("Inferred")}
      on={includeInferred}
      onChange={(value) =>
        runAction(() => setIncludeInferred(inferredStore, value))
      }
    />
  ) : null;
  const activityToggle = (
    <ActivitySwitch
      activeOnly={activeOnly}
      onChange={(value) =>
        runAction(() => setPrerequisitesActiveOnly(activityStore, value))
      }
    />
  );
  const controls = (
    <div className="prereq-controls">
      {phone && root && (
        <button
          className="root-choice"
          type="button"
          onClick={() => {
            setOptionsOpen(false);
            setRootOpen(true);
          }}
        >
          <span className="root-choice-code">{root.code}</span>
          <span className="root-choice-name">{courseName(root, language)}</span>
          {SWAP_ICON}
        </button>
      )}
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
      {phone && inferredToggle}
      {activityToggle}
      {!phone && inferredToggle}
      <HelpTip
        sections={help}
        guide={{
          href: "/docs#guide-prerequisites",
          label: t("Exploring prerequisites"),
        }}
      />
      {!phone && (
        <div className="root-chip">
          {root && (
            <b>
              {root.code} {courseName(root, language)}
            </b>
          )}
          <button
            className="pill-btn"
            type="button"
            onClick={() => {
              setOptionsOpen(false);
              setRootOpen(true);
            }}
          >
            {t("Change")}
          </button>
          {rootId && (
            <button
              className="pill-btn root-recenter"
              type="button"
              onClick={() => report?.drawing.allowed && recenter.current?.()}
              disabled={report?.drawing.allowed === false}
            >
              {t("Recenter")}
            </button>
          )}
        </div>
      )}
    </div>
  );
  return (
    <main
      className="pane-content prereq-pane"
      role="tabpanel"
      aria-label={t("Prerequisites")}
    >
      {!phone && controls}
      {actionError && <ErrorNotice error={actionError} language={language} />}
      {rootError && <ErrorNotice error={rootError} language={language} />}
      <PhoneSheet
        open={phone && optionsOpen}
        title={t("Graph options")}
        onClose={closeOptions}
      >
        {controls}
      </PhoneSheet>
      <div className="prereq-stage">
        {phone && rootId && (
          <div className="prereq-phone-head">
            <button
              ref={optionsTrigger}
              className="phone-options-trigger graph-options-trigger"
              type="button"
              aria-label={t("Graph options")}
              onClick={() => setOptionsOpen(true)}
            >
              {root?.code}
              {SLIDERS_ICON}
            </button>
          </div>
        )}
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
              nodeStates={nodeStates}
              recenterRef={recenter}
              route={route}
              summary={summary}
              graphLoading={graphLoading || !ready}
            />
          ) : (
            <RefusedGraph
              report={report}
              route={route}
              summary={summary}
              graphLoading={graphLoading || !ready}
            />
          )
        ) : null}
        <RootBox open={rootOpen} onClose={closeRoot} />
      </div>
    </main>
  );
}
