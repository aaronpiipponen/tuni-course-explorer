/** Typed same-origin client for the public feedback definition, form report and submission. */
import { getJson, postJson } from "./http";

/** One bilingual text the configured definition holds. */
export interface FeedbackLocalizedText {
  en: string;
  fi: string;
}

/** One selectable answer option and its publication default when it declares one. */
export interface FeedbackSelectOption {
  value: string;
  label: FeedbackLocalizedText;
  publicIssueByDefault?: boolean | null;
}

/** One single-row or multiline text answer with its maximum character count. */
export interface FeedbackTextDefinition {
  kind: "text" | "textarea";
  id: string;
  label: FeedbackLocalizedText;
  required: boolean;
  maxLength: number;
}

/** One select answer with its ordered options. */
export interface FeedbackSelectDefinition {
  kind: "select";
  id: string;
  label: FeedbackLocalizedText;
  required: boolean;
  options: FeedbackSelectOption[];
}

/** One attachment answer with its permitted image types and upload limits. */
export interface FeedbackAttachmentDefinition {
  kind: "attachment";
  id: string;
  label: FeedbackLocalizedText;
  required: boolean;
  acceptedMimeTypes: string[];
  maxFiles: number;
  maxBytesPerFile: number;
}

/** One configured answer kind the form renders. */
export type FeedbackFieldDefinition =
  | FeedbackTextDefinition
  | FeedbackSelectDefinition
  | FeedbackAttachmentDefinition;

/** The configured field names a published GitHub issue takes its parts from. */
export interface FeedbackGithubIssueMapping {
  typeField: string;
  titleField: string;
  bodyFields: string[];
  attachmentField: string;
}

/** The ordered fields, the unchosen select placeholder and the issue mapping. */
export interface FeedbackDefinition {
  selectPlaceholder: FeedbackLocalizedText;
  fields: FeedbackFieldDefinition[];
  githubIssue: FeedbackGithubIssueMapping;
}

/** The current definition beside the configured destination metadata and body bound. */
export interface FeedbackFormReport {
  definition: FeedbackDefinition;
  repository: string;
  visibility: "public" | "private";
  max_request_bytes: number;
}

/** One attachment carrier: its configured field, its display filename and its base64 content. */
export interface FeedbackUploadCarrier {
  field_id: string;
  filename: string;
  content_base64: string;
}

/** One submission: its text and select answers, attachment carriers and explicit choice. */
export interface FeedbackSubmissionRequest {
  answers: Record<string, string | null>;
  attachments: FeedbackUploadCarrier[];
  public_issue: boolean;
}

/** The narrow committed outcome of one accepted submission. */
export interface FeedbackAcknowledgment {
  accepted: true;
  publication_state: "private" | "pending";
}

/** Read the current ordered form definition and its configured destination metadata. */
export function readFeedbackForm(
  signal?: AbortSignal,
): Promise<FeedbackFormReport> {
  return getJson<FeedbackFormReport>("/api/feedback/definition", signal);
}

/** Submit one validated form with its explicit publication choice. */
export function submitFeedback(
  body: FeedbackSubmissionRequest,
  signal?: AbortSignal,
): Promise<FeedbackAcknowledgment> {
  return postJson<FeedbackAcknowledgment>("/api/feedback", body, signal);
}
