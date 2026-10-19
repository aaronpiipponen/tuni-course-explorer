/** The three authentication requests of the administration console. */
import { exchange } from "./http";
import type { SessionReport } from "./types";

export const SESSION_PATH = "/auth/session";
export const LOGIN_PATH = "/auth/login";
export const LOGOUT_PATH = "/auth/logout";

/** Read the console's own session, which also issues an anonymous bootstrap when none exists. */
export function fetchSession(signal?: AbortSignal): Promise<SessionReport> {
  return exchange<SessionReport>(SESSION_PATH, { method: "GET", signal });
}

/**
 * Submit one credential attempt over the session's CSRF token and return the granted session.
 *
 * A wrong credential answers a `401`, which the sign-in screen reports as its own message. A `403`
 * is the terminal admission refusal the shell's handling consumes, and the durable lock, a missing
 * live session and a site or CSRF refusal all answer it.
 */
export function login(
  username: string,
  password: string,
  csrfToken: string,
  signal?: AbortSignal,
): Promise<SessionReport> {
  return exchange<SessionReport>(LOGIN_PATH, {
    method: "POST",
    body: { username, password },
    csrfToken,
    signal,
  });
}

/** End the console's own session on the server. */
export function logout(csrfToken: string, signal?: AbortSignal): Promise<void> {
  return exchange<void>(LOGOUT_PATH, {
    method: "POST",
    body: {},
    csrfToken,
    signal,
  });
}
