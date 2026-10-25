/** Transient result of one Sisu import: the items the placement left out and why. */
import { motion } from "framer-motion";
import type { SisuImportIssue } from "./sisu";
import { useReducedMotion } from "../../shared/useReducedMotion";
import { useWording } from "../../shared/useWording";
import { uiText, type UiTextKey } from "../../shared/wording";

const REASON_KEYS: Record<SisuImportIssue["reason"], UiTextKey> = {
  unresolved:
    "Sisu data did not identify this item uniquely, so it was left out.",
  module_not_placed:
    "The catalogue has no structure for this module, so it was left out. Its courses that are in the catalogue are in Unplaced studies.",
  course_not_represented:
    "This course is not in the catalogue, so it was left out together with its completion.",
};

/** Render the transient result of one Sisu import. */
export function SisuImportNotice({
  issues,
  onDismiss,
}: {
  issues: readonly SisuImportIssue[];
  onDismiss(): void;
}) {
  const reducedMotion = useReducedMotion();
  const { language, t } = useWording();
  return (
    <motion.section
      className="sisu-import-notice"
      role="status"
      initial={reducedMotion ? false : { opacity: 0, height: 0 }}
      animate={{ opacity: 1, height: "auto" }}
      exit={
        reducedMotion
          ? { opacity: 1, height: "auto" }
          : { opacity: 0, height: 0 }
      }
      transition={{
        duration: reducedMotion ? 0 : 0.4,
        ease: [0.22, 0.8, 0.2, 1],
      }}
    >
      <div className="sisu-import-notice-body">
        <h2>{t("The import skipped some items")}</h2>
        <ul>
          {issues.map((issue, index) => (
            <li
              key={`${issue.reason}:${issue.code ?? ""}:${issue.name}:${index}`}
            >
              <span className="sisu-import-item">
                {issue.code ? `${issue.code} ${issue.name}` : issue.name}
              </span>
              <span className="sisu-import-reason">
                {uiText(language, REASON_KEYS[issue.reason])}
              </span>
            </li>
          ))}
        </ul>
        <button className="pill-btn" type="button" onClick={onDismiss}>
          {t("Close")}
        </button>
      </div>
    </motion.section>
  );
}
