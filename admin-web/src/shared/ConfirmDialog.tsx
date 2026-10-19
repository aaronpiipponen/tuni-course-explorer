/**
 * The console's one confirmation dialog, over the established dialog library.
 *
 * It names the exact target of the one action it confirms, cancels on Escape, an outside click or the
 * cancel button, and disables its confirm button while the one explicit request is pending. Its
 * content is the fixed overlay's centered grid child, so the overlay owns the viewport-sized stacking
 * and the dialog hit-tests above its own backdrop.
 */
import * as Dialog from "@radix-ui/react-dialog";
import { wording } from "./wording";

/** Render one confirmation dialog for one named action. */
export function ConfirmDialog({
  open,
  title,
  message,
  pending,
  onCancel,
  onConfirm,
}: {
  open: boolean;
  title: string;
  message: string;
  pending: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <Dialog.Root
      open={open}
      onOpenChange={(next: boolean) => {
        if (!next) {
          onCancel();
        }
      }}
    >
      <Dialog.Portal>
        <Dialog.Overlay className="scrim">
          <Dialog.Content className="dialog" aria-modal="true">
            <Dialog.Title className="dialogTitle">{title}</Dialog.Title>
            <Dialog.Description className="dialogMessage">
              {message}
            </Dialog.Description>
            <div className="acts2">
              <button className="btn" type="button" onClick={onCancel}>
                {wording.inference.cancel}
              </button>
              <button
                className="btn danger"
                type="button"
                disabled={pending}
                onClick={onConfirm}
              >
                {wording.inference.confirm}
              </button>
            </div>
          </Dialog.Content>
        </Dialog.Overlay>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
