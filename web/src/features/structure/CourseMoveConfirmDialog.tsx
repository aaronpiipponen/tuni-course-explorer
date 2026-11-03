/** One confirmation that lists a module move and the courses an addition or a reset pulls. */
import { useRef, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import type { ModuleSummary } from "../../api/types";
import type { DisplayLanguage } from "../../state/types";
import { courseName } from "../../shared/course/presentation";
import { ErrorNotice } from "../../shared/ErrorNotice";
import { moduleName } from "./presentation";
import type { PulledCourse, PulledModule } from "./edits";
import { useWording } from "../../shared/useWording";
import { usePhoneTabsOnClose } from "../../shared/usePhoneTabsOnClose";

/** One later-addition or reset operation's holder, pulled courses and optional module source. */
export type CourseMoveRequest = {
  holder: ModuleSummary;
  moves: readonly PulledCourse[];
  /** The highest-level official modules the operation pulls, with everything they hold. */
  moduleMoves?: readonly PulledModule[];
  /** Localized node that renders the module, supplied when the addition moves the module. */
  moduleFrom?: (language: DisplayLanguage) => string;
  /** The reset actions the move offers beside Move, from the relocating module's own state. */
  resetOptions?: "reset" | "reset-all" | "both";
};

/**
 * One pull confirmation's answer: `true` moves the listed courses and modules in, `"keep"` performs
 * the operation with them left where they are, `"reset"` and `"reset-all"` move the module and
 * reset it, and `false` cancels the operation.
 */
export type CourseMoveAnswer = boolean | "keep" | "reset" | "reset-all";

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

/** Render the courses and modules one later-addition operation pulls, with each one's place. */
export function PulledItemList({
  moves,
  moduleMoves,
}: {
  moves: readonly PulledCourse[];
  moduleMoves: readonly PulledModule[];
}) {
  const { language, t } = useWording();
  return (
    <ul className="move-list">
      {moves.map((move) => (
        <li key={move.course.group_id}>
          {t("{course} · {place}", {
            course: courseName(move.course, language),
            place: move.from(language),
          })}
        </li>
      ))}
      {moduleMoves.map((move) => (
        <li key={move.module.group_id}>
          {t("{module} · {place}", {
            module: moduleName(move.module, language),
            place: move.from(language),
          })}
        </li>
      ))}
    </ul>
  );
}

/**
 * Render the confirmation of one holder operation, with the actions its pull list earns.
 *
 * A request that lists courses or modules offers **Keep** and **Pull** beside **Cancel**, so one
 * answer performs the operation without moving them and the other moves them in. A request that
 * only moves the holder asks **Move here?** with **Cancel** and **Move**.
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
  const pulls = request?.moves ?? [];
  const modules = request?.moduleMoves ?? [];
  const total = pulls.length + modules.length;
  const moves = total > 0;
  const resetOptions = request?.resetOptions;
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
            {!moves
              ? t("Move here?")
              : modules.length === 0
                ? t(
                    pulls.length === 1
                      ? "Move this course into {name}?"
                      : "Move these courses into {name}?",
                    { name },
                  )
                : pulls.length === 0
                  ? t(
                      modules.length === 1
                        ? "Move this module into {name}?"
                        : "Move these modules into {name}?",
                      { name },
                    )
                  : t("Move these courses and modules into {name}?", {
                      name,
                    })}
          </Dialog.Title>
          <Dialog.Description>
            {moduleFrom !== null &&
              t("{name} is already in {place}. Move it here?", {
                name,
                place: moduleFrom,
              })}
            {moduleFrom !== null && moves && " "}
            {resetOptions === "both" && (
              <>
                {" "}
                {t(
                  "Move keeps the module's current content. Reset restores its official content. Reset all also clears its completions.",
                )}
              </>
            )}
            {resetOptions === "reset" && (
              <>
                {" "}
                {t(
                  "Move keeps the module's current content. Reset restores its official content.",
                )}
              </>
            )}
            {resetOptions === "reset-all" && (
              <>
                {" "}
                {t(
                  "Move keeps the module's current content. Reset all restores its official content and clears its completions.",
                )}
              </>
            )}
            {moves && (
              <>
                {t("Move them here, or keep them where they are now.")}
                <PulledItemList moves={pulls} moduleMoves={modules} />
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
            ) : resetOptions !== undefined ? (
              <>
                {(resetOptions === "reset" || resetOptions === "both") && (
                  <button
                    className="dialog-cancel"
                    type="button"
                    disabled={busy}
                    onClick={() => onAnswer("reset")}
                  >
                    {t("Reset")}
                  </button>
                )}
                {(resetOptions === "reset-all" || resetOptions === "both") && (
                  <button
                    className="dialog-cancel"
                    type="button"
                    disabled={busy}
                    onClick={() => onAnswer("reset-all")}
                  >
                    {t("Reset all")}
                  </button>
                )}
                <button
                  className="dialog-confirm"
                  type="button"
                  disabled={busy}
                  onClick={() => onAnswer(true)}
                >
                  {t("Move")}
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
