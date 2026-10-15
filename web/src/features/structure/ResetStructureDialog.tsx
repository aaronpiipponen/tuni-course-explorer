/** Confirmation boundary for destructive reset-all structure customization. */
import * as Dialog from "@radix-ui/react-dialog";
import { useWording } from "../../shared/useWording";

export function ResetStructureDialog({
  open,
  onCancel,
  onReset,
  returnFocus,
}: {
  open: boolean;
  onCancel(): void;
  onReset(): void;
  returnFocus(): void;
}) {
  const { t } = useWording();
  return (
    <Dialog.Root
      open={open}
      onOpenChange={(value) => {
        if (!value) onCancel();
      }}
    >
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-scrim" />
        <Dialog.Content
          className="dialog-panel"
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            returnFocus();
          }}
        >
          <Dialog.Title>{t("Reset all structure changes?")}</Dialog.Title>
          <div className="dialog-foot">
            <Dialog.Close asChild>
              <button className="dialog-cancel" type="button">
                {t("Cancel")}
              </button>
            </Dialog.Close>
            <button className="dialog-confirm" type="button" onClick={onReset}>
              {t("Reset")}
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
