/**
 * One compact confirmation for removing or resetting a programme or a module.
 *
 * The `operation` prop selects the removal or the reset presentation, and `holderKind` selects the
 * programme or module nouns of the title and of the description. Every state shows one short
 * description of the ordinary action: a removal names the holder that leaves the structure, and a
 * reset names the holder whose official content is restored. A scope that holds a completed course
 * shows the further choice between keeping those completions and clearing or removing them, and
 * only then does the panel offer `Delete all` or `Reset all`. A removal outcome is the caller's:
 * the ordinary choice keeps completed courses loose in Unplaced studies, and the destructive
 * `Delete all` drops their selection and completion with the removed holder. The destructive
 * `Reset all` clears the completions its scope holds.
 */
import { useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { ErrorNotice } from "../../shared/ErrorNotice";
import { useWording } from "../../shared/useWording";
import { usePhoneTabsOnClose } from "../../shared/usePhoneTabsOnClose";
import type { UiTextKey } from "../../shared/wording";

/** The variant one open confirmation shows, kept while the panel animates closed. */
type Target = {
  name: string;
  hasCompletedCourses: boolean;
  operation: "remove" | "reset";
  holderKind: "programme" | "module";
};

/** One description per operation, holder noun and completion presence. */
const DESCRIPTIONS: Record<
  "remove" | "reset",
  Record<
    "programme" | "module",
    { withoutCompletions: UiTextKey; withCompletions: UiTextKey }
  >
> = {
  remove: {
    programme: {
      withoutCompletions: "This removes this programme from the structure.",
      withCompletions:
        "This removes this programme from the structure. Keep completed courses under Unplaced studies, or remove them with their completions.",
    },
    module: {
      withoutCompletions: "This removes this module from the structure.",
      withCompletions:
        "This removes this module from the structure. Keep completed courses under Unplaced studies, or remove them with their completions.",
    },
  },
  reset: {
    programme: {
      withoutCompletions: "This restores this programme's official content.",
      withCompletions:
        "This restores this programme's official content. Keep completed courses, or clear their completions too.",
    },
    module: {
      withoutCompletions: "This restores this module's official content.",
      withCompletions:
        "This restores this module's official content. Keep completed courses, or clear their completions too.",
    },
  },
};

/** Render one confirmation for removing or resetting a programme or module. */
export function ModuleRemoveDialog({
  open,
  name,
  hasCompletedCourses,
  operation,
  holderKind,
  busy = false,
  error = null,
  onCancel,
  onKeep,
  onRemove,
  returnFocus,
}: {
  open: boolean;
  name: string;
  /** Whether the removal or reset target holds completed courses. */
  hasCompletedCourses: boolean;
  /** `reset` shares this compact panel with the removal confirmation. */
  operation: "remove" | "reset";
  /** The nouns the title and the description use. */
  holderKind: "programme" | "module";
  busy?: boolean;
  error?: Error | null;
  onCancel(): void;
  /** The ordinary removal, or the ordinary reset that keeps completed courses. */
  onKeep(): void;
  /** The destructive removal, or `Reset all`, which drops the affected completions too. */
  onRemove(): void;
  returnFocus(): void;
}) {
  const { language, t } = useWording();
  usePhoneTabsOnClose(open);
  // The close animation keeps showing the content the confirmation opened with.
  const [retained, setRetained] = useState<Target | null>(null);
  const current: Target | null = open
    ? { name, hasCompletedCourses, operation, holderKind }
    : null;
  if (
    current &&
    (retained?.name !== current.name ||
      retained.hasCompletedCourses !== current.hasCompletedCourses ||
      retained.operation !== current.operation ||
      retained.holderKind !== current.holderKind)
  )
    setRetained(current);
  const shown = current ?? retained;
  const reset = shown?.operation === "reset";
  const description: UiTextKey | null = shown
    ? DESCRIPTIONS[shown.operation][shown.holderKind][
        shown.hasCompletedCourses ? "withCompletions" : "withoutCompletions"
      ]
    : null;
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
          <Dialog.Title>
            {reset
              ? shown?.holderKind === "programme"
                ? t("Reset programme “{name}”?", { name: shown?.name ?? name })
                : t("Reset module “{name}”?", { name: shown?.name ?? name })
              : shown?.holderKind === "programme"
                ? t("Delete programme “{name}”?", { name: shown?.name ?? name })
                : t("Delete module “{name}”?", { name: shown?.name ?? name })}
          </Dialog.Title>
          {description && (
            <Dialog.Description>{t(description)}</Dialog.Description>
          )}
          {error && <ErrorNotice error={error} language={language} />}
          <div className="dialog-foot module-remove-foot">
            <Dialog.Close asChild>
              <button className="dialog-cancel" type="button" disabled={busy}>
                {t("Cancel")}
              </button>
            </Dialog.Close>
            {reset ? (
              <>
                <button
                  className="dialog-cancel"
                  type="button"
                  disabled={busy}
                  onClick={onKeep}
                >
                  {t("Reset")}
                </button>
                {shown?.hasCompletedCourses && (
                  <button
                    className="dialog-confirm"
                    type="button"
                    disabled={busy}
                    onClick={onRemove}
                  >
                    {t("Reset all")}
                  </button>
                )}
              </>
            ) : (
              <>
                <button
                  className="dialog-cancel"
                  type="button"
                  disabled={busy}
                  onClick={onKeep}
                >
                  {t("Delete")}
                </button>
                {shown?.hasCompletedCourses && (
                  <button
                    className="dialog-confirm"
                    type="button"
                    disabled={busy}
                    onClick={onRemove}
                  >
                    {t("Delete all")}
                  </button>
                )}
              </>
            )}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
