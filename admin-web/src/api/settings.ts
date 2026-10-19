/** The Settings tab's fixed configuration, backup and maintenance requests. */
import { runCommand } from "./http";
import type {
  AdminRebuildReport,
  BackupDeletionReport,
  BackupListReport,
  ConfigurationFileReport,
  ConfigurationFilesReport,
  ConfigurationWriteReport,
  DatasetReceipt,
  DatasetVerification,
  ProvisioningReport,
  RebuildReport,
} from "./types";

/** The one file the feature switches live in. */
export const WEB_CONFIGURATION_FILE = "config/web.toml";

/** List the editable configuration files. */
export function readConfigurationFiles(
  signal?: AbortSignal,
  automatic = false,
): Promise<ConfigurationFilesReport> {
  return runCommand<ConfigurationFilesReport>("/api/settings/config/files", {
    signal,
    automatic,
  });
}

/** Read every key of one listed configuration file as the file holds it. */
export function readConfigurationFile(
  file: string,
  csrfToken: string,
  signal?: AbortSignal,
  automatic = false,
): Promise<ConfigurationFileReport> {
  return runCommand<ConfigurationFileReport>("/api/settings/config/read", {
    body: { file },
    csrfToken,
    signal,
    automatic,
  });
}

/** Save one key of one listed configuration file from its JSON literal value. */
export function setConfigurationValue(
  file: string,
  key: string,
  value: string,
  csrfToken: string,
  signal?: AbortSignal,
): Promise<ConfigurationWriteReport> {
  return runCommand<ConfigurationWriteReport>("/api/settings/config/set", {
    body: { file, key, value },
    csrfToken,
    signal,
  });
}

/** List the regular files under the backup root. */
export function readBackups(
  signal?: AbortSignal,
  automatic = false,
): Promise<BackupListReport> {
  return runCommand<BackupListReport>("/api/settings/backups", {
    signal,
    automatic,
  });
}

/** Delete one listed backup file. */
export function deleteBackup(
  name: string,
  csrfToken: string,
  signal?: AbortSignal,
): Promise<BackupDeletionReport> {
  return runCommand<BackupDeletionReport>("/api/settings/backups/delete", {
    body: { name },
    csrfToken,
    signal,
  });
}

/** Rebuild the site's frontend, containers, web server and its verified bind. */
export function rebuildSite(
  csrfToken: string,
  signal?: AbortSignal,
): Promise<RebuildReport> {
  return runCommand<RebuildReport>("/api/settings/rebuild", {
    body: {},
    csrfToken,
    signal,
  });
}

/**
 * Build the administration frontend, whose successful response queues the backend's own restart.
 *
 * The request is an explicit action, so it carries no automatic-read marker. The final ASGI body
 * send completes before the restart is queued, and no restart follows a failed build.
 */
export function rebuildAdminPanel(
  csrfToken: string,
  signal?: AbortSignal,
): Promise<AdminRebuildReport> {
  return runCommand<AdminRebuildReport>("/api/settings/rebuild-admin", {
    body: {},
    csrfToken,
    signal,
  });
}

/** Enroll or select the dataset through the fixed setup command. */
export function setupDataset(
  csrfToken: string,
  signal?: AbortSignal,
): Promise<DatasetReceipt> {
  return runCommand<DatasetReceipt>("/api/settings/datasets/setup", {
    body: {},
    csrfToken,
    signal,
  });
}

/** Migrate the selected dataset to this checkout's migration head. */
export function migrateDataset(
  csrfToken: string,
  signal?: AbortSignal,
): Promise<DatasetVerification> {
  return runCommand<DatasetVerification>("/api/settings/datasets/migrate", {
    body: {},
    csrfToken,
    signal,
  });
}

/** Set up or update the worker over one origin branch. */
export function setupWorker(
  branch: string,
  codeOnly: boolean,
  csrfToken: string,
  signal?: AbortSignal,
): Promise<ProvisioningReport> {
  return runCommand<ProvisioningReport>("/api/settings/worker/setup", {
    body: { branch, code_only: codeOnly },
    csrfToken,
    signal,
  });
}

/** Read the worker's prepared code and resource readiness. */
export function preflightWorker(
  csrfToken: string,
  signal?: AbortSignal,
): Promise<ProvisioningReport> {
  return runCommand<ProvisioningReport>("/api/settings/worker/preflight", {
    body: {},
    csrfToken,
    signal,
  });
}
