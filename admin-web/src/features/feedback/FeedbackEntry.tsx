/**
 * One saved feedback submission: its configured answers in definition order and its operational
 * identity, current publication outcome, issue link and named local deletion.
 *
 * Only the current definition's fields are rendered. An answer whose configured option is gone
 * shows its stored value as text, and an attachment whose field is gone is omitted with it. A
 * recorded safe failure is shown as its fixed description, never as a stored message.
 */
import { useState } from "react";
import { readFeedbackAttachment } from "../../api/feedback";
import { failureText, handleAdmissionFailure } from "../../api/http";
import type {
  FeedbackDefinition,
  StoredAttachment,
  StoredFeedback,
} from "../../api/types";
import { ConfirmDialog } from "../../shared/ConfirmDialog";
import { moment } from "../../shared/format";
import { FailureNotice } from "../../shared/Panel";
import type { SessionAccess } from "../../shared/StagePanel";
import { wording } from "../../shared/wording";
import { buildZip } from "../../shared/zip";
import { FeedbackAttachments } from "./FeedbackAttachments";

const stateClass: Record<StoredFeedback["publication_state"], string> = {
  private: "tag no",
  pending: "tag",
  published: "tag ok",
  partial: "tag",
  failed: "tag no",
  uncertain: "tag",
};

/** Decode one standard base64 carrier into the bytes the archive stores. */
function base64Bytes(value: string): Uint8Array {
  const binary = atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return bytes;
}

/** Render one submission's answers and its one named deletion confirmation. */
export function FeedbackEntry({
  definition,
  submission,
  session,
  onRefusal,
  pending,
  onDelete,
}: {
  definition: FeedbackDefinition;
  submission: StoredFeedback;
  session: SessionAccess;
  onRefusal: (status: number) => void;
  pending: boolean;
  onDelete(submission: StoredFeedback): void;
}) {
  const detail = wording.feedback;
  const [confirming, setConfirming] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [downloadFailure, setDownloadFailure] = useState<string | null>(null);
  const time = moment(submission.created_at);
  const attachmentsByField = new Map<string, StoredAttachment[]>();
  for (const attachment of submission.attachments) {
    const list = attachmentsByField.get(attachment.field_id) ?? [];
    list.push(attachment);
    attachmentsByField.set(attachment.field_id, list);
  }
  const downloadAttachments = async (): Promise<void> => {
    if (downloading) return;
    setDownloading(true);
    setDownloadFailure(null);
    try {
      const entries = await Promise.all(
        submission.attachments.map(async (attachment) => {
          const report = await readFeedbackAttachment(
            submission.id,
            attachment.id,
            session.csrfToken,
          );
          return {
            name: attachment.filename,
            data: base64Bytes(report.content_base64),
          };
        }),
      );
      const url = URL.createObjectURL(buildZip(entries));
      const link = document.createElement("a");
      link.href = url;
      link.download = `feedback-${submission.id}.zip`;
      document.body.append(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) {
      setDownloadFailure(failureText(error, wording.readFailed));
      handleAdmissionFailure(error, onRefusal);
    } finally {
      setDownloading(false);
    }
  };

  return (
    <article className="feedback-entry">
      <div className="feedback-entry-meta">
        <span>
          <b>{detail.id}</b> <code>{submission.id}</code>
        </span>
        <span className="feedback-meta-time">
          <b>{detail.created}</b>
          <time>{time}</time>
        </span>
        <span className={stateClass[submission.publication_state]}>
          {detail[submission.publication_state]}
        </span>
        {submission.issue_url !== null && (
          <a
            href={submission.issue_url}
            target="_blank"
            rel="noopener noreferrer"
          >
            {detail.issueLink}
          </a>
        )}
        {submission.publication_failure !== null && (
          <span>
            {detail.publicationFailure[submission.publication_failure]}
          </span>
        )}
        <div className="feedback-entry-actions">
          {submission.attachments.length > 0 && (
            <button
              className="btn xs"
              type="button"
              disabled={downloading}
              onClick={() => void downloadAttachments()}
            >
              <span className="feedback-swap-label">
                <span aria-hidden={downloading}>
                  {detail.downloadAttachments.replace(
                    "{count}",
                    String(submission.attachments.length),
                  )}
                </span>
                <span aria-hidden={!downloading}>
                  {detail.preparingDownload}
                </span>
              </span>
            </button>
          )}
          <button
            className="btn xs danger feedback-delete"
            type="button"
            disabled={pending}
            onClick={() => setConfirming(true)}
          >
            {detail.delete}
          </button>
        </div>
      </div>
      <FailureNotice text={downloadFailure} />
      <dl className="feedback-answers">
        {definition.fields.map((field) => {
          if (field.kind === "attachment") {
            const attachments = attachmentsByField.get(field.id) ?? [];
            if (attachments.length === 0) return null;
            return (
              <div
                className="feedback-answer feedback-answer-attachment feedback-answer-images"
                key={field.id}
              >
                <dt>{field.label.en}</dt>
                <dd>
                  <FeedbackAttachments
                    feedbackId={submission.id}
                    attachments={attachments}
                    session={session}
                    onRefusal={onRefusal}
                  />
                </dd>
              </div>
            );
          }
          const value = submission.answers[field.id] ?? null;
          if (field.kind === "select") {
            const option = field.options.find(
              (candidate) => candidate.value === value,
            );
            return (
              <div
                className="feedback-answer feedback-answer-select"
                key={field.id}
              >
                <dt>{field.label.en}</dt>
                <dd>
                  {value === null
                    ? definition.selectPlaceholder.en
                    : (option?.label.en ?? value)}
                </dd>
              </div>
            );
          }
          if (field.kind === "textarea") {
            return (
              <div
                className="feedback-answer feedback-answer-textarea"
                key={field.id}
              >
                <dt>{field.label.en}</dt>
                <dd>
                  <textarea
                    className="feedback-answer-textarea"
                    readOnly
                    rows={3}
                    aria-label={field.label.en}
                    value={value ?? ""}
                  />
                </dd>
              </div>
            );
          }
          return (
            <div
              className="feedback-answer feedback-answer-text"
              key={field.id}
            >
              <dt>{field.label.en}</dt>
              <dd className="feedback-answer-text">{value ?? ""}</dd>
            </div>
          );
        })}
      </dl>
      <ConfirmDialog
        open={confirming}
        title={detail.deleteTitle}
        message={detail.deleteMessage
          .replace("{id}", submission.id)
          .replace("{time}", time)}
        pending={pending}
        onCancel={() => setConfirming(false)}
        onConfirm={() => {
          setConfirming(false);
          onDelete(submission);
        }}
      />
    </article>
  );
}
