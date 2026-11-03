/** The Feedback tab's fixed listing, protected attachment read and named local deletion. */
import { runCommand } from "./http";
import type {
  FeedbackAttachmentReport,
  FeedbackDeletionReport,
  FeedbackListReport,
} from "./types";

/** Run the fixed feedback listing with its optional search text and select filters. */
export function readFeedbackList(
  input: { query: string | null; filters: Record<string, string> },
  csrfToken: string,
  signal?: AbortSignal,
  automatic?: boolean,
): Promise<FeedbackListReport> {
  return runCommand<FeedbackListReport>("/api/feedback/list", {
    body: { query: input.query, filters: input.filters },
    csrfToken,
    signal,
    automatic,
  });
}

/** Read one stored image of one submission through both stored identities. */
export function readFeedbackAttachment(
  feedbackId: string,
  attachmentId: string,
  csrfToken: string,
  signal?: AbortSignal,
): Promise<FeedbackAttachmentReport> {
  return runCommand<FeedbackAttachmentReport>("/api/feedback/attachment", {
    body: { feedback_id: feedbackId, attachment_id: attachmentId },
    csrfToken,
    signal,
  });
}

/** Delete exactly one named submission with its stored images. */
export function deleteFeedback(
  feedbackId: string,
  csrfToken: string,
): Promise<FeedbackDeletionReport> {
  return runCommand<FeedbackDeletionReport>("/api/feedback/delete", {
    body: { feedback_id: feedbackId },
    csrfToken,
  });
}
