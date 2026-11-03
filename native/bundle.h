/* Opened structure bundle and its owned record views. */

#pragma once

#include <string>
#include <vector>

#include "c_records.h"
#include "fact_model.h"
#include "records.h"

namespace tce {

/* Own one structure's record and pointer arrays for the lifetime of its bundle. */
struct StructureView {
    CourseStructureRecord record{};
    std::vector<std::vector<const char *>> arrays;
    std::vector<std::vector<std::string>> owned;
    std::vector<CoursePieceRecord> piece_records;
    std::vector<CourseUseRecord> use_records;
    std::vector<CourseFactRecord> fact_records;
    std::vector<CourseDiagnosticRecord> diagnostic_records;
    std::vector<CourseSummaryRecord> course_records;
    std::vector<CourseModuleRecord> module_records;
    std::vector<CourseCoverageRecord> coverage_records;
    std::vector<CourseBindingRecord> binding_records;
    std::vector<CourseContextRecord> context_records;
    std::vector<std::vector<CourseContextChildRecord>> context_children;
    std::vector<CourseMemberRecord> member_records;
    std::vector<CourseDisplayNodeRecord> display_node_records;
    std::vector<CourseDisplayEdgeRecord> display_edge_records;

    const char *const *array(const std::vector<std::string> &values)
    {
        arrays.emplace_back();
        std::vector<const char *> &target = arrays.back();
        target.reserve(values.size());
        for (const std::string &value : values) target.push_back(value.c_str());
        return target.empty() ? nullptr : target.data();
    }

    CourseStringList list(std::vector<std::string> values)
    {
        owned.push_back(std::move(values));
        std::vector<std::string> &stored = owned.back();
        return CourseStringList{array(stored), (int32_t) stored.size()};
    }
};

void build_view(const Compilation &compilation, StructureView &view);

struct StructureBundle {
    Compiled *compiled = nullptr;
    std::vector<StructureView> views;
    std::vector<CourseStructureRecord> records;
};

}  // namespace tce
