/** The Inference tab's fixed run, report, target and dataset requests. */
import { runCommand } from "./http";
import type {
  DatasetDeletionReport,
  DatasetListReport,
  InferenceAdministrativeSummary,
  InferenceTargetDisposition,
  LifecycleAction,
  LifecycleStatus,
  TargetDecisionToken,
} from "./types";

/** Read the inference run's lifecycle status. */
export function readInferenceStatus(
  signal?: AbortSignal,
  automatic = false,
): Promise<LifecycleStatus> {
  return runCommand<LifecycleStatus>("/api/inference/status", {
    signal,
    automatic,
  });
}

/** Run one lifecycle action on the inference run and return its status. */
export function runInferenceAction(
  action: LifecycleAction,
  csrfToken: string,
  signal?: AbortSignal,
): Promise<LifecycleStatus> {
  return runCommand<LifecycleStatus>("/api/inference/action", {
    body: { action },
    csrfToken,
    signal,
  });
}

/** Read the retained-server inference summary once for its four report panels. */
export function readInferenceSummary(
  signal?: AbortSignal,
  automatic = false,
): Promise<InferenceAdministrativeSummary> {
  return runCommand<InferenceAdministrativeSummary>("/api/inference/summary", {
    signal,
    automatic,
  });
}

/** Read one canonical target's identity and current durable decision. */
export function readTarget(
  targetId: string,
  csrfToken: string,
  signal?: AbortSignal,
): Promise<InferenceTargetDisposition> {
  return runCommand<InferenceTargetDisposition>("/api/inference/target/read", {
    body: { target_id: targetId },
    csrfToken,
    signal,
  });
}

/** Record one canonical target's durable decision. */
export function recordDecision(
  targetId: string,
  disposition: TargetDecisionToken,
  csrfToken: string,
  signal?: AbortSignal,
): Promise<InferenceTargetDisposition> {
  return runCommand<InferenceTargetDisposition>(
    "/api/inference/target/decision",
    { body: { target_id: targetId, disposition }, csrfToken, signal },
  );
}

/** List the retained dataset chain in selected-first order. */
export function readDatasets(
  signal?: AbortSignal,
  automatic = false,
): Promise<DatasetListReport> {
  return runCommand<DatasetListReport>("/api/inference/datasets", {
    signal,
    automatic,
  });
}

/** Delete one listed non-selected dataset. */
export function deleteDataset(
  datasetId: string,
  csrfToken: string,
  signal?: AbortSignal,
): Promise<DatasetDeletionReport> {
  return runCommand<DatasetDeletionReport>("/api/inference/datasets/delete", {
    body: { dataset_id: datasetId },
    csrfToken,
    signal,
  });
}
