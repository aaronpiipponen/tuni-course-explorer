/** Choice of where a completed course goes when it is deselected from Structure. */
import * as Dialog from "@radix-ui/react-dialog";
import { useWording } from "../../shared/useWording";

export function CompletedCourseDeselectDialog({
  open,
  courseCode,
  onCancel,
  onKeepLoose,
  onRemove,
  returnFocus,
}: {
  open: boolean;
  courseCode: string;
  onCancel(): void;
  onKeepLoose(): void;
  onRemove(): void;
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
          <Dialog.Title>{t("Completed course")}</Dialog.Title>
          <Dialog.Description>
            {t(
              "{code} is completed. Move it to Unplaced studies and keep it completed, or remove it from your selection? Removing also removes its completion.",
              { code: courseCode },
            )}
          </Dialog.Description>
          <div className="dialog-foot dialog-foot-wrap">
            <Dialog.Close asChild>
              <button className="dialog-cancel" type="button">
                {t("Cancel")}
              </button>
            </Dialog.Close>
            <button
              className="dialog-cancel"
              type="button"
              onClick={onKeepLoose}
            >
              {t("Move")}
            </button>
            <button className="dialog-confirm" type="button" onClick={onRemove}>
              {t("Remove")}
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
