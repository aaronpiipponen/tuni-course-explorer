/** One confirmation that lists a module move and the courses an addition or a reset pulls. */
import { useRef, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import type { ModuleSummary } from "../../api/types";
import type { DisplayLanguage } from "../../state/types";
import { courseName } from "../../shared/course/presentation";
import { ErrorNotice } from "../../shared/ErrorNotice";
import { moduleName } from "./presentation";
import type { PulledCourse } from "./edits";
import { useWording } from "../../shared/useWording";
import { usePhoneTabsOnClose } from "../../shared/usePhoneTabsOnClose";

/** One later-addition or reset operation's holder, its pulled courses and its optional module source. */
export type CourseMoveRequest = {
  holder: ModuleSummary;
  moves: readonly PulledCourse[];
  /** Localized node that renders the module now, supplied when the addition moves the module. */
  moduleFrom?: (language: DisplayLanguage) => string;
};

/**
 * One pull confirmation's answer: `true` moves the listed courses in, `"keep"` performs the
 * operation with those courses left where they are, and `false` cancels the operation.
 */
export type CourseMoveAnswer = boolean | "keep";

/** Return one pending course-move confirmation and the promise its answer resolves. */
export function useCourseMoveConfirm(): {
  request: CourseMoveRequest | null;
  confirm(request: CourseMoveRequest): Promise<CourseMoveAnswer>;
  answer(result: CourseMoveAnswer): void;
} {
  const [request, setRequest] = useState<CourseMoveRequest | null>(null);
  const pending = useRef<((result: CourseMoveAnswer) => void) | null>(null);
  return {
    request,
    confirm: (next) =>
      new Promise<CourseMoveAnswer>((resolve) => {
        pending.current = resolve;
        setRequest(next);
      }),
    answer: (result) => {
      const resolve = pending.current;
      pending.current = null;
      setRequest(null);
      resolve?.(result);
    },
  };
}

/**
 * The confirmation of one holder operation, with the actions its pull list earns.
 *
 * A request that lists courses offers **Keep** and **Pull** beside **Cancel**, so one answer performs
 * the operation without moving them and the other moves them in. A request that only moves the
 * holder asks **Move here?** with **Cancel** and **Move**.
 */
export function CourseMoveConfirmDialog({
  request,
  busy = false,
  error = null,
  onAnswer,
  returnFocus,
}: {
  request: CourseMoveRequest | null;
  busy?: boolean;
  error?: Error | null;
  onAnswer(result: CourseMoveAnswer): void;
  returnFocus(): void;
}) {
  const { language, t } = useWording();
  usePhoneTabsOnClose(request !== null);
  const name = request ? moduleName(request.holder, language) : "";
  const count = request?.moves.length ?? 0;
  const moves = count > 0;
  const moduleFrom = request?.moduleFrom?.(language) ?? null;
  return (
    <Dialog.Root
      open={request !== null}
      onOpenChange={(next) => {
        if (!next) onAnswer(false);
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
          <Dialog.Title>
            {moves
              ? t(
                  count === 1
                    ? "Move this course into {name}?"
                    : "Move these courses into {name}?",
                  { name },
                )
              : t("Move here?")}
          </Dialog.Title>
          <Dialog.Description>
            {moduleFrom !== null &&
              t("{name} is already in {place}. Move it here?", {
                name,
                place: moduleFrom,
              })}
            {moduleFrom !== null && moves && " "}
            {moves && (
              <>
                {t("Move them here, or keep them where they are now.")}
                <ul className="move-list">
                  {(request?.moves ?? []).map((move) => (
                    <li key={move.course.group_id}>
                      {t("{course} · {place}", {
                        course: courseName(move.course, language),
                        place: move.from(language),
                      })}
                    </li>
                  ))}
                </ul>
              </>
            )}
          </Dialog.Description>
          {error && <ErrorNotice error={error} language={language} />}
          <div className="dialog-foot dialog-foot-wrap">
            <Dialog.Close asChild>
              <button className="dialog-cancel" type="button" disabled={busy}>
                {t("Cancel")}
              </button>
            </Dialog.Close>
            {moves ? (
              <>
                <button
                  className="dialog-cancel"
                  type="button"
                  disabled={busy}
                  onClick={() => onAnswer("keep")}
                >
                  {t("Keep")}
                </button>
                <button
                  className="dialog-confirm"
                  type="button"
                  disabled={busy}
                  onClick={() => onAnswer(true)}
                >
                  {t("Pull")}
                </button>
              </>
            ) : (
              <button
                className="dialog-confirm"
                type="button"
                disabled={busy}
                onClick={() => onAnswer(true)}
              >
                {t("Move")}
              </button>
            )}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
