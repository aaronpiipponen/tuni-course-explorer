/** Transient result of one Sisu import: the items the placement left out and why. */
import type { ReactNode } from "react";
import { motion } from "framer-motion";
import type { SisuImportIssue } from "./sisu";
import { SISU_IMPORT_REASON_KEYS } from "./sisuImportWording";
import { useReducedMotion } from "../../shared/useReducedMotion";
import { useWording } from "../../shared/useWording";

/** Return the code and name that label one captured item in the confirmation and result notice. */
export function itemLabel(item: { code: string | null; name: string }): string {
  return item.code ? `${item.code} ${item.name}` : item.name;
}

/** Render one captured item's label and the reason the import left it out. */
export function SisuIssueItem({
  label,
  reason,
  children,
}: {
  label: string;
  reason: SisuImportIssue["reason"];
  children?: ReactNode;
}) {
  const { t } = useWording();
  return (
    <>
      <span className="sisu-import-item">{label}</span>
      <span className="sisu-import-reason">
        {t(SISU_IMPORT_REASON_KEYS[reason])}
      </span>
      {children}
    </>
  );
}

/** Render the transient result of one Sisu import. */
export function SisuImportNotice({
  issues,
  onDismiss,
}: {
  issues: readonly SisuImportIssue[];
  onDismiss(): void;
}) {
  const reducedMotion = useReducedMotion();
  const { t } = useWording();
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
              <SisuIssueItem label={itemLabel(issue)} reason={issue.reason} />
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
