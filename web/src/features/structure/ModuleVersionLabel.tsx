/** One shared official module-version label: validity bounds, period memberships and exact id. */
import type { CatalogueModule } from "../../api/types";
import { useWording } from "../../shared/useWording";

type VersionFacts = Pick<
  CatalogueModule,
  "sisu_module_id" | "validity_start" | "validity_end" | "curriculum_periods"
>;

/** Render one exact version's official facts: stated validity bounds, periods and exact id. */
export function ModuleVersionLabel({ version }: { version: VersionFacts }) {
  const { t } = useWording();
  const { validity_start: start, validity_end: end } = version;
  const validity =
    start !== null && end !== null
      ? t("Valid {start} – {end}", { start, end })
      : start !== null
        ? t("Valid from {start}", { start })
        : end !== null
          ? t("Valid until {end}", { end })
          : t("Validity not stated");
  const periods = version.curriculum_periods.length
    ? version.curriculum_periods
        .map((period) => `${period.id} (${period.academic_year_start})`)
        .join(", ")
    : "—";
  return (
    <span className="module-version-label">
      <span>{validity}</span>
      <span>{t("Periods: {periods}", { periods })}</span>
      <span>{t("Version {id}", { id: version.sisu_module_id })}</span>
    </span>
  );
}
