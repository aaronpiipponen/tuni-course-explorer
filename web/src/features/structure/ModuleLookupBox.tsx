/** Structure root picker rows over the official programme/module substring endpoint. */
import { useEffect, useRef, useState } from "react";
import type { ModuleSummary } from "../../api/types";
import { ErrorNotice } from "../../shared/ErrorNotice";
import { LookupSkeletons } from "../../shared/LookupSkeletons";
import { moduleName } from "./presentation";
import { useWording } from "../../shared/useWording";
import { useModuleLookup } from "./useModuleLookup";

export function ModuleLookupBox({
  open,
  onPick,
  pendingId,
}: {
  open: boolean;
  onPick: (module: ModuleSummary) => void;
  pendingId: string | null;
}) {
  const [query, setQuery] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const { language, t } = useWording();
  const { report, loading, error } = useModuleLookup(open, query);
  useEffect(() => {
    if (open) input.current?.focus();
  }, [open]);
  return (
    <>
      <div className="course-lookup-controls module-lookup-controls">
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <circle cx="11" cy="11" r="7" />
          <path d="m20 20-3.5-3.5" />
        </svg>
        <input
          ref={input}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder={t("Filter programmes and modules by name or code")}
          aria-label={t("Filter programmes and modules by name or code")}
        />
      </div>
      {error && <ErrorNotice error={error} language={language} />}
      {loading && (
        <LookupSkeletons label={t("Loading programmes and modules")} />
      )}
      {!loading &&
        !error &&
        (query.trim() ? (
          report?.results.length ? (
            <div className="plist">
              {report.results.map((module) => (
                <button
                  className="prow root-module-row"
                  key={module.group_id}
                  type="button"
                  disabled={pendingId !== null}
                  onClick={() => onPick(module)}
                >
                  <span
                    className={`pk ${module.module_type === "DegreeProgramme" ? "programme" : "module"}`}
                  >
                    {t(
                      module.module_type === "DegreeProgramme"
                        ? "programme"
                        : "module",
                    )}
                  </span>
                  <span className="scode">{module.code ?? ""}</span>
                  <span className="sname">{moduleName(module, language)}</span>
                  <span className="add">
                    {pendingId === module.group_id
                      ? t("opening…")
                      : t("open →")}
                  </span>
                </button>
              ))}
            </div>
          ) : (
            report && (
              <p className="sempty">
                {t("No programmes or modules match this search.")}
              </p>
            )
          )
        ) : (
          <p className="sempty">
            {t("Type to search programmes and modules by name or code.")}
          </p>
        ))}
    </>
  );
}
