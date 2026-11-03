/** Modal prompt that chooses one exact version of a module group with several candidates. */
import { useState } from "react";
import type { RefObject } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import type { CatalogueModule, ModuleLookupGroup } from "../../api/types";
import { useWording } from "../../shared/useWording";
import { usePhoneTabsOnClose } from "../../shared/usePhoneTabsOnClose";
import { ModuleVersionLabel } from "./ModuleVersionLabel";
import { moduleName } from "./presentation";

/**
 * Render one ambiguous group's version prompt.
 *
 * The dialog keeps its options mounted while it animates closed. Choosing a version reports the
 * exact canonical identity, and Cancel leaves the lookup and its query untouched.
 */
export function ModuleVersionHandoff({
  group,
  cancelRef,
  disabled,
  onCancel,
  onSelect,
}: {
  group: ModuleLookupGroup | null;
  cancelRef: RefObject<HTMLButtonElement | null>;
  disabled: boolean;
  onCancel(): void;
  onSelect(module: CatalogueModule): void;
}) {
  const { language, t } = useWording();
  usePhoneTabsOnClose(group !== null);
  // The close animation keeps showing the group the prompt opened with.
  const [retained, setRetained] = useState<ModuleLookupGroup | null>(null);
  if (group && group !== retained) setRetained(group);
  const shown = group ?? retained;
  return (
    <Dialog.Root
      open={group !== null}
      onOpenChange={(open) => {
        if (!open) onCancel();
      }}
    >
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-scrim" />
        <Dialog.Content
          className="dialog-panel"
          onCloseAutoFocus={(event) => event.preventDefault()}
        >
          <span className="dialog-eyebrow">// {t("module versions")}</span>
          <Dialog.Title>{t("Choose module version")}</Dialog.Title>
          {shown && (
            <Dialog.Description>
              {t(
                "{name} has more than one version in the curriculum. Choose the version to add.",
                { name: moduleName(shown, language) },
              )}
            </Dialog.Description>
          )}
          <div className="module-versions thin-scrollbar">
            {shown?.candidates.map((candidate) => {
              const target = { group_id: shown.group_id, ...candidate };
              return (
                <button
                  key={candidate.sisu_module_id}
                  type="button"
                  className="dialog-option module-version-option"
                  disabled={disabled}
                  aria-label={t("Add {code} {name} to the structure", {
                    code: candidate.code ?? "",
                    name: moduleName(target, language),
                  })}
                  onClick={() => onSelect(target)}
                >
                  <span className="dialog-code">{candidate.code ?? ""}</span>
                  <span className="dialog-name">
                    {moduleName(target, language)}
                  </span>
                  <span className="module-version-add">{t("+ add")}</span>
                  <ModuleVersionLabel version={candidate} />
                </button>
              );
            })}
          </div>
          <div className="dialog-foot">
            <Dialog.Close asChild>
              <button
                ref={cancelRef}
                className="dialog-cancel"
                type="button"
                disabled={disabled}
              >
                {t("Cancel")}
              </button>
            </Dialog.Close>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
