/** Inline group-scoped picker for one official module group with several eligible versions. */
import { useMemo } from "react";
import type { CatalogueModule } from "../../api/types";
import { ErrorNotice } from "../../shared/ErrorNotice";
import { LookupSkeletons } from "../../shared/LookupSkeletons";
import { LookupVirtualList } from "../../shared/LookupVirtualList";
import { useCatalogueRead } from "../../shared/course/useCatalogueRead";
import { useWording } from "../../shared/useWording";
import { ModuleVersionLabel } from "./ModuleVersionLabel";
import { moduleName } from "./presentation";

/** One version row's exact group and version identity. */
const versionKey = (module: CatalogueModule) =>
  JSON.stringify([module.group_id, module.sisu_module_id]);

/**
 * Show every candidate of one exact group as a native selectable row.
 *
 * The full catalogue already carries the exact identity, validity and period facts, so this list
 * reads the group without a text query or an arbitrary default and never fabricates a version.
 */
export function ModuleVersionPicker({
  groupId,
  onSelect,
  disabled,
}: {
  groupId: string;
  onSelect(module: CatalogueModule): void;
  disabled: boolean;
}) {
  const { language, t } = useWording();
  const { catalogue, loading, error } = useCatalogueRead(true, groupId);
  const candidates = useMemo(
    () =>
      catalogue?.modules.find((item) => item.group_id === groupId)?.candidates,
    [catalogue, groupId],
  );
  const items = useMemo(
    () =>
      (candidates ?? []).map((candidate) => ({
        group_id: groupId,
        ...candidate,
      })),
    [candidates, groupId],
  );
  return (
    <section className="module-version-picker">
      <div className="eyebrow">// {t("Choose module version")}</div>
      {error && <ErrorNotice error={error} language={language} />}
      {loading && (
        <LookupSkeletons label={t("Loading programmes and modules")} />
      )}
      {!loading && !error && items.length === 0 && (
        <div className="dnote">{t("No versions available.")}</div>
      )}
      {!loading && !error && items.length > 0 && (
        <LookupVirtualList
          items={items}
          getItemKey={versionKey}
          className="plist"
          resetKey={groupId}
          renderRow={(module) => (
            <button
              className="prow module-version-row"
              type="button"
              disabled={disabled}
              onClick={() => onSelect(module)}
            >
              <span className="code">{module.code ?? ""}</span>
              <span className="pn">{moduleName(module, language)}</span>
              <ModuleVersionLabel version={module} />
              <span className="add">{t("Select")}</span>
            </button>
          )}
        />
      )}
    </section>
  );
}
