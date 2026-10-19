/**
 * The administration DTO fields the console consumes, mirroring the backend report owners.
 *
 * Every type here names only the fields the console consumes, and a nullable member is a fact the
 * owner reports as unknown. The publication route count arrives under one of two field names, and
 * the console reads whichever one the report carries.
 */

export interface SessionReport {
  authenticated: boolean;
  csrf_token: string;
  poll_seconds: number;
  app_url: string;
  repository_url: string;
}

export interface ContainerStatus {
  state: string;
  health: string | null;
  image: string | null;
}

export interface WebsiteStatus {
  unit: string;
  state: string;
  substate: string;
  main_pid: number;
  host: string;
  port: number;
  configured_workers: number;
  entry_point: string;
  started_at: string | null;
  uptime_seconds: number | null;
  checkout_branch: string;
  checkout_revision: string;
}

export interface HostStatus {
  uptime_seconds: number;
  cpu_usage_percent: number;
  memory_total_bytes: number;
  memory_used_bytes: number;
  data_bytes: number | null;
  models_bytes: number | null;
  backups_bytes: number | null;
  disk_total_bytes: number;
  disk_free_bytes: number;
}

export interface DatabaseStatus {
  container: ContainerStatus;
  host: string;
  port: number;
  name: string;
  schema_revision: string | null;
  expected_schema_revision: string;
  at_head: boolean | null;
  size_bytes: number | null;
  connections: number | null;
  shared_memory_bytes: number | null;
}

export interface EmbeddingStatus {
  container: ContainerStatus;
  host: string;
  port: number;
  model: string;
  artifact: string;
  context_size: number;
  threads: number;
  pooling: string;
  normalization: number;
}

export interface ServingStatus {
  selection_enabled: boolean;
  dataset_id: string | null;
  kind: string | null;
  predecessor_id: string | null;
  pointer: string | null;
  receipt_schema_revision: string | null;
}

export interface HubStatus {
  alias: string;
  path: string;
  modified_at: string | null;
  newer_than_web_start: boolean | null;
}

export interface ServerStatusReport {
  schema_version: number;
  website: WebsiteStatus;
  host: HostStatus;
  database: DatabaseStatus;
  embedding: EmbeddingStatus;
  serving: ServingStatus;
  hubs: HubStatus[];
}

export type StageName = "ingestion" | "translation" | "embedding" | "inference";

/** The four lifecycle actions every stage panel offers. */
export type LifecycleAction = "start" | "pause" | "resume" | "stop";

export interface IngestionProgress {
  kind: "ingestion";
  stage: string;
  response_count: number;
  verified_response_count: number;
  verification_total: number | null;
  normalized: boolean;
}

export interface EmbeddingProgress {
  kind: "embedding";
  reconciled: boolean;
  desired_count: number;
  pending_count: number;
  completed_count: number;
  failed_count: number;
  generated_count: number;
}

export interface WorkerControllerStatus {
  session_id: string | null;
  lifecycle: string;
  revision: string | null;
  desired_count: number | null;
  completed_count: number | null;
  active_seconds: number;
  error_type: string | null;
  reboot_due: boolean;
  remaining_count: number | null;
  items_per_second: number | null;
  projected_remaining_seconds: number | null;
}

export interface TranslationProgress {
  kind: "translation";
  worker: WorkerControllerStatus | null;
}

export interface InferenceStageProgress {
  stage: "multiview" | "rerank" | "inference";
  done: number;
  total: number;
  remaining: number;
}

export interface InferenceWorkerStatus extends WorkerControllerStatus {
  progress: {
    cycle_id: string;
    stage: string;
    desired_targets: number;
  } | null;
  coverage: { cycle_id: string | null } | null;
  stages: InferenceStageProgress[];
  stage_processed_count: number;
}

export interface InferenceProgress {
  kind: "inference";
  worker: InferenceWorkerStatus | null;
  preparation: "snapshot" | "transfer" | "restore" | "job" | null;
}

export type StageProgress =
  | IngestionProgress
  | EmbeddingProgress
  | TranslationProgress
  | InferenceProgress;

export interface LifecycleStatus {
  stage: StageName;
  lifecycle: string;
  session_id: string | null;
  revision: string | null;
  progress: StageProgress | null;
  active_seconds: number;
  error_type: string | null;
  items_per_second: number | null;
  eta_seconds: number | null;
}

export interface CatalogueSummary {
  curriculum_period_count: number;
  canonical_course_count: number;
  active_course_count: number;
  course_version_count: number;
  canonical_module_count: number;
  module_version_count: number;
}

export interface TeachingTextCoverageCount {
  field: string;
  language: string;
  official_count: number;
  derived_count: number;
  stale_count: number;
  missing_count: number;
}

export interface TeachingTextCoverageReport {
  canonical_course_count: number;
  representative_course_count: number;
  no_representative_course_count: number;
  name_only_course_count: number;
  unembeddable_course_count: number;
  fields: TeachingTextCoverageCount[];
}

export interface CourseEmbeddingCoverageCount {
  field: string;
  language: string;
  origin: string;
  pending_count: number;
  completed_count: number;
  failed_count: number;
}

export interface CourseEmbeddingCoverageReport {
  total_chunk_count: number;
  pending_count: number;
  completed_count: number;
  failed_count: number;
  fields: CourseEmbeddingCoverageCount[];
}

export interface EmbeddingHubReport {
  catalogue_path: string;
  outcomes_path: string;
  chunk_count: number;
  outcomes_chunk_count: number;
}

export interface PublicationDiagnostics {
  eligible_targets: number;
  selected_targets: number;
  processed_targets: number;
  local_targets: number;
  other_route_targets?: number;
  oversize_cloud_targets?: number;
  accepted_targets: number;
  published_targets: number;
  operator_done_targets: number;
  observed_packet_candidates: number;
  expected_packet_candidates: number;
  historical_proposal_rows: number;
  current_equivalence_groups: number;
  transitive_warnings: unknown[];
  proposal_version: string;
  prompt_version: string;
  schema_version: string;
  pipeline_version: string;
}

export interface InferenceGenerationCount {
  model_identity: string;
  prompt_version: string;
  schema_version: string;
  pipeline_version: string;
  route: string;
  targets: number;
}

export interface InferenceCoverageSummary {
  schema_version: number;
  eligible_targets: number;
  retained_complete_targets: number;
  published_targets: number;
  uncovered_targets: number;
  current_equivalence_groups: number;
  historical_proposal_rows: number;
  generation_counts: InferenceGenerationCount[];
  cycle_id: string | null;
  stage: string | null;
  failed_targets: number;
  pending_targets: number;
}

export interface TargetFailureRecord {
  target_group_id: string;
  stage: string;
  attempt_count: number;
  error_type: string;
  reason: string;
  exhausted: boolean;
  created_at: string;
}

export interface InferenceAdministrativeSummary {
  schema_version: number;
  dataset_scope: string;
  coverage: InferenceCoverageSummary;
  publication: PublicationDiagnostics;
  failures: TargetFailureRecord[];
  operator_done_targets: number;
  operator_failed_target_group_ids: string[];
  routing_policy: string;
  recommendation_policy: string;
  finding_filter_policy: string;
}

export type TargetDisposition = "done" | "failed";

/** The three decision tokens a target decision command admits, NOTHING included. */
export type TargetDecisionToken = "nothing" | TargetDisposition;

export interface InferenceTargetDisposition {
  dataset_id: string;
  target_group_id: string;
  course_code: string | null;
  course_name: string | null;
  disposition: TargetDisposition | null;
}

export interface DatasetListEntry {
  dataset_id: string;
  kind: "initial" | "returned";
  database_name: string;
  dump_path: string | null;
  selected: boolean;
}

export interface DatasetListReport {
  schema_version: number;
  datasets: DatasetListEntry[];
}

export interface DatasetDeletionReport {
  schema_version: number;
  dataset_id: string;
  database_name: string;
}

export type LogSource =
  | "server-stdout"
  | "server-stderr"
  | "keepalive"
  | "worker-runner"
  | "worker-runtime";

export type CommandOutcome =
  "success" | "failure" | "login" | "failed-login" | "lock";

export interface CommandLogEntry {
  time: string;
  command: string;
  exit_code: number;
  duration_seconds: number;
  result: CommandOutcome;
  failure_line: string | null;
}

export interface CommandLogReport {
  schema_version: number;
  entries: CommandLogEntry[];
}

export interface LogSessionEntry {
  stage: StageName;
  session_id: string;
  created_at: string;
}

export interface LogSessionsReport {
  schema_version: number;
  sessions: LogSessionEntry[];
}

export interface LogReadReport {
  schema_version: number;
  stage: StageName;
  session_id: string | null;
  source: string;
  available: boolean;
  text: string | null;
}

export interface UsageRouteSummary {
  route: string;
  requests: number;
  mean_duration_seconds: number;
}

export interface UsageReport {
  window_start: string;
  window_end: string;
  requests: number;
  mean_duration_seconds: number | null;
  routes: UsageRouteSummary[];
}

/** One configuration value as its file holds it, including null for a bare environment key. */
export type JsonValue =
  null | boolean | number | string | JsonValue[] | { [key: string]: JsonValue };

export interface ConfigurationFilesReport {
  schema_version: number;
  files: string[];
}

export interface ConfigurationFileReport {
  schema_version: number;
  file: string;
  values: Record<string, JsonValue>;
}

export interface ConfigurationWriteReport {
  schema_version: number;
  file: string;
  key: string;
}

export interface BackupFile {
  name: string;
  size_bytes: number;
  modified_at: string;
}

export interface BackupListReport {
  schema_version: number;
  backups: BackupFile[];
}

export interface BackupDeletionReport {
  schema_version: number;
  name: string;
}

export interface RebuildReport {
  schema_version: number;
  steps: string[];
  host: string;
  port: number;
}

export interface AdminRebuildReport {
  schema_version: number;
  steps: string[];
}

export interface DatasetVerification {
  schema_version: number;
  alembic_revision: string;
  table_row_counts: Record<string, number>;
}

export interface DatasetReceipt {
  schema_version: number;
  dataset_id: string;
  database_name: string;
  kind: "initial" | "returned";
  revision: string;
  verification: DatasetVerification;
}

export interface WorkerCodeReport {
  branch: string;
  revision: string;
  server_origin_differs: boolean;
}

export interface WorkerResourcesReport {
  ready: boolean;
  missing: string[];
}

export interface ProvisioningReport {
  code: WorkerCodeReport;
  resources: WorkerResourcesReport | null;
}
