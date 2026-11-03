/** Explicit minimum-route control: click calculates, click again clears. */
import { useWording } from "../../../shared/useWording";
import type { MinimumRouteSession } from "./useMinimumRoute";

/** Render the explicit minimum route control. */
export function RouteControl({
  route,
  disabled,
}: {
  route: MinimumRouteSession;
  disabled: boolean;
}) {
  const { t } = useWording();
  const active = route.result !== null;
  const busy = route.calculating;
  const state = busy ? "busy" : active ? "active" : "idle";
  return (
    <section className="routebox" aria-label={t("Minimum route")}>
      <button
        type="button"
        className={`rbtn${active ? " on" : ""}${busy ? " busy" : ""}`}
        data-state={state}
        disabled={disabled && !active}
        onClick={() => (active ? route.clear() : route.find())}
      >
        <span className="rbtn-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24">
            <circle cx="6" cy="5" r="2.2" />
            <circle cx="18" cy="12" r="2.2" />
            <circle cx="7" cy="19" r="2.2" />
            <path d="M6 7.2c0 5 12 1 12 2.6M18 14.2c0 3-11 0-11 2.6" />
          </svg>
          <i className="route-control-spinner" aria-hidden="true" />
        </span>
        <span className="rbtn-copy">
          <span className="rbtn-copy-state rbtn-copy-idle">
            {t("Find minimum route")}
            <small>{t("cheapest route to the selected course")}</small>
          </span>
          <span className="rbtn-copy-state rbtn-copy-active">
            {t("Clear minimum route")}
            <small>{t("click to clear")}</small>
          </span>
          <span className="rbtn-copy-state rbtn-copy-busy">
            {t("Calculating…")}
            <small>{t("cheapest route to the selected course")}</small>
          </span>
        </span>
      </button>
    </section>
  );
}
