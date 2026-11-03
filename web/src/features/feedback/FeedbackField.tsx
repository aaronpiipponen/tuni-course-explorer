/** One configured feedback answer control rendered from its current field definition. */
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { AnimatePresence, motion } from "framer-motion";
import type { DragEvent } from "react";
import type { FeedbackFieldDefinition } from "../../api/feedback";
import { useReducedMotion } from "../../shared/useReducedMotion";
import { useWording } from "../../shared/useWording";

/** One chosen attachment with a stable identity for its animating row. */
export interface ChosenFile {
  id: number;
  file: File;
}

/** The one easing the attachment rows share. */
const FILE_EASE: [number, number, number, number] = [0.22, 0.8, 0.2, 1];

/** The one chevron the text select and its menu share. */
function Chevron() {
  return (
    <svg
      className="feedback-select-chevron"
      viewBox="0 0 12 12"
      aria-hidden="true"
    >
      <path d="m2.5 4.5 3.5 3.5 3.5-3.5" />
    </svg>
  );
}

/** Render one text, select or attachment control with its field label and its field error. */
export function FeedbackField({
  field,
  language,
  placeholder,
  answer,
  files,
  onAnswer,
  onAddFiles,
  onRemoveFile,
  error,
  disabled,
}: {
  field: FeedbackFieldDefinition;
  language: "en" | "fi";
  placeholder: string;
  answer: string | null;
  files: readonly ChosenFile[];
  onAnswer(value: string | null): void;
  onAddFiles(files: File[]): void;
  onRemoveFile(id: number): void;
  error: string | null;
  disabled: boolean;
}) {
  const { t } = useWording();
  const reducedMotion = useReducedMotion();
  const label = field.label[language];
  const inputId = `feedback-field-${field.id}`;
  const labelId = `${inputId}-label`;
  const errorId = `${inputId}-error`;
  const describedBy = error === null ? undefined : errorId;
  const invalid = error === null ? undefined : true;

  if (field.kind === "attachment") {
    const drop = (event: DragEvent<HTMLLabelElement>) => {
      event.preventDefault();
      if (disabled) return;
      onAddFiles(Array.from(event.dataTransfer.files));
    };
    return (
      <div
        className="feedback-field"
        role="group"
        aria-labelledby={labelId}
        data-field-id={field.id}
      >
        <span className="feedback-label" id={labelId}>
          {label}
        </span>
        <label
          className="feedback-drop"
          onDrop={drop}
          onDragOver={(event) => event.preventDefault()}
        >
          <span className="feedback-drop-choose">{t("Choose images")}</span>
          <span className="feedback-drop-note">{t("or drop images here")}</span>
          <input
            className="feedback-file-input"
            type="file"
            aria-label={label}
            aria-invalid={invalid}
            aria-describedby={describedBy}
            accept={field.acceptedMimeTypes.join(",")}
            multiple={field.maxFiles > 1}
            disabled={disabled}
            onChange={(event) => {
              const selected = Array.from(event.target.files ?? []);
              event.target.value = "";
              onAddFiles(selected);
            }}
          />
        </label>
        <ul className="feedback-files">
          <AnimatePresence>
            {files.map((chosen) => (
              <motion.li
                key={chosen.id}
                className="feedback-file-row"
                initial={reducedMotion ? false : { height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={{
                  duration: reducedMotion ? 0 : 0.18,
                  ease: FILE_EASE,
                }}
              >
                <div className="feedback-file-card">
                  <span className="feedback-file-name">{chosen.file.name}</span>
                  <button
                    className="feedback-file-remove"
                    type="button"
                    aria-label={t("Remove {name}", {
                      name: chosen.file.name,
                    })}
                    disabled={disabled}
                    onClick={() => onRemoveFile(chosen.id)}
                  >
                    {t("Remove")}
                  </button>
                </div>
              </motion.li>
            ))}
          </AnimatePresence>
        </ul>
        {error !== null && (
          <p className="feedback-field-error" id={errorId} role="alert">
            {error}
          </p>
        )}
      </div>
    );
  }

  if (field.kind === "select") {
    const chosen =
      field.options.find((option) => option.value === answer) ?? null;
    return (
      <div className="feedback-field" data-field-id={field.id}>
        <span className="feedback-label" id={labelId}>
          {label}
        </span>
        <DropdownMenu.Root modal={false}>
          <DropdownMenu.Trigger asChild>
            <button
              className="feedback-select"
              id={inputId}
              type="button"
              aria-labelledby={labelId}
              aria-invalid={invalid}
              aria-describedby={describedBy}
              disabled={disabled}
            >
              <span
                className={`feedback-select-value${chosen === null ? " is-placeholder" : ""}`}
              >
                {chosen === null ? placeholder : chosen.label[language]}
              </span>
              <Chevron />
            </button>
          </DropdownMenu.Trigger>
          <DropdownMenu.Portal>
            <DropdownMenu.Content
              className="feedback-select-menu thin-scrollbar"
              sideOffset={4}
              align="start"
            >
              <DropdownMenu.RadioGroup
                value={answer ?? ""}
                onValueChange={(value) => onAnswer(value === "" ? null : value)}
              >
                {field.options.map((option) => (
                  <DropdownMenu.RadioItem
                    className="feedback-select-item"
                    key={option.value}
                    value={option.value}
                  >
                    {option.label[language]}
                  </DropdownMenu.RadioItem>
                ))}
              </DropdownMenu.RadioGroup>
            </DropdownMenu.Content>
          </DropdownMenu.Portal>
        </DropdownMenu.Root>
        {error !== null && (
          <p className="feedback-field-error" id={errorId} role="alert">
            {error}
          </p>
        )}
      </div>
    );
  }

  if (field.kind === "textarea") {
    return (
      <div className="feedback-field" data-field-id={field.id}>
        <label className="feedback-label" htmlFor={inputId}>
          {label}
        </label>
        <textarea
          className="feedback-textarea thin-scrollbar"
          id={inputId}
          rows={4}
          aria-invalid={invalid}
          aria-describedby={describedBy}
          required={field.required}
          disabled={disabled}
          value={answer ?? ""}
          onChange={(event) =>
            onAnswer(event.target.value === "" ? null : event.target.value)
          }
        />
        {error !== null && (
          <p className="feedback-field-error" id={errorId} role="alert">
            {error}
          </p>
        )}
      </div>
    );
  }

  return (
    <div className="feedback-field" data-field-id={field.id}>
      <label className="feedback-label" htmlFor={inputId}>
        {label}
      </label>
      <input
        className="feedback-input"
        id={inputId}
        type="text"
        aria-invalid={invalid}
        aria-describedby={describedBy}
        required={field.required}
        disabled={disabled}
        value={answer ?? ""}
        onChange={(event) =>
          onAnswer(event.target.value === "" ? null : event.target.value)
        }
      />
      {error !== null && (
        <p className="feedback-field-error" id={errorId} role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
