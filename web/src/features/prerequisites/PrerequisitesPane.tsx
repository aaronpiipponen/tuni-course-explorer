/** Prerequisite graph controls, explicit route session and root/member overlays. */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useIsPresent } from "framer-motion";
import { useProfileSelector } from "../../state/useProfileSelector";
import { useCourseSummaries } from "../../shared/course/useCourseSummaries";
import { courseName } from "../../shared/course/presentation";
import { ActivitySwitch } from "../../shared/ActivitySwitch";
import { TwoOptionSwitch } from "../../shared/TwoOptionSwitch";
import { ToggleChip } from "../../shared/ToggleChip";
import { HelpLink, HelpTip, type HelpSection } from "../../shared/HelpTip";
import { ErrorNotice } from "../../shared/ErrorNotice";
import { useAction } from "../../shared/useAction";
import { useNotice } from "../../shared/useNotice";
import { useWording } from "../../shared/useWording";
import { uiText, type UiTextKey } from "../../shared/wording";
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

/** The empty-graph notice text, indexed by three bits: bit 0 is set when Recommended is off, bit 2
 * when Active only is on, and bit 4 when Inferred is off on a site that serves the inference
 * feature. */
const EMPTY_GRAPH_TEXT: readonly UiTextKey[] = [
  "No prerequisites with these options.",
  "No prerequisites with these options. Consider turning Recommended on.",
  "No prerequisites with these options. Consider turning Active only off.",
  "No prerequisites with these options. Consider turning Recommended on or Active only off.",
  "No prerequisites with these options. Consider turning Inferred on.",
  "No prerequisites with these options. Consider turning Recommended on or Inferred on.",
  "No prerequisites with these options. Consider turning Active only off or Inferred on.",
  "No prerequisites with these options. Consider turning Recommended on, Active only off or Inferred on.",
];

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
  const isPresent = useIsPresent();
  // The drawing and the route stay open while the pane slides out.
  const inputs = usePrerequisiteInputs(isPresent);
  const {
    report,
    loading: graphLoading,
    error,
    ready,
  } = usePrerequisiteReport(inputs);
  const notice = useNotice();
  // A drawing with only its root has no prerequisite paths, which reads as a failed load. The
  // notice stays until the drawing changes and does not read a previous root while the next loads.
  const emptyGraph =
    ready &&
    report?.drawing.allowed === true &&
    report.drawing.edge_count === 0;
  // One notice sentence per combination of the settings that could keep a prerequisite out of the
  // drawing, so the hint only suggests a change that is available and not already made.
  const emptyGraphText =
    EMPTY_GRAPH_TEXT[
      (includeRecommended ? 0 : 1) |
        (activeOnly ? 2 : 0) |
        (inference_enabled && !includeInferred ? 4 : 0)
    ];
  useEffect(() => {
    // A missing report means the drawing is loading or the pane is leaving. The notice stays with
    // its tab through that gap instead of vanishing before the pane slides out.
    if (report === null) return;
    if (!emptyGraph) {
      notice.dismiss("prerequisite graph empty");
      return;
    }
    notice.show(
      (displayLanguage) => uiText(displayLanguage, emptyGraphText),
      undefined,
      { key: "prerequisite graph empty", persistent: true },
    );
  }, [emptyGraph, emptyGraphText, notice, ready, report]);
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
          term: (
            <HelpLink href="/docs#guide-prerequisites/graph-options">
              {t("Completed / Selected")}
            </HelpLink>
          ),
          text: t(
            "Choose which courses count as covered: only completed courses, or every selected course, including completed ones. Covered courses add no new credits to the route.",
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
            "Leaves inactive courses out of the graph and the route. Selected or completed inactive courses and the opened root are shown. Turn it off to include other inactive courses. The course picker uses this same setting.",
          ),
        },
        ...(inference_enabled
          ? [
              {
                term: (
                  <HelpLink href="/docs#guide-prerequisites/official-and-inferred-prerequisites">
                    {t("Inferred")}
                  </HelpLink>
                ),
                text: (
                  <>
                    {t(
                      "Adds prerequisites found by analysis of teaching text, separately from the university's official requirements. A course is marked inferred only when no official occurrence reaches it. A connection is dashed only when all its relationships are inferred.",
                    )}{" "}
                    <HelpLink href="/docs#inference-experiments/limitations">
                      {t("inference experiments")}
                    </HelpLink>{" "}
                    {t("describe the evidence and its limits.")}
                  </>
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
          term: (
            <HelpLink href="/docs#guide-prerequisites/find-the-minimum-route">
              {t("Find minimum route")}
            </HelpLink>
          ),
          text: t(
            "Calculates a temporary route with the fewest new credits beyond your basis. A shared course counts once. The result states whether it is exact, approximate or unresolved, or whether a route cannot be found. Changing the root, options, courses or graph marks, or leaving this tab, clears the shown route. Use Clear minimum route to return to the plain graph.",
          ),
        },
      ],
    },
    {
      heading: t("graph"),
      items: [
        {
          term: (
            <HelpLink href="/docs#guide-prerequisites/read-the-drawing">
              {t("Exploring prerequisites")}
            </HelpLink>
          ),
          text: t(
            "AND requires every branch. OR requires one alternative. Other requirement boxes state how many courses or credits are needed. Complete marks a course completed across the app. A completion mark on a module or requirement box applies to that graph requirement instead. Exclude blocks routes through the marked course or requirement.",
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
      <HelpTip sections={help} />
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
