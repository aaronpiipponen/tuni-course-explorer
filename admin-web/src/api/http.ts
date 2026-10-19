/**
 * Same-origin JSON transport for the administration console.
 *
 * Every request carries the session cookie, asks for no stored response and names the console's own
 * origin implicitly, so the browser supplies the Origin header itself. A POST carries the session's
 * CSRF token. An automatic read adds the console's own fixed marker header so the backend can omit
 * a successful scheduled poll from the sole command log. A failed request is an authentication,
 * admission or transport condition. A command that ran and failed answers a 200 envelope whose
 * nonzero exit code becomes a command failure. No request is retried, and no request or response
 * body is logged.
 */

/** One request answered with an HTTP status outside the successful range. */
export class ApiError extends Error {
  /**
   * Record one refused request and the status that refused it.
   *
   * A status of 401 or 403 is an admission condition the application handles. Any other status is a
   * transport or server condition the affected panel reports.
   */
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** One command that ran and reported a nonzero exit code or no report. */
export class CommandFailure extends Error {
  /**
   * Record one command outcome with the safe failure line the command reported.
   *
   * The line names an exception class and an optional checked return code, never captured output.
   */
  constructor(readonly failureLine: string | null) {
    super(failureLine ?? "command failed");
    this.name = "CommandFailure";
  }
}

/**
 * Report one failed request as an admission refusal to the application shell.
 *
 * An `ApiError` with status 401 or 403 calls `onRefusal` once with that status and reports true, so
 * one returned value says whether the caller must stop its own handling. A caller that sets its own
 * failure state before it notifies the shell is unmounted by that handling. Any other error reports
 * false and stays the calling panel's own failure. The call sends no request, stores no state and
 * retries nothing.
 */
export function handleAdmissionFailure(
  error: unknown,
  onRefusal: (status: number) => void,
): boolean {
  if (
    error instanceof ApiError &&
    (error.status === 401 || error.status === 403)
  ) {
    onRefusal(error.status);
    return true;
  }
  return false;
}

/** The transient outcome of one fixed command, as the backend serializes it. */
interface CommandEnvelope {
  exit_code: number;
  report: Record<string, unknown> | null;
  failure_line: string | null;
}

interface RequestOptions {
  method: "GET" | "POST";
  body?: unknown;
  csrfToken?: string;
  signal?: AbortSignal;
  automatic?: boolean;
}

// The one request header that marks a read the console repeats on its own timer.
const AUTOMATIC_READ_HEADER = "X-Admin-Automatic-Read";

async function request(
  path: string,
  options: RequestOptions,
): Promise<unknown | undefined> {
  const headers: Record<string, string> = {};
  if (options.method === "POST") {
    headers["content-type"] = "application/json";
    headers["X-CSRF-Token"] = options.csrfToken ?? "";
  }
  if (options.automatic === true) {
    headers[AUTOMATIC_READ_HEADER] = "1";
  }
  const response = await fetch(path, {
    method: options.method,
    headers,
    body:
      options.method === "POST"
        ? JSON.stringify(options.body ?? {})
        : undefined,
    credentials: "same-origin",
    cache: "no-store",
    signal: options.signal,
  });
  if (!response.ok) {
    throw new ApiError(`request failed (${response.status})`, response.status);
  }
  if (response.status === 204) {
    return undefined;
  }
  return (await response.json()) as unknown;
}

/** Run one fixed command over the console transport and return its report. */
export async function runCommand<T>(
  path: string,
  options: {
    body?: unknown;
    csrfToken?: string;
    signal?: AbortSignal;
    automatic?: boolean;
  } = {},
): Promise<T> {
  const payload = (await request(path, {
    method: options.body === undefined ? "GET" : "POST",
    body: options.body,
    csrfToken: options.csrfToken,
    signal: options.signal,
    automatic: options.automatic,
  })) as CommandEnvelope | undefined;
  if (payload === undefined || typeof payload.exit_code !== "number") {
    throw new CommandFailure(null);
  }
  if (payload.exit_code !== 0) {
    throw new CommandFailure(payload.failure_line);
  }
  if (payload.report === null) {
    throw new CommandFailure(payload.failure_line);
  }
  return payload.report as T;
}

/** Send one JSON request whose answer is a single decoded object rather than a command envelope. */
export async function exchange<T>(
  path: string,
  options: RequestOptions,
): Promise<T> {
  return (await request(path, options)) as T;
}

/** Return the message one failed request presents, never a response body or a status detail. */
export function failureText(error: unknown, fallback: string): string {
  if (error instanceof CommandFailure) {
    return error.failureLine ?? fallback;
  }
  return fallback;
}
