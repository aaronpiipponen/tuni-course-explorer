/**
 * Session-boundary proofs for the console shell.
 *
 * Each invocation drives one authentication transition with the real application, the real API
 * clients and a fetch boundary that stands in for the browser. No product behavior is imitated: the
 * boundary answers the exact routes the console requests, records them, and exposes only the fields
 * the console transport reads. The signed-in shell mounts every tab tree, so a transition answers
 * the whole initial read wave and one explicit-action transition navigates the real shell and clicks
 * one named action of one panel.
 */
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type {
  BackupListReport,
  CatalogueSummary,
  CommandLogReport,
  ConfigurationFileReport,
  ConfigurationFilesReport,
  CourseEmbeddingCoverageReport,
  DatasetListReport,
  InferenceAdministrativeSummary,
  LifecycleStatus,
  LogReadReport,
  LogSessionsReport,
  ServerStatusReport,
  SessionReport,
  StageName,
  TeachingTextCoverageReport,
  UsageReport,
} from "../api/types";
import { wording } from "../shared/wording";
import { App } from "./App";

(
  globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

const APP_URL = "http://localhost:8026/";
const REPOSITORY_URL = "https://github.com/owner/repo";
const CONFIG_FILE = "config/web.toml";
const OPERATOR = "synthetic-operator";
const PASSWORD = "synthetic-console-password";
const ADMIN_REBUILD_PATH = "/api/settings/rebuild-admin";

const ADMIN_REBUILD_REPORT = { schema_version: 1, steps: ["frontend"] };

const ANONYMOUS: SessionReport = {
  authenticated: false,
  csrf_token: "csrf-anonymous",
  poll_seconds: 3600,
  app_url: APP_URL,
  repository_url: REPOSITORY_URL,
};

const AUTHENTICATED: SessionReport = {
  authenticated: true,
  csrf_token: "csrf-authenticated",
  poll_seconds: 3600,
  app_url: APP_URL,
  repository_url: REPOSITORY_URL,
};

const DASHBOARD_REPORT: ServerStatusReport = {
  schema_version: 1,
  website: {
    unit: "synthetic-web.service",
    state: "active",
    substate: "running",
    main_pid: 42,
    host: "127.0.0.1",
    port: 8026,
    configured_workers: 2,
    entry_point: "scripts/run_web.sh",
    started_at: "2026-10-10T04:39:00Z",
    uptime_seconds: 3600,
    checkout_branch: "admin-ui",
    checkout_revision: "a".repeat(40),
  },
  host: {
    uptime_seconds: 7200,
    cpu_usage_percent: 37.5,
    memory_total_bytes: 1024,
    memory_used_bytes: 512,
    data_bytes: 1024,
    models_bytes: null,
    backups_bytes: null,
    disk_total_bytes: 2048,
    disk_free_bytes: 1024,
  },
  database: {
    container: { state: "running", health: null, image: "pgvector" },
    host: "127.0.0.1",
    port: 5432,
    name: "course_explorer",
    schema_revision: "20261014_0018",
    expected_schema_revision: "20261014_0018",
    at_head: true,
    size_bytes: null,
    connections: 4,
    shared_memory_bytes: 1024,
  },
  embedding: {
    container: { state: "running", health: null, image: "llama" },
    host: "127.0.0.1",
    port: 8080,
    model: "BAAI/bge-m3",
    artifact: "models/synthetic.gguf",
    context_size: 2048,
    threads: 2,
    pooling: "cls",
    normalization: 2,
  },
  serving: {
    selection_enabled: true,
    dataset_id: "b".repeat(32),
    kind: "returned",
    predecessor_id: null,
    pointer: "data/admin/selected-dataset.json",
    receipt_schema_revision: "20261014_0018",
  },
  hubs: [
    {
      alias: "EMBEDDING_HUB_VECTOR",
      path: "config/derived/embedding-hub.json",
      modified_at: "2026-10-18T08:41:00Z",
      newer_than_web_start: false,
    },
  ],
};

/** One idle stage status with no progress member, which the panels render as rows alone. */
function lifecycleStatus(stage: StageName): LifecycleStatus {
  return {
    stage,
    lifecycle: "idle",
    session_id: null,
    revision: null,
    progress: null,
    active_seconds: 0,
    error_type: null,
    items_per_second: null,
    eta_seconds: null,
  };
}

const CATALOGUE_SUMMARY: CatalogueSummary = {
  curriculum_period_count: 1,
  canonical_course_count: 2,
  active_course_count: 3,
  course_version_count: 4,
  canonical_module_count: 5,
  module_version_count: 6,
};

const TEACHING_TEXT_COVERAGE: TeachingTextCoverageReport = {
  canonical_course_count: 2,
  representative_course_count: 2,
  no_representative_course_count: 0,
  name_only_course_count: 0,
  unembeddable_course_count: 0,
  fields: [],
};

const EMBEDDING_COVERAGE: CourseEmbeddingCoverageReport = {
  total_chunk_count: 2,
  pending_count: 1,
  completed_count: 1,
  failed_count: 0,
  fields: [],
};

const DATASETS: DatasetListReport = {
  schema_version: 1,
  datasets: [],
};

const COMMAND_LOG_REPORT: CommandLogReport = { schema_version: 1, entries: [] };

const LOG_SESSIONS_REPORT: LogSessionsReport = {
  schema_version: 1,
  sessions: [],
};

const EMBEDDING_LOG_REPORT: LogReadReport = {
  schema_version: 1,
  stage: "embedding",
  session_id: null,
  source: "embedding-runtime",
  available: true,
  text: "synthetic embedding log\n",
};

const USAGE_REPORT: UsageReport = {
  window_start: "2026-10-18T00:00:00Z",
  window_end: "2026-10-19T00:00:00Z",
  requests: 0,
  mean_duration_seconds: null,
  routes: [],
};

const CONFIGURATION_FILES: ConfigurationFilesReport = {
  schema_version: 1,
  files: [CONFIG_FILE],
};

const CONFIGURATION_FILE: ConfigurationFileReport = {
  schema_version: 1,
  file: CONFIG_FILE,
  values: {
    WEB_PORT: 8027,
    WEB_INFERENCE_ENABLED: true,
    WEB_EMBEDDINGS_ENABLED: true,
  },
};

const BACKUP_LIST: BackupListReport = { schema_version: 1, backups: [] };

const INFERENCE_SUMMARY: InferenceAdministrativeSummary = {
  schema_version: 1,
  dataset_scope: "selected",
  coverage: {
    schema_version: 1,
    eligible_targets: 1,
    retained_complete_targets: 0,
    published_targets: 0,
    uncovered_targets: 1,
    current_equivalence_groups: 0,
    historical_proposal_rows: 0,
    generation_counts: [],
    cycle_id: null,
    stage: null,
    failed_targets: 0,
    pending_targets: 0,
  },
  publication: {
    eligible_targets: 1,
    selected_targets: 0,
    processed_targets: 0,
    local_targets: 0,
    accepted_targets: 0,
    published_targets: 0,
    operator_done_targets: 0,
    observed_packet_candidates: 0,
    expected_packet_candidates: 0,
    historical_proposal_rows: 0,
    current_equivalence_groups: 0,
    transitive_warnings: [],
    proposal_version: "synthetic",
    prompt_version: "synthetic",
    schema_version: "synthetic",
    pipeline_version: "synthetic",
  },
  failures: [],
  operator_done_targets: 0,
  operator_failed_target_group_ids: [],
  routing_policy: "synthetic",
  recommendation_policy: "synthetic",
  finding_filter_policy: "synthetic",
};

/** One report per feature read the mounted panels request. */
const REPORTS: Record<string, unknown> = {
  "GET /api/dashboard": DASHBOARD_REPORT,
  "GET /api/preparation/status/ingestion": lifecycleStatus("ingestion"),
  "GET /api/preparation/status/translation": lifecycleStatus("translation"),
  "GET /api/preparation/status/embedding": lifecycleStatus("embedding"),
  "GET /api/preparation/report/catalogue": CATALOGUE_SUMMARY,
  "GET /api/preparation/report/teaching-text": TEACHING_TEXT_COVERAGE,
  "GET /api/preparation/report/embedding": EMBEDDING_COVERAGE,
  "GET /api/inference/status": lifecycleStatus("inference"),
  "GET /api/inference/summary": INFERENCE_SUMMARY,
  "GET /api/inference/datasets": DATASETS,
  "GET /api/logs/commands": COMMAND_LOG_REPORT,
  "GET /api/logs/sessions": LOG_SESSIONS_REPORT,
  "POST /api/logs/embedding": EMBEDDING_LOG_REPORT,
  "POST /api/logs/usage": USAGE_REPORT,
  "GET /api/settings/config/files": CONFIGURATION_FILES,
  "POST /api/settings/config/read": CONFIGURATION_FILE,
  "GET /api/settings/backups": BACKUP_LIST,
};

/** One browser response exposing only the fields the console transport reads. */
interface StubResponse {
  ok: boolean;
  status: number;
  json: () => Promise<unknown>;
}

function respond(status: number, body?: unknown): StubResponse {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  };
}

function envelope(report: unknown): StubResponse {
  return respond(200, { exit_code: 0, report, failure_line: null });
}

interface RecordedCall {
  method: string;
  path: string;
  body: string | null;
  automatic: boolean;
}

const calls: RecordedCall[] = [];

function routeOf(call: RecordedCall): string {
  return `${call.method} ${call.path}`;
}

/** Return how many times one exact route was requested. */
function countOf(route: string): number {
  return calls.filter((call) => routeOf(call) === route).length;
}

/** One protected request whose admission the site refuses. */
type RefusalSource =
  | "dashboard"
  | "logout"
  | "stage-action"
  | "inference-action"
  | "hub-write"
  | "logs-read"
  | "settings-write";

/** One protected request one invocation refuses, with the status the site answers. */
interface ProtectedRefusal {
  source: RefusalSource;
  status: 401 | 403;
}

/** One tab one invocation opens from the dashboard. */
interface TabTransition {
  name: string;
  kind: "tab";
  tab: string;
  panel: string;
  route: string;
}

/** One transition one invocation drives. */
type Transition =
  | {
      name: string;
      kind:
        | "authenticated"
        | "login-success"
        | "login-refusal"
        | "login-locked"
        | "bootstrap-locked"
        | "logout"
        | "admin-rebuild-success"
        | "admin-rebuild-failure";
    }
  | TabTransition
  | ({ name: string; kind: "protected" } & ProtectedRefusal)
  | { name: string; kind: "protected-wave"; status: 401 };

const REFUSAL_ROUTES: Record<RefusalSource, string> = {
  dashboard: "GET /api/dashboard",
  logout: "POST /auth/logout",
  "stage-action": "POST /api/preparation/action",
  "inference-action": "POST /api/inference/action",
  "hub-write": "POST /api/preparation/hubs",
  "logs-read": "GET /api/logs/commands",
  "settings-write": "POST /api/settings/config/set",
};

const REFUSAL_SOURCES = Object.keys(REFUSAL_ROUTES) as RefusalSource[];

/** One tab transition per implemented tab, opening it from the dashboard. */
const TAB_TRANSITIONS: TabTransition[] = [
  {
    name: "tab-dashboard",
    kind: "tab",
    tab: wording.tabs.dashboard,
    panel: wording.dashboard.serving,
    route: "GET /api/dashboard",
  },
  {
    name: "tab-preparation",
    kind: "tab",
    tab: wording.tabs.preparation,
    panel: wording.stage.ingestion,
    route: "GET /api/preparation/status/ingestion",
  },
  {
    name: "tab-inference",
    kind: "tab",
    tab: wording.tabs.inference,
    panel: wording.inference.run,
    route: "GET /api/inference/status",
  },
  {
    name: "tab-logs",
    kind: "tab",
    tab: wording.tabs.logs,
    panel: wording.logs.commandLog,
    route: "GET /api/logs/commands",
  },
  {
    name: "tab-settings",
    kind: "tab",
    tab: wording.tabs.settings,
    panel: wording.settings.configuration,
    route: "GET /api/settings/config/files",
  },
];

const TRANSITIONS: Transition[] = [
  { name: "login-success", kind: "login-success" },
  { name: "login-refusal", kind: "login-refusal" },
  { name: "login-locked", kind: "login-locked" },
  { name: "bootstrap-locked", kind: "bootstrap-locked" },
  { name: "logout", kind: "logout" },
  { name: "admin-rebuild-success", kind: "admin-rebuild-success" },
  { name: "admin-rebuild-failure", kind: "admin-rebuild-failure" },
  ...TAB_TRANSITIONS,
  { name: "protected-wave-401", kind: "protected-wave", status: 401 },
  ...REFUSAL_SOURCES.flatMap((source) =>
    ([401, 403] as const).map((status) => ({
      name: `protected-${source}-${status}`,
      kind: "protected" as const,
      source,
      status,
    })),
  ),
];

/** The tab, panel and action button one protected action transition clicks. */
function actionFor(
  source: RefusalSource,
): { tab: string; panel: string; name: string } | null {
  if (source === "stage-action") {
    return {
      tab: wording.tabs.preparation,
      panel: wording.stage.translation,
      name: wording.action.start,
    };
  }
  if (source === "inference-action") {
    return {
      tab: wording.tabs.inference,
      panel: wording.inference.run,
      name: wording.action.start,
    };
  }
  if (source === "hub-write") {
    return {
      tab: wording.tabs.preparation,
      panel: wording.preparation.embeddingCoverage,
      name: wording.preparation.writeHubs,
    };
  }
  return null;
}

/** The protected heading the refusal of one source unmounts. */
function protectedHeading(source: RefusalSource): string {
  if (source === "stage-action") {
    return wording.stage.translation;
  }
  if (source === "inference-action") {
    return wording.inference.run;
  }
  if (source === "hub-write") {
    return wording.preparation.embeddingCoverage;
  }
  if (source === "logs-read") {
    return wording.logs.commandLog;
  }
  if (source === "settings-write") {
    return wording.settings.configuration;
  }
  return wording.dashboard.serving;
}

/** The signed-in shell holds one server-status read, and every refusal source names one route. */
const REFUSAL_REQUESTS = 1;

/** Answer every request of one transition, refusing exactly the named protected route. */
function install(transition: Transition): void {
  const refusal =
    transition.kind === "protected"
      ? { route: REFUSAL_ROUTES[transition.source], status: transition.status }
      : null;
  const wave = transition.kind === "protected-wave" ? transition.status : null;
  let authenticated =
    transition.kind !== "login-success" &&
    transition.kind !== "login-refusal" &&
    transition.kind !== "login-locked";

  const answer = (method: string, path: string): StubResponse => {
    const route = `${method} ${path}`;
    if (refusal !== null && route === refusal.route) {
      if (refusal.status === 401) {
        // The site answers a protected request as anonymous once the session it held is gone.
        authenticated = false;
      }
      return respond(refusal.status);
    }
    if (route === "GET /auth/session") {
      if (transition.kind === "bootstrap-locked") {
        return respond(403);
      }
      return respond(200, authenticated ? AUTHENTICATED : ANONYMOUS);
    }
    if (route === "POST /auth/login") {
      if (transition.kind === "login-refusal") {
        return respond(401, { detail: "Authentication failed" });
      }
      if (transition.kind === "login-locked") {
        return respond(403);
      }
      authenticated = true;
      return respond(200, AUTHENTICATED);
    }
    if (route === "POST /auth/logout") {
      authenticated = false;
      return respond(204);
    }
    if (route === `POST ${ADMIN_REBUILD_PATH}`) {
      if (transition.kind === "admin-rebuild-failure") {
        return respond(200, { exit_code: 1, report: null, failure_line: null });
      }
      // The restart that follows the answered build ends the session the shell held.
      authenticated = false;
      return envelope(ADMIN_REBUILD_REPORT);
    }
    if (wave !== null && path.startsWith("/api/")) {
      // Every protected read of the mounted trees is refused, as a lost session answers them all.
      authenticated = false;
      return respond(wave);
    }
    if (route in REPORTS) {
      return envelope(REPORTS[route]);
    }
    throw new Error(`unexpected request ${route}`);
  };

  vi.stubGlobal("fetch", (async (input: unknown, init?: RequestInit) => {
    const path = String(input);
    const method = init?.method ?? "GET";
    const headers = (init?.headers ?? {}) as Record<string, string>;
    calls.push({
      method,
      path,
      body: (init?.body as string | undefined) ?? null,
      automatic: headers["X-Admin-Automatic-Read"] === "1",
    });
    return answer(method, path);
  }) as unknown as typeof fetch);
}

function heading(container: HTMLElement, text: string): boolean {
  return [...container.querySelectorAll("h1, h3")].some(
    (element) => element.textContent === text,
  );
}

/** Report whether one panel's heading is present and inside a hidden tab tree. */
function headingIsHidden(container: HTMLElement, text: string): boolean {
  const element = [...container.querySelectorAll("h1, h3")].find(
    (candidate) => candidate.textContent === text,
  );
  if (element === undefined) {
    throw new Error(`no heading named ${text}`);
  }
  return element.closest("[hidden]") !== null;
}

/** Return the text of one titled panel's own read marker. */
function markerOf(container: HTMLElement, title: string): string {
  const section = [...container.querySelectorAll("section.panel")].find(
    (element) => element.querySelector("h3")?.textContent === title,
  );
  if (section === undefined) {
    throw new Error(`no panel titled ${title}`);
  }
  return section.querySelector(".live")?.textContent ?? "";
}

function buttonNamed(container: HTMLElement, name: string): HTMLButtonElement {
  const found = [...container.querySelectorAll("button")].find(
    (element) => element.textContent?.trim() === name,
  );
  if (found === undefined) {
    throw new Error(`no button named ${name}`);
  }
  return found;
}

/** Return the text of the open confirmation dialog, which renders in a body-level portal. */
function dialogText(): string {
  return document.body.querySelector(".dialog")?.textContent ?? "";
}

/** Return the one button the open confirmation dialog renders with that text. */
function dialogButtonNamed(name: string): HTMLButtonElement {
  const found = [...document.body.querySelectorAll("button")].filter(
    (element) => element.textContent?.trim() === name,
  );
  if (found.length !== 1) {
    throw new Error(`${found.length} dialog buttons named ${name}`);
  }
  return found[0];
}

function panelAction(
  container: HTMLElement,
  title: string,
  name: string,
): HTMLButtonElement {
  const section = [...container.querySelectorAll("section.panel")].find(
    (element) => element.querySelector("h3")?.textContent === title,
  );
  if (section === undefined) {
    throw new Error(`no panel titled ${title}`);
  }
  return buttonNamed(section as HTMLElement, name);
}

function fieldNamed(container: HTMLElement, name: string): HTMLInputElement {
  const found = container.querySelector<HTMLInputElement>(
    `input[name="${name}"]`,
  );
  if (found === null) {
    throw new Error(`no input named ${name}`);
  }
  return found;
}

/** Return the input one authored accessible name labels. */
function labelledInput(container: HTMLElement, name: string): HTMLInputElement {
  const found = container.querySelector<HTMLInputElement>(
    `input[aria-label="${name}"]`,
  );
  if (found === null) {
    throw new Error(`no input labelled ${name}`);
  }
  return found;
}

function type(input: HTMLInputElement, value: string): void {
  const setter = Object.getOwnPropertyDescriptor(
    HTMLInputElement.prototype,
    "value",
  )?.set;
  setter?.call(input, value);
  input.dispatchEvent(new Event("input", { bubbles: true }));
}

/** Flush the pending request chain and its state updates. */
async function settle(): Promise<void> {
  await act(async () => {
    for (let turn = 0; turn < 6; turn += 1) {
      await new Promise((resolve) => setTimeout(resolve, 0));
    }
  });
}

function sessionCalls(): RecordedCall[] {
  return calls.filter((call) => call.path === "/auth/session");
}

/** Submit one credential attempt and return the password field of the sign-in screen. */
async function submitCredentials(
  container: HTMLElement,
): Promise<HTMLInputElement> {
  const form = container.querySelector("form");
  const password = fieldNamed(container, "pass");
  await act(async () => {
    type(fieldNamed(container, "user"), OPERATOR);
    type(password, PASSWORD);
    form?.dispatchEvent(
      new Event("submit", { bubbles: true, cancelable: true }),
    );
  });
  await settle();
  return password;
}

/** Drive one protected refusal at its named request and assert the state the shell leaves. */
async function refuseProtected(
  container: HTMLElement,
  refusal: ProtectedRefusal,
): Promise<void> {
  const refusalRoute = REFUSAL_ROUTES[refusal.source];
  const action = actionFor(refusal.source);
  if (action !== null) {
    await act(async () => {
      buttonNamed(container, action.tab).click();
    });
    await settle();
    // Opening the tab reveals the tree the signed-in session already mounted and read.
    expect(headingIsHidden(container, action.panel)).toBe(false);
    await act(async () => {
      panelAction(container, action.panel, action.name).click();
    });
    await settle();
  }

  if (refusal.source === "settings-write") {
    // The Settings tab's one configuration save is the refused request.
    await act(async () => {
      buttonNamed(container, wording.tabs.settings).click();
    });
    await settle();
    expect(headingIsHidden(container, wording.settings.configuration)).toBe(
      false,
    );
    await act(async () => {
      buttonNamed(container, CONFIG_FILE).click();
    });
    await settle();
    await act(async () => {
      type(labelledInput(container, "WEB_PORT"), "18026");
    });
    await settle();
    await act(async () => {
      buttonNamed(
        container,
        wording.settings.saveFile.replace("{file}", CONFIG_FILE),
      ).click();
    });
    await settle();
  }

  if (refusal.source === "logout") {
    // The Dashboard tree is mounted and read before the one sign-out action.
    expect(headingIsHidden(container, wording.dashboard.serving)).toBe(false);
    await act(async () => {
      buttonNamed(container, wording.signOut).click();
    });
    await settle();
  }

  // The named protected route was refused on every request the signed-in page makes of it.
  expect(countOf(refusalRoute)).toBe(REFUSAL_REQUESTS);

  if (refusal.status === 403) {
    // The lock's bare 403 clears the shell and renders an empty root.
    expect(container.innerHTML).toBe("");
    expect(sessionCalls()).toHaveLength(1);
    return;
  }

  // A protected 401 returns to sign-in through exactly one fresh bootstrap.
  expect(heading(container, wording.signIn.heading)).toBe(true);
  expect(container.querySelector("form")).not.toBeNull();
  expect(heading(container, protectedHeading(refusal.source))).toBe(false);
  expect(container.querySelector("table")).toBeNull();
  expect(sessionCalls()).toHaveLength(2);
  expect(routeOf(calls[calls.length - 1])).toBe("GET /auth/session");
}

/** Drive one refusal of every protected read the signed-in page issues. */
async function refuseWave(container: HTMLElement): Promise<void> {
  // Concurrent refusals of the initial wave share the shell's one re-bootstrap.
  expect(heading(container, wording.signIn.heading)).toBe(true);
  expect(container.querySelector("table")).toBeNull();
  expect(sessionCalls()).toHaveLength(2);
  // The unmounted trees issue no further read, so the re-bootstrap is the last request.
  expect(routeOf(calls[calls.length - 1])).toBe("GET /auth/session");
}

/** Drive one administration rebuild from the Settings tab through its own confirmation. */
async function rebuildAdminPanel(container: HTMLElement): Promise<void> {
  expect(headingIsHidden(container, wording.dashboard.serving)).toBe(false);
  await act(async () => {
    buttonNamed(container, wording.tabs.settings).click();
  });
  await settle();
  expect(headingIsHidden(container, wording.settings.configuration)).toBe(
    false,
  );
  await act(async () => {
    buttonNamed(container, wording.settings.rebuildAdmin).click();
  });
  await settle();
  // The administration action has its own confirmation, which names the sign-out it causes.
  expect(dialogText()).toContain(wording.settings.rebuildAdminConfirm);
  await act(async () => {
    dialogButtonNamed(wording.inference.confirm).click();
  });
  await settle();
}

/** Open one tab from the dashboard and assert the retained tree it owns. */
async function openTab(
  container: HTMLElement,
  transition: TabTransition,
): Promise<void> {
  expect(headingIsHidden(container, wording.dashboard.serving)).toBe(false);
  const before = calls.length;
  await act(async () => {
    buttonNamed(container, transition.tab).click();
  });
  await settle();
  expect(headingIsHidden(container, transition.panel)).toBe(false);
  // Every tree was mounted and read with the signed-in session, and a tab switch reads nothing.
  expect(calls.length).toBe(before);
  expect(countOf(transition.route)).toBe(1);
  for (const other of TAB_TRANSITIONS) {
    if (other.panel !== transition.panel) {
      expect(headingIsHidden(container, other.panel)).toBe(true);
    }
  }
}

describe.each(TRANSITIONS)("console session transition $name", (transition) => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    calls.length = 0;
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    install(transition);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    vi.unstubAllGlobals();
  });

  it("keeps protected panels behind the server session", async () => {
    await act(async () => {
      root.render(createElement(App));
    });
    await settle();

    if (transition.kind === "tab") {
      await openTab(container, transition);
      return;
    }

    if (transition.kind === "protected") {
      await refuseProtected(container, transition);
      return;
    }

    if (transition.kind === "protected-wave") {
      await refuseWave(container);
      return;
    }

    if (transition.kind === "admin-rebuild-success") {
      await rebuildAdminPanel(container);

      // The answered build discards every protected tree and shows the sign-out notice without a
      // bootstrap of its own, because the backend that holds the sessions restarts next.
      expect(countOf(`POST ${ADMIN_REBUILD_PATH}`)).toBe(1);
      expect(sessionCalls()).toHaveLength(1);
      expect(routeOf(calls[calls.length - 1])).toBe(
        `POST ${ADMIN_REBUILD_PATH}`,
      );
      expect(heading(container, wording.dashboard.serving)).toBe(false);
      expect(heading(container, wording.signIn.heading)).toBe(true);
      expect(container.textContent).toContain(wording.settings.adminRebuilt);

      // A fresh sign-in submission reads a session before its own login attempt.
      const before = calls.length;
      await submitCredentials(container);
      const after = calls.slice(before);
      expect(after.slice(0, 2).map(routeOf)).toEqual([
        "GET /auth/session",
        "POST /auth/login",
      ]);
      expect(after[1].body).toContain(PASSWORD);
      expect(calls.every((call) => !call.path.includes(PASSWORD))).toBe(true);
      // The granted session mounts the protected Dashboard again and clears the notice.
      expect(heading(container, wording.dashboard.serving)).toBe(true);
      expect(container.textContent).not.toContain(
        wording.settings.adminRebuilt,
      );
      return;
    }

    if (transition.kind === "admin-rebuild-failure") {
      await rebuildAdminPanel(container);

      // The refused build restarts nothing, retains the protected session and shows the command's
      // own safe failure inside the panel that asked for it.
      expect(countOf(`POST ${ADMIN_REBUILD_PATH}`)).toBe(1);
      expect(sessionCalls()).toHaveLength(1);
      expect(heading(container, wording.dashboard.serving)).toBe(true);
      expect(heading(container, wording.settings.configuration)).toBe(true);
      expect(
        [...container.querySelectorAll("p.failure")].map(
          (element) => element.textContent,
        ),
      ).toContain(wording.writeFailed);
      expect(container.textContent).not.toContain(
        wording.settings.adminRebuilt,
      );
      return;
    }

    if (transition.kind === "bootstrap-locked") {
      // The lock's bare 403 at the shell's own bootstrap is terminal, with no second request.
      expect(calls.map(routeOf)).toEqual(["GET /auth/session"]);
      expect(container.innerHTML).toBe("");
      return;
    }

    if (transition.kind === "login-locked") {
      // The lock's bare 403 ends the sign-in attempt, with no second attempt and no read.
      expect(heading(container, wording.signIn.heading)).toBe(true);
      await submitCredentials(container);
      expect(calls.map(routeOf)).toEqual([
        "GET /auth/session",
        "POST /auth/login",
      ]);
      expect(container.innerHTML).toBe("");
      return;
    }

    if (
      transition.kind === "login-success" ||
      transition.kind === "login-refusal"
    ) {
      // An anonymous session shows the sign-in screen and mounts no protected panel.
      expect(heading(container, wording.signIn.heading)).toBe(true);
      expect(heading(container, wording.dashboard.serving)).toBe(false);
      expect(calls.some((call) => call.path === "/api/dashboard")).toBe(false);

      const password = await submitCredentials(container);
      const login = calls.find((call) => call.path === "/auth/login");
      expect(login?.method).toBe("POST");
      expect(login?.body).toContain(PASSWORD);
      expect(calls.every((call) => !call.path.includes(PASSWORD))).toBe(true);

      if (transition.kind === "login-refusal") {
        expect(container.querySelector(".loginerr")?.textContent).toBe(
          wording.signIn.refused,
        );
        // The password field is cleared, and the refused attempt is the last request.
        expect(password.value).toBe("");
        expect(heading(container, wording.dashboard.serving)).toBe(false);
        expect(calls.some((call) => call.path === "/api/dashboard")).toBe(
          false,
        );
        expect(calls.map(routeOf)).toEqual([
          "GET /auth/session",
          "POST /auth/login",
        ]);
        return;
      }
      // The granted session replaces the anonymous one and mounts the protected Dashboard.
      expect(heading(container, wording.signIn.heading)).toBe(false);
      expect(container.querySelector('input[name="pass"]')).toBeNull();
      expect(heading(container, wording.dashboard.serving)).toBe(true);
      expect(calls.some((call) => call.path === "/api/dashboard")).toBe(true);
      return;
    }

    if (transition.kind === "logout") {
      // Signing out ends the server session and unmounts every protected report.
      expect(heading(container, wording.dashboard.serving)).toBe(true);
      await act(async () => {
        buttonNamed(container, wording.signOut).click();
      });
      await settle();
      expect(calls.filter((call) => call.path === "/auth/logout")).toHaveLength(
        1,
      );
      expect(heading(container, wording.dashboard.serving)).toBe(false);
      expect(heading(container, wording.signIn.heading)).toBe(true);
      expect(sessionCalls()).toHaveLength(2);
      return;
    }
  });
});

describe("signed-in tab session", () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    calls.length = 0;
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    install({ name: "authenticated", kind: "authenticated" });
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    vi.unstubAllGlobals();
  });

  it("keeps tab reports for the signed-in session", async () => {
    await act(async () => {
      root.render(createElement(App));
    });
    await settle();

    // Sign-in reads every enabled consumer once. The signed-in shell holds one server-status read,
    // and the inference summary and the two listing consumers are enabled by its selection report.
    const twice = ["GET /api/inference/datasets"];
    expect(calls).toHaveLength(
      Object.keys(REPORTS).length + twice.length + sessionCalls().length,
    );
    for (const route of Object.keys(REPORTS)) {
      expect(countOf(route)).toBe(twice.includes(route) ? 2 : 1);
    }
    // Every one of those automatic reads carries the loop's own marker, so the backend can omit a
    // successful poll from the command log.
    for (const call of calls) {
      if (call.path === "/auth/session") {
        continue;
      }
      expect(call.automatic).toBe(true);
    }

    // The signed-in page holds every tree, and the selected tab alone is visible.
    expect(headingIsHidden(container, wording.dashboard.serving)).toBe(false);
    for (const transition of TAB_TRANSITIONS.slice(1)) {
      expect(headingIsHidden(container, transition.panel)).toBe(true);
    }
    // The header carries GitHub, Docs, the App address and the sign-out control, and no account
    // name.
    const header = container.querySelector("header");
    expect(header?.textContent).toContain(wording.github);
    expect(header?.textContent).toContain(wording.docs);
    expect(header?.textContent).toContain(wording.app);
    expect(header?.textContent).toContain(wording.signOut);
    expect(header?.textContent).not.toContain(OPERATOR);
    const headerLinks = [...(header?.querySelectorAll("a") ?? [])];
    const githubLink = headerLinks.find((link) =>
      link.textContent?.includes(wording.github),
    );
    expect(githubLink?.getAttribute("href")).toBe(REPOSITORY_URL);
    expect(githubLink?.getAttribute("target")).toBe("_blank");
    const wikiLink = headerLinks.find((link) =>
      link.textContent?.includes(wording.docs),
    );
    expect(wikiLink?.getAttribute("href")).toBe(`${APP_URL}docs#home`);
    expect(markerOf(container, wording.dashboard.serving)).not.toContain(
      wording.notRead,
    );
    expect(markerOf(container, wording.dashboard.serving)).not.toContain(
      wording.reading,
    );

    // Switching through every tab reveals its retained report and marker and reads nothing.
    const before = calls.length;
    for (const transition of TAB_TRANSITIONS) {
      await act(async () => {
        buttonNamed(container, transition.tab).click();
      });
      await settle();
      expect(headingIsHidden(container, transition.panel)).toBe(false);
    }
    expect(calls.length).toBe(before);

    // Returning to the Dashboard shows the report and marker sign-in read.
    await act(async () => {
      buttonNamed(container, wording.tabs.dashboard).click();
    });
    await settle();
    expect(calls.length).toBe(before);
    expect(headingIsHidden(container, wording.dashboard.serving)).toBe(false);
    expect(container.textContent).toContain(
      DASHBOARD_REPORT.website.entry_point,
    );
    expect(markerOf(container, wording.dashboard.serving)).not.toContain(
      wording.notRead,
    );
    expect(markerOf(container, wording.dashboard.serving)).not.toContain(
      wording.reading,
    );
  });

  it("restores the open tab after a reload", async () => {
    await act(async () => {
      root.render(createElement(App));
    });
    await settle();

    await act(async () => {
      buttonNamed(container, wording.tabs.logs).click();
    });
    await settle();
    expect(container.querySelector('[aria-current="page"]')?.textContent).toBe(
      wording.tabs.logs,
    );

    act(() => root.unmount());
    root = createRoot(container);
    await act(async () => {
      root.render(createElement(App));
    });
    await settle();

    expect(container.querySelector('[aria-current="page"]')?.textContent).toBe(
      wording.tabs.logs,
    );
    expect(headingIsHidden(container, wording.logs.commandLog)).toBe(false);
  });
});

/** One active poll interval of the synthetic selection session. */
const SELECTION_POLL_MS = 1000;

const SELECTION_SESSION: SessionReport = {
  ...AUTHENTICATED,
  poll_seconds: SELECTION_POLL_MS / 1000,
};

// One ordinary dashboard command failure, as the runner reports a checked child failure.
const DASHBOARD_FAILURE_LINE = JSON.stringify({
  error: "CalledProcessError",
  returncode: 1,
});

type SelectionState = "true" | "false" | "failure";

/** Return one dashboard report with the requested selection state. */
function selectionReport(
  selection: Exclude<SelectionState, "failure">,
): ServerStatusReport {
  return {
    ...DASHBOARD_REPORT,
    serving: {
      ...DASHBOARD_REPORT.serving,
      selection_enabled: selection === "true",
    },
  };
}

/** Answer the initial reads, holding the first dashboard response until it is released. */
function installSelection(selection: SelectionState): () => void {
  let release = (): void => {};
  const held = new Promise<void>((resolve) => {
    release = resolve;
  });
  vi.stubGlobal("fetch", (async (input: unknown, init?: RequestInit) => {
    const path = String(input);
    const method = init?.method ?? "GET";
    const headers = (init?.headers ?? {}) as Record<string, string>;
    calls.push({
      method,
      path,
      body: (init?.body as string | undefined) ?? null,
      automatic: headers["X-Admin-Automatic-Read"] === "1",
    });
    if (path === "/auth/session") {
      return respond(200, SELECTION_SESSION);
    }
    if (path === "/api/dashboard") {
      await held;
      if (selection === "failure") {
        return respond(200, {
          exit_code: 1,
          report: null,
          failure_line: DASHBOARD_FAILURE_LINE,
        });
      }
      return envelope(selectionReport(selection));
    }
    const route = `${method} ${path}`;
    if (route in REPORTS) {
      return envelope(REPORTS[route]);
    }
    throw new Error(`unexpected request ${route}`);
  }) as unknown as typeof fetch);
  return release;
}

/** Flush the pending request chain and its state updates under the fake clock. */
async function flushMicrotasks(): Promise<void> {
  await act(async () => {
    for (let turn = 0; turn < 20; turn += 1) {
      await Promise.resolve();
    }
  });
}

/** Set the page's own hidden state and notify the mounted read loops. */
function setDocumentHidden(hidden: boolean): void {
  Object.defineProperty(document, "hidden", {
    configurable: true,
    value: hidden,
  });
  document.dispatchEvent(new Event("visibilitychange"));
}

describe.each(["true", "false", "failure"] as const)(
  "selection gating from a %s dashboard report",
  (selection) => {
    let container: HTMLDivElement;
    let root: Root;
    let release: () => void;

    beforeEach(() => {
      calls.length = 0;
      vi.useFakeTimers();
      container = document.createElement("div");
      document.body.appendChild(container);
      root = createRoot(container);
      release = installSelection(selection);
    });

    afterEach(() => {
      act(() => root.unmount());
      container.remove();
      vi.useRealTimers();
      vi.unstubAllGlobals();
      Reflect.deleteProperty(document, "hidden");
    });

    it("gates dataset reads on the reported selection state", async () => {
      await act(async () => {
        root.render(createElement(App));
      });
      await flushMicrotasks();

      // The shell and every ungated panel read at sign-in, while the gated consumers wait.
      expect(heading(container, wording.dashboard.serving)).toBe(true);
      expect(countOf("GET /api/inference/summary")).toBe(0);
      expect(countOf("GET /api/inference/datasets")).toBe(0);

      // A waiting gated consumer states the read in its header marker instead of its body.
      for (const title of [
        wording.inference.diagnostics,
        wording.inference.coverage,
        wording.inference.identities,
        wording.inference.failures,
        wording.inference.datasetCleanup,
        wording.settings.dataset,
      ]) {
        expect(markerOf(container, title)).toContain(wording.reading);
      }
      const bodyReadingNotes = [
        ...container.querySelectorAll(".pb > .note"),
      ].filter((element) => element.textContent?.trim() === wording.reading);
      expect(bodyReadingNotes).toHaveLength(0);

      release();
      await flushMicrotasks();

      if (selection === "true") {
        // An enabled report reads the summary once and each listing consumer once.
        expect(countOf("GET /api/dashboard")).toBe(1);
        expect(countOf("GET /api/inference/summary")).toBe(1);
        expect(countOf("GET /api/inference/datasets")).toBe(2);
        expect(container.textContent).not.toContain(wording.selectionDisabled);
        return;
      }

      // A disabled or failed first report issues neither read across one poll and a visible return.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(SELECTION_POLL_MS);
      });
      await flushMicrotasks();
      setDocumentHidden(true);
      await flushMicrotasks();
      setDocumentHidden(false);
      await flushMicrotasks();
      expect(countOf("GET /api/inference/summary")).toBe(0);
      expect(countOf("GET /api/inference/datasets")).toBe(0);

      if (selection === "false") {
        // The plain state names the site's reason and is not a failure.
        expect(container.textContent).toContain(wording.selectionDisabled);
        expect(container.querySelectorAll("p.failure")).toHaveLength(0);
        return;
      }

      // A failed dashboard read stays visible and is not relabeled as a disabled site.
      expect(container.textContent).not.toContain(wording.selectionDisabled);
      expect(
        [...container.querySelectorAll("p.failure")].map(
          (element) => element.textContent,
        ),
      ).toContain(DASHBOARD_FAILURE_LINE);
    });
  },
);
