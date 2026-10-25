/** One module-version hand-off: its Cancel control and the shared exact version picker. */
import type { RefObject } from "react";
import type { CatalogueModule, ModuleLookupGroup } from "../../api/types";
import { useWording } from "../../shared/useWording";
import { ModuleVersionPicker } from "./ModuleVersionPicker";

/**
 * Render one ambiguous group's Cancel control and its candidate picker.
 *
 * A caller renders this only while a group is selected, so the picker never shows an empty
 * version list for a surface without a hand-off.
 */
export function ModuleVersionHandoff({
  group,
  cancelRef,
  disabled,
  onCancel,
  onSelect,
}: {
  group: ModuleLookupGroup;
  cancelRef: RefObject<HTMLButtonElement | null>;
  disabled: boolean;
  onCancel(): void;
  onSelect(module: CatalogueModule): void;
}) {
  const { t } = useWording();
  return (
    <>
      <div className="module-version-cancel">
        <button
          className="pill-btn"
          type="button"
          ref={cancelRef}
          disabled={disabled}
          onClick={onCancel}
        >
          {t("Cancel")}
        </button>
      </div>
      <ModuleVersionPicker
        groupId={group.group_id}
        onSelect={onSelect}
        disabled={disabled}
      />
    </>
  );
}
