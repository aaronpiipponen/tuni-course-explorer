/** The Settings dataset panel's fixed inventory, role action and copy requests. */
import { runCommand, runStreamingCommand } from "./http";
import type {
  DatasetDeletionReport,
  DatasetListReport,
  DatasetMigrateRole,
  DatasetReceipt,
  DatasetVerification,
  PromotionStep,
} from "./types";

/** Read the retained dataset inventory with its roles, receipts and resource facts. */
export function readDatasets(
  signal?: AbortSignal,
  automatic = false,
): Promise<DatasetListReport> {
  return runCommand<DatasetListReport>("/api/datasets", {
    signal,
    automatic,
  });
}

/** Enroll or select the dataset through the fixed setup command. */
export function setupDataset(
  csrfToken: string,
  signal?: AbortSignal,
): Promise<DatasetReceipt> {
  return runCommand<DatasetReceipt>("/api/datasets/setup", {
    body: {},
    csrfToken,
    signal,
  });
}

/** Migrate one role's dataset, or the configured bootstrap database, to this checkout's head. */
export function migrateDataset(
  role: DatasetMigrateRole,
  csrfToken: string,
  signal?: AbortSignal,
): Promise<DatasetVerification> {
  return runCommand<DatasetVerification>("/api/datasets/migrate", {
    body: { role },
    csrfToken,
    signal,
  });
}

/** Delete one listed non-selected dataset, confirming a Working target explicitly. */
export function deleteDataset(
  datasetId: string,
  confirmWorking: boolean,
  csrfToken: string,
  signal?: AbortSignal,
): Promise<DatasetDeletionReport> {
  return runCommand<DatasetDeletionReport>("/api/datasets/delete", {
    body: { dataset_id: datasetId, confirm_working: confirmWorking },
    csrfToken,
    signal,
  });
}

/** Copy one listed source dataset and assign the verified copy to Working. */
export function copyToWorking(
  sourceDatasetId: string,
  csrfToken: string,
  signal?: AbortSignal,
): Promise<DatasetReceipt> {
  return runCommand<DatasetReceipt>("/api/datasets/copy-to-working", {
    body: { source_dataset_id: sourceDatasetId },
    csrfToken,
    signal,
  });
}

/**
 * Copy one listed source dataset and promote the copy to Selected.
 *
 * The request answers one newline-delimited stream, so each step its owner reports reaches `onStep`
 * before the terminal receipt. The confirmation is sent unchanged and gates the serving restart in
 * the owning service.
 */
export function copyToSelected(
  sourceDatasetId: string,
  confirmRestart: boolean,
  csrfToken: string,
  onStep: (step: PromotionStep) => void,
  signal?: AbortSignal,
): Promise<DatasetReceipt> {
  return runStreamingCommand<DatasetReceipt>("/api/datasets/copy-to-selected", {
    body: {
      source_dataset_id: sourceDatasetId,
      confirm_restart: confirmRestart,
    },
    csrfToken,
    onStep,
    signal,
  });
}
