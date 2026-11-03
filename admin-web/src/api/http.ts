/**
 * Same-origin transport for the administration console.
 *
 * Every request carries the session cookie, asks for no stored response and names the console's own
 * origin implicitly, so the browser supplies the Origin header itself. A POST carries the session's
 * CSRF token. An automatic read adds the console's own fixed marker header so the backend can omit
 * a successful scheduled poll from the sole command log. A failed request is an authentication,
 * admission or transport condition. A command that ran and failed answers a 200 envelope whose
 * nonzero exit code becomes a command failure. One JSON answer and one newline-delimited command
 * stream share that header, cookie, status and envelope handling. No request is retried, and no
 * request or response body is logged.
 */
import type { PromotionStep } from "./types";

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
   * Record one command outcome with its retained class line and its transient guidance line.
   *
   * The failure line names an exception class and an optional checked return code, never captured
   * output, and it is the command log's failure detail alone. The guidance line is the owning
   * operation's fixed advice for the operator, and the panel shows it in place of the class line.
   */
  constructor(
    readonly failureLine: string | null,
    readonly guidanceLine: string | null = null,
  ) {
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
  guidance_line?: string | null;
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

/** Send one request over the console boundary and return the accepted response. */
async function send(path: string, options: RequestOptions): Promise<Response> {
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
  return response;
}

/** Decode one command envelope and return its report, or raise its ordinary failure. */
function decodeEnvelope(payload: unknown): unknown {
  const envelope = payload as CommandEnvelope | undefined;
  if (envelope === undefined || typeof envelope.exit_code !== "number") {
    throw new CommandFailure(null);
  }
  if (envelope.exit_code !== 0) {
    throw new CommandFailure(
      envelope.failure_line,
      envelope.guidance_line ?? null,
    );
  }
  if (envelope.report === null) {
    throw new CommandFailure(
      envelope.failure_line,
      envelope.guidance_line ?? null,
    );
  }
  return envelope.report;
}

async function request(
  path: string,
  options: RequestOptions,
): Promise<unknown | undefined> {
  const response = await send(path, options);
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
  const payload = await request(path, {
    method: options.body === undefined ? "GET" : "POST",
    body: options.body,
    csrfToken: options.csrfToken,
    signal: options.signal,
    automatic: options.automatic,
  });
  return decodeEnvelope(payload) as T;
}

/** Send one JSON request whose answer is a single decoded object rather than a command envelope. */
export async function exchange<T>(
  path: string,
  options: RequestOptions,
): Promise<T> {
  return (await request(path, options)) as T;
}

/**
 * Run one admitted command that reports its coarse steps and then one terminal result.
 *
 * Each complete physical line holds either one `step` record or the terminal `result` record. A
 * step reaches `onStep` as it arrives, so a caller sees progress before the command finishes. The
 * terminal record is decoded with the same envelope handling as `runCommand`. An end of stream
 * without that record, a partial final line and a malformed record are ordinary command failures,
 * never success. The reader is never retried, and an aborted read leaves the command running on
 * the server.
 */
export async function runStreamingCommand<T>(
  path: string,
  options: {
    body: unknown;
    csrfToken: string;
    onStep: (step: PromotionStep) => void;
    signal?: AbortSignal;
  },
): Promise<T> {
  const response = await send(path, {
    method: "POST",
    body: options.body,
    csrfToken: options.csrfToken,
    signal: options.signal,
  });
  if (response.body === null) {
    throw new CommandFailure(null);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffered = "";
  let report: unknown;
  let finished = false;
  while (!finished) {
    const chunk = await reader.read();
    if (chunk.done) {
      buffered += decoder.decode();
      break;
    }
    buffered += decoder.decode(chunk.value, { stream: true });
    let newline = buffered.indexOf("\n");
    while (newline !== -1) {
      const line = buffered.slice(0, newline);
      buffered = buffered.slice(newline + 1);
      report = consume(line, options.onStep);
      if (report !== undefined) {
        finished = true;
        break;
      }
      newline = buffered.indexOf("\n");
    }
  }
  if (report === undefined || buffered !== "") {
    throw new CommandFailure(null);
  }
  return report as T;
}

/** Report one stream record's step to the caller, or return its terminal report. */
function consume(line: string, onStep: (step: PromotionStep) => void): unknown {
  let record: unknown;
  try {
    record = JSON.parse(line);
  } catch {
    throw new CommandFailure(null);
  }
  if (typeof record !== "object" || record === null) {
    throw new CommandFailure(null);
  }
  const { step, result } = record as { step?: unknown; result?: unknown };
  if (typeof step === "string") {
    onStep(step as PromotionStep);
    return undefined;
  }
  if (result === undefined) {
    throw new CommandFailure(null);
  }
  return decodeEnvelope(result);
}

/**
 * Return the message one failed command presents, never a response body or a status detail.
 *
 * A command failure shows its owning operation's guidance line. Its class line stays in the
 * command log alone, and a failure without guidance shows the panel's ordinary fallback.
 */
export function failureText(error: unknown, fallback: string): string {
  if (error instanceof CommandFailure) {
    return error.guidanceLine ?? fallback;
  }
  return fallback;
}
