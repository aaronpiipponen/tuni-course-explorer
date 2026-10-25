/** Compact confirmation with Cancel and one confirming action. */
import * as Dialog from "@radix-ui/react-dialog";
import { ErrorNotice } from "./ErrorNotice";
import { useWording } from "./useWording";
import { usePhoneTabsOnClose } from "./usePhoneTabsOnClose";

/** Render one confirmation dialog with a cancel action and one confirming action. */
export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel,
  error,
  onCancel,
  onConfirm,
  returnFocus,
}: {
  open: boolean;
  title: string;
  description: string;
  confirmLabel: string;
  error?: Error | null;
  onCancel(): void;
  onConfirm(): void;
  returnFocus(): void;
}) {
  const { language, t } = useWording();
  usePhoneTabsOnClose(open);
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
          <Dialog.Title>{title}</Dialog.Title>
          <Dialog.Description>{description}</Dialog.Description>
          {error && <ErrorNotice error={error} language={language} />}
          <div className="dialog-foot dialog-foot-wrap">
            <Dialog.Close asChild>
              <button className="dialog-cancel" type="button">
                {t("Cancel")}
              </button>
            </Dialog.Close>
            <button
              className="dialog-confirm"
              type="button"
              onClick={onConfirm}
            >
              {confirmLabel}
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
