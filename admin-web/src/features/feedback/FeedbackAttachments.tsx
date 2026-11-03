/**
 * One field's stored images with one explicit read each.
 *
 * Every attachment keeps its control in one fixed row at the top, in definition order, and a
 * rendered control is highlighted instead of moving. Images appear below that row with their own
 * filename underneath, so a rendered image is always identified and toggling one never reorders the
 * controls. The store holds PNG and JPEG images alone, so every attachment carries a control. The
 * reads are transient and run only on those explicit controls.
 */
import { useEffect, useRef, useState } from "react";
import { readFeedbackAttachment } from "../../api/feedback";
import { failureText, handleAdmissionFailure } from "../../api/http";
import type {
  FeedbackAttachmentReport,
  StoredAttachment,
} from "../../api/types";
import { FailureNotice } from "../../shared/Panel";
import type { SessionAccess } from "../../shared/StagePanel";
import { wording } from "../../shared/wording";

interface AttachmentState {
  report: FeedbackAttachmentReport | null;
  loading: boolean;
}

/** Render one image with its filename beneath, unfolding on mount and on close. */
function RenderedImage({
  attachment,
  report,
  closing,
}: {
  attachment: StoredAttachment;
  report: FeedbackAttachmentReport;
  closing: boolean;
}) {
  const [shown, setShown] = useState(false);
  useEffect(() => {
    const frame = window.requestAnimationFrame(() => setShown(true));
    return () => window.cancelAnimationFrame(frame);
  }, []);
  return (
    <figure className={`feedback-figure${shown && !closing ? " shown" : ""}`}>
      <div className="feedback-figure-clip">
        <div className="feedback-figure-content">
          <img
            className="feedback-image-preview"
            src={`data:${report.attachment.mime_type};base64,${report.content_base64}`}
            alt={attachment.filename}
          />
          <figcaption className="feedback-image-name">
            {attachment.filename}
          </figcaption>
        </div>
      </div>
    </figure>
  );
}

/** Render one field's stored images with their fixed controls and their previews. */
export function FeedbackAttachments({
  feedbackId,
  attachments,
  session,
  onRefusal,
}: {
  feedbackId: string;
  attachments: StoredAttachment[];
  session: SessionAccess;
  onRefusal: (status: number) => void;
}) {
  const [states, setStates] = useState<Record<string, AttachmentState>>({});
  const [closing, setClosing] = useState<Record<string, boolean>>({});
  const [failure, setFailure] = useState<string | null>(null);
  const controllers = useRef(new Map<string, AbortController>());
  const closers = useRef(new Map<string, number>());

  useEffect(
    () => () => {
      for (const controller of controllers.current.values()) {
        controller.abort();
      }
      controllers.current.clear();
      for (const timer of closers.current.values()) {
        window.clearTimeout(timer);
      }
      closers.current.clear();
    },
    [],
  );

  const load = (attachment: StoredAttachment): void => {
    controllers.current.get(attachment.id)?.abort();
    const controller = new AbortController();
    controllers.current.set(attachment.id, controller);
    setStates((previous) => ({
      ...previous,
      [attachment.id]: {
        report: previous[attachment.id]?.report ?? null,
        loading: true,
      },
    }));
    setFailure(null);
    void (async () => {
      try {
        const report = await readFeedbackAttachment(
          feedbackId,
          attachment.id,
          session.csrfToken,
          controller.signal,
        );
        if (controller.signal.aborted) return;
        setStates((previous) => ({
          ...previous,
          [attachment.id]: { report, loading: false },
        }));
      } catch (error) {
        if (controller.signal.aborted) return;
        setStates((previous) => ({
          ...previous,
          [attachment.id]: {
            report: previous[attachment.id]?.report ?? null,
            loading: false,
          },
        }));
        setFailure(failureText(error, wording.readFailed));
        handleAdmissionFailure(error, onRefusal);
      }
    })();
  };

  const close = (attachment: StoredAttachment): void => {
    if (closing[attachment.id]) return;
    setClosing((previous) => ({ ...previous, [attachment.id]: true }));
    const timer = window.setTimeout(() => {
      closers.current.delete(attachment.id);
      setStates((previous) => ({
        ...previous,
        [attachment.id]: { report: null, loading: false },
      }));
      setClosing((previous) => {
        const next = { ...previous };
        delete next[attachment.id];
        return next;
      });
    }, 240);
    closers.current.set(attachment.id, timer);
  };

  const toggle = (attachment: StoredAttachment): void => {
    if (closing[attachment.id]) return;
    if (states[attachment.id]?.report) {
      close(attachment);
      return;
    }
    load(attachment);
  };

  return (
    <div className="feedback-attachments">
      <div className="feedback-attachment-controls">
        {attachments.map((attachment) => {
          const loading = states[attachment.id]?.loading ?? false;
          const rendered = Boolean(states[attachment.id]?.report);
          return (
            <button
              key={attachment.id}
              className={`btn xs${rendered ? " on" : ""}`}
              type="button"
              aria-pressed={rendered}
              disabled={loading}
              aria-label={wording.feedback.viewAttachment.replace(
                "{name}",
                attachment.filename,
              )}
              onClick={() => toggle(attachment)}
            >
              <span className="feedback-swap-label">
                <span aria-hidden={loading}>{attachment.filename}</span>
                <span aria-hidden={!loading}>{wording.reading}</span>
              </span>
            </button>
          );
        })}
      </div>
      {attachments.map((attachment) => {
        const report = states[attachment.id]?.report;
        if (!report) return null;
        return (
          <RenderedImage
            key={attachment.id}
            attachment={attachment}
            report={report}
            closing={closing[attachment.id] ?? false}
          />
        );
      })}
      <FailureNotice text={failure} />
    </div>
  );
}
