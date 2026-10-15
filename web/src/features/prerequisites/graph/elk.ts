/** Lazily started ELK worker shared by prerequisite graph layouts. */
import ELK from "elkjs/lib/elk-api";
import ElkWorker from "elkjs/lib/elk-worker.min.js?worker";

const elk = new ELK({ workerFactory: () => new ElkWorker() });
export type ElkNode = Parameters<typeof elk.layout>[0];
export function layoutWithElk(
  input: ElkNode,
): Promise<Awaited<ReturnType<typeof elk.layout>>> {
  return elk.layout(input);
}
