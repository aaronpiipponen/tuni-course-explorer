/** Standalone ordered feedback page with transient answers, explicit consent and saved outcomes. */
import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { AnimatePresence, motion } from "framer-motion";
import { AnimatedHeight } from "../../shared/AnimatedHeight";
import {
  readFeedbackForm,
  submitFeedback,
  type FeedbackAcknowledgment,
  type FeedbackDefinition,
  type FeedbackFieldDefinition,
  type FeedbackFormReport,
  type FeedbackSubmissionRequest,
  type FeedbackUploadCarrier,
} from "../../api/feedback";
import { ApiError } from "../../api/http";
import { ConfirmDialog } from "../../shared/ConfirmDialog";
import { useReducedMotion } from "../../shared/useReducedMotion";
import { useWording } from "../../shared/useWording";
import { FeedbackField, type ChosenFile } from "./FeedbackField";
import { derivedPublicationChoice } from "./publication";
import "./feedback.css";

type Answers = Record<string, string | null>;
type FileLists = Record<string, ChosenFile[]>;
type FieldErrors = Record<string, string | null>;

/** The one easing the view exchange shares. */
const VIEW_EASE: [number, number, number, number] = [0.22, 0.8, 0.2, 1];

/** Read one chosen file as standard base64 without its data URL prefix. */
function readBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result;
      if (typeof result !== "string") {
        reject(new Error("the file reader produced no data URL"));
        return;
      }
      const comma = result.indexOf(",");
      if (comma < 0) {
        reject(new Error("the file reader produced no data URL"));
        return;
      }
      resolve(result.slice(comma + 1));
    };
    reader.onerror = () =>
      reject(reader.error ?? new Error("the file could not be read"));
    reader.readAsDataURL(file);
  });
}

/** Return the ordered, de-duplicated localized labels a published issue includes. */
function designatedLabels(
  definition: FeedbackDefinition,
  language: "en" | "fi",
): { fields: string; attachment: string } {
  const byId = new Map(
    definition.fields.map((field) => [field.id, field] as const),
  );
  const ids = [
    definition.githubIssue.typeField,
    definition.githubIssue.titleField,
    ...definition.githubIssue.bodyFields,
  ];
  const fields = [...new Set(ids)]
    .map((id) => byId.get(id)?.label[language] ?? id)
    .join(", ");
  const attachment =
    byId.get(definition.githubIssue.attachmentField)?.label[language] ??
    definition.githubIssue.attachmentField;
  return { fields, attachment };
}

/** Return whether one answer is present for a required text or select field. */
function answered(
  field: FeedbackFieldDefinition,
  value: string | null,
): boolean {
  if (field.kind === "attachment") return false;
  return value !== null && value.trim() !== "";
}

/** Render the feedback page and its one transient form. */
export function FeedbackPage({ returnToApp }: { returnToApp: () => void }) {
  const { language, t } = useWording();
  const [report, setReport] = useState<FeedbackFormReport | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [answers, setAnswers] = useState<Answers>({});
  const [files, setFiles] = useState<FileLists>({});
  const [manualChoice, setManualChoice] = useState<boolean | null>(null);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [confirmationOpen, setConfirmationOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [acknowledgment, setAcknowledgment] =
    useState<FeedbackAcknowledgment | null>(null);
  const inFlight = useRef(false);
  const nextFileId = useRef(0);
  const submitButton = useRef<HTMLButtonElement>(null);
  const originalTitle = useRef(document.title);
  const reducedMotion = useReducedMotion();
  const page = useRef<HTMLDivElement>(null);

  useEffect(() => {
    document.title = t("Feedback");
  }, [t]);
  useEffect(
    () => () => {
      document.title = originalTitle.current;
    },
    [],
  );

  useEffect(() => {
    const controller = new AbortController();
    readFeedbackForm(controller.signal)
      .then((form) => {
        if (!controller.signal.aborted) setReport(form);
      })
      .catch(() => {
        if (!controller.signal.aborted) setLoadFailed(true);
      });
    return () => controller.abort();
  }, []);

  const definition = report?.definition ?? null;
  const publication =
    definition === null
      ? true
      : (manualChoice ?? derivedPublicationChoice(definition, answers));

  const setAnswer = (fieldId: string, value: string | null): void => {
    setAnswers((previous) => ({ ...previous, [fieldId]: value }));
    setFieldErrors((previous) =>
      previous[fieldId] ? { ...previous, [fieldId]: null } : previous,
    );
  };

  const addFiles = (
    field: Extract<FeedbackFieldDefinition, { kind: "attachment" }>,
    selected: File[],
  ): void => {
    const existing = files[field.id] ?? [];
    let error: string | null = null;
    if (existing.length + selected.length > field.maxFiles) {
      error = t("Too many images for {field}. Limit: {limit}.", {
        field: field.label[language],
        limit: field.maxFiles,
      });
    } else {
      for (const file of selected) {
        if (file.size > field.maxBytesPerFile) {
          error = t(
            "An image for {field} exceeds the size limit of {limit} bytes.",
            { field: field.label[language], limit: field.maxBytesPerFile },
          );
          break;
        }
        if (!field.acceptedMimeTypes.includes(file.type)) {
          error = t("Choose a PNG or JPEG image for {field}.", {
            field: field.label[language],
          });
          break;
        }
      }
    }
    if (error !== null) {
      setFieldErrors((previous) => ({ ...previous, [field.id]: error }));
      return;
    }
    const added = selected.map((file) => ({
      id: (nextFileId.current += 1),
      file,
    }));
    setFiles((previous) => ({
      ...previous,
      [field.id]: [...(previous[field.id] ?? []), ...added],
    }));
    setFieldErrors((previous) =>
      previous[field.id] ? { ...previous, [field.id]: null } : previous,
    );
  };

  const removeFile = (fieldId: string, id: number): void => {
    setFiles((previous) => ({
      ...previous,
      [fieldId]: (previous[fieldId] ?? []).filter((item) => item.id !== id),
    }));
    setFieldErrors((previous) =>
      previous[fieldId] ? { ...previous, [fieldId]: null } : previous,
    );
  };

  const validate = (current: FeedbackDefinition): boolean => {
    const errors: FieldErrors = {};
    for (const field of current.fields) {
      if (field.kind === "attachment") {
        if (field.required && (files[field.id]?.length ?? 0) === 0) {
          errors[field.id] = t("Add an image for this required question.");
        }
        continue;
      }
      const value = answers[field.id] ?? null;
      if (field.required && !answered(field, value)) {
        errors[field.id] = t("Answer this required question.");
        continue;
      }
      if (
        value !== null &&
        field.kind !== "select" &&
        value.length > field.maxLength
      ) {
        errors[field.id] = t(
          "The answer is too long. Maximum length: {limit} characters.",
          { limit: field.maxLength },
        );
      }
    }
    setFieldErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const buildRequest = async (
    current: FeedbackDefinition,
    publicIssue: boolean,
  ): Promise<FeedbackSubmissionRequest> => {
    const answerValues: Answers = {};
    const attachments: FeedbackUploadCarrier[] = [];
    for (const field of current.fields) {
      if (field.kind === "attachment") {
        for (const chosen of files[field.id] ?? []) {
          attachments.push({
            field_id: field.id,
            filename: chosen.file.name,
            content_base64: await readBase64(chosen.file),
          });
        }
      } else {
        answerValues[field.id] = answers[field.id] ?? null;
      }
    }
    return {
      answers: answerValues,
      attachments,
      public_issue: publicIssue,
    };
  };

  const startSubmit = async (publicIssue: boolean): Promise<void> => {
    if (inFlight.current || report === null) return;
    inFlight.current = true;
    setSubmitting(true);
    setFormError(null);
    try {
      const body = await buildRequest(report.definition, publicIssue);
      const byteLength = new TextEncoder().encode(JSON.stringify(body)).length;
      if (byteLength > report.max_request_bytes) {
        setFormError(
          t("Feedback is too large. Remove images or shorten the answers."),
        );
        return;
      }
      setAcknowledgment(await submitFeedback(body));
    } catch (error) {
      setFormError(
        error instanceof ApiError && error.status === 429
          ? t("Too many feedback submissions. Try again later.")
          : t("Could not submit feedback. Your answers are still in the form."),
      );
    } finally {
      inFlight.current = false;
      setSubmitting(false);
    }
  };

  const requestSubmit = (): void => {
    if (submitting || definition === null) return;
    if (!validate(definition)) return;
    setConfirmationOpen(true);
  };

  const returnFocus = (): void => {
    if (submitButton.current?.isConnected) submitButton.current.focus();
  };

  const returnLink = (
    <a
      className="feedback-return"
      href="/"
      onClick={(event) => {
        event.preventDefault();
        returnToApp();
      }}
    >
      {t("Return to app")}
    </a>
  );
  // The view the page exchanges, named before the loading branch so the effect and the exchange
  // read one value.
  const view =
    acknowledgment !== null ? "saved" : submitting ? "submitting" : "form";

  useLayoutEffect(() => {
    if (page.current && page.current.scrollTop > 0)
      page.current.scrollTo({
        top: 0,
        behavior: reducedMotion ? "instant" : "smooth",
      });
  }, [view, reducedMotion]);

  if (report === null) {
    return (
      <div className="feedback-page thin-scrollbar">
        <main className="feedback-shell">
          {returnLink}
          <h1>{t("Feedback")}</h1>
          {loadFailed ? (
            <p className="feedback-error" role="alert">
              {t("Could not load feedback form. Reload the page to try again.")}
            </p>
          ) : (
            <p className="feedback-loading">{t("Loading feedback form…")}</p>
          )}
        </main>
      </div>
    );
  }

  let content: ReactNode;
  if (acknowledgment !== null) {
    content = (
      <>
        {returnLink}
        <h1>{t("Feedback saved")}</h1>
        <p className="feedback-outcome">
          {acknowledgment.publication_state === "pending"
            ? t("GitHub publication pending")
            : t("Saved as private feedback")}
        </p>
      </>
    );
  } else if (submitting) {
    content = (
      <>
        {returnLink}
        <h1>{t("Feedback")}</h1>
        <p className="feedback-loading">{t("Submitting feedback…")}</p>
      </>
    );
  } else {
    const labels = designatedLabels(report.definition, language);
    const toggleLabel =
      report.visibility === "public"
        ? t("Create public GitHub issue")
        : t("Create GitHub issue in a private repository");
    const confirmationTitle = !publication
      ? t("Submit feedback?")
      : report.visibility === "public"
        ? t("Create public GitHub issue?")
        : t("Create GitHub issue in a private repository?");
    const confirmationBody = !publication
      ? t(
          "Save this feedback privately? No GitHub issue is created and the feedback is saved on this site.",
        )
      : report.visibility === "public"
        ? t(
            "Create a public GitHub issue in {repository} with {fields} and any images in {attachment}? Other answers stay private. Turn off the GitHub issue toggle to save private feedback without creating an issue.",
            {
              repository: report.repository,
              fields: labels.fields,
              attachment: labels.attachment,
            },
          )
        : t(
            "Create a GitHub issue in the private repository {repository} with {fields} and any images in {attachment}? Other answers stay private. Turn off the GitHub issue toggle to save private feedback without creating an issue.",
            {
              repository: report.repository,
              fields: labels.fields,
              attachment: labels.attachment,
            },
          );
    content = (
      <>
        {returnLink}
        <form
          className="feedback-form"
          noValidate
          onSubmit={(event) => {
            event.preventDefault();
            requestSubmit();
          }}
        >
          <h1>{t("Feedback")}</h1>
          {report.definition.fields.map((field) => (
            <FeedbackField
              field={field}
              key={field.id}
              language={language}
              placeholder={report.definition.selectPlaceholder[language]}
              answer={answers[field.id] ?? null}
              files={files[field.id] ?? []}
              onAnswer={(value) => setAnswer(field.id, value)}
              onAddFiles={(selected) =>
                field.kind === "attachment"
                  ? addFiles(field, selected)
                  : undefined
              }
              onRemoveFile={(id) =>
                field.kind === "attachment"
                  ? removeFile(field.id, id)
                  : undefined
              }
              error={fieldErrors[field.id] ?? null}
              disabled={submitting}
            />
          ))}
          <section className="feedback-publication">
            <label className="feedback-toggle">
              <input
                type="checkbox"
                checked={publication}
                disabled={submitting}
                onChange={(event) => setManualChoice(event.target.checked)}
              />
              <span>{toggleLabel}</span>
            </label>
            <p className="feedback-explanation">
              {t(
                "The GitHub issue includes {fields} and any images in {attachment}. Other answers stay private.",
                {
                  fields: labels.fields,
                  attachment: labels.attachment,
                },
              )}
            </p>
          </section>
          {formError !== null && (
            <p className="feedback-error" role="alert">
              {formError}
            </p>
          )}
          <div className="feedback-actions">
            <button
              ref={submitButton}
              className="feedback-submit"
              type="submit"
              disabled={submitting}
            >
              {submitting ? t("Submitting feedback…") : t("Submit feedback")}
            </button>
          </div>
        </form>
        <ConfirmDialog
          open={confirmationOpen}
          title={confirmationTitle}
          description={confirmationBody}
          confirmLabel={
            publication ? t("Submit and create issue") : t("Submit feedback")
          }
          onCancel={() => setConfirmationOpen(false)}
          onConfirm={() => {
            setConfirmationOpen(false);
            void startSubmit(publication);
          }}
          returnFocus={returnFocus}
        />
      </>
    );
  }

  return (
    <div className="feedback-page thin-scrollbar" ref={page}>
      <AnimatedHeight>
        <AnimatePresence mode="wait">
          <motion.main
            key={view}
            className="feedback-shell"
            initial={{ opacity: 0, y: reducedMotion ? 0 : 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{
              duration: reducedMotion ? 0 : 0.26,
              ease: VIEW_EASE,
            }}
          >
            {content}
          </motion.main>
        </AnimatePresence>
      </AnimatedHeight>
    </div>
  );
}
