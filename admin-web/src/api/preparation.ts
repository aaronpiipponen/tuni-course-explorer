/** The Data preparation tab's fixed stage, report and hub requests. */
import { runCommand } from "./http";
import type {
  CatalogueSummary,
  CourseEmbeddingCoverageReport,
  EmbeddingHubReport,
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

/** Read one preparation report from its owning fixed command. */
export function readPreparationReport(
  kind: PreparationReportKind,
  signal?: AbortSignal,
  automatic = false,
): Promise<PreparationReport> {
  return runCommand<PreparationReport>(`/api/preparation/report/${kind}`, {
    signal,
    automatic,
  });
}

/** Write both embedding hub files from the selected dataset. */
export function writeHubs(
  csrfToken: string,
  signal?: AbortSignal,
): Promise<EmbeddingHubReport> {
  return runCommand<EmbeddingHubReport>("/api/preparation/hubs", {
    body: {},
    csrfToken,
    signal,
  });
}
