/** Structure root picker over the locally filtered official catalogue, with its version hand-off. */
import { useEffect, useRef, useState } from "react";
import type { CatalogueModule, ModuleLookupGroup } from "../../api/types";
import { ErrorNotice } from "../../shared/ErrorNotice";
import { LookupSkeletons } from "../../shared/LookupSkeletons";
import { LookupVirtualList } from "../../shared/LookupVirtualList";
import { moduleName } from "./presentation";
import { ModuleVersionHandoff } from "./ModuleVersionHandoff";
import { useWording } from "../../shared/useWording";
import { useModuleLookup } from "./useModuleLookup";
import { useModuleVersionHandoff } from "./useModuleVersionHandoff";

/** One module group row's canonical identity. */
const groupKey = (row: ModuleLookupGroup) => row.group_id;

/** Render the structure root picker over the filtered official catalogue. */
export function ModuleLookupBox({
  open,
  onPick,
  pendingId,
}: {
  open: boolean;
  onPick: (module: CatalogueModule) => void;
  pendingId: string | null;
}) {
  const [query, setQuery] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const { language, t } = useWording();
  const { report, loading, error } = useModuleLookup(open, query);
  const handoff = useModuleVersionHandoff(
    onPick,
    input,
    JSON.stringify([open, query]),
  );
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
          handoff.group ? (
            <ModuleVersionHandoff
              group={handoff.group}
              cancelRef={handoff.cancelRef}
              disabled={pendingId !== null}
              onCancel={handoff.cancel}
              onSelect={handoff.pick}
            />
          ) : report?.results.length ? (
            <LookupVirtualList
              items={report.results}
              getItemKey={groupKey}
              className="plist"
              resetKey={`${open}-${query}-${language}`}
              inputRef={input}
              renderRow={(row) => (
                <button
                  className="prow root-module-row"
                  type="button"
                  disabled={pendingId !== null}
                  onClick={() => handoff.activate(row)}
                >
                  <span className="scode">{row.code ?? ""}</span>
                  <span className="sname">{moduleName(row, language)}</span>
                </button>
              )}
            />
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
