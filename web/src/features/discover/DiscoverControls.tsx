/** Persisted controls for choosing Discover's report, scope and calculation basis. */
import type { DiscoverState } from "./state";
import { TwoOptionSwitch } from "../../shared/TwoOptionSwitch";
import { ActivitySwitch } from "../../shared/ActivitySwitch";
import { HelpTip } from "../../shared/HelpTip";
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
    term: t("All / Partially covered"),
    text: t(
      "The All mode proposes a course only when your courses cover all of its prerequisites. The Partially covered mode proposes a course when any prerequisite is covered, including courses whose prerequisites are all covered, ranked by coverage.",
    ),
  };
  const sharedHelp = [
    {
      term: t("Completed / Selected"),
      text: t(
        "Which of your courses count as done: only the ones you marked completed, or everything you have selected.",
      ),
    },
    {
      term: t("Active only"),
      text: t(
        "Proposes only courses that are currently active. Turn it off to include inactive courses. Inactive courses you already have still count as done.",
      ),
    },
  ];
  const marksHelp = [
    ...(inference_enabled
      ? [
          {
            term: t("inferred"),
            text: t("Listed only because of inferred prerequisites."),
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
                        term: t("Required / Recommended"),
                        text: t(
                          inference_enabled
                            ? "Required and Recommended show how many of the courses in the best-matching prerequisite option of each category your basis covers. A category with no course prerequisites has no meter. The All mode lists only courses whose prerequisite requirements your basis satisfies, and it shows no meters. Official and inferred prerequisites both count. The inferred mark shows a course listed only because of inferred prerequisites."
                            : "Required and Recommended show how many of the courses in the best-matching prerequisite option of each category your basis covers. A category with no course prerequisites has no meter. The All mode lists only courses whose prerequisite requirements your basis satisfies, and it shows no meters. Only official prerequisites count.",
                        ),
                      },
                    ]
                  : [
                      {
                        term: t("Similarity"),
                        text: t(
                          "Similarity shows how close the course's teaching text is to your whole basis. It is a similarity score, not prerequisite coverage or official equivalence.",
                        ),
                      },
                    ],
            },
            { heading: t("marks"), items: marksHelp },
          ]}
          guide={{
            href: "/docs#guide-discover",
            label: t("Discovering courses"),
          }}
        />
      </div>
    </>
  );
}
