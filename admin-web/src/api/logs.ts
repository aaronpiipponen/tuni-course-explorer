/** The Logs tab's fixed command-log, session, runtime and usage requests. */
import { runCommand } from "./http";
import type {
  CommandLogReport,
  LogReadReport,
  LogSessionsReport,
  LogSource,
  StageName,
  UsageReport,
} from "./types";

/** Read the retained administration command log. */
export function readCommandLog(
  signal?: AbortSignal,
  automatic = false,
): Promise<CommandLogReport> {
  return runCommand<CommandLogReport>("/api/logs/commands", {
    signal,
    automatic,
  });
}

/** List the sessions the four stage roots hold. */
export function readLogSessions(
  signal?: AbortSignal,
  automatic = false,
): Promise<LogSessionsReport> {
  return runCommand<LogSessionsReport>("/api/logs/sessions", {
    signal,
    automatic,
  });
}

/** Read the last lines of one fixed source of one listed session. */
export function readSessionLog(
  stage: StageName,
  sessionId: string,
  source: LogSource,
  lines: number,
  csrfToken: string,
  signal?: AbortSignal,
  automatic = false,
): Promise<LogReadReport> {
  return runCommand<LogReadReport>("/api/logs/read", {
    body: { stage, session_id: sessionId, source, lines },
    csrfToken,
    signal,
    automatic,
  });
}

/** Read the last lines of the embedding service's own container log. */
export function readEmbeddingLog(
  lines: number,
  csrfToken: string,
  signal?: AbortSignal,
  automatic = false,
): Promise<LogReadReport> {
  return runCommand<LogReadReport>("/api/logs/embedding", {
    body: { lines },
    csrfToken,
    signal,
    automatic,
  });
}

/** Read the windowed request usage report, which prunes the records past retention. */
export function readUsage(
  hours: number,
  csrfToken: string,
  signal?: AbortSignal,
  automatic = false,
): Promise<UsageReport> {
  return runCommand<UsageReport>("/api/logs/usage", {
    body: { hours },
    csrfToken,
    signal,
    automatic,
  });
}
