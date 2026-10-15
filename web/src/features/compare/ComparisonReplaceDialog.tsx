/** Accessible replacement choice for a full comparison, hydrated from official summaries. */
import * as Dialog from "@radix-ui/react-dialog";
import type { CourseSummary } from "../../api/types";
import { replaceComparisonSlot } from "./actions";
import { useProfileSelector } from "../../state/useProfileSelector";
import { courseName } from "../../shared/course/presentation";
import { useCourseSummaries } from "../../shared/course/useCourseSummaries";
import { ErrorNotice } from "../../shared/ErrorNotice";
import { useAction } from "../../shared/useAction";
import { useWording } from "../../shared/useWording";

export function ComparisonReplaceDialog({
  course,
  open,
  onClose,
  returnFocus,
}: {
  course: CourseSummary;
  open: boolean;
  onClose: () => void;
  returnFocus: () => void;
}) {
  const { store, value: slots } = useProfileSelector(
    (state) => state.compare.slots,
  );
  const { language, t } = useWording();
  const ids = slots.filter((id): id is string => id !== null);
  const {
    courses,
    loading,
    error: requestError,
  } = useCourseSummaries(open ? ids : []);
  const { runAction, error: actionError } = useAction();
  const choose = (slot: 0 | 1) =>
    runAction(() => {
      replaceComparisonSlot(store, course.group_id, slot);
      onClose();
    });
  return (
    <Dialog.Root
      open={open}
      onOpenChange={(open) => {
        if (!open) onClose();
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
          <span className="dialog-eyebrow">// {t("compare is full")}</span>
          <Dialog.Title>{t("Replace which course?")}</Dialog.Title>
          <Dialog.Description>
            {t(
              "Two courses are already in the comparison. Choose the one to replace with {name}.",
              {
                name: `${course.code} ${courseName(course, language)}`,
              },
            )}
          </Dialog.Description>
          {loading && <p>{t("Loading comparison courses…")}</p>}
          {requestError && (
            <ErrorNotice error={requestError} language={language} />
          )}
          {actionError && (
            <ErrorNotice error={actionError} language={language} />
          )}
          {!loading &&
            !requestError &&
            slots.map((id, index) => {
              const found = courses.find((item) => item.group_id === id);
              const letter = index === 0 ? "A" : "B";
              return (
                <button
                  key={index}
                  type="button"
                  className="dialog-option"
                  aria-label={t("Replace slot {slot}: {name}", {
                    slot: letter,
                    name: found
                      ? `${found.code} ${courseName(found, language)}`
                      : t("course details unavailable"),
                  })}
                  onClick={() => choose(index as 0 | 1)}
                >
                  <span className="dialog-code">{found?.code}</span>
                  <span className="dialog-name">
                    {found
                      ? courseName(found, language)
                      : t("Course details unavailable")}
                  </span>
                  <span className="dialog-label">{t("Replace")}</span>
                </button>
              );
            })}
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
