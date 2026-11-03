/* Record and compilation types shared by the native prerequisite units.
 *
 * One compilation carries its calculation nodes, provenance facts, source uses, diagnostics,
 * coverage, summaries, identity tables and projection records.
 */

#pragma once

#include <algorithm>
#include <cstdint>
#include <string>
#include <string_view>
#include <unordered_map>
#include <vector>

#include "fact_model.h"

namespace tce {

enum NodeKind {
    N_COURSE = 0, N_AND, N_OR, N_ALTERNATIVES, N_CARDINALITY, N_CREDITS, N_COUNT,
    N_MODULE_BLOCK, N_OPAQUE, N_UNRESOLVED, N_EXPANDED
};

inline const char *origin_name(int origin)
{
    switch (origin) {
        case 0: return "official";
        case 1: return "inferred";
        default: return "composed";
    }
}

inline const char *official_kind_name(int kind)
{
    switch (kind) {
        case 0: return "compulsory";
        case 1: return "recommended";
        case 2: return "module_rule";
        case 3: return "substitution";
        default: return "";
    }
}

inline const char *module_type_name(int type)
{
    switch (type) {
        case 0: return "DegreeProgramme";
        case 1: return "StudyModule";
        case 2: return "GroupingModule";
        default: return nullptr;
    }
}

inline const char *category_name(int category)
{
    switch (category) {
        case 0: return "required";
        case 1: return "recommended";
        default: return "";
    }
}

struct Prov {
    int origin = 0;
    int official_kind = -1;
    int inferred_category = -1;
    std::string inference;
};

struct Node {
    int kind = N_COURSE;
    Prov prov;
    std::vector<int> children;
    std::string course;
    std::string module;
    std::string work_payload;
    std::string referenced;
    std::string detail;
    std::string reason;
    int64_t credits_min = -1;
    int64_t credits_max = -1;
    int64_t manual_min = -1;
    std::string credits_min_text;
    std::string credits_max_text;
    std::string manual_min_text;
    int32_t require_min = -1;
    int32_t require_max = -1;
    int32_t count_min = -1;
    int32_t count_max = -1;
    bool cycle = false;
    bool module_rule = false;
    std::vector<std::string> use_members;
    std::vector<int> use_diagnostics;
};

struct FactRecord {
    int origin = 0;
    int official_kind = -1;
    int inferred_category = -1;
    std::string inference;
};

struct UseRecord {
    int piece = -1;
    int fact = -1;
    std::vector<int> children;
    Path source;
    std::vector<std::string> members;
    std::vector<int> diagnostics;
};

struct DiagnosticRecord {
    std::string kind;
    int fact = -1;
    std::vector<std::string> referenced;
    std::string detail;
    std::string module;
};

struct CoverageRecord {
    std::string target;
    std::string state;
    int64_t eligible = 0;
    int64_t processed = 0;
    int64_t accepted = 0;
};

/* One finalized display box before it becomes a frozen DTO. */
struct ProjNodeRec {
    std::string node_id;
    int kind = 0;
    std::string owner_group_id;
    std::string course_group_id;
    std::string module_group_id;
    int32_t require_min = -1;
    int32_t require_max = -1;
    std::string credits_min;
    std::string credits_max;
    int32_t count_min = -1;
    int32_t count_max = -1;
    std::string referenced_group_id;
    std::string reason;
    std::string detail;
    std::vector<std::string> member_group_ids;
    std::vector<std::string> diagnostic_ids;
    bool is_root = false;
    bool via_inferred = false;
    bool via_recommended = false;
    bool has_official_provenance = false;
    bool has_inferred_provenance = false;
    bool display_as_inferred = false;
    bool markable = false;
};

struct ProjEdgeRec {
    std::string edge_id;
    std::string source_node_id;
    std::string target_node_id;
    std::vector<std::string> member_ids;
    bool inferred_only = false;
};

struct ProjBindingRec {
    std::string support_id;
    std::string owner_group_id;
    std::string piece_id;
    std::vector<std::string> use_ids;
    std::vector<std::string> node_ids;
    std::vector<std::string> mark_node_ids;
};

struct ProjContextChildRec {
    int32_t slot = 0;
    std::string context_id;
};

struct ProjContextRec {
    std::string context_id;
    std::string owner_group_id;
    std::string piece_id;
    std::vector<ProjContextChildRec> children;
    std::vector<std::string> member_ids;
};

struct ProjMemberRec {
    std::string member_id;
    std::string source_node_id;
    std::string target_node_id;
    std::string fact_id;
};

struct ProjectionRecords {
    bool ready = false;
    bool has_root_context = false;
    std::string root_context_id;
    std::vector<ProjNodeRec> nodes;
    std::vector<ProjEdgeRec> edges;
    std::vector<ProjBindingRec> bindings;
    std::vector<ProjContextRec> contexts;
    std::vector<ProjMemberRec> members;
};

/* Identities and reachable tables computed once per compiled structure. */
struct IdentifiedRecords {
    bool ready = false;
    std::vector<std::string> piece_id;
    std::vector<std::string> use_id;
    std::vector<std::string> fact_id;
    std::vector<std::string> diagnostic_id;
    std::vector<int> pieces;
    std::vector<int> uses;
    std::vector<int> facts;
    std::vector<int> diagnostics;
    std::vector<std::string> work_key;
    int root_use = -1;
    int required_use = -1;
    int recommended_use = -1;
    std::unordered_map<std::string, int> piece_index;
    std::unordered_map<std::string, int> use_index;
    std::unordered_map<std::string, int> fact_index;
    std::unordered_map<std::string, int> diagnostic_index;
};

struct CourseSummaryRec {
    std::string group;
    std::string name_fi;
    std::string name_en;
    bool has_name_fi = false;
    bool has_name_en = false;
    std::string code;
    std::string official_url;
    int64_t credits_min = 0;
    int64_t credits_max = 0;
    std::string credits_min_text;
    std::string credits_max_text;
    bool has_credits_max = false;
    bool active = false;
};

struct ModuleSummaryRec {
    std::string group;
    std::string sisu;
    std::string module_type;
    std::string code;
    std::string name_fi;
    std::string name_en;
    bool has_code = false;
    bool has_name_fi = false;
    bool has_name_en = false;
};

struct Compilation {
    std::string root;
    int32_t year = 0;
    int requirements = -1;
    int required = -1;
    int recommended = -1;
    std::vector<int> extra_roots;
    bool active_only = false;
    bool include_inferred = false;
    bool include_recommended = false;
    std::vector<Node> nodes;
    std::vector<FactRecord> facts;
    std::vector<UseRecord> uses;
    std::vector<DiagnosticRecord> diagnostics;
    std::unordered_map<std::string, CourseSummaryRec> summaries;
    std::unordered_map<std::string, ModuleSummaryRec> modules;
    std::vector<CoverageRecord> coverage;
    std::vector<std::string> excluded_group_ids;
    std::vector<std::string> completed_node_keys;
    std::vector<std::string> excluded_node_keys;
    std::vector<int> root_diagnostics;
    /* Fixture records carry an opaque work identity directly. Compiled records derive it from the
     * work payload. The field is empty for every compiled structure. */
    std::vector<std::string> fixture_work_keys;
    bool summary_only = false;
    IdentifiedRecords identified;
    ProjectionRecords projection;
};

struct Compiled {
    std::vector<Compilation> compilations;
    std::shared_ptr<const std::unordered_map<std::string, int>> ranks;
};

struct Frag {
    int use = -1;
    std::vector<int> diagnostics;
    std::unordered_map<std::string, ModuleSummaryRec> modules;
    std::vector<CoverageRecord> coverage;
    bool empty() const { return use < 0; }
};

inline const char *piece_kind_name(int kind)
{
    switch (kind) {
        case N_COURSE: return "course";
        case N_AND: return "and";
        case N_OR: return "or";
        case N_ALTERNATIVES: return "course_alternatives";
        case N_CARDINALITY: return "cardinality";
        case N_CREDITS: return "credits";
        case N_COUNT: return "course_count";
        case N_MODULE_BLOCK: return "module_block";
        case N_OPAQUE: return "opaque_credits";
        case N_UNRESOLVED: return "unresolved";
        default: return "expanded_course";
    }
}

enum DisplayKind {
    D_COURSE = 0, D_MODULE, D_AND, D_OR, D_CARDINALITY, D_CREDITS, D_COUNT, D_OPAQUE,
    D_INTERNAL, D_UNRESOLVED, D_IGNORED
};

inline std::vector<std::string> sorted_unique(std::vector<std::string> values)
{
    std::sort(values.begin(), values.end());
    values.erase(std::unique(values.begin(), values.end()), values.end());
    return values;
}

inline std::string join_list(const std::vector<std::string> &values)
{
    std::string result;
    for (size_t index = 0; index < values.size(); ++index) {
        if (index > 0) result += ", ";
        result += values[index];
    }
    return result;
}

inline std::string join_path(const std::vector<std::string> &values)
{
    std::string result;
    for (size_t index = 0; index < values.size(); ++index) {
        if (index > 0) result += " -> ";
        result += values[index];
    }
    return result;
}

inline std::string optional_number(int64_t value)
{
    return value < 0 ? std::string("None") : std::to_string(value);
}

/* A source node names a bundle-owned course or module identity. The view stays valid for the
 * lifetime of the loaded fact bundle, so graph keys and edges copy no identity strings. */
struct Visit {
    bool module = false;
    std::string_view group;
    bool allow_substitutions = true;
    bool allow_equivalences = true;
};

struct SourceKey {
    bool module = false;
    std::string_view group;
    bool operator==(const SourceKey &other) const
    {
        return module == other.module && group == other.group;
    }
};

struct SourceKeyHash {
    size_t operator()(const SourceKey &key) const
    {
        /* Hash the two fields without allocating a prefixed marker string: this hash is called for
         * every node, edge and Tarjan map lookup of the per-candidate source graph. */
        size_t value = std::hash<std::string_view>()(key.group);
        return key.module ? value ^ 0x9e3779b97f4a7c15ULL : value;
    }
};

/* One graph visit, distinguished by its source and its two traversal permissions. The source
 * marker is hashed field by field, so one visit allocates no formatted string. */
struct VisitKey {
    bool module = false;
    bool allow_substitutions = true;
    bool allow_equivalences = true;
    std::string_view group;
    bool operator==(const VisitKey &other) const
    {
        return module == other.module && allow_substitutions == other.allow_substitutions
               && allow_equivalences == other.allow_equivalences && group == other.group;
    }
};

struct VisitKeyHash {
    size_t operator()(const VisitKey &key) const
    {
        size_t value = std::hash<std::string_view>()(key.group);
        value ^= key.module ? 0x85ebca6bULL : 0;
        value ^= key.allow_substitutions ? 0xc2b2ae35ULL : 0;
        value ^= key.allow_equivalences ? 0x27d4eb2fULL : 0;
        return value;
    }
};


}  // namespace tce
