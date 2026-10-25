/**
 * Run one explicit route calculation in a disposable browser worker.
 *
 * One call creates one worker, posts one request and settles on its one result, its error, or
 * cancellation. Every terminal path removes the listeners and terminates the worker.
 */
import type { PrerequisitePath } from "../../../api/types";
import type { SolverRequest } from "../../../solver/request";
import RouteWorker from "./worker?worker";

/**
 * Calculate one route in a disposable worker and settle on its result.
 *
 * Each call creates one worker, posts the request once and removes the worker on every
 * settlement. An already-aborted signal rejects before a worker starts, a later abort rejects with
 * `AbortError` and terminates the worker, a worker error rejects with its message, and an
 * unreadable reply rejects as an unreadable message. The worker is never reused.
 */
export function calculateRouteInWorker(
  request: SolverRequest,
  signal: AbortSignal,
): Promise<PrerequisitePath> {
  if (signal.aborted) {
    return Promise.reject(
      new DOMException("The route calculation was cancelled", "AbortError"),
    );
  }
  const worker = new RouteWorker();
  return new Promise<PrerequisitePath>((resolve, reject) => {
    const cleanup = () => {
      worker.removeEventListener("message", onMessage);
      worker.removeEventListener("error", onError);
      worker.removeEventListener("messageerror", onMessageError);
      signal.removeEventListener("abort", onAbort);
      worker.terminate();
    };
    const onMessage = (event: MessageEvent<PrerequisitePath>) => {
      cleanup();
      resolve(event.data);
    };
    const onError = (event: ErrorEvent) => {
      cleanup();
      reject(new Error(event.message || "The route worker failed"));
    };
    const onMessageError = () => {
      cleanup();
      reject(new Error("The route worker returned an unreadable message"));
    };
    const onAbort = () => {
      cleanup();
      reject(
        new DOMException("The route calculation was cancelled", "AbortError"),
      );
    };
    worker.addEventListener("message", onMessage);
    worker.addEventListener("error", onError);
    worker.addEventListener("messageerror", onMessageError);
    signal.addEventListener("abort", onAbort);
    worker.postMessage(request);
  });
}
