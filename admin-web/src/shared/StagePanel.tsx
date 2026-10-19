/**
 * One preparation stage panel: its automatic status read, its measured progress and its four
 * lifecycle actions.
 *
 * The panel invokes only its own stage's fixed action, so no action chains several stages. A stop
 * asks for confirmation naming that stage. A successful action presents the status it returned, and
 * a failed action stays visible in the panel.
 */
import { useCallback, useState } from "react";
import {
  readStageStatus,
  runStageAction,
  type PreparationStage,
} from "../api/preparation";
import { failureText, handleAdmissionFailure } from "../api/http";
import type {
  LifecycleAction,
  LifecycleStatus,
  WorkerControllerStatus,
} from "../api/types";
import { AutoMarker } from "./AutoMarker";
import { ConfirmDialog } from "./ConfirmDialog";
import { count, humanDuration, percent, rate, stateText } from "./format";
import { FailureNotice, Panel, Row, Rows } from "./Panel";
import { usePanelRead } from "./usePanelRead";
import { wording } from "./wording";

/** The session facts every authenticated panel request needs. */
export interface SessionAccess {
  csrfToken: string;
  pollSeconds: number;
}

/** The shared lifecycle action row of one stage panel. */
export function StageActions({
  stageLabel,
  pending,
  failure,
  onAction,
}: {
  stageLabel: string;
  pending: boolean;
  failure: string | null;
  onAction: (action: LifecycleAction) => void;
}) {
  const [confirming, setConfirming] = useState(false);
  const actions: LifecycleAction[] = ["start", "pause", "resume", "stop"];
  return (
    <>
      <div className="acts">
        {actions.map((action) => (
          <button
            key={action}
            className={`btn${action === "start" ? " p" : ""}${action === "stop" ? " danger" : ""}`}
            type="button"
            disabled={pending}
            onClick={() =>
              action === "stop" ? setConfirming(true) : onAction(action)
            }
          >
            {wording.action[action]}
          </button>
        ))}
      </div>
      <FailureNotice text={failure} />
      <ConfirmDialog
        open={confirming}
        title={`${wording.action.stop} ${stageLabel}`}
        message={wording.stopConfirm.replace("{stage}", stageLabel)}
        pending={pending}
        onCancel={() => setConfirming(false)}
        onConfirm={() => {
          setConfirming(false);
          onAction("stop");
        }}
      />
    </>
  );
}

/** Render one preparation stage's status panel with its own actions. */
export function StagePanel({
  stage,
  session,
  onRefusal,
}: {
  stage: PreparationStage;
  session: SessionAccess;
  onRefusal: (status: number) => void;
}) {
  const [actionFailure, setActionFailure] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const read = useCallback(
    (signal: AbortSignal, automatic: boolean) =>
      readStageStatus(stage, signal, automatic),
    [stage],
  );
  const panel = usePanelRead(read, {
    pollSeconds: session.pollSeconds,
    enabled: true,
    onRefusal,
    failureTextValue: wording.readFailed,
  });

  const onAction = async (action: LifecycleAction): Promise<void> => {
    setPending(true);
    setActionFailure(null);
    try {
      const result = await runStageAction(stage, action, session.csrfToken);
      panel.apply(result);
    } catch (error) {
      if (handleAdmissionFailure(error, onRefusal)) {
        return;
      }
      setActionFailure(failureText(error, wording.writeFailed));
    } finally {
      setPending(false);
    }
  };

  const status = panel.report;
  const stageLabel = wording.stage[stage];
  return (
    <Panel
      title={stageLabel}
      span={4}
      marker={
        <AutoMarker
          reading={panel.loading}
          lastSuccess={panel.lastSuccess}
          label={stageLabel}
        />
      }
    >
      <FailureNotice text={panel.failure} />
      {status === null ? null : (
        <>
          <Rows>
            <Row
              label={wording.row.state}
              value={stateText(status.lifecycle)}
            />
            <Row
              label={wording.row.session}
              value={status.session_id ?? wording.unknown}
            />
            <Row
              label={wording.row.revision}
              value={<code>{status.revision ?? wording.unknown}</code>}
            />
            <Row
              label={wording.row.host}
              value={
                stage === "translation"
                  ? wording.row.worker
                  : wording.row.server
              }
            />
            <Row
              label={wording.row.activeTime}
              value={humanDuration(status.active_seconds)}
            />
            <Row
              label={wording.row.rate}
              value={rate(status.items_per_second)}
            />
            <Row
              label={wording.row.eta}
              value={humanDuration(status.eta_seconds)}
            />
            <ProgressRows stage={stage} status={status} />
          </Rows>
          <ProgressBar stage={stage} status={status} />
          <StageActions
            stageLabel={stageLabel}
            pending={pending}
            failure={actionFailure}
            onAction={(action) => void onAction(action)}
          />
        </>
      )}
    </Panel>
  );
}

function ProgressRows({
  stage,
  status,
}: {
  stage: PreparationStage;
  status: LifecycleStatus;
}) {
  const progress = status.progress;
  if (progress === null) {
    return null;
  }
  if (stage === "ingestion" && progress.kind === "ingestion") {
    return (
      <>
        <Row
          label={wording.row.responses}
          value={count(progress.response_count)}
        />
        <Row
          label={wording.row.verifiedResponses}
          value={count(progress.verified_response_count)}
        />
        {progress.verification_total === null ? null : (
          <Row
            label={wording.row.verificationTotal}
            value={count(progress.verification_total)}
          />
        )}
        <Row
          label={wording.row.normalized}
          value={progress.normalized ? wording.yes : wording.no}
        />
      </>
    );
  }
  if (stage === "embedding" && progress.kind === "embedding") {
    return (
      <>
        <Row
          label={wording.row.desired}
          value={count(progress.desired_count)}
        />
        <Row
          label={wording.row.completed}
          value={count(progress.completed_count)}
        />
        <Row
          label={wording.row.remaining}
          value={count(progress.pending_count + progress.failed_count)}
        />
      </>
    );
  }
  if (stage === "translation" && progress.kind === "translation") {
    const worker = progress.worker;
    return (
      <>
        <Row
          label={wording.row.desired}
          value={count(worker?.desired_count ?? null)}
        />
        <Row
          label={wording.row.completed}
          value={count(worker?.completed_count ?? null)}
        />
        <Row
          label={wording.row.remaining}
          value={count(worker?.remaining_count ?? null)}
        />
        <Row label={wording.row.rebootDue} value={rebootDueText(worker)} />
      </>
    );
  }
  return null;
}

/** Present one mirrored worker's reboot flag, and unknown while no worker status is reported. */
export function rebootDueText(worker: WorkerControllerStatus | null): string {
  if (worker === null) {
    return wording.unknown;
  }
  return worker.reboot_due ? wording.yes : wording.no;
}

function ProgressBar({
  stage,
  status,
}: {
  stage: PreparationStage;
  status: LifecycleStatus;
}) {
  const percentDone = progressPercent(stage, status);
  if (percentDone === null) {
    return null;
  }
  return (
    <div className="prog">
      <i style={{ width: `${percentDone}%` }} />
    </div>
  );
}

function progressPercent(
  stage: PreparationStage,
  status: LifecycleStatus,
): number | null {
  const progress = status.progress;
  if (progress === null) {
    return null;
  }
  if (stage === "ingestion" && progress.kind === "ingestion") {
    // The verification total is the ingestion owner's own requested work, so no total is inferred.
    return progress.verification_total === null
      ? null
      : percent(progress.verified_response_count, progress.verification_total);
  }
  if (stage === "embedding" && progress.kind === "embedding") {
    return percent(progress.completed_count, progress.desired_count);
  }
  if (stage === "translation" && progress.kind === "translation") {
    const worker = progress.worker;
    if (worker?.desired_count == null || worker.completed_count == null) {
      return null;
    }
    return percent(worker.completed_count, worker.desired_count);
  }
  return null;
}
