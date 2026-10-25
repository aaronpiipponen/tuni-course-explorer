/**
 * Explicit route ownership: one disposable worker per uncached calculation and one shared cache.
 *
 * The worker constructor is the one external boundary double. It records the posted request and
 * lets a test settle the promise with the real solver result, so the hook's lifecycle, guards and
 * cache use are observed without a second solver.
 */
import { act, createElement, type ReactNode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type {
  CourseSummary,
  PrerequisiteGraphReport,
  PrerequisitePath,
  SolverStructure,
} from "../../../api/types";
import { ReadCache } from "../../../app/readCache";
import { ReadCacheContext } from "../../../app/readCacheContext";
import { runRequest, type SolverRequest } from "../../../solver/request";
import { usePrerequisiteInputs } from "../usePrerequisiteInputs";
import { useMinimumRoute, type MinimumRouteSession } from "./useMinimumRoute";

(
  globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

const workers = vi.hoisted(() => {
  type Instance = {
    request: SolverRequest | null;
    terminated: boolean;
    emitResult(result: PrerequisitePath): void;
  };
  const instances: Instance[] = [];
  class WorkerDouble extends EventTarget {
    request: SolverRequest | null = null;
    terminated = false;
    constructor() {
      super();
      instances.push(this as unknown as Instance);
    }
    postMessage(request: SolverRequest) {
      this.request = request;
    }
    terminate() {
      this.terminated = true;
    }
    emitResult(result: PrerequisitePath) {
      this.dispatchEvent(new MessageEvent("message", { data: result }));
    }
  }
  return { instances, WorkerDouble };
});

vi.mock("./worker?worker", () => ({ default: workers.WorkerDouble }));

type Inputs = ReturnType<typeof usePrerequisiteInputs>;

const course = (group_id: string): CourseSummary => ({
  group_id,
  name_fi: null,
  name_en: group_id,
  code: group_id,
  credits_min: "5",
  credits_max: null,
  is_active: true,
  official_url: "https://example.invalid",
});
const structure: SolverStructure = {
  root_group_id: "root",
  academic_year_start: 2026,
  root_use_id: null,
  pieces: [],
  uses: [],
  facts: [],
  diagnostics: [],
  root_diagnostic_ids: [],
  courses: [course("root")],
  modules: [],
  include_recommended: false,
  include_inferred: false,
  active_only: false,
  inferred_coverage: [],
  excluded_group_ids: [],
  completed_node_keys: [],
  excluded_node_keys: [],
  bindings: [],
  projection_root_context_id: null,
  projection_contexts: [],
  members: [],
};
const makeReport = (
  overrides: Partial<PrerequisiteGraphReport> = {},
): PrerequisiteGraphReport => ({
  drawing: {
    allowed: true,
    limit: null,
    course_count: 1,
    node_count: 1,
    edge_count: 0,
    element_count: 1,
  },
  dataset_identity: "dataset-a",
  max_compact_nodes: 10000,
  solver: structure,
  display: null,
  ...overrides,
});
const request = {
  target_code: "root",
  completed_codes: [] as string[],
  selected_codes: [] as string[],
  excluded_codes: [] as string[],
  include_recommended: false,
  include_inferred: false,
  active_only: false,
  basis: "completed" as const,
  completed_node_keys: [] as string[],
  excluded_node_keys: [] as string[],
};
const makeInputs = (overrides: Partial<Inputs> = {}): Inputs => {
  const value = { ...request, ...(overrides.request ?? {}) };
  return {
    request: value,
    key: JSON.stringify(value),
    active: true,
    graphRequest: null,
    graphKey: "graph-key",
    graphInputError: null,
    graphInputsPending: false,
    ...overrides,
  };
};
const routeKeyFor = (report: PrerequisiteGraphReport, inputs: Inputs): string =>
  JSON.stringify([
    "minimum-route",
    report.dataset_identity,
    inputs.graphKey,
    inputs.key,
    report.max_compact_nodes,
  ]);

let session: MinimumRouteSession | null = null;

function RouteHarness({
  inputs,
  report,
  ready,
}: {
  inputs: Inputs;
  report: PrerequisiteGraphReport;
  ready: boolean;
}) {
  session = useMinimumRoute(inputs, report, ready);
  return null;
}

describe("explicit route ownership", () => {
  let container: HTMLDivElement;
  let root: Root;
  let cache: ReadCache;

  beforeEach(() => {
    workers.instances.length = 0;
    session = null;
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    cache = new ReadCache("dataset-a", 8);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  const mount = (
    inputs: Inputs,
    report: PrerequisiteGraphReport,
    ready = true,
  ) => {
    act(() =>
      root.render(
        createElement(
          ReadCacheContext.Provider,
          { value: cache },
          createElement(RouteHarness, { inputs, report, ready }) as ReactNode,
        ),
      ),
    );
  };

  it("presents cached routes only after an explicit find", async () => {
    const report = makeReport();
    const inputs = makeInputs();
    const response = runRequest({
      operation: "route",
      structure,
      basis_group_ids: [],
      max_compact_nodes: 10000,
    });
    mount(inputs, report);
    expect(session?.result).toBeNull();
    expect(workers.instances).toHaveLength(0);

    act(() => session?.find());
    expect(workers.instances).toHaveLength(1);
    const calculation = workers.instances[0];
    expect(calculation.request).toEqual({
      operation: "route",
      structure,
      basis_group_ids: [],
      max_compact_nodes: 10000,
    });
    expect(calculation.terminated).toBe(false);
    expect(session?.calculating).toBe(true);

    await act(async () => calculation.emitResult(response));
    expect(calculation.terminated).toBe(true);
    expect(session?.result).toEqual(response);
    expect(session?.calculating).toBe(false);

    act(() => session?.clear());
    expect(session?.result).toBeNull();
    mount(inputs, report);
    expect(session?.result).toBeNull();

    const changed = makeInputs({
      request: { ...request, completed_codes: ["other"] },
    });
    mount(changed, report);
    mount(inputs, report);
    expect(session?.result).toBeNull();

    act(() => session?.find());
    expect(workers.instances).toHaveLength(1);
    expect(session?.result).toEqual(response);

    act(() => root.unmount());
    root = createRoot(container);
    mount(inputs, report);
    expect(session?.result).toBeNull();
    act(() => session?.find());
    expect(workers.instances).toHaveLength(1);
    expect(session?.result).toEqual(response);
  });

  it.each([
    [
      "changed inputs",
      (inputs: Inputs, report: PrerequisiteGraphReport) =>
        mount(
          makeInputs({
            request: { ...request, completed_codes: ["other"] },
            graphKey: inputs.graphKey,
          }),
          report,
        ),
    ],
    [
      "readiness loss",
      (inputs: Inputs, report: PrerequisiteGraphReport) =>
        mount(inputs, report, false),
    ],
    ["report replacement", (inputs: Inputs) => mount(inputs, makeReport())],
    [
      "dataset change",
      (inputs: Inputs) =>
        mount(inputs, makeReport({ dataset_identity: "dataset-b" })),
    ],
    [
      "pane exit",
      (_inputs: Inputs, report: PrerequisiteGraphReport) =>
        mount(makeInputs({ active: false }), report),
    ],
    [
      "unmount",
      () => {
        act(() => root.unmount());
        root = createRoot(container);
      },
    ],
  ])(
    "discards a worker calculation when its inputs cease to be current through %s",
    async (_cause, change) => {
      const report = makeReport();
      const inputs = makeInputs();
      const response = runRequest({
        operation: "route",
        structure,
        basis_group_ids: [],
        max_compact_nodes: 10000,
      });
      mount(inputs, report);
      act(() => session?.find());
      const calculation = workers.instances[0];
      expect(calculation.terminated).toBe(false);

      change(inputs, report);

      expect(calculation.terminated).toBe(true);
      await act(async () => calculation.emitResult(response));
      expect(session?.result ?? null).toBeNull();
      expect(cache.get(routeKeyFor(report, inputs))).toBeUndefined();
    },
  );
});
