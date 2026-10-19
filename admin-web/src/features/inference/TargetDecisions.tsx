/**
 * The Target decisions panel: one explicit canonical target identity read and its durable decision.
 *
 * The input starts empty and no report is shown before a successful identity read. The decisions are
 * available only for the identity that read resolved: DONE and FAILED ask for confirmation first,
 * while NOTHING records immediately. A recorded decision replaces the report from its own command
 * result and then refreshes the retained-server summary.
 */
import { useState } from "react";
import { failureText, handleAdmissionFailure } from "../../api/http";
import { readTarget, recordDecision } from "../../api/inference";
import type {
  InferenceTargetDisposition,
  TargetDecisionToken,
} from "../../api/types";
import { ConfirmDialog } from "../../shared/ConfirmDialog";
import { FailureNotice, Panel, Row, Rows } from "../../shared/Panel";
import type { SessionAccess } from "../../shared/StagePanel";
import { wording } from "../../shared/wording";

/** The decision tokens the panel offers, in display order. */
const CHOICES: TargetDecisionToken[] = ["nothing", "done", "failed"];

function choiceText(choice: TargetDecisionToken): string {
  if (choice === "done") {
    return wording.inference.done;
  }
  if (choice === "failed") {
    return wording.inference.failed;
  }
  return wording.inference.nothing;
}

function decisionText(
  disposition: InferenceTargetDisposition["disposition"],
): string {
  return choiceText(disposition ?? "nothing");
}

/** Render the target decisions panel. */
export function TargetDecisions({
  session,
  onRefusal,
  onDecisionRecorded,
}: {
  session: SessionAccess;
  onRefusal: (status: number) => void;
  onDecisionRecorded: () => void;
}) {
  const detail = wording.inference;
  const [input, setInput] = useState("");
  const [resolved, setResolved] = useState<InferenceTargetDisposition | null>(
    null,
  );
  const [choice, setChoice] = useState<TargetDecisionToken>("nothing");
  const [failure, setFailure] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [confirming, setConfirming] = useState(false);

  const onSearch = async (): Promise<void> => {
    setPending(true);
    setFailure(null);
    try {
      const report = await readTarget(input, session.csrfToken);
      setResolved(report);
      setChoice(report.disposition ?? "nothing");
    } catch (error) {
      setResolved(null);
      setFailure(failureText(error, wording.readFailed));
      handleAdmissionFailure(error, onRefusal);
    } finally {
      setPending(false);
    }
  };

  const onRecord = async (): Promise<void> => {
    if (resolved === null) {
      return;
    }
    setPending(true);
    setFailure(null);
    try {
      const report = await recordDecision(
        resolved.target_group_id,
        choice,
        session.csrfToken,
      );
      setResolved(report);
      setChoice(report.disposition ?? "nothing");
      onDecisionRecorded();
    } catch (error) {
      setFailure(failureText(error, wording.writeFailed));
      handleAdmissionFailure(error, onRefusal);
    } finally {
      setPending(false);
    }
  };

  const ready = resolved !== null && input === resolved.target_group_id;
  return (
    <Panel title={detail.targetDecisions}>
      <div className="lookup">
        <input
          aria-label={detail.targetInput}
          value={input}
          spellCheck={false}
          onChange={(event) => setInput(event.target.value)}
        />
        <button
          className="btn"
          type="button"
          disabled={pending}
          onClick={() => void onSearch()}
        >
          {detail.search}
        </button>
      </div>
      <FailureNotice text={failure} />
      {resolved === null ? (
        <p className="note">{detail.noTarget}</p>
      ) : (
        <>
          <Rows>
            <Row label={detail.dataset} value={<b>{resolved.dataset_id}</b>} />
            <Row
              label={detail.canonicalGroup}
              value={<code>{resolved.target_group_id}</code>}
            />
            <Row
              label={detail.officialCode}
              value={resolved.course_code ?? wording.unknown}
            />
            <Row
              label={detail.englishName}
              value={resolved.course_name ?? wording.unknown}
            />
            <Row
              label={detail.decision}
              value={
                <span className="tag">
                  {decisionText(resolved.disposition)}
                </span>
              }
            />
          </Rows>
          {ready ? null : <p className="note">{detail.editedInput}</p>}
        </>
      )}
      <div className="decide">
        <button
          className="btn p"
          type="button"
          disabled={!ready || pending}
          onClick={() =>
            choice === "nothing" ? void onRecord() : setConfirming(true)
          }
        >
          {detail.recordDecision}
        </button>
        <div className="choice">
          {CHOICES.map((option) => (
            <button
              key={choiceText(option)}
              className={`chip${option === choice ? " on" : ""}`}
              type="button"
              aria-pressed={option === choice}
              disabled={!ready || pending}
              onClick={() => setChoice(option)}
            >
              {choiceText(option)}
            </button>
          ))}
        </div>
      </div>
      <ConfirmDialog
        open={confirming}
        title={detail.recordDecision}
        message={
          choice === "failed" ? detail.decisionFailed : detail.decisionDone
        }
        pending={pending}
        onCancel={() => setConfirming(false)}
        onConfirm={() => {
          setConfirming(false);
          void onRecord();
        }}
      />
    </Panel>
  );
}
