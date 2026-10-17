/** Exact official course-summary JSON contract used to hydrate browser-owned identities. */
import type { DisplayLanguage } from "../state/types";

export type CourseSummary = {
  group_id: string;
  name_fi: string | null;
  name_en: string | null;
  code: string;
  credits_min: string;
  credits_max: string | null;
  is_active: boolean;
  official_url: string;
};
export type CourseSummariesRequest = { identifiers: readonly string[] };
export type CourseSummariesReport = { results: readonly CourseSummary[] };
export type CourseLookupRequest = {
  query: string;
  display_language: DisplayLanguage;
  include_inactive: boolean;
};
export type CourseLookupReport = CourseLookupRequest & {
  results: readonly CourseSummary[];
};
export type ComparisonRequest = { course_a: string; course_b: string };
export type ModuleSummary = {
  group_id: string;
  sisu_module_id: string;
  module_type: string;
  code: string | null;
  name_fi: string | null;
  name_en: string | null;
};
export type ModuleLookupRequest = {
  query: string;
  display_language: DisplayLanguage;
};
export type ModuleLookupReport = ModuleLookupRequest & {
  academic_year_start: number;
  results: readonly ModuleSummary[];
};
export type StructureRuleType =
  | "CompositeRule"
  | "CreditsRule"
  | "CourseUnitCountRule"
  | "CourseUnitRule"
  | "ModuleRule"
  | "AnyCourseUnitRule"
  | "AnyModuleRule";
export type StructureUnresolved =
  | "course_not_represented"
  | "module_not_found"
  | "no_current_version"
  | "ambiguous_version"
  | "missing_rule"
  | "module_cycle";
export type StructureRule = {
  node_type: StructureRuleType;
  sibling_position: number;
  require_min: number | null;
  require_max: number | null;
  all_mandatory: boolean | null;
  credits_min: string | null;
  credits_max: string | null;
  count_min: number | null;
  count_max: number | null;
  children: readonly StructureRule[];
  course: CourseSummary | null;
  module: StructureModule | null;
  unresolved: StructureUnresolved | null;
};
export type StructureModule = {
  module: ModuleSummary;
  target_credits_min: string | null;
  target_credits_max: string | null;
  rule: StructureRule;
};
export type StudyStructureReport = {
  academic_year_start: number;
  root: StructureModule;
};
export type PrerequisitesRequest = {
  target_code: string;
  completed_codes: readonly string[];
  selected_codes: readonly string[];
  excluded_codes: readonly string[];
  include_recommended: boolean;
  include_inferred: boolean;
  active_only: boolean;
  basis: "completed" | "selected";
  completed_node_keys: readonly string[];
  excluded_node_keys: readonly string[];
};
export type GraphProvenance = {
  origin: "official" | "inferred" | "composed";
  official_kind:
    "compulsory" | "recommended" | "module_rule" | "substitution" | null;
  inferred_category: "required" | "recommended" | null;
};
export type GraphCourseNode = {
  node_id: string;
  action_key: string;
  course: CourseSummary;
  is_root: boolean;
  display_as_inferred: boolean;
};
export type GraphConnectorKind =
  | "and"
  | "or"
  | "cardinality"
  | "credits"
  | "course_count"
  | "opaque_credits"
  | "internal_requirement"
  | "unresolved";
export type GraphConnectorNode = {
  node_id: string;
  action_key: string;
  kind: GraphConnectorKind;
  require_min: number | null;
  require_max: number | null;
  credits_min: string | null;
  credits_max: string | null;
  count_min: number | null;
  count_max: number | null;
  referenced_group_id: string | null;
  unresolved_reason: string | null;
  detail: string | null;
  member_group_ids: readonly string[];
};
export type GraphEdgeRelationship = GraphProvenance & {
  inference: {
    confidence: string;
    requirement_ids: readonly string[];
    evidence: readonly {
      kind: "expression_proposal";
      reference_id: string;
    }[];
  } | null;
  occurrence_ids: readonly string[];
  condition_occurrence_ids: readonly string[];
};
export type GraphEdge = {
  source_node_id: string;
  target_node_id: string;
  relationships: readonly GraphEdgeRelationship[];
};
export type PrerequisitePathState =
  | "exact"
  | "approximate"
  | "approximation_failed"
  | "unresolved"
  | "no_solution"
  | "shortfall";
export type PathCourse = {
  course: CourseSummary;
  occurrence_ids: readonly string[];
};
export type PathOpaqueWork = { work_key: string; credits_min: string };
export type PathShortfall = {
  kind: "all_mandatory" | "cardinality" | "credits" | "course_count";
  occurrence_id: string;
  required_count: number | null;
  achieved_count: number | null;
  required_credits: string | null;
  achieved_credits: string | null;
};
export type PathProblem = {
  occurrence_id: string;
  action_key: string;
  state: "no_solution" | "unresolved" | "shortfall";
  reason: string;
  detail: string | null;
  referenced_group_id: string | null;
};
export type PrerequisitePath = {
  state: PrerequisitePathState;
  new_courses: readonly PathCourse[];
  total_new_credits: string | null;
  new_opaque_work: readonly PathOpaqueWork[];
  selected_occurrence_ids: readonly string[];
  shortfalls: readonly PathShortfall[];
  blocked_excluded_group_ids: readonly string[];
  blocked_excluded_node_keys: readonly string[];
  problems: readonly PathProblem[];
};
export type GraphModuleNode = {
  node_id: string;
  occurrence_id: string;
  action_key: string;
  module: ModuleSummary;
  credits_min: string | null;
  credits_max: string | null;
  member_courses: readonly CourseSummary[];
};
export type GraphIgnoredNode = {
  node_id: string;
  part_id: string;
  action_key: string;
};
export type IgnoredPart = {
  part_id: string;
  kind: string;
  anchor_occurrence_id: string | null;
  action_key: string;
  referenced_group_ids: readonly string[];
  detail: string | null;
};
export type GraphCompilationIssue = {
  reason: string;
  course_group_path: readonly string[];
  occurrence_id: string;
  action_key: string;
  origin: GraphProvenance["origin"];
  official_kind: GraphProvenance["official_kind"];
};
export type GraphNodeState = {
  action_key: string;
  is_excluded: boolean;
  manually_completed: boolean;
  completed_by_courses: boolean;
  satisfied_by_basis: boolean;
};
/**
 * The graph read's own report: drawing context and located graph facts.
 * A minimum route is a separate explicit `/api/minimum-route` operation returning
 * `PrerequisitePath`.
 */
export type PrerequisiteGraphReport = {
  drawing: {
    allowed: boolean;
    limit: number | null;
    course_count: number;
    node_count: number;
    edge_count: number;
    element_count: number;
  };
  selected_group_ids: readonly string[];
  completed_group_ids: readonly string[];
  basis: "completed" | "selected";
  excluded_group_ids: readonly string[];
  completed_node_keys: readonly string[];
  excluded_node_keys: readonly string[];
  compilation: {
    tree: {
      root: CourseSummary;
      courses: readonly CourseSummary[];
      ignored_parts: readonly IgnoredPart[];
      issues: readonly GraphCompilationIssue[];
      excluded_group_ids: readonly string[];
    };
    graph: {
      course_nodes: readonly GraphCourseNode[];
      connector_nodes: readonly GraphConnectorNode[];
      edges: readonly GraphEdge[];
      module_nodes: readonly GraphModuleNode[];
      ignored_nodes: readonly GraphIgnoredNode[];
      node_states: readonly GraphNodeState[];
    };
  };
};
export type ComparisonVerdict =
  | "heavily_overlapping"
  | "partly_overlapping"
  | "same_area_different_content"
  | "loosely_related"
  | "unrelated";
export type ComparisonMeters = {
  overall_relatedness: number | null;
  content_similarity: number | null;
  learning_outcome_similarity: number | null;
  overlap: { a_in_b: number | null; b_in_a: number | null };
};
export type CourseComparisonReport = {
  course_a: CourseSummary;
  course_b: CourseSummary;
  meters: ComparisonMeters;
  verdict: ComparisonVerdict | null;
  uses_derived_text: boolean;
};
export type SearchMethod =
  "exact_code" | "substring" | "fuzzy_name" | "semantic";
export type SearchRequest = {
  query: string;
  display_language: DisplayLanguage;
  include_inactive: boolean;
};
export type UnifiedCourseSearchResult = {
  course: CourseSummary;
  match_sources: readonly SearchMethod[];
  fuzzy_score: number | null;
  semantic_score: number | null;
};
export type UnifiedSearchReport = {
  display_language: DisplayLanguage;
  semantic_min_score: number;
  fuzzy_min_score: number;
  include_inactive: boolean;
  semantic_available: boolean;
  tier_priority: readonly SearchMethod[];
  results: readonly UnifiedCourseSearchResult[];
};

/** Inputs shared by the next-course and recommendation commands. */
export type DiscoveryRequest = {
  selected_courses: readonly string[];
  completed_courses: readonly string[];
  basis: "completed" | "selected";
  mode: "all" | "at_least_one";
  display_language: DisplayLanguage;
  include_inferred: boolean;
  active_only: boolean;
};
export type NextCourseResult = {
  course: CourseSummary;
  required_coverage: number | null;
  recommended_coverage: number | null;
  depends_on_inferred: boolean;
};
export type NextCoursesReport = {
  selected_group_ids: readonly string[];
  completed_group_ids: readonly string[];
  basis: DiscoveryRequest["basis"];
  mode: DiscoveryRequest["mode"];
  display_language: DisplayLanguage;
  include_inferred: boolean;
  active_only: boolean;
  results: readonly NextCourseResult[];
};
export type SimilarityRecommendation = {
  course: CourseSummary;
  relatedness: number;
  score: number;
  overlap_with_basis: number | null;
  uses_derived_text: boolean;
};
export type RecommendationsReport = {
  similarity_results: readonly SimilarityRecommendation[];
};
export type { DisplayLanguage };
