/** The Data preparation tab's fixed stage, report and serving-artifact requests. */
import { runCommand } from "./http";
import type {
  CatalogueSummary,
  CourseEmbeddingCoverageReport,
  DatasetReport,
  ServingArtifactsReport,
  LifecycleAction,
  LifecycleStatus,
  StageName,
  TeachingTextCoverageReport,
} from "./types";

/** The three stages the preparation tab owns. */
export type PreparationStage = Extract<
  StageName,
  "ingestion" | "translation" | "embedding"
>;

/** One preparation report the tab renders. */
export type PreparationReportKind = "catalogue" | "teaching-text" | "embedding";

/** The report each preparation report kind returns. */
export type PreparationReport =
  CatalogueSummary | TeachingTextCoverageReport | CourseEmbeddingCoverageReport;

/** Read one preparation stage's lifecycle status. */
export function readStageStatus(
  stage: PreparationStage,
  signal?: AbortSignal,
  automatic = false,
): Promise<LifecycleStatus> {
  return runCommand<LifecycleStatus>(`/api/preparation/status/${stage}`, {
    signal,
    automatic,
  });
}

/** Run one lifecycle action on one preparation stage and return its status. */
export function runStageAction(
  stage: PreparationStage,
  action: LifecycleAction,
  csrfToken: string,
  signal?: AbortSignal,
): Promise<LifecycleStatus> {
  return runCommand<LifecycleStatus>("/api/preparation/action", {
    body: { stage, action },
    csrfToken,
    signal,
  });
}

/** Read one preparation report from its owning fixed command for the role it resolves. */
export function readPreparationReport(
  kind: PreparationReportKind,
  signal?: AbortSignal,
  automatic = false,
): Promise<DatasetReport<PreparationReport>> {
  return runCommand<DatasetReport<PreparationReport>>(
    `/api/preparation/report/${kind}`,
    {
      signal,
      automatic,
    },
  );
}

/** Build the selected dataset's serving artifacts. */
export function buildServingArtifacts(
  csrfToken: string,
  signal?: AbortSignal,
): Promise<ServingArtifactsReport> {
  return runCommand<ServingArtifactsReport>(
    "/api/preparation/serving-artifacts",
    {
      body: {},
      csrfToken,
      signal,
    },
  );
}
