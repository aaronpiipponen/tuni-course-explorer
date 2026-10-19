/**
 * The Inference run panel: the mirrored worker progress of the one inference run and its four
 * lifecycle actions.
 *
 * The run's rows come from the server's inference stage status, whose worker member mirrors what the
 * server has observed. The cycle is the worker's own coverage cycle when it reports one, and unknown
 * otherwise. A stop asks for confirmation naming the run, and a successful action presents the status
 * it returned.
 */
import { useState } from "react";
import { failureText, handleAdmissionFailure } from "../../api/http";
import { readInferenceStatus, runInferenceAction } from "../../api/inference";
import type { LifecycleAction, LifecycleStatus } from "../../api/types";
import { AutoMarker } from "../../shared/AutoMarker";
import { humanDuration, rate, stateText } from "../../shared/format";
import { FailureNotice, Panel, Row, Rows } from "../../shared/Panel";
import {
  rebootDueText,
  StageActions,
  type SessionAccess,
} from "../../shared/StagePanel";
import { usePanelRead } from "../../shared/usePanelRead";
import { wording } from "../../shared/wording";

const inferenceRead = (signal: AbortSignal, automatic: boolean) =>
  readInferenceStatus(signal, automatic);

function RunRows({ status }: { status: LifecycleStatus }) {
  const progress = status.progress;
  const worker = progress?.kind === "inference" ? progress.worker : null;
  const preparation =
    progress?.kind === "inference" ? progress.preparation : null;
  return (
    <>
      <Rows>
        <Row
          label={wording.row.cycle}
          value={<code>{worker?.coverage?.cycle_id ?? wording.unknown}</code>}
        />
        <Row
          label={wording.row.stage}
          value={stateText(worker?.progress?.stage ?? status.lifecycle)}
        />
        <Row
          label={wording.row.session}
          value={status.session_id ?? wording.unknown}
        />
        <Row
          label={wording.row.activeTime}
          value={humanDuration(status.active_seconds)}
        />
        <Row label={wording.row.rate} value={rate(status.items_per_second)} />
        <Row
          label={wording.row.eta}
          value={humanDuration(status.eta_seconds)}
        />
        <Row
          label={wording.row.rebootDue}
          value={rebootDueText(worker)}
          accent
        />
        {preparation === null ? null : (
          <Row label={wording.row.preparation} value={preparation} />
        )}
      </Rows>
      {worker === null
        ? null
        : worker.stages.map((stage) => (
            <div className="pline" key={stage.stage}>
              <span className="n">{stage.stage}</span>
              <div className="prog">
                <i
                  style={{
                    width: `${stage.total <= 0 ? 0 : Math.round((stage.done / stage.total) * 100)}%`,
                  }}
                />
              </div>
              <span className="c">
                {stage.done} / {stage.total} / {stage.remaining}{" "}
                {wording.row.remaining}
              </span>
            </div>
          ))}
    </>
  );
}

/** Render the inference run panel. */
export function InferenceRun({
  session,
  onRefusal,
}: {
  session: SessionAccess;
  onRefusal: (status: number) => void;
}) {
  const [actionFailure, setActionFailure] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const panel = usePanelRead(inferenceRead, {
    pollSeconds: session.pollSeconds,
    enabled: true,
    onRefusal,
    failureTextValue: wording.readFailed,
  });

  const onAction = async (action: LifecycleAction): Promise<void> => {
    setPending(true);
    setActionFailure(null);
    try {
      const result = await runInferenceAction(action, session.csrfToken);
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

  const title = wording.inference.run;
  return (
    <Panel
      title={title}
      marker={
        <AutoMarker
          reading={panel.loading}
          lastSuccess={panel.lastSuccess}
          label={title}
        />
      }
    >
      <FailureNotice text={panel.failure} />
      {panel.report === null ? null : (
        <>
          <RunRows status={panel.report} />
          <StageActions
            stageLabel={title}
            pending={pending}
            failure={actionFailure}
            onAction={(action) => void onAction(action)}
          />
        </>
      )}
    </Panel>
  );
}
