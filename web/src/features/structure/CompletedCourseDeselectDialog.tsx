/**
 * One choice for a completed course that is deselected from Structure.
 *
 * A course that already sits under Unplaced studies is only removed, because keeping it loose there
 * changes nothing. Any other completed course offers keeping it under Unplaced studies or removing
 * it from the selection together with its completion.
 */
import * as Dialog from "@radix-ui/react-dialog";
import { useWording } from "../../shared/useWording";
import { usePhoneTabsOnClose } from "../../shared/usePhoneTabsOnClose";

/** Render one choice for a completed course deselected from Structure. */
export function CompletedCourseDeselectDialog({
  open,
  courseCode,
  unplaced,
  onCancel,
  onKeepLoose,
  onRemove,
  returnFocus,
}: {
  open: boolean;
  courseCode: string;
  /** Whether the course already sits under Unplaced studies, where keeping it loose changes nothing. */
  unplaced: boolean;
  onCancel(): void;
  onKeepLoose(): void;
  onRemove(): void;
  returnFocus(): void;
}) {
  const { t } = useWording();
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
          <Dialog.Title>{t("Completed course")}</Dialog.Title>
          <Dialog.Description>
            {unplaced
              ? t(
                  "This removes {code} from your selection together with its completion.",
                  { code: courseCode },
                )
              : t(
                  "This moves {code} to Unplaced studies and keeps its completion, or removes it from your selection together with its completion.",
                  { code: courseCode },
                )}
          </Dialog.Description>
          <div className="dialog-foot dialog-foot-wrap">
            <Dialog.Close asChild>
              <button className="dialog-cancel" type="button">
                {t("Cancel")}
              </button>
            </Dialog.Close>
            {!unplaced && (
              <button
                className="dialog-cancel"
                type="button"
                onClick={onKeepLoose}
              >
                {t("Move")}
              </button>
            )}
            <button className="dialog-confirm" type="button" onClick={onRemove}>
              {t("Remove")}
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
