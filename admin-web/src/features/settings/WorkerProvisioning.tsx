/**
 * The Worker provisioning panel: the explicit worker setup and the read-only preflight.
 *
 * The setup posts one branch and one code-only choice and asks for confirmation first. The preflight
 * is an explicit user action that reads the prepared worker and refreshes only when the operator
 * asks, so no request reaches the worker on mount or on a timer, and a setup report and a preflight
 * report are rendered separately from the command each one returned.
 */
import { useState } from "react";
import { failureText, handleAdmissionFailure } from "../../api/http";
import { preflightWorker, setupWorker } from "../../api/settings";
import type { ProvisioningReport } from "../../api/types";
import { AutoMarker } from "../../shared/AutoMarker";
import { ConfirmDialog } from "../../shared/ConfirmDialog";
import { FailureNotice, Panel, Row, Rows } from "../../shared/Panel";
import type { SessionAccess } from "../../shared/StagePanel";
import { Switch } from "../../shared/Switch";
import { useDemandRead } from "../../shared/useDemandRead";
import { wording } from "../../shared/wording";

/** Render the code and resource facts one provisioning report carries. */
function ReportRows({ report }: { report: ProvisioningReport }) {
  const detail = wording.settings;
  return (
    <Rows>
      <Row
        label={detail.codeBranch}
        value={<code>{report.code.branch}</code>}
      />
      <Row
        label={detail.codeRevision}
        value={<code>{report.code.revision}</code>}
      />
      <Row
        label={detail.serverOriginDiffers}
        value={report.code.server_origin_differs ? wording.yes : wording.no}
      />
      <Row
        label={detail.resourcesReady}
        value={
          report.resources === null
            ? wording.unknown
            : report.resources.ready
              ? wording.yes
              : wording.no
        }
      />
      {report.resources === null ||
      report.resources.missing.length === 0 ? null : (
        <Row
          label={detail.missingResources}
          value={report.resources.missing.join(", ")}
        />
      )}
    </Rows>
  );
}

/** Render the worker provisioning panel. */
export function WorkerProvisioning({
  session,
  onRefusal,
}: {
  session: SessionAccess;
  onRefusal: (status: number) => void;
}) {
  const detail = wording.settings;
  const [branch, setBranch] = useState("");
  const [codeOnly, setCodeOnly] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [pending, setPending] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [setup, setSetup] = useState<ProvisioningReport | null>(null);
  const preflight = useDemandRead(
    (signal: AbortSignal) => preflightWorker(session.csrfToken, signal),
    {
      identity: "preflight",
      onRefusal,
      failureTextValue: wording.readFailed,
    },
  );

  const onSetup = async (): Promise<void> => {
    setPending(true);
    setFailure(null);
    try {
      setSetup(await setupWorker(branch, codeOnly, session.csrfToken));
    } catch (error) {
      if (handleAdmissionFailure(error, onRefusal)) {
        return;
      }
      setFailure(failureText(error, wording.writeFailed));
    } finally {
      setPending(false);
    }
  };

  const ready = branch.trim() !== "";
  return (
    <Panel
      title={detail.workerProvisioning}
      marker={
        <AutoMarker
          reading={preflight.loading}
          lastSuccess={preflight.lastSuccess}
          label={detail.preflight}
          demand
          indicator={false}
        />
      }
    >
      <div className="cfgrow">
        <span className="k">{detail.originBranch}</span>
        <span className="val">
          <input
            aria-label={detail.originBranch}
            value={branch}
            spellCheck={false}
            disabled={pending}
            onChange={(event) => setBranch(event.target.value)}
          />
        </span>
      </div>
      <div className="cfgrow bordered">
        <span className="k">{detail.codeOnly}</span>
        <span className="val">
          <Switch
            label={detail.codeOnly}
            checked={codeOnly}
            disabled={pending}
            onChange={setCodeOnly}
          />
        </span>
      </div>
      <div className="acts">
        <button
          className="btn p"
          type="button"
          disabled={pending || !ready}
          onClick={() => setConfirming(true)}
        >
          {detail.workerSetup}
        </button>
        <button
          className="btn"
          type="button"
          disabled={preflight.loading}
          onClick={preflight.reload}
        >
          {detail.preflight}
        </button>
      </div>
      {ready ? null : <p className="note">{detail.branchRequired}</p>}
      <FailureNotice text={failure} />
      {setup === null ? null : (
        <>
          <p className="note">{detail.setupReport}</p>
          <ReportRows report={setup} />
        </>
      )}
      {preflight.report === null ? null : (
        <>
          <p className="note">{detail.preflightReport}</p>
          <ReportRows report={preflight.report} />
        </>
      )}
      <FailureNotice text={preflight.failure} />
      <ConfirmDialog
        open={confirming}
        title={detail.workerSetup}
        message={detail.workerSetupConfirm.replace("{branch}", branch)}
        pending={pending}
        onCancel={() => setConfirming(false)}
        onConfirm={() => {
          setConfirming(false);
          void onSetup();
        }}
      />
    </Panel>
  );
}
