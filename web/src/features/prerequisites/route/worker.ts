/**
 * Run the shared minimum-route solver for one explicit calculation in a browser worker.
 *
 * The module receives one solver request, runs it once and posts its result. A failing calculation
 * leaves the worker error event to the client, so no fabricated route reaches the page.
 */
import { runRequest, type SolverRequest } from "../../../solver/request";

type WorkerScope = {
  postMessage(message: unknown): void;
  addEventListener(
    type: "message",
    listener: (event: MessageEvent<SolverRequest>) => void,
  ): void;
};

const scope = globalThis as unknown as WorkerScope;

scope.addEventListener("message", (event) => {
  scope.postMessage(runRequest(event.data));
});
