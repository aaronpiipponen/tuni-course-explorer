/** The product mark, with the site name on the app surface. */
import { useWording } from "./useWording";

/** Render the product name and, when requested, the site name beside it. */
export function BrandMark({ site = false }: { site?: boolean }) {
  const { t } = useWording();
  return (
    <span className="brand">
      <span className="brand-text">{t("course-explorer")}</span>
      {site && (
        <>
          <span>/</span>
          <span className="brand-text">{t("tuni")}</span>
        </>
      )}
    </span>
  );
}
