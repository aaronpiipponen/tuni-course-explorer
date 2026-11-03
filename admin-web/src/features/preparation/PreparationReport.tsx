/**
 * One preparation report panel: the catalogue summary, the teaching-text coverage or the embedding
 * coverage, and the one serving-artifact build the embedding coverage owns.
 *
 * Each report is its owning fixed command's own report read for the role the backend resolved:
 * Working first, Selected when Working is absent, and no report in a bootstrap state. The panel
 * names that role before the report. A build posts one empty request, reports its returned artifact
 * and count facts and states that the web supervisor reads the artifacts at start, so a build takes
 * effect after a full supervisor restart.
 */
import { useCallback, useState } from "react";
import { failureText, handleAdmissionFailure } from "../../api/http";
import {
  readPreparationReport,
  buildServingArtifacts,
  type PreparationReportKind,
  type PreparationReport as PreparationReportData,
} from "../../api/preparation";
import type {
  CatalogueSummary,
  CourseEmbeddingCoverageReport,
  DatasetReport,
  TeachingTextCoverageReport,
} from "../../api/types";
import { AutoMarker } from "../../shared/AutoMarker";
import { DatasetRoleStatus } from "../../shared/DatasetRoleStatus";
import { count } from "../../shared/format";
import { DataTable, FailureNotice, Panel, Row, Rows } from "../../shared/Panel";
import type { SessionAccess } from "../../shared/StagePanel";
import { usePanelRead } from "../../shared/usePanelRead";
import { wording } from "../../shared/wording";

/** Label one coverage row by field, uppercase language and, when the report has one, origin. */
function cellLabel(field: string, language: string, origin?: string): string {
  const base = `${field} ${language.toUpperCase()}`;
  return origin === undefined ? base : `${base} ${origin}`;
}

function CatalogueRows({ report }: { report: CatalogueSummary }) {
  const detail = wording.preparation;
  return (
    <Rows>
      <Row
        label={detail.periods}
        value={count(report.curriculum_period_count)}
      />
      <Row
        label={detail.canonicalCourses}
        value={count(report.canonical_course_count)}
      />
      <Row
        label={detail.activeCourses}
        value={count(report.active_course_count)}
      />
      <Row
        label={detail.courseVersions}
        value={count(report.course_version_count)}
      />
      <Row
        label={detail.canonicalModules}
        value={count(report.canonical_module_count)}
      />
      <Row
        label={detail.moduleVersions}
        value={count(report.module_version_count)}
      />
    </Rows>
  );
}

function TeachingTextTable({ report }: { report: TeachingTextCoverageReport }) {
  const detail = wording.preparation;
  const totals = report.fields.reduce(
    (sum, cell) => ({
      official: sum.official + cell.official_count,
      derived: sum.derived + cell.derived_count,
      stale: sum.stale + cell.stale_count,
      missing: sum.missing + cell.missing_count,
    }),
    { official: 0, derived: 0, stale: 0, missing: 0 },
  );
  const rows = [
    [
      detail.allRepresentativeFields,
      count(totals.official),
      count(totals.derived),
      count(totals.stale),
      count(totals.missing),
    ],
    ...report.fields.map((cell) => [
      cellLabel(cell.field, cell.language),
      count(cell.official_count),
      count(cell.derived_count),
      count(cell.stale_count),
      count(cell.missing_count),
    ]),
  ];
  return (
    <>
      <DataTable
        head={[
          detail.scope,
          detail.official,
          detail.derived,
          detail.stale,
          detail.missing,
        ]}
        rows={rows}
        align={["", "r", "r", "r", "r"]}
      />
      <Rows>
        <Row
          label={detail.representativeCourses}
          value={count(report.representative_course_count)}
        />
        <Row
          label={detail.noRepresentativeCourses}
          value={count(report.no_representative_course_count)}
        />
        <Row
          label={detail.nameOnlyCourses}
          value={count(report.name_only_course_count)}
        />
        <Row
          label={detail.unembeddableCourses}
          value={count(report.unembeddable_course_count)}
        />
      </Rows>
    </>
  );
}

function EmbeddingCoverage({
  report,
  session,
  onRefusal,
}: {
  report: CourseEmbeddingCoverageReport;
  session: SessionAccess;
  onRefusal: (status: number) => void;
}) {
  const detail = wording.preparation;
  const [pending, setPending] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);

  const onBuild = async (): Promise<void> => {
    setPending(true);
    setResult(null);
    setFailure(null);
    try {
      const artifacts = await buildServingArtifacts(session.csrfToken);
      const built = artifacts.embeddings_enabled
        ? wording.preparation.servingArtifactsBuilt
            .replace("{pair}", artifacts.hub_pair_path)
            .replace(
              "{catalogue}",
              `${artifacts.catalogue_path} (${artifacts.chunk_count})`,
            )
            .replace(
              "{outcomes}",
              `${artifacts.outcomes_path} (${artifacts.outcomes_chunk_count})`,
            )
            .replace("{groups}", `${artifacts.search_group_count}`)
            .replace("{blocks}", `${artifacts.search_block_count}`)
            .replace("{centroids}", `${artifacts.centroid_count}`)
            .replace("{neighbors}", `${artifacts.neighbor_count}`)
            .replace("{roots}", `${artifacts.study_fragment_projectable}`)
        : wording.preparation.servingArtifactsBuiltWithoutEmbeddings
            .replace("{catalogue}", artifacts.catalogue_artifact_path)
            .replace("{roots}", `${artifacts.study_fragment_projectable}`);
      setResult(`${built} ${wording.preparation.servingArtifactsRestart}`);
    } catch (error) {
      if (handleAdmissionFailure(error, onRefusal)) {
        return;
      }
      setFailure(failureText(error, wording.writeFailed));
    } finally {
      setPending(false);
    }
  };

  const rows = [
    ...report.fields.map((cell) => [
      cellLabel(cell.field, cell.language, cell.origin),
      count(cell.pending_count),
      count(cell.completed_count),
      count(cell.failed_count),
    ]),
    [
      detail.total,
      count(report.pending_count),
      count(report.completed_count),
      count(report.failed_count),
    ],
  ];
  return (
    <>
      <DataTable
        head={[
          detail.cell,
          wording.row.pending,
          wording.row.completed,
          wording.row.failed,
        ]}
        rows={rows}
        align={["", "r", "r", "r"]}
      />
      <div className="acts">
        <button
          className="btn p"
          type="button"
          disabled={pending}
          onClick={() => void onBuild()}
        >
          {detail.buildServingArtifacts}
        </button>
      </div>
      {result === null ? null : <p className="note">{result}</p>}
      <FailureNotice text={failure} />
    </>
  );
}

/** Render one preparation report panel with its own automatic read. */
export function PreparationReport({
  kind,
  session,
  onRefusal,
}: {
  kind: PreparationReportKind;
  session: SessionAccess;
  onRefusal: (status: number) => void;
}) {
  const read = useCallback(
    (signal: AbortSignal, automatic: boolean) =>
      readPreparationReport(kind, signal, automatic),
    [kind],
  );
  const panel = usePanelRead<DatasetReport<PreparationReportData>>(read, {
    pollSeconds: session.pollSeconds,
    enabled: true,
    onRefusal,
    failureTextValue: wording.readFailed,
  });
  const title =
    kind === "catalogue"
      ? wording.preparation.catalogueSummary
      : kind === "teaching-text"
        ? wording.preparation.teachingTextCoverage
        : wording.preparation.embeddingCoverage;
  const scope = panel.report;
  return (
    <Panel
      title={title}
      span={4}
      marker={
        <AutoMarker
          reading={panel.loading}
          lastSuccess={panel.lastSuccess}
          label={title}
        />
      }
    >
      <FailureNotice text={panel.failure} />
      {scope === null ? null : <DatasetRoleStatus role={scope.role} />}
      <ReportBody
        kind={kind}
        report={scope?.report ?? null}
        session={session}
        onRefusal={onRefusal}
      />
    </Panel>
  );
}

function ReportBody({
  kind,
  report,
  session,
  onRefusal,
}: {
  kind: PreparationReportKind;
  report: PreparationReportData | null;
  session: SessionAccess;
  onRefusal: (status: number) => void;
}) {
  if (report === null) {
    return null;
  }
  if (kind === "catalogue") {
    return <CatalogueRows report={report as CatalogueSummary} />;
  }
  if (kind === "teaching-text") {
    return <TeachingTextTable report={report as TeachingTextCoverageReport} />;
  }
  return (
    <EmbeddingCoverage
      report={report as CourseEmbeddingCoverageReport}
      session={session}
      onRefusal={onRefusal}
    />
  );
}
