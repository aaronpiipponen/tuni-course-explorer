/* C record layouts of the native prerequisite interface. */

#pragma once

#include <cstdint>

extern "C" {

/* Frozen record view handed to the Python DTO boundary. Every calculation and display identity is
 * already final when these records are built. The Python side constructs the frozen models and
 * derives nothing. */

struct CourseStringList {
    const char *const *items;
    int32_t count;
};

struct CoursePieceRecord {
    const char *piece_id;
    int32_t kind;
    CourseStringList children;
    const char *course_group_id;
    const char *module_group_id;
    const char *work_key;
    int32_t require_min;
    int32_t require_max;
    const char *credits_min;
    const char *credits_max;
    int32_t count_min;
    int32_t count_max;
    const char *reason;
    const char *referenced_group_id;
    const char *detail;
    const char *manual_credits_min;
    uint8_t module_rule;
    uint8_t cycle_closing;
};

struct CourseUseRecord {
    const char *use_id;
    const char *piece_id;
    const char *fact_id;
    CourseStringList children;
    CourseStringList diagnostic_ids;
    CourseStringList member_group_ids;
};

struct CourseFactRecord {
    const char *fact_id;
    int32_t origin;
    int32_t official_kind;
    int32_t inferred_category;
    const char *inference;
};

struct CourseDiagnosticRecord {
    const char *diagnostic_id;
    const char *kind;
    const char *fact_id;
    CourseStringList referenced_group_ids;
    const char *detail;
    const char *module_group_id;
};

struct CourseSummaryRecord {
    const char *group_id;
    const char *name_fi;
    const char *name_en;
    const char *code;
    const char *credits_min;
    const char *credits_max;
    const char *official_url;
    uint8_t has_name_fi;
    uint8_t has_name_en;
    uint8_t has_credits_max;
    uint8_t is_active;
};

struct CourseModuleRecord {
    const char *group_id;
    const char *sisu_module_id;
    const char *module_type;
    const char *code;
    const char *name_fi;
    const char *name_en;
    uint8_t has_code;
    uint8_t has_name_fi;
    uint8_t has_name_en;
};

struct CourseCoverageRecord {
    const char *target_group_id;
    const char *coverage_state;
    int64_t eligible_source_count;
    int64_t processed_source_count;
    int64_t accepted_source_count;
};

struct CourseBindingRecord {
    const char *support_id;
    const char *owner_group_id;
    const char *piece_id;
    CourseStringList use_ids;
    CourseStringList node_ids;
    CourseStringList mark_node_ids;
};

struct CourseContextChildRecord {
    int32_t slot;
    const char *context_id;
};

struct CourseContextRecord {
    const char *context_id;
    const char *owner_group_id;
    const char *piece_id;
    const CourseContextChildRecord *children;
    int32_t child_count;
    CourseStringList member_ids;
};

struct CourseMemberRecord {
    const char *member_id;
    const char *source_node_id;
    const char *target_node_id;
    const char *fact_id;
};

struct CourseDisplayNodeRecord {
    const char *node_id;
    int32_t kind;
    const char *owner_group_id;
    const char *course_group_id;
    const char *module_group_id;
    int32_t require_min;
    int32_t require_max;
    const char *credits_min;
    const char *credits_max;
    int32_t count_min;
    int32_t count_max;
    const char *referenced_group_id;
    const char *reason;
    const char *detail;
    CourseStringList member_group_ids;
    CourseStringList diagnostic_ids;
    uint8_t is_root;
    uint8_t via_inferred;
    uint8_t via_recommended;
    uint8_t has_official_provenance;
    uint8_t has_inferred_provenance;
    uint8_t display_as_inferred;
    uint8_t markable;
};

struct CourseDisplayEdgeRecord {
    const char *edge_id;
    const char *source_node_id;
    const char *target_node_id;
    CourseStringList member_ids;
    uint8_t inferred_only;
};

struct CourseStructureRecord {
    const char *root_group_id;
    int32_t academic_year_start;
    uint8_t active_only;
    uint8_t include_recommended;
    uint8_t include_inferred;
    const char *requirements_use_id;
    const char *required_use_id;
    const char *recommended_use_id;
    const CoursePieceRecord *pieces;
    int32_t piece_count;
    const CourseUseRecord *uses;
    int32_t use_count;
    const CourseFactRecord *facts;
    int32_t fact_count;
    const CourseDiagnosticRecord *diagnostics;
    int32_t diagnostic_count;
    const CourseSummaryRecord *courses;
    int32_t course_count;
    const CourseModuleRecord *modules;
    int32_t module_count;
    const CourseCoverageRecord *coverage;
    int32_t coverage_count;
    CourseStringList excluded_group_ids;
    CourseStringList completed_node_keys;
    CourseStringList excluded_node_keys;
    CourseStringList root_diagnostic_ids;
    const char *projection_root_context_id;
    const CourseBindingRecord *bindings;
    int32_t binding_count;
    const CourseContextRecord *contexts;
    int32_t context_count;
    const CourseMemberRecord *members;
    int32_t member_count;
    int32_t drawing_course_count;
    int32_t drawing_node_count;
    int32_t drawing_edge_count;
    const CourseDisplayNodeRecord *nodes;
    int32_t node_count;
    const CourseDisplayEdgeRecord *edges;
    int32_t edge_count;
};


struct NativeOutcome {
    const char *root;
    int has_outcome;
    double required_coverage;
    double recommended_coverage;
    int has_required;
    int has_recommended;
};


}  // extern "C"
