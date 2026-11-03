/* Frozen C record view over one compiled prerequisite structure.
 *
 * Owns the record arrays and the string/pointer backing they expose to the Python DTO boundary. The
 * view copies no identity and derives no relationship.
 */

#include "bundle.h"
#include <algorithm>
#include <string>
#include <utility>
#include <vector>
#include "pipeline.h"
#include "records.h"

namespace tce {

/* Own one structure's record and pointer arrays for the lifetime of its bundle. */
std::vector<std::string> piece_children(const Compilation &compilation, const Node &node)
{
    std::vector<std::string> children;
    for (int child : node.children)
        children.push_back(compilation.identified.piece_id[(size_t) child]);
    return children;
}

std::vector<std::string> use_children(const Compilation &compilation, const UseRecord &use)
{
    std::vector<std::string> children;
    for (int child : use.children)
        children.push_back(compilation.identified.use_id[(size_t) child]);
    return children;
}

std::vector<std::string> use_diagnostics(const Compilation &compilation, const UseRecord &use)
{
    std::vector<std::string> diagnostics;
    for (int diagnostic : use.diagnostics)
        diagnostics.push_back(compilation.identified.diagnostic_id[(size_t) diagnostic]);
    return diagnostics;
}

void build_view(const Compilation &compilation, StructureView &view)
{
    const IdentifiedRecords &ids = compilation.identified;
    const ProjectionRecords &projection = compilation.projection;
    CourseStructureRecord &record = view.record;
    record.root_group_id = compilation.root.c_str();
    record.academic_year_start = compilation.year;
    record.active_only = compilation.active_only ? 1 : 0;
    record.include_recommended = compilation.include_recommended ? 1 : 0;
    record.include_inferred = compilation.include_inferred ? 1 : 0;
    record.requirements_use_id =
        ids.root_use >= 0 ? ids.use_id[(size_t) ids.root_use].c_str() : nullptr;
    record.required_use_id =
        ids.required_use >= 0 ? ids.use_id[(size_t) ids.required_use].c_str() : nullptr;
    record.recommended_use_id =
        ids.recommended_use >= 0 ? ids.use_id[(size_t) ids.recommended_use].c_str() : nullptr;

    if (compilation.summary_only) {
        auto root = compilation.summaries.find(compilation.root);
        if (root == compilation.summaries.end()) return;
        const CourseSummaryRec &summary = root->second;
        CourseSummaryRecord entry{};
        entry.group_id = summary.group.c_str();
        entry.name_fi = summary.name_fi.c_str();
        entry.name_en = summary.name_en.c_str();
        entry.code = summary.code.c_str();
        entry.credits_min = summary.credits_min_text.c_str();
        entry.credits_max = summary.credits_max_text.c_str();
        entry.official_url = summary.official_url.c_str();
        entry.has_name_fi = summary.has_name_fi ? 1 : 0;
        entry.has_name_en = summary.has_name_en ? 1 : 0;
        entry.has_credits_max = summary.has_credits_max ? 1 : 0;
        entry.is_active = summary.active ? 1 : 0;
        view.course_records.push_back(entry);
        record.courses = view.course_records.data();
        record.course_count = 1;
        return;
    }

    for (int index : ids.pieces) {
        const Node &node = compilation.nodes[(size_t) index];
        CoursePieceRecord piece{};
        piece.piece_id = ids.piece_id[(size_t) index].c_str();
        piece.kind = node.kind;
        piece.children = view.list(piece_children(compilation, node));
        piece.course_group_id = node.course.c_str();
        piece.module_group_id = node.module.c_str();
        piece.work_key = ids.work_key[(size_t) index].c_str();
        piece.require_min = node.require_min;
        piece.require_max = node.require_max;
        piece.credits_min = node.credits_min_text.c_str();
        piece.credits_max = node.credits_max_text.c_str();
        piece.count_min = node.count_min;
        piece.count_max = node.count_max;
        piece.reason = node.reason.c_str();
        piece.referenced_group_id = node.referenced.c_str();
        piece.detail = node.detail.c_str();
        piece.manual_credits_min = node.manual_min_text.c_str();
        piece.module_rule = node.module_rule ? 1 : 0;
        piece.cycle_closing = node.cycle ? 1 : 0;
        view.piece_records.push_back(piece);
    }
    record.pieces = view.piece_records.data();
    record.piece_count = (int32_t) view.piece_records.size();

    for (int index : ids.uses) {
        const UseRecord &use = compilation.uses[(size_t) index];
        CourseUseRecord entry{};
        entry.use_id = ids.use_id[(size_t) index].c_str();
        entry.piece_id = ids.piece_id[(size_t) use.piece].c_str();
        entry.fact_id = ids.fact_id[(size_t) use.fact].c_str();
        entry.children = view.list(use_children(compilation, use));
        entry.diagnostic_ids = view.list(use_diagnostics(compilation, use));
        entry.member_group_ids = view.list(use.members);
        view.use_records.push_back(entry);
    }
    record.uses = view.use_records.data();
    record.use_count = (int32_t) view.use_records.size();

    for (int index : ids.facts) {
        const FactRecord &fact = compilation.facts[(size_t) index];
        CourseFactRecord entry{};
        entry.fact_id = ids.fact_id[(size_t) index].c_str();
        entry.origin = fact.origin;
        entry.official_kind = fact.official_kind;
        entry.inferred_category = fact.inferred_category;
        entry.inference = fact.inference.c_str();
        view.fact_records.push_back(entry);
    }
    record.facts = view.fact_records.data();
    record.fact_count = (int32_t) view.fact_records.size();

    for (int index : ids.diagnostics) {
        const DiagnosticRecord &diagnostic = compilation.diagnostics[(size_t) index];
        CourseDiagnosticRecord entry{};
        entry.diagnostic_id = ids.diagnostic_id[(size_t) index].c_str();
        entry.kind = diagnostic.kind.c_str();
        entry.fact_id = ids.fact_id[(size_t) diagnostic.fact].c_str();
        entry.referenced_group_ids = view.list(diagnostic.referenced);
        entry.detail = diagnostic.detail.c_str();
        entry.module_group_id = diagnostic.module.c_str();
        view.diagnostic_records.push_back(entry);
    }
    record.diagnostics = view.diagnostic_records.data();
    record.diagnostic_count = (int32_t) view.diagnostic_records.size();

    std::vector<std::string> summary_groups;
    for (const auto &[group, _] : compilation.summaries) summary_groups.push_back(group);
    std::sort(summary_groups.begin(), summary_groups.end());
    for (const std::string &group : summary_groups) {
        const CourseSummaryRec &summary = compilation.summaries.at(group);
        CourseSummaryRecord entry{};
        entry.group_id = summary.group.c_str();
        entry.name_fi = summary.name_fi.c_str();
        entry.name_en = summary.name_en.c_str();
        entry.code = summary.code.c_str();
        entry.credits_min = summary.credits_min_text.c_str();
        entry.credits_max = summary.credits_max_text.c_str();
        entry.official_url = summary.official_url.c_str();
        entry.has_name_fi = summary.has_name_fi ? 1 : 0;
        entry.has_name_en = summary.has_name_en ? 1 : 0;
        entry.has_credits_max = summary.has_credits_max ? 1 : 0;
        entry.is_active = summary.active ? 1 : 0;
        view.course_records.push_back(entry);
    }
    record.courses = view.course_records.data();
    record.course_count = (int32_t) view.course_records.size();

    std::vector<std::string> module_groups;
    for (const auto &[group, _] : compilation.modules) module_groups.push_back(group);
    std::sort(module_groups.begin(), module_groups.end());
    for (const std::string &group : module_groups) {
        const ModuleSummaryRec &summary = compilation.modules.at(group);
        CourseModuleRecord entry{};
        entry.group_id = summary.group.c_str();
        entry.sisu_module_id = summary.sisu.c_str();
        entry.module_type = summary.module_type.c_str();
        entry.code = summary.code.c_str();
        entry.name_fi = summary.name_fi.c_str();
        entry.name_en = summary.name_en.c_str();
        entry.has_code = summary.has_code ? 1 : 0;
        entry.has_name_fi = summary.has_name_fi ? 1 : 0;
        entry.has_name_en = summary.has_name_en ? 1 : 0;
        view.module_records.push_back(entry);
    }
    record.modules = view.module_records.data();
    record.module_count = (int32_t) view.module_records.size();

    for (const CoverageRecord &item : compilation.coverage) {
        CourseCoverageRecord entry{};
        entry.target_group_id = item.target.c_str();
        entry.coverage_state = item.state.c_str();
        entry.eligible_source_count = item.eligible;
        entry.processed_source_count = item.processed;
        entry.accepted_source_count = item.accepted;
        view.coverage_records.push_back(entry);
    }
    record.coverage = view.coverage_records.data();
    record.coverage_count = (int32_t) view.coverage_records.size();
    record.excluded_group_ids = view.list(compilation.excluded_group_ids);
    record.completed_node_keys = view.list(compilation.completed_node_keys);
    record.excluded_node_keys = view.list(compilation.excluded_node_keys);
    std::vector<std::string> root_diagnostics;
    for (int diagnostic : compilation.root_diagnostics)
        root_diagnostics.push_back(ids.diagnostic_id[(size_t) diagnostic]);
    record.root_diagnostic_ids = view.list(std::move(root_diagnostics));
    record.projection_root_context_id = projection.has_root_context
        ? projection.root_context_id.c_str() : nullptr;

    for (const ProjBindingRec &binding : projection.bindings) {
        CourseBindingRecord entry{};
        entry.support_id = binding.support_id.c_str();
        entry.owner_group_id = binding.owner_group_id.c_str();
        entry.piece_id = binding.piece_id.c_str();
        entry.use_ids = view.list(binding.use_ids);
        entry.node_ids = view.list(binding.node_ids);
        entry.mark_node_ids = view.list(binding.mark_node_ids);
        view.binding_records.push_back(entry);
    }
    record.bindings = view.binding_records.data();
    record.binding_count = (int32_t) view.binding_records.size();

    view.context_children.reserve(projection.contexts.size());
    for (const ProjContextRec &context : projection.contexts) {
        std::vector<CourseContextChildRecord> children;
        for (const ProjContextChildRec &child : context.children)
            children.push_back(CourseContextChildRecord{child.slot, child.context_id.c_str()});
        view.context_children.push_back(std::move(children));
    }
    for (size_t index = 0; index < projection.contexts.size(); ++index) {
        const ProjContextRec &context = projection.contexts[index];
        CourseContextRecord entry{};
        entry.context_id = context.context_id.c_str();
        entry.owner_group_id = context.owner_group_id.c_str();
        entry.piece_id = context.piece_id.c_str();
        entry.children = view.context_children[index].data();
        entry.child_count = (int32_t) view.context_children[index].size();
        entry.member_ids = view.list(context.member_ids);
        view.context_records.push_back(entry);
    }
    record.contexts = view.context_records.data();
    record.context_count = (int32_t) view.context_records.size();

    for (const ProjMemberRec &member : projection.members) {
        CourseMemberRecord entry{};
        entry.member_id = member.member_id.c_str();
        entry.source_node_id = member.source_node_id.c_str();
        entry.target_node_id = member.target_node_id.c_str();
        entry.fact_id = member.fact_id.c_str();
        view.member_records.push_back(entry);
    }
    record.members = view.member_records.data();
    record.member_count = (int32_t) view.member_records.size();

    int32_t drawing_courses = 0;
    for (const ProjNodeRec &node : projection.nodes)
        if (node.kind == D_COURSE) ++drawing_courses;
    record.drawing_course_count = drawing_courses;
    record.drawing_node_count = (int32_t) projection.nodes.size();
    record.drawing_edge_count = (int32_t) projection.edges.size();

    for (const ProjNodeRec &node : projection.nodes) {
        CourseDisplayNodeRecord entry{};
        entry.node_id = node.node_id.c_str();
        entry.kind = node.kind;
        entry.owner_group_id = node.owner_group_id.c_str();
        entry.course_group_id = node.course_group_id.c_str();
        entry.module_group_id = node.module_group_id.c_str();
        entry.require_min = node.require_min;
        entry.require_max = node.require_max;
        entry.credits_min = node.credits_min.c_str();
        entry.credits_max = node.credits_max.c_str();
        entry.count_min = node.count_min;
        entry.count_max = node.count_max;
        entry.referenced_group_id = node.referenced_group_id.c_str();
        entry.reason = node.reason.c_str();
        entry.detail = node.detail.c_str();
        entry.member_group_ids = view.list(node.member_group_ids);
        entry.diagnostic_ids = view.list(node.diagnostic_ids);
        entry.is_root = node.is_root ? 1 : 0;
        entry.via_inferred = node.via_inferred ? 1 : 0;
        entry.via_recommended = node.via_recommended ? 1 : 0;
        entry.has_official_provenance = node.has_official_provenance ? 1 : 0;
        entry.has_inferred_provenance = node.has_inferred_provenance ? 1 : 0;
        entry.display_as_inferred = node.display_as_inferred ? 1 : 0;
        entry.markable = node.markable ? 1 : 0;
        view.display_node_records.push_back(entry);
    }
    record.nodes = view.display_node_records.data();
    record.node_count = (int32_t) view.display_node_records.size();

    for (const ProjEdgeRec &edge : projection.edges) {
        CourseDisplayEdgeRecord entry{};
        entry.edge_id = edge.edge_id.c_str();
        entry.source_node_id = edge.source_node_id.c_str();
        entry.target_node_id = edge.target_node_id.c_str();
        entry.member_ids = view.list(edge.member_ids);
        entry.inferred_only = edge.inferred_only ? 1 : 0;
        view.display_edge_records.push_back(entry);
    }
    record.edges = view.display_edge_records.data();
    record.edge_count = (int32_t) view.display_edge_records.size();
}


}  // namespace tce
