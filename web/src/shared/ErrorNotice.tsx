/**
 * Visible UI presentation for bootstrap, API and user-action failures.
 *
 * A supplied language renders one localized summary plus any diagnostic detail under the
 * translated "Original technical detail" label. When no profile language is available (bootstrap
 * failure), both English and Finnish summaries render, each tagged with its `lang`, and the
 * diagnostic detail is preserved once. Diagnostics are always shown as supplied.
 */
import type { DisplayLanguage } from "../state/types";
import { errorPresentation } from "./errorPresentation";
import { uiText } from "./wording";

export function ErrorNotice({
  error,
  language,
}: {
  error: Error;
  language?: DisplayLanguage;
}) {
  if (language === undefined) {
    const english = errorPresentation(error, "en");
    const finnish = errorPresentation(error, "fi");
    const detail = english.detail ?? finnish.detail;
    return (
      <p className="error-notice" role="alert">
        <span lang="en">{english.summary}</span>
        {" · "}
        <span lang="fi">{finnish.summary}</span>
        {detail && (
          <span className="error-detail" lang="en">
            {" "}
            {uiText("en", "Original technical detail")}: {detail}
          </span>
        )}
      </p>
    );
  }
  const presented = errorPresentation(error, language);
  return (
    <p className="error-notice" role="alert">
      {presented.summary}
      {presented.detail && (
        <span className="error-detail">
          {" "}
          {uiText(language, "Original technical detail")}: {presented.detail}
        </span>
      )}
    </p>
  );
}
