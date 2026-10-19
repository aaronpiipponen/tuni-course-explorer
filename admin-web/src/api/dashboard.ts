/** The Dashboard's one fixed server status read. */
import { runCommand } from "./http";
import type { ServerStatusReport } from "./types";

const DASHBOARD_PATH = "/api/dashboard";

/** Read the server status report. */
export function readDashboard(
  signal?: AbortSignal,
  automatic = false,
): Promise<ServerStatusReport> {
  return runCommand<ServerStatusReport>(DASHBOARD_PATH, { signal, automatic });
}
