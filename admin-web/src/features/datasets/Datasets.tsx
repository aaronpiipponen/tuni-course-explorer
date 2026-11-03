/**
 * The Settings dataset panel: both dataset roles, one retained inventory and the explicit role
 * actions.
 *
 * The panel renders the shell's one automatic inventory read, so the inventory reads on its own
 * interval whether or not the site's selection is enabled, and a bootstrap deployment, a stopped
 * database service and an unavailable dataset state tree all reach it. Before its first successful
 * read, and while the read reports the dataset state unavailable, every role fact reads unknown, so
 * the panel claims neither an absent role nor an idle stage. Enrollment, role migration, both
 * copies and deletion each name their exact target in one confirmation and reuse the dataset
 * owner that guards them again under its action lock. The promotion is the one streamed command.
 * It shows the coarse steps its owner reports, keeps an indeterminate pending marker on the
 * current step, and treats its successful terminal result as the only completion. A failed action
 * shows its owning guidance, and the inventory and the dashboard are then re-read to discover the
 * actual selection. A busy stage disables the Working copy, the Working deletion and the Working
 * migration.
 */
import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  copyToSelected,
  copyToWorking,
  deleteDataset,
  migrateDataset,
  setupDataset,
} from "../../api/datasets";
import { failureText, handleAdmissionFailure } from "../../api/http";
import type {
  DatasetListEntry,
  DatasetListReport,
  DatasetMigrateRole,
  PromotionStep,
  ServerStatusReport,
  StageName,
} from "../../api/types";
import { AutoMarker } from "../../shared/AutoMarker";
import { ConfirmDialog } from "../../shared/ConfirmDialog";
import { FailureNotice, Panel } from "../../shared/Panel";
import type { SessionAccess } from "../../shared/StagePanel";
import type { PanelRead } from "../../shared/usePanelRead";
import { wording } from "../../shared/wording";

// The four stage roots the inventory reports, in the order the owner lists them.
const STAGES: StageName[] = [
  "ingestion",
  "embedding",
  "translation",
  "inference",
];

// The ordered coarse steps one promotion reports before each mutation.
const PROMOTION_STEPS: PromotionStep[] = [
  "copy",
  "build",
  "switch",
  "restart",
  "prove",
];

/** One mutation this panel confirms, and the exact target it names. */
type Mutation =
  | { kind: "enroll" }
  | { kind: "migrate"; role: DatasetMigrateRole }
  | { kind: "delete"; entry: DatasetListEntry }
  | { kind: "working"; entry: DatasetListEntry }
  | { kind: "selected"; entry: DatasetListEntry };

/** Render the label/value facts of one dataset card. */
function factList(facts: [string, ReactNode][]) {
  return (
    <dl className="datasetFacts">
      {facts.map(([label, value]) => (
        <div className="datasetFact" key={label}>
          <dt>{label}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

/** Render the facts of one role card from its posted receipt. */
function roleFacts(entry: DatasetListEntry) {
  const detail = wording.datasets;
  return factList([
    [detail.namedDatabase, <code key="database">{entry.database_name}</code>],
    [
      detail.predecessor,
      <code key="predecessor">
        {entry.predecessor_id ?? detail.noPredecessor}
      </code>,
    ],
    [
      detail.recordedHead,
      <code key="revision">{entry.receipt_schema_revision}</code>,
    ],
    [
      detail.dump,
      entry.dump_path === null ? (
        detail.absent
      ) : (
        <code key="dump">{entry.dump_path}</code>
      ),
    ],
    [
      detail.artifacts,
      entry.artifacts_present
        ? detail.artifactsPresent
        : detail.artifactsAbsent,
    ],
  ]);
}

/** Render the facts of one retained inventory card from its posted receipt. */
function retainedFacts(entry: DatasetListEntry) {
  const detail = wording.datasets;
  return factList([
    [detail.dataset, <code key="dataset">{entry.dataset_id}</code>],
    [detail.namedDatabase, <code key="database">{entry.database_name}</code>],
    [
      detail.dump,
      entry.dump_path === null ? (
        detail.absent
      ) : (
        <code key="dump">{entry.dump_path}</code>
      ),
    ],
    [
      detail.artifacts,
      entry.artifacts_present
        ? detail.artifactsPresent
        : detail.artifactsAbsent,
    ],
  ]);
}

/** Render the facts every role card reports while no dataset state is readable. */
function unknownRoleFacts() {
  const detail = wording.datasets;
  return factList([
    [detail.namedDatabase, <code key="database">{wording.unknown}</code>],
    [detail.predecessor, <code key="predecessor">{wording.unknown}</code>],
    [detail.recordedHead, <code key="revision">{wording.unknown}</code>],
    [detail.dump, <code key="dump">{wording.unknown}</code>],
    [detail.artifacts, wording.unknown],
  ]);
}

/** Render the dataset role panel from the shell's shared inventory read. */
export function Datasets({
  session,
  onRefusal,
  dashboard,
  listing,
}: {
  session: SessionAccess;
  onRefusal: (status: number) => void;
  dashboard: PanelRead<ServerStatusReport>;
  listing: PanelRead<DatasetListReport>;
}) {
  const detail = wording.datasets;
  const [confirming, setConfirming] = useState<Mutation | null>(null);
  const [pending, setPending] = useState<Mutation | null>(null);
  const [progress, setProgress] = useState<PromotionStep[]>([]);
  const [failure, setFailure] = useState<string | null>(null);
  const promotion = useRef<AbortController | null>(null);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      promotion.current?.abort();
    };
  }, []);

  const report = listing.report;
  const entries = report?.datasets ?? [];
  const selected = entries.find((entry) => entry.selected);
  const working = entries.find((entry) => entry.working);
  const bootstrap = report?.mode === "bootstrap";
  const enrolled = report?.mode === "enrolled";
  const roleKnown = report !== null && report.mode !== "unavailable";
  const busy =
    report === null
      ? null
      : STAGES.some((stage) => report.stage_busy[stage] === true);

  const onConfirm = async (): Promise<void> => {
    const mutation = confirming;
    if (mutation === null) {
      return;
    }
    setConfirming(null);
    setPending(mutation);
    setFailure(null);
    try {
      switch (mutation.kind) {
        case "enroll":
          await setupDataset(session.csrfToken);
          break;
        case "migrate":
          await migrateDataset(mutation.role, session.csrfToken);
          break;
        case "delete":
          await deleteDataset(
            mutation.entry.dataset_id,
            mutation.entry.working,
            session.csrfToken,
          );
          break;
        case "working":
          await copyToWorking(mutation.entry.dataset_id, session.csrfToken);
          break;
        case "selected": {
          // This browser read is the panel's own request. A sign-out or unmount aborts it, while
          // the owner keeps the admitted mutation and its safe command-log outcome.
          promotion.current?.abort();
          const controller = new AbortController();
          promotion.current = controller;
          await copyToSelected(
            mutation.entry.dataset_id,
            true,
            session.csrfToken,
            (step) => {
              if (mounted.current) {
                setProgress((seen) => [...seen, step]);
              }
            },
            controller.signal,
          );
          break;
        }
      }
      if (!mounted.current) {
        return;
      }
      listing.reload();
      dashboard.reload();
    } catch (error) {
      if (!mounted.current) {
        return;
      }
      if (handleAdmissionFailure(error, onRefusal)) {
        promotion.current?.abort();
        return;
      }
      setFailure(failureText(error, wording.writeFailed));
      // The actual selection is whatever the owner's rollback left. Reloading reads that selection.
      listing.reload();
      dashboard.reload();
    } finally {
      if (mounted.current) {
        setPending(null);
        setProgress([]);
      }
    }
  };

  const confirmTitle = (mutation: Mutation): string => {
    switch (mutation.kind) {
      case "enroll":
        return detail.enroll;
      case "migrate":
        return mutation.role === "selected"
          ? detail.migrateSelected
          : mutation.role === "working"
            ? detail.migrateWorking
            : detail.migrateDatabase;
      case "working":
        return detail.copyToWorking;
      case "selected":
        return detail.copyToSelected;
      case "delete":
        return detail.deleteTitle;
    }
  };

  const confirmMessage = (mutation: Mutation): string => {
    switch (mutation.kind) {
      case "enroll":
        return detail.enrollConfirm;
      case "migrate":
        return mutation.role === "selected"
          ? detail.migrateSelectedConfirm
          : mutation.role === "working"
            ? detail.migrateWorkingConfirm
            : detail.migrateDatabaseConfirm.replace(
                "{database_name}",
                report?.bootstrap_database ?? wording.unknown,
              );
      case "working":
        return detail.copyToWorkingMessage
          .replace("{dataset_id}", mutation.entry.dataset_id)
          .replace("{database_name}", mutation.entry.database_name);
      case "selected":
        return detail.copyToSelectedMessage
          .replace("{dataset_id}", mutation.entry.dataset_id)
          .replace("{database_name}", mutation.entry.database_name);
      case "delete":
        return (
          mutation.entry.working
            ? detail.deleteWorkingMessage
            : detail.deleteMessage
        )
          .replace("{dataset_id}", mutation.entry.dataset_id)
          .replace("{database_name}", mutation.entry.database_name);
    }
  };

  const current = progress.length === 0 ? null : progress[progress.length - 1];
  const rollback = progress.includes("rollback");
  // The step whose failure made the owner restore the earlier selection.
  const stopped =
    rollback && progress.length > 1 ? progress[progress.length - 2] : null;

  const stepClass = (step: PromotionStep): string => {
    if (!progress.includes(step)) {
      return "step";
    }
    if (step === current) {
      return "step on";
    }
    return step === stopped ? "step stopped" : "step done";
  };

  return (
    <Panel
      title={detail.panel}
      span={12}
      marker={
        <AutoMarker
          reading={listing.loading}
          lastSuccess={listing.lastSuccess}
          label={detail.panel}
        />
      }
    >
      <FailureNotice text={listing.failure} />
      <div className="datasetBoard">
        {bootstrap ? (
          <section className="datasetBootstrap">
            <p className="note">
              {detail.bootstrap.replace(
                "{database_name}",
                report?.bootstrap_database ?? wording.unknown,
              )}
            </p>
            <div className="acts">
              <button
                className="btn p"
                type="button"
                disabled={pending !== null}
                onClick={() => setConfirming({ kind: "enroll" })}
              >
                {detail.enroll}
              </button>
              <button
                className="btn"
                type="button"
                disabled={pending !== null}
                onClick={() =>
                  setConfirming({ kind: "migrate", role: "database" })
                }
              >
                {detail.migrateDatabase}
              </button>
            </div>
          </section>
        ) : (
          <div className="datasetRoles">
            <section className="datasetRoleCard">
              <div className="datasetRoleHead">
                <span className="tag ok">{detail.selectedTag}</span>
              </div>
              {!roleKnown ? (
                unknownRoleFacts()
              ) : selected === undefined ? null : (
                <>
                  <b className="datasetRoleId">{selected.dataset_id}</b>
                  {roleFacts(selected)}
                  <div className="acts">
                    <button
                      className="btn xs"
                      type="button"
                      disabled={pending !== null}
                      onClick={() =>
                        setConfirming({ kind: "migrate", role: "selected" })
                      }
                    >
                      {detail.migrateSelected}
                    </button>
                  </div>
                </>
              )}
            </section>
            <section className="datasetRoleCard">
              <div className="datasetRoleHead">
                <span className="tag">{detail.workingTag}</span>
              </div>
              {!roleKnown ? (
                unknownRoleFacts()
              ) : working === undefined ? (
                <div className="datasetEmpty">
                  <b>{detail.workingAbsentTitle}</b>
                  <span>{detail.workingAbsentHint}</span>
                </div>
              ) : (
                <>
                  <b className="datasetRoleId">{working.dataset_id}</b>
                  {roleFacts(working)}
                  <div className="acts">
                    <button
                      className="btn xs"
                      type="button"
                      disabled={pending !== null || busy === true}
                      onClick={() =>
                        setConfirming({ kind: "migrate", role: "working" })
                      }
                    >
                      {detail.migrateWorking}
                    </button>
                  </div>
                </>
              )}
            </section>
          </div>
        )}
        {pending?.kind === "selected" ? (
          <ol className="steplist" aria-label={detail.copyToSelected}>
            {PROMOTION_STEPS.map((step) => (
              <li
                key={step}
                className={stepClass(step)}
                aria-current={step === current ? "step" : undefined}
              >
                {detail.promotionSteps[step]}
                {step === current ? <span className="steppulse" /> : null}
              </li>
            ))}
            {rollback ? (
              <li className="step on">{detail.promotionSteps.rollback}</li>
            ) : null}
          </ol>
        ) : null}
        <div className="datasetDivider" role="separator" />
        <h4 className="roleTitle datasetInventoryTitle">{detail.inventory}</h4>
        {report === null ? null : report.mode === "unavailable" ? (
          <p className="warn-note">{wording.stateUnavailable}</p>
        ) : entries.length === 0 ? (
          <p className="note">{detail.noDatasets}</p>
        ) : (
          <div className="datasetInventory">
            {entries.map((entry) => (
              <article className="datasetCard" key={entry.dataset_id}>
                {retainedFacts(entry)}
                <div className="datasetCardActions">
                  <div className="rowacts">
                    {enrolled ? (
                      <>
                        {entry.database_presence === "present" ? (
                          <>
                            <button
                              className="btn xs"
                              type="button"
                              disabled={pending !== null || busy === true}
                              onClick={() =>
                                setConfirming({ kind: "working", entry })
                              }
                            >
                              {detail.copyToWorking}
                            </button>
                            <button
                              className="btn xs"
                              type="button"
                              disabled={pending !== null}
                              onClick={() =>
                                setConfirming({ kind: "selected", entry })
                              }
                            >
                              {detail.copyToSelected}
                            </button>
                          </>
                        ) : null}
                        {entry.selected ? null : (
                          <button
                            className="btn xs danger"
                            type="button"
                            disabled={
                              pending !== null ||
                              (entry.working && busy === true)
                            }
                            onClick={() =>
                              setConfirming({ kind: "delete", entry })
                            }
                          >
                            {detail.delete}
                          </button>
                        )}
                      </>
                    ) : null}
                  </div>
                  <span className="datasetRoleMarks">
                    {entry.selected ? (
                      <span className="tag ok">{detail.selectedTag}</span>
                    ) : null}
                    {entry.working ? (
                      <span className="tag">{detail.workingTag}</span>
                    ) : null}
                  </span>
                </div>
              </article>
            ))}
          </div>
        )}
      </div>
      <FailureNotice text={failure} />
      <ConfirmDialog
        open={confirming !== null}
        title={confirming === null ? "" : confirmTitle(confirming)}
        message={confirming === null ? "" : confirmMessage(confirming)}
        pending={pending !== null}
        onCancel={() => setConfirming(null)}
        onConfirm={() => void onConfirm()}
      />
    </Panel>
  );
}
