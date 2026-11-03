/** The console's product and site mark. */
import { wording } from "../shared/wording";

/** Render the product name and the site name beside it. */
export function BrandMark() {
  return (
    <span className="brand">
      <span className="brand-text">{wording.brand}</span>
      <span>/</span>
      <span className="brand-text">{wording.brandSite}</span>
    </span>
  );
}
