/** Shared Unplaced studies root prompt. Pending courses commit only after root load succeeds. */
import * as Dialog from "@radix-ui/react-dialog";
import { ErrorNotice } from "../../shared/ErrorNotice";
import { ModuleLookupBox } from "./ModuleLookupBox";
import { useChooseRoot } from "./useChooseRoot";
import { useAction } from "../../shared/useAction";
import { useWording } from "../../shared/useWording";

export function RootPromptDialog({
  open,
  count,
  onChosen,
  onCancel,
  returnFocus,
}: {
  open: boolean;
  count: number;
  onChosen: () => void;
  onCancel: () => void;
  returnFocus: () => void;
}) {
  const chooser = useChooseRoot();
  const { runAction, error: actionError } = useAction();
  const { language, t } = useWording();
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
          <span className="dialog-eyebrow">// {t("structure root")}</span>
          <Dialog.Title>{t("Choose a root first")}</Dialog.Title>
          <Dialog.Description>
            {t(
              "Unplaced studies live in your structure of studies. Choose a degree programme or module to start it; {courses} will be added to Unplaced studies.",
              {
                courses:
                  count === 1
                    ? t("this course")
                    : t("these {count} courses", { count }),
              },
            )}
          </Dialog.Description>
          {chooser.error && (
            <ErrorNotice error={chooser.error} language={language} />
          )}
          {actionError && (
            <ErrorNotice error={actionError} language={language} />
          )}
          <ModuleLookupBox
            open={open}
            pendingId={chooser.pending}
            onPick={(module) => {
              void chooser.choose(module).then((success) => {
                if (success) runAction(onChosen);
              });
            }}
          />
          <div className="dialog-foot">
            <Dialog.Close asChild>
              <button className="dialog-cancel" type="button">
                {t("Cancel")}
              </button>
            </Dialog.Close>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
