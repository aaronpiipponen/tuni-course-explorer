/** Persisted controls for choosing Discover's report, scope and calculation basis. */
import type { DiscoverState } from "./state";
import { TwoOptionSwitch } from "../../shared/TwoOptionSwitch";
import { ActivitySwitch } from "../../shared/ActivitySwitch";
import { HelpTip } from "../../shared/HelpTip";
import { useWording } from "../../shared/useWording";

export function DiscoverControls({
  options,
  onChange,
}: {
  options: DiscoverState;
  onChange: (patch: Partial<DiscoverState>) => void;
}) {
  const { t } = useWording();
  const modeHelp = {
    term: t("All / At least one"),
    text: t(
      "All proposes a course only when all of its prerequisites are covered by your courses. At least one proposes a course when any one prerequisite is covered, ranked by how much of it is covered.",
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
  return (
    <>
      <div
        className="discover-tabs"
        role="tablist"
        aria-label={t("Discovery list")}
      >
        {(
          [
            ["next", "Next courses"],
            ["recommended", "Recommended"],
          ] as const
        ).map(([value, labelKey]) => (
          <button
            key={value}
            type="button"
            role="tab"
            aria-selected={options.list === value}
            className={`discover-tab${options.list === value ? " on" : ""}`}
            onClick={() => onChange({ list: value })}
          >
            {t(labelKey)}
          </button>
        ))}
      </div>
      <div className="discover-controls">
        {options.list === "next" && (
          <TwoOptionSwitch
            labels={[t("All"), t("At least one")]}
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
          ]}
        />
      </div>
    </>
  );
}
