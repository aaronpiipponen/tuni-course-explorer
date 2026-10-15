/** Confirmation before an already-placed course or module is moved into another node. */
import * as Dialog from "@radix-ui/react-dialog";
import { useWording } from "../../shared/useWording";

export function MoveConfirmDialog({
  open,
  name,
  place,
  onCancel,
  onMove,
  returnFocus,
}: {
  open: boolean;
  name: string;
  place: string;
  onCancel(): void;
  onMove(): void;
  returnFocus(): void;
}) {
  const { t } = useWording();
  return (
    <Dialog.Root
      open={open}
      onOpenChange={(next) => {
        if (!next) onCancel();
      }}
    >
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-scrim" />
        <Dialog.Content
          className="dialog-panel dialog-panel-compact"
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            returnFocus();
          }}
        >
          <Dialog.Title>{t("Move here?")}</Dialog.Title>
          <Dialog.Description>
            {t("{name} is already in {place}. Move it here?", {
              name,
              place,
            })}
          </Dialog.Description>
          <div className="dialog-foot dialog-foot-wrap">
            <Dialog.Close asChild>
              <button className="dialog-cancel" type="button">
                {t("Cancel")}
              </button>
            </Dialog.Close>
            <button className="dialog-confirm" type="button" onClick={onMove}>
              {t("Move")}
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
