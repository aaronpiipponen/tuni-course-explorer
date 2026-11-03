/**
 * One named confirmation for a scoped programme replacement.
 *
 * The description names the replacement with the operation that applies it, states the place that
 * already displays the replacement when one does, lists the courses it pulls out of the nodes they
 * are in, and states the outcome for the replaced programme: its customisation is discarded and
 * its uncompleted courses leave the structure, while its completed courses are kept when it holds
 * one. A replacement that pulls a course asks through **Keep** and **Pull** beside **Cancel**,
 * so one answer replaces the programme without moving those courses and the other moves them in.
 */
import { useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { ErrorNotice } from "../../shared/ErrorNotice";
import type { DisplayLanguage } from "../../state/types";
import type { PulledCourse, PulledModule } from "./edits";
import { useWording } from "../../shared/useWording";
import { PulledItemList } from "./CourseMoveConfirmDialog";
import { usePhoneTabsOnClose } from "../../shared/usePhoneTabsOnClose";

type Target = {
  operation: "replace";
  name: string;
  replacementName: string;
  /** The node that displays the replacement programme, supplied when a visible node does. */
  moduleFrom?: (language: DisplayLanguage) => string;
  /** Whether the replaced programme holds a completed course. */
  hasCompletedCourses: boolean;
};

/** Render one named confirmation for a scoped programme replacement. */
export function ProgrammeConfirmDialog({
  operation,
  name,
  replacementName,
  moduleFrom,
  moves,
  moduleMoves,
  hasCompletedCourses,
  busy,
  error,
  onCancel,
  onConfirm,
  returnFocus,
}: {
  operation: "replace" | null;
  name: string;
  replacementName: string;
  /** The courses the replacement programme pulls out of the nodes they are in. */
  moves: readonly PulledCourse[];
  /** The highest-level official modules the replacement pulls with everything they hold. */
  moduleMoves: readonly PulledModule[];
  /** The node that displays the replacement programme, supplied when a visible node does. */
  moduleFrom?: (language: DisplayLanguage) => string;
  /** Whether the replaced programme holds a completed course. */
  hasCompletedCourses: boolean;
  busy: boolean;
  error: Error | null;
  onCancel(): void;
  /** The answer, which is whether the replacement moves the listed courses in. */
  onConfirm(pull: boolean): void;
  returnFocus(): void;
}) {
  const { language, t } = useWording();
  usePhoneTabsOnClose(operation !== null);
  // The close animation keeps showing the names the confirmation opened with.
  const [retained, setRetained] = useState<Target | null>(null);
  const current: Target | null =
    operation !== null
      ? { operation, name, replacementName, moduleFrom, hasCompletedCourses }
      : null;
  if (
    current &&
    (retained?.operation !== current.operation ||
      retained.name !== current.name ||
      retained.replacementName !== current.replacementName ||
      retained.moduleFrom !== current.moduleFrom ||
      retained.hasCompletedCourses !== current.hasCompletedCourses)
  )
    setRetained(current);
  const shown = current ?? retained;
  const placement = shown?.moduleFrom?.(language) ?? null;
  const pulls = moves.length + moduleMoves.length;
  return (
    <Dialog.Root
      open={operation !== null}
      onOpenChange={(value) => {
        if (!value) onCancel();
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
          {shown && (
            <>
              <Dialog.Title>
                {t("Replace programme “{name}”?", { name: shown.name })}
              </Dialog.Title>
              <Dialog.Description>
                <span>
                  {t("This replaces this programme with “{name}”.", {
                    name: shown.replacementName,
                  })}{" "}
                </span>
                {placement !== null && (
                  <span>
                    {t(
                      "{name} is already in {place} and moves here with its contents.",
                      { name: shown.replacementName, place: placement },
                    )}{" "}
                  </span>
                )}
                {pulls > 0 && (
                  <span>
                    {t("Move them here, or keep them where they are now.")}
                  </span>
                )}
                {pulls > 0 && (
                  <PulledItemList moves={moves} moduleMoves={moduleMoves} />
                )}
                {t(
                  shown.hasCompletedCourses
                    ? "This discards the replaced programme's customisation, removes its uncompleted courses and keeps its completed courses."
                    : "This discards the replaced programme's customisation and removes its uncompleted courses.",
                )}
              </Dialog.Description>
            </>
          )}
          {error && <ErrorNotice error={error} language={language} />}
          <div className="dialog-foot dialog-foot-wrap">
            <Dialog.Close asChild>
              <button className="dialog-cancel" type="button" disabled={busy}>
                {t("Cancel")}
              </button>
            </Dialog.Close>
            {pulls > 0 ? (
              <>
                <button
                  className="dialog-cancel"
                  type="button"
                  disabled={busy}
                  onClick={() => onConfirm(false)}
                >
                  {t("Keep")}
                </button>
                <button
                  className="dialog-confirm"
                  type="button"
                  disabled={busy}
                  onClick={() => onConfirm(true)}
                >
                  {t("Pull")}
                </button>
              </>
            ) : (
              <button
                className="dialog-confirm"
                type="button"
                disabled={busy}
                onClick={() => onConfirm(true)}
              >
                {t("Replace")}
              </button>
            )}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
