/**
 * JSON contracts of the served read requests and reports, including the prerequisite graph report
 * and its solver structure.
 */
import type { DisplayLanguage } from "../state/types";

/** Official course identity and display summary. */
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
/** Request for official course summaries by identifier. */
export type CourseSummariesRequest = { identifiers: readonly string[] };
/** Official course summaries with serving dataset identity. */
export type CourseSummariesReport = {
  results: readonly CourseSummary[];
  dataset_identity: string;
};
/** Canonical course identities for a comparison request. */
export type ComparisonRequest = { course_a: string; course_b: string };
/** Official module identity and display summary. */
export type ModuleSummary = {
  group_id: string;
  sisu_module_id: string;
  module_type: string;
  code: string | null;
  name_fi: string | null;
  name_en: string | null;
};
/** One official course identity a local narrowing filter matches and displays. */
export type CatalogueCourse = Omit<CourseSummary, "official_url">;
/** One exact official module candidate a local narrowing filter matches and displays. */
export type CatalogueModule = ModuleSummary & {
  validity_start: string | null;
  validity_end: string | null;
  curriculum_periods: readonly {
    id: string;
    academic_year_start: number;
  }[];
};
/** The minimal official catalogue every narrowing surface filters locally. */
export type CatalogueReport = {
  dataset_identity: string;
  courses: readonly CatalogueCourse[];
  modules: readonly {
    group_id: string;
    candidates: readonly Omit<CatalogueModule, "group_id">[];
  }[];
};
/**
 * One local module-search row: the canonical group with every eligible candidate and the display
 * fields of one candidate.
 *
 * The row names no selected version. `candidates` is the full eligible set of the group, and the
 * top-level display fields come from the candidate that represents the group in the result order.
 */
export type ModuleLookupGroup = Pick<
  ModuleSummary,
  "group_id" | "module_type" | "code" | "name_fi" | "name_en"
> & { candidates: CatalogueReport["modules"][number]["candidates"] };
/** Results from a local course lookup over the served catalogue. */
export type LocalCourseLookupReport = { results: readonly CatalogueCourse[] };
/** Results from a local module lookup over the served catalogue. */
export type LocalModuleLookupReport = {
  results: readonly ModuleLookupGroup[];
};
/** Official structure rule kinds represented by the browser. */
export type StructureRuleType =
  | "CompositeRule"
  | "CreditsRule"
  | "CourseUnitCountRule"
  | "CourseUnitRule"
  | "ModuleRule"
  | "AnyCourseUnitRule"
  | "AnyModuleRule";
/** Reasons a structure rule cannot resolve to an official object. */
export type StructureUnresolved =
  | "course_not_represented"
  | "module_not_found"
  | "no_current_version"
  | "ambiguous_version"
  | "missing_rule"
  | "module_cycle";
/** One official structure rule and its resolved child. */
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
  referenced_group_id: string | null;
  children: readonly StructureRule[];
  course: CourseSummary | null;
  module: StructureModule | null;
  unresolved: StructureUnresolved | null;
};
/** One official module with its target credits and structure rule. */
export type StructureModule = {
  module: ModuleSummary;
  target_credits_min: string | null;
  target_credits_max: string | null;
  rule: StructureRule;
};
/** One requested root structure with its academic year. */
export type StudyStructureReport = {
  academic_year_start: number;
  root: StructureModule;
};
/** Batched study structures and unresolved root selections. */
export type StudyStructuresReport = {
  academic_year_start: number;
  roots: readonly StructureModule[];
  unavailable_root_group_ids: readonly string[];
  version_selection_required: readonly string[];
  dataset_identity: string;
};
/**
 * The local full prerequisite calculation snapshot: the live profile inputs a route calculation
 * reads, including the graph-only node marks.
 */
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
/**
 * The structural graph inputs. Under Active only, an inactive course in the selected or completed
 * set stays in the drawing where the graph reaches it, and the opened root is drawn whether or not
 * it is active.
 */
export type PrerequisiteGraphRequest = {
  target_code: string;
  selected_codes: readonly string[];
  completed_codes: readonly string[];
  include_recommended: boolean;
  include_inferred: boolean;
  active_only: boolean;
};
/** Provenance fact bound to a solver source use. */
export type SolverFact = {
  fact_id: string;
  origin: "official" | "inferred" | "composed";
  official_kind:
    "compulsory" | "recommended" | "module_rule" | "substitution" | null;
  inferred_category: "required" | "recommended" | null;
  inference: {
    confidence: string;
    requirement_ids: readonly string[];
    evidence: readonly {
      kind: "expression_proposal";
      reference_id: string;
    }[];
  } | null;
};
/** One interned prerequisite calculation piece. */
export type SolverPiece = {
  piece_id: string;
  kind:
    | "course"
    | "and"
    | "or"
    | "expanded_course"
    | "course_alternatives"
    | "cardinality"
    | "credits"
    | "course_count"
    | "module_block"
    | "opaque_credits"
    | "unresolved";
  children: readonly string[];
  course_group_id: string | null;
  module_group_id: string | null;
  work_key: string | null;
  require_min: number | null;
  require_max: number | null;
  credits_min: string | null;
  credits_max: string | null;
  count_min: number | null;
  count_max: number | null;
  reason: string | null;
  referenced_group_id: string | null;
  detail: string | null;
  manual_credits_min: string | null;
  module_rule: boolean;
  cycle_closing: boolean;
};
/** One ordered prerequisite source use and its child uses. */
export type SolverUse = {
  use_id: string;
  piece_id: string;
  fact_id: string;
  children: readonly string[];
  diagnostic_ids: readonly string[];
  member_group_ids: readonly string[];
};
/** One located solver diagnostic and its source fact. */
export type SolverDiagnostic = {
  diagnostic_id: string;
  kind: string;
  fact_id: string;
  referenced_group_ids: readonly string[];
  detail: string | null;
  module_group_id: string | null;
};
/** One scoped solver support and its drawn node bindings. */
export type SolverSupportBinding = {
  support_id: string;
  owner_group_id: string;
  piece_id: string;
  use_ids: readonly string[];
  node_ids: readonly string[];
  mark_node_ids: readonly string[];
};
/** One child slot in a solver projection context. */
export type SolverProjectionChild = {
  slot: number;
  context_id: string;
};
/** One solver projection context and its relationship members. */
export type SolverProjectionContext = {
  context_id: string;
  owner_group_id: string;
  piece_id: string;
  children: readonly SolverProjectionChild[];
  member_ids: readonly string[];
};
/** One prerequisite relationship member between drawn nodes. */
export type SolverMember = {
  member_id: string;
  source_node_id: string;
  target_node_id: string;
  fact_id: string;
};
/** Native prerequisite structure consumed by the browser route solver. */
export type SolverStructure = {
  root_group_id: string;
  academic_year_start: number;
  root_use_id: string | null;
  pieces: readonly SolverPiece[];
  uses: readonly SolverUse[];
  facts: readonly SolverFact[];
  diagnostics: readonly SolverDiagnostic[];
  root_diagnostic_ids: readonly string[];
  courses: readonly CourseSummary[];
  modules: readonly ModuleSummary[];
  include_recommended: boolean;
  include_inferred: boolean;
  active_only: boolean;
  inferred_coverage: readonly {
    target_group_id: string;
    coverage_state: string;
    coverage: {
      eligible_source_count: number;
      processed_source_count: number;
      accepted_source_count: number;
    };
  }[];
  excluded_group_ids: readonly string[];
  completed_node_keys: readonly string[];
  excluded_node_keys: readonly string[];
  bindings: readonly SolverSupportBinding[];
  projection_root_context_id: string | null;
  projection_contexts: readonly SolverProjectionContext[];
  members: readonly SolverMember[];
};
/** Kinds of nodes emitted for the prerequisite drawing. */
export type DisplayNodeKind =
  | "course"
  | "module"
  | "and"
  | "or"
  | "cardinality"
  | "credits"
  | "course_count"
  | "opaque_credits"
  | "internal_requirement"
  | "unresolved"
  | "ignored";
/** One node in the projected prerequisite drawing. */
export type GraphDisplayNode = {
  node_id: string;
  kind: DisplayNodeKind;
  owner_group_id: string | null;
  course_group_id: string | null;
  module_group_id: string | null;
  require_min: number | null;
  require_max: number | null;
  credits_min: string | null;
  credits_max: string | null;
  count_min: number | null;
  count_max: number | null;
  referenced_group_id: string | null;
  reason: string | null;
  detail: string | null;
  member_group_ids: readonly string[];
  diagnostic_ids: readonly string[];
  is_root: boolean;
  via_inferred: boolean;
  via_recommended: boolean;
  has_official_provenance: boolean;
  has_inferred_provenance: boolean;
  display_as_inferred: boolean;
  markable: boolean;
};
/** One relationship connection in the projected prerequisite drawing. */
export type GraphEdge = {
  edge_id: string;
  source_node_id: string;
  target_node_id: string;
  member_ids: readonly string[];
  inferred_only: boolean;
};
/** One graph node's completion, exclusion and satisfaction state. */
export type GraphNodeState = {
  node_id: string;
  is_excluded: boolean;
  manually_completed: boolean;
  completed_by_courses: boolean;
  satisfied_by_basis: boolean;
};
/** Projected prerequisite drawing nodes and connections. */
export type GraphDisplay = {
  nodes: readonly GraphDisplayNode[];
  edges: readonly GraphEdge[];
};
/** Outcomes returned by the minimum-route solver. */
export type PrerequisitePathState =
  | "exact"
  | "approximate"
  | "approximation_failed"
  | "unresolved"
  | "no_solution"
  | "shortfall";
/** One course selected by a minimum route. */
export type PathCourse = {
  course: CourseSummary;
  node_ids: readonly string[];
};
/** One opaque minimum-route work item. */
export type PathOpaqueWork = {
  work_key: string;
  credits_min: string;
  node_ids: readonly string[];
};
/** One located minimum-route credit or count shortfall. */
export type PathShortfall = {
  kind: "all_mandatory" | "cardinality" | "credits" | "course_count";
  node_id: string;
  support_id: string | null;
  required_count: number | null;
  achieved_count: number | null;
  count_deficit: number | null;
  required_credits: string | null;
  achieved_credits: string | null;
  credit_deficit: string | null;
};
/** One located minimum-route problem. */
export type PathProblem = {
  node_id: string;
  support_id: string | null;
  fact_id: string | null;
  state: "no_solution" | "unresolved" | "shortfall";
  reason: string;
  detail: string | null;
  referenced_group_id: string | null;
};
/** Complete minimum-route result for one prerequisite structure. */
export type PrerequisitePath = {
  state: PrerequisitePathState;
  new_courses: readonly PathCourse[];
  total_new_credits: string | null;
  new_opaque_work: readonly PathOpaqueWork[];
  selected_nodes: readonly string[];
  lit_members: readonly string[];
  covered_courses: readonly CourseSummary[];
  facts: readonly SolverFact[];
  shortfalls: readonly PathShortfall[];
  blocked_excluded_group_ids: readonly string[];
  blocked_excluded_node_keys: readonly string[];
  problems: readonly PathProblem[];
};
/**
 * The graph read's native report: its solver structure, permitted display and drawing allowance.
 * `dataset_identity` names the serving dataset the read resolved and `max_compact_nodes` is the
 * configured solver allocation limit the browser worker applies. An explicit Find calculates the
 * route from `solver` in a browser worker.
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
  dataset_identity: string;
  max_compact_nodes: number;
  solver: SolverStructure;
  display: GraphDisplay | null;
};
/** Categories returned by course comparison. */
export type ComparisonVerdict =
  | "heavily_overlapping"
  | "partly_overlapping"
  | "same_area_different_content"
  | "loosely_related"
  | "unrelated";
/** Similarity measurements returned for a course comparison. */
export type ComparisonMeters = {
  overall_relatedness: number | null;
  content_similarity: number | null;
  learning_outcome_similarity: number | null;
  overlap: { a_in_b: number | null; b_in_a: number | null };
};
/** Backend course comparison report. */
export type CourseComparisonReport = {
  course_a: CourseSummary;
  course_b: CourseSummary;
  meters: ComparisonMeters;
  verdict: ComparisonVerdict | null;
  uses_derived_text: boolean;
  dataset_identity: string;
};
/** Search methods that can contribute a result. */
export type SearchMethod =
  "exact_code" | "substring" | "fuzzy_name" | "semantic";
/** Unified course-search request. */
export type SearchRequest = {
  query: string;
  display_language: DisplayLanguage;
  include_inactive: boolean;
};
/** One unified course-search result and its match scores. */
export type UnifiedCourseSearchResult = {
  course: CourseSummary;
  match_sources: readonly SearchMethod[];
  fuzzy_score: number | null;
  semantic_score: number | null;
};
/** Unified course-search report and its configured method order. */
export type UnifiedSearchReport = {
  dataset_identity: string;
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
/** One next-course discovery result. */
export type NextCourseResult = {
  course: CourseSummary;
  required_coverage: number | null;
  recommended_coverage: number | null;
  depends_on_inferred: boolean;
};
/** Next-course discovery report. */
export type NextCoursesReport = {
  dataset_identity: string;
  selected_group_ids: readonly string[];
  completed_group_ids: readonly string[];
  basis: DiscoveryRequest["basis"];
  mode: DiscoveryRequest["mode"];
  display_language: DisplayLanguage;
  include_inferred: boolean;
  active_only: boolean;
  results: readonly NextCourseResult[];
};
/** One similarity recommendation for a course basis. */
export type SimilarityRecommendation = {
  course: CourseSummary;
  relatedness: number;
  score: number;
  overlap_with_basis: number | null;
  uses_derived_text: boolean;
};
/** Similarity recommendation report. */
export type RecommendationsReport = {
  dataset_identity: string;
  similarity_results: readonly SimilarityRecommendation[];
};

/** The site's two served feature switches and the identity of the dataset it serves. */
export type WebFeatures = {
  embeddings_enabled: boolean;
  inference_enabled: boolean;
  dataset_identity: string;
};
/** Display language values used by API requests and reports. */
export type { DisplayLanguage };
