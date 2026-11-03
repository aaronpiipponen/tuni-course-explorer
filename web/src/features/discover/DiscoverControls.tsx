/** Persisted controls for choosing Discover's report, scope and calculation basis. */
import type { DiscoverState } from "./state";
import { TwoOptionSwitch } from "../../shared/TwoOptionSwitch";
import { ActivitySwitch } from "../../shared/ActivitySwitch";
import { HelpLink, HelpTip } from "../../shared/HelpTip";
import { useWording } from "../../shared/useWording";
import type { UiTextKey } from "../../shared/wording";
import { useWebFeatures } from "../../app/useWebFeatures";
import { showPhoneTabs } from "../../shared/phoneTabs";

/** Render the available discovery report tabs. */
export function DiscoverListTabs({
  options,
  onChange,
}: {
  options: DiscoverState;
  onChange: (patch: Partial<DiscoverState>) => void;
}) {
  const { t } = useWording();
  const { embeddings_enabled } = useWebFeatures();
  const lists: readonly (readonly [DiscoverState["list"], UiTextKey])[] =
    embeddings_enabled
      ? [
          ["next", "Next courses"],
          ["recommended", "Recommended"],
        ]
      : [["next", "Next courses"]];
  return (
    <div
      className="discover-tabs"
      role="tablist"
      aria-label={t("Discovery list")}
    >
      {lists.map(([value, labelKey]) => (
        <button
          key={value}
          type="button"
          role="tab"
          aria-selected={options.list === value}
          className={`discover-tab${options.list === value ? " on" : ""}`}
          onClick={() => {
            if (value !== options.list) {
              onChange({ list: value });
              showPhoneTabs();
            }
          }}
        >
          {t(labelKey)}
        </button>
      ))}
    </div>
  );
}

/** Render discovery scope, basis and report controls. */
export function DiscoverControls({
  options,
  onChange,
  showTabs = true,
}: {
  options: DiscoverState;
  onChange: (patch: Partial<DiscoverState>) => void;
  showTabs?: boolean;
}) {
  const { t } = useWording();
  const { inference_enabled } = useWebFeatures();
  const modeHelp = {
    term: (
      <HelpLink href="/docs#guide-discover/coverage-and-activity">
        {t("All / Partially covered")}
      </HelpLink>
    ),
    text: t(
      "All lists courses whose prerequisite requirements your basis satisfies. Partially covered lists courses with at least one covered prerequisite, including fully covered courses. It orders them by required coverage, then recommended coverage. Recommended prerequisites also take part in eligibility.",
    ),
  };
  const sharedHelp = [
    {
      term: (
        <HelpLink href="/docs#guide-discover/set-the-basis">
          {t("Completed / Selected")}
        </HelpLink>
      ),
      text: t(
        "Choose the courses used as the basis for suggestions: only completed courses, or every selected course, including completed ones. Select or complete courses in any tab to build the basis.",
      ),
    },
    {
      term: t("Active only"),
      text: t(
        "Proposes only active courses. Turn it off to include inactive courses. Inactive courses in your basis still contribute to suggestions.",
      ),
    },
  ];
  const marksHelp = [
    ...(inference_enabled
      ? [
          {
            term: (
              <HelpLink href="/docs#inference-experiments/limitations">
                {t("inferred")}
              </HelpLink>
            ),
            text: t(
              "Inferred prerequisites or equivalence groups are what bring this course onto the list. They are analysis, not official requirements. The linked experiments explain the evidence and its limits.",
            ),
            tag: true,
          },
        ]
      : []),
    {
      term: t("selected"),
      text: t("In the profile's selection, not completed."),
      tag: true,
    },
    {
      term: t("completed"),
      text: t("Marked completed and also selected."),
      tag: true,
    },
  ];
  return (
    <>
      {showTabs && <DiscoverListTabs options={options} onChange={onChange} />}
      <div className="discover-controls">
        {options.list === "next" && (
          <TwoOptionSwitch
            labels={[t("All"), t("Partially covered")]}
            firstSelected={options.mode === "all"}
            onChange={(all) => onChange({ mode: all ? "all" : "at_least_one" })}
            ariaLabel={t("Prerequisite mode")}
          />
        )}
        <TwoOptionSwitch
          labels={[t("Completed (basis)"), t("Selected (basis)")]}
          firstSelected={options.basis === "completed"}
          onChange={(completed) =>
            onChange({ basis: completed ? "completed" : "selected" })
          }
          ariaLabel={t("Discovery basis")}
        />
        <ActivitySwitch
          activeOnly={options.activeOnly}
          onChange={(activeOnly) => onChange({ activeOnly })}
        />
        <HelpTip
          sections={[
            {
              heading: t("options"),
              items:
                options.list === "next"
                  ? [modeHelp, ...sharedHelp]
                  : sharedHelp,
            },
            {
              heading: t("percentages"),
              items:
                options.list === "next"
                  ? [
                      {
                        term: (
                          <HelpLink href="/docs#next-courses/coverage-and-the-inferred-dependence-mark">
                            {t("Required / Recommended")}
                          </HelpLink>
                        ),
                        text: (
                          <>
                            {t(
                              "Each percentage shows how much of the best-covered prerequisite option your basis covers in that category. A category without course prerequisites has no meter. All shows no meters, because satisfying a choice can require fewer than all its alternatives.",
                            )}{" "}
                            {t(
                              inference_enabled
                                ? "Official and inferred prerequisites both count."
                                : "Only official prerequisites count.",
                            )}
                          </>
                        ),
                      },
                    ]
                  : [
                      {
                        term: (
                          <HelpLink href="/docs#recommendations/relatedness-to-the-trimmed-basis-vector">
                            {t("Similarity")}
                          </HelpLink>
                        ),
                        text: t(
                          "Measures how close the course's content and learning outcomes are to the subject profile formed from your basis. It is a similarity score, not prerequisite coverage or official equivalence. The list leaves out courses that closely duplicate a basis course. A note identifies derived translations used in the comparison.",
                        ),
                      },
                    ],
            },
            { heading: t("marks"), items: marksHelp },
          ]}
        />
      </div>
    </>
  );
}
