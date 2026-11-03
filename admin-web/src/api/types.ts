/**
 * The administration DTO fields the console consumes, mirroring the backend report owners.
 *
 * Every type here names only the fields the console consumes, and a nullable member is a fact the
 * owner reports as unknown. The publication route count arrives under one of two field names, and
 * the console reads whichever one the report carries.
 */

/** The signed-in session's authentication state and the facts every console request needs. */
export interface SessionReport {
  authenticated: boolean;
  csrf_token: string;
  poll_seconds: number;
  app_url: string;
  repository_url: string;
}

/** One container's run state, health and image. */
export interface ContainerStatus {
  state: string;
  health: string | null;
  image: string | null;
}

/** The web server unit's state, listener and checkout identity. */
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

/** The host's uptime, CPU, memory, data, model, backup and disk totals. */
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

/** The database container's connection and schema state. */
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

/** The embedding service's container, endpoint and model settings. */
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

/** The serving dataset selection's switches and pointer facts. */
export interface ServingStatus {
  selection_enabled: boolean | null;
  embeddings_enabled: boolean;
  dataset_id: string | null;
  kind: string | null;
  predecessor_id: string | null;
  pointer: string | null;
  receipt_schema_revision: string | null;
}

/** One embedding hub file's name, path, modification time and freshness against the web start. */
export interface HubStatus {
  name: "catalogue" | "outcomes";
  path: string;
  modified_at: string | null;
  newer_than_web_start: boolean | null;
}

/** The server status read with its website, host, database, embedding, serving and hub facts. */
export interface ServerStatusReport {
  schema_version: number;
  website: WebsiteStatus;
  host: HostStatus;
  database: DatabaseStatus;
  embedding: EmbeddingStatus;
  serving: ServingStatus;
  hubs: HubStatus[];
}

/** The four preparation stages the console reports. */
export type StageName = "ingestion" | "translation" | "embedding" | "inference";

/** The four lifecycle actions every stage panel offers. */
export type LifecycleAction = "start" | "pause" | "resume" | "stop";

/** One ingestion run's response, verification and normalization counts. */
export interface IngestionProgress {
  kind: "ingestion";
  stage: string;
  response_count: number;
  verified_response_count: number;
  verification_total: number | null;
  normalized: boolean;
}

/** One embedding run's reconciliation, desired, completed, failed and generated counts. */
export interface EmbeddingProgress {
  kind: "embedding";
  reconciled: boolean;
  desired_count: number;
  pending_count: number;
  completed_count: number;
  failed_count: number;
  generated_count: number;
}

/** One worker session's lifecycle, progress counts and timing. */
export interface WorkerControllerStatus {
  session_id: string | null;
  lifecycle: string;
  desired_count: number | null;
  completed_count: number | null;
  active_seconds: number;
  error_type: string | null;
  reboot_due: boolean;
  remaining_count: number | null;
  items_per_second: number | null;
  projected_remaining_seconds: number | null;
}

/** One translation run's worker status. */
export interface TranslationProgress {
  kind: "translation";
  worker: WorkerControllerStatus | null;
}

/** One inference stage's processed, total and remaining target counts. */
export interface InferenceStageProgress {
  stage: "multiview" | "rerank" | "inference";
  done: number;
  total: number;
  remaining: number;
}

/** One inference worker's cycle stage, coverage and per-stage progress. */
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

/** One inference run's worker status and preparation step. */
export interface InferenceProgress {
  kind: "inference";
  worker: InferenceWorkerStatus | null;
  preparation: "snapshot" | "transfer" | "restore" | "job" | null;
}

/** The progress report of one stage by kind. */
export type StageProgress =
  | IngestionProgress
  | EmbeddingProgress
  | TranslationProgress
  | InferenceProgress;

/** One stage's lifecycle state, session, progress and timing. */
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

/** The counts of periods, courses, modules and versions in a dataset. */
export interface CatalogueSummary {
  curriculum_period_count: number;
  canonical_course_count: number;
  active_course_count: number;
  course_version_count: number;
  canonical_module_count: number;
  module_version_count: number;
}

/** The official, derived, stale and missing teaching-text counts of one field and language. */
export interface TeachingTextCoverageCount {
  field: string;
  language: string;
  official_count: number;
  derived_count: number;
  stale_count: number;
  missing_count: number;
}

/** The teaching-text coverage of every field, with the course counts it reads. */
export interface TeachingTextCoverageReport {
  canonical_course_count: number;
  representative_course_count: number;
  no_representative_course_count: number;
  name_only_course_count: number;
  unembeddable_course_count: number;
  fields: TeachingTextCoverageCount[];
}

/** The pending, completed and failed chunk counts of one field, language and origin. */
export interface CourseEmbeddingCoverageCount {
  field: string;
  language: string;
  origin: string;
  pending_count: number;
  completed_count: number;
  failed_count: number;
}

/** The chunk coverage of the dataset's courses. */
export interface CourseEmbeddingCoverageReport {
  total_chunk_count: number;
  pending_count: number;
  completed_count: number;
  failed_count: number;
  fields: CourseEmbeddingCoverageCount[];
}

interface ServingArtifactPaths {
  catalogue_artifact_path: string;
  study_fragment_path: string;
  study_fragment_roots: number;
  study_fragment_projectable: number;
  study_fragment_unavailable: number;
  study_fragment_selection_required: number;
  study_fragment_bytes: number;
  study_fragment_build_wall_seconds: number;
  study_fragment_build_core_seconds: number;
}

/** One build report. An embeddings-off build reports every embedding field as null. */
export type ServingArtifactsReport =
  | (ServingArtifactPaths & {
      embeddings_enabled: true;
      catalogue_path: string;
      outcomes_path: string;
      hub_pair_path: string;
      shared_centroid_path: string;
      shared_chunk_path: string;
      search_group_count: number;
      search_block_count: number;
      chunk_count: number;
      outcomes_chunk_count: number;
      centroid_count: number;
      neighbor_count: number;
    })
  | (ServingArtifactPaths & {
      embeddings_enabled: false;
      catalogue_path: null;
      outcomes_path: null;
      hub_pair_path: null;
      shared_centroid_path: null;
      shared_chunk_path: null;
      search_group_count: null;
      search_block_count: null;
      chunk_count: null;
      outcomes_chunk_count: null;
      centroid_count: null;
      neighbor_count: null;
    });

/** The target, candidate and proposal counts one publication reports. */
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

/** The targets one model, prompt, schema and pipeline version produced. */
export interface InferenceGenerationCount {
  model_identity: string;
  prompt_version: string;
  schema_version: string;
  pipeline_version: string;
  route: string;
  targets: number;
}

/** The inference coverage counts, generation counts and current cycle. */
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

/** One target's stored failure with its stage, attempt count and reason. */
export interface TargetFailureRecord {
  target_group_id: string;
  stage: string;
  attempt_count: number;
  error_type: string;
  reason: string;
  exhausted: boolean;
  created_at: string;
}

/** The inference coverage, publication diagnostics, failures and policies in one read. */
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

/** One operator decision a target accepts. */
export type TargetDisposition = "done" | "failed";

/** The three decision tokens a target decision command admits, NOTHING included. */
export type TargetDecisionToken = "nothing" | TargetDisposition;

/** One target's current operator disposition. */
export interface InferenceTargetDisposition {
  dataset_id: string;
  target_group_id: string;
  course_code: string | null;
  course_name: string | null;
  disposition: TargetDisposition | null;
}

/** The two dataset roles a console read or write can name. */
export type DatasetRole = "selected" | "working";

/** One console summary read and the role it resolved before it ran its report. */
export interface DatasetReport<T> {
  role: DatasetRole | null;
  report: T | null;
}

/** One dataset in the inventory with its role flags, presence and artifacts state. */
export interface DatasetListEntry {
  dataset_id: string;
  kind: "initial" | "returned" | "copied";
  database_name: string;
  predecessor_id: string | null;
  receipt_schema_revision: string;
  dump_path: string | null;
  selected: boolean;
  working: boolean;
  database_presence: "present" | "absent" | "unavailable";
  artifacts_present: boolean;
}

/** The dataset inventory and the mode the console reads it in. */
export interface DatasetListReport {
  schema_version: number;
  datasets: DatasetListEntry[];
  mode: "bootstrap" | "enrolled" | "unavailable";
  database_probe: "available" | "unavailable";
  bootstrap_database: string | null;
  stage_busy: Record<StageName, boolean>;
}

/** The coarse steps a promotion reports before each of its mutations, rollback included. */
export type PromotionStep =
  "copy" | "build" | "switch" | "restart" | "prove" | "rollback";

/** One role, or the configured bootstrap database, an explicit migration acts on. */
export type DatasetMigrateRole = "selected" | "working" | "database";

/** The identity of the dataset a deletion removes. */
export interface DatasetDeletionReport {
  schema_version: number;
  dataset_id: string;
  database_name: string;
}

/** One log source the console can read. */
export type LogSource =
  | "server-stdout"
  | "server-stderr"
  | "keepalive"
  | "worker-runner"
  | "worker-runtime";

/** The recorded result of one administration command. */
export type CommandOutcome =
  "success" | "failure" | "login" | "failed-login" | "lock";

/** One command log line with its command, exit code, duration and result. */
export interface CommandLogEntry {
  time: string;
  command: string;
  exit_code: number;
  duration_seconds: number;
  result: CommandOutcome;
  failure_line: string | null;
}

/** The command log entries in one read. */
export interface CommandLogReport {
  schema_version: number;
  entries: CommandLogEntry[];
}

/** One stage session the log view can read. */
export interface LogSessionEntry {
  stage: StageName;
  session_id: string;
  created_at: string;
}

/** The stage sessions the log view lists. */
export interface LogSessionsReport {
  schema_version: number;
  sessions: LogSessionEntry[];
}

/** One stage session's log text and whether it is available. */
export interface LogReadReport {
  schema_version: number;
  stage: StageName;
  session_id: string | null;
  source: string;
  available: boolean;
  text: string | null;
}

/** One route's request count and mean, p95 and p99 durations. */
export interface UsageRouteSummary {
  route: string;
  requests: number;
  mean_duration_seconds: number;
  p95_duration_seconds: number;
  p99_duration_seconds: number;
}

/** The usage report of one hour window with its totals and route rows. */
export interface UsageReport {
  window_start: string;
  window_end: string;
  requests: number;
  mean_duration_seconds: number | null;
  p95_duration_seconds: number | null;
  p99_duration_seconds: number | null;
  routes: UsageRouteSummary[];
}

/** One configuration value as its file holds it, including null for a bare environment key. */
export type JsonValue =
  null | boolean | number | string | JsonValue[] | { [key: string]: JsonValue };

/** The names of the configuration files the console can read. */
export interface ConfigurationFilesReport {
  schema_version: number;
  files: string[];
}

/** One configuration file's values by key. */
export interface ConfigurationFileReport {
  schema_version: number;
  file: string;
  values: Record<string, JsonValue>;
}

/** The file and key one configuration write names. */
export interface ConfigurationWriteReport {
  schema_version: number;
  file: string;
  key: string;
}

/** One backup file's name, size and modification time. */
export interface BackupFile {
  name: string;
  size_bytes: number;
  modified_at: string;
}

/** The backup files the cleanup lists. */
export interface BackupListReport {
  schema_version: number;
  backups: BackupFile[];
}

/** The name of the backup file a deletion removes. */
export interface BackupDeletionReport {
  schema_version: number;
  name: string;
}

/** The steps one rebuild runs and the address it checks. */
export interface RebuildReport {
  schema_version: number;
  steps: string[];
  host: string;
  port: number;
}

/** The steps one administration rebuild queues. */
export interface AdminRebuildReport {
  schema_version: number;
  steps: string[];
}

/** The schema revision and table row counts of one dataset verification read. */
export interface DatasetVerification {
  schema_version: number;
  alembic_revision: string;
  table_row_counts: Record<string, number>;
}

/** The record of one enrolled dataset with its verification. */
export interface DatasetReceipt {
  schema_version: number;
  dataset_id: string;
  database_name: string;
  kind: "initial" | "returned" | "copied";
  verification: DatasetVerification;
}

/** The worker's checkout branch and revision and whether the server origin differs. */
export interface WorkerCodeReport {
  branch: string;
  revision: string;
  server_origin_differs: boolean;
}

/** Whether the worker's required resources are ready and which are missing. */
export interface WorkerResourcesReport {
  ready: boolean;
  missing: string[];
}

/** The worker code and resource facts one provisioning read reports. */
export interface ProvisioningReport {
  code: WorkerCodeReport;
  resources: WorkerResourcesReport | null;
}

/** One bilingual text the feedback definition holds. */
export interface FeedbackLocalizedText {
  en: string;
  fi: string;
}

/** One selectable feedback option and its publication default when it declares one. */
export interface FeedbackSelectOption {
  value: string;
  label: FeedbackLocalizedText;
  publicIssueByDefault?: boolean | null;
}

/** One single-row or multiline text answer with its maximum character count. */
export interface FeedbackTextDefinition {
  kind: "text" | "textarea";
  id: string;
  label: FeedbackLocalizedText;
  required: boolean;
  maxLength: number;
}

/** One select answer with its ordered options. */
export interface FeedbackSelectDefinition {
  kind: "select";
  id: string;
  label: FeedbackLocalizedText;
  required: boolean;
  options: FeedbackSelectOption[];
}

/** One attachment answer with its permitted image types and upload limits. */
export interface FeedbackAttachmentDefinition {
  kind: "attachment";
  id: string;
  label: FeedbackLocalizedText;
  required: boolean;
  acceptedMimeTypes: string[];
  maxFiles: number;
  maxBytesPerFile: number;
}

/** One configured answer kind the inbox renders. */
export type FeedbackFieldDefinition =
  | FeedbackTextDefinition
  | FeedbackSelectDefinition
  | FeedbackAttachmentDefinition;

/** The configured field names a published GitHub issue takes its parts from. */
export interface FeedbackGithubIssueMapping {
  typeField: string;
  titleField: string;
  bodyFields: string[];
  attachmentField: string;
}

/** The ordered feedback fields, the unchosen select placeholder and the issue mapping. */
export interface FeedbackDefinition {
  selectPlaceholder: FeedbackLocalizedText;
  fields: FeedbackFieldDefinition[];
  githubIssue: FeedbackGithubIssueMapping;
}

/** One stored feedback image's metadata. */
export interface StoredAttachment {
  id: string;
  feedback_id: string;
  field_id: string;
  filename: string;
  mime_type: string;
}

/** One saved submission with its answers, publication choice and attachment metadata. */
export interface StoredFeedback {
  id: string;
  created_at: string;
  answers: Record<string, string | null>;
  public_issue: boolean;
  publication_state:
    "private" | "pending" | "uncertain" | "published" | "partial" | "failed";
  issue_url: string | null;
  publication_failure:
    | "attachment_upload_incomplete"
    | "github_outcome_unconfirmed"
    | "github_unavailable"
    | "publication_input_invalid"
    | null;
  attachments: StoredAttachment[];
}

/** The current definition and every selected submission in reported order. */
export interface FeedbackListReport {
  definition: FeedbackDefinition;
  submissions: StoredFeedback[];
}

/** One stored attachment's metadata and its transient base64 content carrier. */
export interface FeedbackAttachmentReport {
  attachment: StoredAttachment;
  content_base64: string;
}

/** The identity of the one submission a deletion removes. */
export interface FeedbackDeletionReport {
  feedback_id: string;
}
