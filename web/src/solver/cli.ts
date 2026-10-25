/**
 * Read one machine solver request from standard input and write its one JSON result to standard
 * output.
 *
 * An uncaught error ends the process with a nonzero status and its message on standard error, so
 * a caller never receives a partial result.
 */
import { runRequest, type SolverRequest } from "./request";

/** The process members the entry reads, with no Node globals in the frontend type set. */
type NodeProcess = {
  readonly stdin: {
    setEncoding(encoding: string): void;
    on(event: "data", listener: (chunk: string) => void): void;
    on(event: "end", listener: () => void): void;
  };
  readonly stdout: { write(text: string): void };
};

declare const process: NodeProcess;

let requestText = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk: string) => {
  requestText += chunk;
});
process.stdin.on("end", () => {
  const request = JSON.parse(requestText) as SolverRequest;
  process.stdout.write(`${JSON.stringify(runRequest(request))}\n`);
});
