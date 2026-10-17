/**
 * Standalone screen for unreadable saved browser data.
 *
 * No profile language exists here, so the screen states its failure and its controls in English.
 * Export hands the stored text out unchanged, and reset asks for a confirmation before it
 * replaces every profile.
 */
import { useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { ErrorNotice } from "../../shared/ErrorNotice";
import { useAction } from "../../shared/useAction";

export function StorageRecovery({
  error,
  onExport,
  onReset,
}: {
  error: Error;
  onExport(): void;
  onReset(): void;
}) {
  const [confirmOpen, setConfirmOpen] = useState(false);
  const { runAction, error: exportError } = useAction();
  const { runAction: runReset, error: resetError } = useAction();
  return (
    <main className="storage-recovery">
      <section className="recovery-panel">
        <ErrorNotice error={error} language="en" />
        {exportError && <ErrorNotice error={exportError} language="en" />}
        <div className="recovery-actions">
          <button
            className="dialog-cancel"
            type="button"
            onClick={() => runAction(onExport)}
          >
            Export saved data
          </button>
          <button
            className="dialog-confirm"
            type="button"
            onClick={() => setConfirmOpen(true)}
          >
            Reset saved data
          </button>
        </div>
      </section>
      <Dialog.Root open={confirmOpen} onOpenChange={setConfirmOpen}>
        <Dialog.Portal>
          <Dialog.Overlay className="dialog-scrim" />
          <Dialog.Content
            className="dialog-panel dialog-panel-compact"
            aria-describedby={undefined}
          >
            <Dialog.Title>Reset saved data</Dialog.Title>
            <p>
              This deletes every profile saved in this browser. The app then
              starts with a new My plan profile.
            </p>
            {resetError && <ErrorNotice error={resetError} language="en" />}
            <div className="dialog-foot recovery-confirm-foot">
              <Dialog.Close asChild>
                <button className="dialog-cancel" type="button">
                  Cancel
                </button>
              </Dialog.Close>
              <button
                className="dialog-confirm"
                type="button"
                onClick={() => runReset(onReset)}
              >
                Reset
              </button>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </main>
  );
}
