/* Native prerequisite compiler.
 *
 * Reads the canonical official curriculum facts, the inferred expressions and the equivalence
 * groups from the caller-owned fact bundle, and builds one provenance-free piece DAG per target.
 * The compiler owns calculation roots, ordered child slots, source positions and diagnostics. The
 * identity tables, drawing projection, record view and evaluator are separate translation units.
 */

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <map>
#include <memory>
#include <set>
#include <string>
#include <string_view>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>

#include "canonical_json.h"
#include "fact_model.h"
#include "pipeline.h"
#include "records.h"
#include "support.h"

namespace tce {

class Compiler {
public:
    Compiler(const Bundle &bundle, Compilation &compilation, std::string root, int32_t year)
        : bundle_(bundle), compilation_(compilation), root_(std::move(root)), year_(year)
    {
    }

    bool active_only = false;
    bool include_inferred = false;
    bool include_recommended = true;
    bool direct_only = true;
    // The narrow discovery projection asks only for the root identity, academic year and course
    // summaries. Calculation nodes and summaries stay identical. The drawing-only record tables
    // (facts, uses, module summaries, coverage and root diagnostics) are not built.
    bool drawing = true;
    bool failed = false;

    std::vector<std::string> ancestors_courses;
    std::vector<std::string> ancestors_modules;
    std::unordered_map<SourceKey, int, SourceKeyHash> source_components;
    std::vector<int> pending;
    std::unordered_set<std::string> retained;
    std::vector<std::string> excluded_inputs;
    std::vector<std::string> completed_keys;
    std::vector<std::string> excluded_keys;

    struct CompiledOption {
        int32_t index = 0;
        Frag frag;
        std::vector<std::string> references;
    };

    Frag build();
    std::unordered_set<std::string> mandatory_expanded_heads(int root_use) const;
    int prune_expansions(int use, bool mandatory,
                         const std::unordered_set<std::string> &heads,
                         std::unordered_map<std::string, int> &memo);

private:
    const CourseFact *course(const std::string &group) const;
    const ModuleFact *module(const std::string &group) const;

    int intern_fact(const Prov &prov);
    int add(Node node, const Path &source);
    int leaf_course(const std::string &group, bool cycle, const Prov &prov, const Path &source,
                    const std::vector<int> &diagnostics);
    int unresolved(const std::string &reason, const std::string &referenced,
                   const std::string &detail, int official_kind, const Path &source,
                   const std::vector<int> &diagnostics = {});
    int intern_diagnostic(const std::string &kind, int fact,
                          const std::vector<std::string> &referenced, const std::string &detail,
                          const std::string &module);
    int ignored(const std::string &kind, int official_kind,
                const std::vector<std::string> &referenced, const std::string &detail,
                const std::string &module);
    std::vector<int> take_pending(size_t offset);
    std::vector<int> take_pending(size_t offset, bool ignored_only);
    void replay(const Frag &fragment);
    Frag finish_frag(size_t offset, int use) const;
    int reintern_use(int use, const std::vector<int> &children, int extra_diagnostic = -1);

    bool contains_missing_module(int use) const;
    std::vector<std::string> member_group_ids(int use);

    Frag compile_course_requirements(const CourseFact &fact);
    void compile_category_pools(const CourseFact &fact, const Path &source,
                                bool treat_inactive_as_active, Frag *required, Frag *recommended);
    std::vector<CompiledOption> compile_official_options(const CourseFact &fact,
                                                         int requirement_kind, const Path &source);
    Frag finish_official_options(const std::vector<CompiledOption> &options, int official_kind,
                                 bool has_inferred, const Path &source);
    Frag pool_category(const Frag &official, const std::vector<Frag> &inferred, int official_kind,
                       const Path &source);
    Frag compile_prerequisite_member(const Member &member, int official_kind, const Path &source);
    Frag expand_module_requirement(const std::string &module_id, int official_kind,
                                   const Path &source);
    Frag expand_course_requirement(const std::string &group, int origin, int official_kind,
                                   int inferred_category, const std::string &inference,
                                   const Path &source, bool allow_substitutions,
                                   bool allow_equivalences);
    bool select_version(const ModuleFact &fact, const Version **version, bool &used_fallback,
                        std::string &reason) const;
    bool content_unexpandable(const Rule &rule) const;

    Frag compile_rule(const Rule &rule, const std::string &module_id,
                      const std::string &version_id, const Path &source, const Path &work_path);
    Frag dispatch_rule(const Rule &rule, const std::string &module_id, const Path &source,
                       const Path &work_path);
    std::vector<Frag> compile_rule_children(const Rule &rule, const std::string &module_id,
                                            const std::string &version_id, const Path &source,
                                            const Path &work_path);
    Frag compile_composite(const Rule &rule, const std::string &module_id, const Path &source,
                           const Path &work_path);
    Frag compile_bounded(const Rule &rule, const std::string &module_id, const Path &source,
                         const Path &work_path);
    Frag compile_course_unit(const Rule &rule, const std::string &module_id, const Path &source);
    Frag compile_module_reference(const Rule &rule, const std::string &module_id, const Path &source);
    Frag compile_unrestricted(const Rule &rule, const std::string &module_id,
                              const Path &source);
    Frag malformed(const Rule &rule, const std::string &module_id, const std::string &detail,
                   const Path &source);
    std::string unexpected_field(const Rule &rule, std::initializer_list<const char *> allowed) const;

    std::vector<Frag> compile_substitution_branches(const CourseFact &fact, const Path &source);
    Frag compile_substitution_member(const SubMember &member, const Path &source);
    std::vector<Frag> compile_equivalence_branches(const std::string &group, int official_kind,
                                                   int inferred_category, const Path &source);
    bool has_ancestor_equivalent(const std::string &group) const;
    std::vector<std::string_view> equivalence_candidates(const std::string &group) const;

    std::vector<Frag> expand_inferred_options(const std::vector<Expr> &roots, const Path &source);
    Frag expand_inferred_expression(const Expr &expression, const Path &source);
    bool category_homogeneous(const Expr &expression, int category) const;
    void inferred_option_roots(const Expr &expression, std::vector<Expr> *required,
                               std::vector<Expr> *recommended);
    const InferredFact *read_inferred(const CourseFact &fact);

    std::pair<std::vector<std::string>, std::vector<std::string>> cycle_ancestors(
        const std::string &kind, const std::string &group,
        const std::vector<std::string> &courses, const std::vector<std::string> &modules) const;
    void build_source_index();
    void index_course_sources(std::string_view group, bool allow_substitutions,
                              bool allow_equivalences, std::vector<Visit> *successors,
                              std::vector<std::string_view> *equivalents);
    void index_module_sources(std::string_view group, std::vector<Visit> *successors);
    void index_expression(const Expr &expression, const std::string &owner,
                          std::vector<Visit> *successors);

    std::unordered_map<std::string, Frag> course_memo_;
    std::unordered_map<std::string, Frag> module_memo_;
    std::unordered_map<std::string, Frag> rule_memo_;
    std::unordered_map<std::string, std::vector<std::string>> member_memo_;
    std::unordered_map<std::string, CoverageRecord> coverage_;
    std::unordered_map<std::string, ModuleSummaryRec> module_summaries_;

    const Bundle &bundle_;
    Compilation &compilation_;
    std::string root_;
    int32_t year_;
};

bool ignored_diagnostic_kind(const std::string &kind)
{
    static const std::unordered_set<std::string> kinds{
        "empty_option", "missing_substitution_course", "missing_module_alternative",
        "module_version_fallback", "free_choice", "unexpandable_content", "all_mandatory_bounds",
        "module_cycle", "course_cycle",
    };
    return kinds.count(kind) != 0;
}

bool is_rule_inherit_kind(int kind)
{
    return kind == N_AND || kind == N_EXPANDED || kind == N_MODULE_BLOCK || kind == N_CREDITS
        || kind == N_COUNT;
}

const char *rule_type_name(int type)
{
    switch (type) {
        case R_COMPOSITE: return "CompositeRule";
        case R_CREDITS: return "CreditsRule";
        case R_COURSE_UNIT: return "CourseUnitRule";
        case R_MODULE: return "ModuleRule";
        case R_ANY_COURSE: return "AnyCourseUnitRule";
        case R_ANY_MODULE: return "AnyModuleRule";
        case R_COUNT: return "CourseUnitCountRule";
        default: return "UnknownRule";
    }
}

const CourseFact *Compiler::course(const std::string &group) const
{
    auto found = bundle_.courses.find(group);
    return found == bundle_.courses.end() ? nullptr : &found->second;
}

const ModuleFact *Compiler::module(const std::string &group) const
{
    auto found = bundle_.modules.find(group);
    return found == bundle_.modules.end() ? nullptr : &found->second;
}

int Compiler::intern_fact(const Prov &prov)
{
    if (!drawing) return -1;
    for (size_t index = 0; index < compilation_.facts.size(); ++index) {
        const FactRecord &fact = compilation_.facts[index];
        if (fact.origin == prov.origin && fact.official_kind == prov.official_kind
            && fact.inferred_category == prov.inferred_category
            && fact.inference == prov.inference)
            return (int) index;
    }
    FactRecord fact;
    fact.origin = prov.origin;
    fact.official_kind = prov.official_kind;
    fact.inferred_category = prov.inferred_category;
    fact.inference = prov.inference;
    compilation_.facts.push_back(std::move(fact));
    return (int) compilation_.facts.size() - 1;
}

int Compiler::intern_diagnostic(const std::string &kind, int fact,
                                const std::vector<std::string> &referenced,
                                const std::string &detail, const std::string &module)
{
    if (!drawing) {
        // Discovery classification reads only the diagnostic kind. Pending sets are deduplicated
        // by identity, and this projection never emits the record, so no string copy or scan is
        // needed beyond the one kind the classification reads.
        DiagnosticRecord record;
        record.kind = kind;
        record.fact = -1;
        compilation_.diagnostics.push_back(std::move(record));
        return (int) compilation_.diagnostics.size() - 1;
    }
    for (size_t index = 0; index < compilation_.diagnostics.size(); ++index) {
        const DiagnosticRecord &record = compilation_.diagnostics[index];
        if (record.kind == kind && record.fact == fact && record.referenced == referenced
            && record.detail == detail && record.module == module)
            return (int) index;
    }
    DiagnosticRecord record;
    record.kind = kind;
    record.fact = fact;
    record.referenced = referenced;
    record.detail = detail;
    record.module = module;
    compilation_.diagnostics.push_back(std::move(record));
    return (int) compilation_.diagnostics.size() - 1;
}

int Compiler::ignored(const std::string &kind, int official_kind,
                      const std::vector<std::string> &referenced, const std::string &detail,
                      const std::string &module)
{
    Prov prov;
    prov.origin = 0;
    prov.official_kind = official_kind;
    int fact = intern_fact(prov);
    return intern_diagnostic(kind, fact, referenced, detail, module);
}

int Compiler::add(Node node, const Path &source)
{
    int piece = (int) compilation_.nodes.size();
    compilation_.nodes.push_back(std::move(node));
    if (drawing) {
        const Node &stored = compilation_.nodes[piece];
        UseRecord use;
        use.piece = piece;
        use.fact = intern_fact(stored.prov);
        use.children = stored.children;
        use.source = source;
        use.members = stored.use_members;
        use.diagnostics = stored.use_diagnostics;
        compilation_.uses.push_back(std::move(use));
    }
    return piece;
}

int Compiler::leaf_course(const std::string &group, bool cycle, const Prov &prov,
                          const Path &source, const std::vector<int> &diagnostics)
{
    Node node;
    node.kind = N_COURSE;
    node.course = group;
    node.cycle = cycle;
    node.module_rule = prov.official_kind == 2;
    node.prov = prov;
    node.use_diagnostics = diagnostics;
    return add(std::move(node), source);
}

int Compiler::unresolved(const std::string &reason, const std::string &referenced,
                         const std::string &detail, int official_kind, const Path &source,
                         const std::vector<int> &diagnostics)
{
    Node node;
    node.kind = N_UNRESOLVED;
    node.reason = reason;
    node.referenced = referenced;
    node.detail = detail;
    node.module_rule = official_kind == 2;
    node.prov.origin = 0;
    node.prov.official_kind = official_kind;
    node.use_diagnostics = diagnostics;
    return add(std::move(node), source);
}

std::vector<int> Compiler::take_pending(size_t offset)
{
    std::vector<int> result;
    std::unordered_set<int> seen;
    for (size_t index = offset; index < pending.size(); ++index)
        if (seen.insert(pending[index]).second) result.push_back(pending[index]);
    pending.erase(pending.begin() + (long) offset, pending.end());
    return result;
}

std::vector<int> Compiler::take_pending(size_t offset, bool ignored_only)
{
    std::vector<int> result;
    std::unordered_set<int> seen;
    for (size_t index = offset; index < pending.size(); ++index) {
        int diagnostic = pending[index];
        if (ignored_only && !ignored_diagnostic_kind(compilation_.diagnostics[diagnostic].kind))
            continue;
        if (seen.insert(diagnostic).second) result.push_back(diagnostic);
    }
    pending.erase(pending.begin() + (long) offset, pending.end());
    return result;
}

void Compiler::replay(const Frag &fragment)
{
    pending.insert(pending.end(), fragment.diagnostics.begin(), fragment.diagnostics.end());
    if (!drawing) return;
    for (const auto &[group, summary] : fragment.modules) module_summaries_[group] = summary;
    for (const CoverageRecord &record : fragment.coverage)
        coverage_.emplace(record.target, record);
}

bool Compiler::contains_missing_module(int use) const
{
    std::vector<int> stack{use};
    std::unordered_set<int> seen;
    while (!stack.empty()) {
        int current = stack.back();
        stack.pop_back();
        if (!seen.insert(current).second) continue;
        const Node &node = compilation_.nodes[current];
        if (node.kind == N_UNRESOLVED && node.reason == "missing_module") return true;
        for (int child : compilation_.nodes[current].children) stack.push_back(child);
    }
    return false;
}

std::vector<std::string> Compiler::member_group_ids(int use)
{
    auto cached = member_memo_.find(std::to_string(use));
    if (cached != member_memo_.end()) return cached->second;
    std::unordered_set<std::string> found;
    std::vector<int> stack{use};
    std::unordered_set<int> seen;
    while (!stack.empty()) {
        int current = stack.back();
        stack.pop_back();
        if (!seen.insert(current).second) continue;
        const Node &node = compilation_.nodes[current];
        const std::vector<int> &children = compilation_.nodes[current].children;
        if (node.kind == N_COURSE) {
            if (!node.course.empty()) found.insert(node.course);
            continue;
        }
        if (node.kind == N_EXPANDED) {
            if (!children.empty()) {
                const Node &head = compilation_.nodes[children[0]];
                if (!head.course.empty()) found.insert(head.course);
            }
            continue;
        }
        if (node.kind == N_ALTERNATIVES) {
            if (!children.empty()) stack.push_back(children[0]);
            continue;
        }
        for (int child : children) stack.push_back(child);
    }
    std::vector<std::string> result(found.begin(), found.end());
    std::sort(result.begin(), result.end());
    member_memo_[std::to_string(use)] = result;
    return result;
}

std::pair<std::vector<std::string>, std::vector<std::string>> Compiler::cycle_ancestors(
    const std::string &kind, const std::string &group, const std::vector<std::string> &courses,
    const std::vector<std::string> &modules) const
{
    SourceKey key{kind == "module", group};
    auto found = source_components.find(key);
    if (found == source_components.end()) return {courses, modules};
    std::vector<std::string> filtered_courses;
    std::vector<std::string> filtered_modules;
    for (const std::string &value : courses) {
        auto component = source_components.find(SourceKey{false, value});
        if (component != source_components.end() && component->second == found->second)
            filtered_courses.push_back(value);
    }
    for (const std::string &value : modules) {
        auto component = source_components.find(SourceKey{true, value});
        if (component != source_components.end() && component->second == found->second)
            filtered_modules.push_back(value);
    }
    return {filtered_courses, filtered_modules};
}

bool Compiler::select_version(const ModuleFact &fact, const Version **version, bool &used_fallback,
                              std::string &reason) const
{
    std::vector<const Version *> exact;
    for (const Version &candidate : fact.versions)
        for (int32_t period : candidate.periods)
            if (period == year_) {
                exact.push_back(&candidate);
                break;
            }
    if (exact.size() == 1) {
        *version = exact[0];
        used_fallback = false;
        return true;
    }
    if (exact.size() > 1) {
        reason = "ambiguous_module_version";
        return false;
    }
    std::vector<const Version *> validity;
    for (const Version &candidate : fact.versions) {
        if (!candidate.periods.empty()) continue;
        bool start_ok = candidate.validity_start == 0 || candidate.validity_start <= year_;
        bool end_ok = candidate.validity_end == 0 || year_ <= candidate.validity_end;
        if (start_ok && end_ok) validity.push_back(&candidate);
    }
    if (validity.size() == 1) {
        *version = validity[0];
        used_fallback = false;
        return true;
    }
    if (validity.size() > 1) {
        reason = "ambiguous_module_version";
        return false;
    }
    if (fact.versions.empty()) {
        reason = "missing_module";
        return false;
    }
    auto fallback_year = [this](const Version &candidate, bool &ok) {
        ok = true;
        if (!candidate.periods.empty()) {
            int32_t earlier = -1;
            int32_t first = -1;
            for (int32_t period : candidate.periods) {
                if (first < 0 || period < first) first = period;
                if (period < year_ && period > earlier) earlier = period;
            }
            return earlier >= 0 ? earlier : first;
        }
        if (candidate.validity_end != 0 && candidate.validity_end < year_)
            return candidate.validity_end;
        if (candidate.validity_start != 0) return candidate.validity_start;
        ok = false;
        return (int32_t) 0;
    };
    std::vector<std::pair<int32_t, const Version *>> ranked;
    for (const Version &candidate : fact.versions) {
        bool ok = true;
        int32_t value = fallback_year(candidate, ok);
        if (!ok) {
            reason = "missing_module";
            return false;
        }
        ranked.emplace_back(value, &candidate);
    }
    std::vector<int32_t> earlier;
    for (const auto &[value, _] : ranked)
        if (value < year_) earlier.push_back(value);
    int32_t best = 0;
    if (!earlier.empty()) {
        best = earlier[0];
        for (int32_t value : earlier) best = std::max(best, value);
    } else {
        best = ranked[0].first;
        for (const auto &[value, _] : ranked) best = std::min(best, value);
    }
    const Version *chosen = nullptr;
    for (const auto &[value, candidate] : ranked) {
        if (value != best) continue;
        if (chosen == nullptr || candidate->sisu > chosen->sisu) chosen = candidate;
    }
    *version = chosen;
    used_fallback = true;
    return chosen != nullptr;
}

bool Compiler::content_unexpandable(const Rule &rule) const
{
    if (rule.type == R_ANY_COURSE || rule.type == R_ANY_MODULE) return true;
    if (rule.type == R_COMPOSITE) {
        if (rule.children.empty()) return true;
        for (const Rule &child : rule.children)
            if (!content_unexpandable(child)) return false;
        return true;
    }
    if (rule.type == R_CREDITS || rule.type == R_COUNT) {
        for (const Rule &child : rule.children)
            if (!content_unexpandable(child)) return false;
        return true;
    }
    return false;
}

std::string Compiler::unexpected_field(const Rule &rule,
                                       std::initializer_list<const char *> allowed) const
{
    auto permitted = [&allowed](const char *name) {
        for (const char *value : allowed)
            if (std::strcmp(value, name) == 0) return true;
        return false;
    };
    if (rule.require_min != -1 && !permitted("require_min")) return "require_min";
    if (rule.require_max != -1 && !permitted("require_max")) return "require_max";
    if (rule.all_mandatory != -1 && !permitted("all_mandatory")) return "all_mandatory";
    if (rule.credits_min != -1 && !permitted("credits_min")) return "credits_min";
    if (rule.credits_max != -1 && !permitted("credits_max")) return "credits_max";
    if (rule.count_min != -1 && !permitted("count_min")) return "count_min";
    if (rule.count_max != -1 && !permitted("count_max")) return "count_max";
    if (!rule.ref.empty() && !permitted("referenced_group_id")) return "referenced_group_id";
    return {};
}

Frag Compiler::malformed(const Rule &rule, const std::string &module_id, const std::string &detail,
                         const Path &source)
{
    Frag result;
    result.use = unresolved("malformed_rule", module_id,
                            std::string(rule_type_name(rule.type)) + ": " + detail, 2, source);
    return result;
}

std::vector<Frag> Compiler::compile_rule_children(const Rule &rule, const std::string &module_id,
                                                  const std::string &version_id, const Path &source,
                                                  const Path &work_path)
{
    std::vector<Frag> result;
    for (const Rule &child : rule.children) {
        Frag compiled = compile_rule(child, module_id, version_id,
                                     extend(source, child.sibling),
                                     extend(work_path, child.sibling));
        if (!compiled.empty()) result.push_back(std::move(compiled));
    }
    return result;
}

Frag Compiler::finish_frag(size_t offset, int use) const
{
    Frag result;
    result.use = use;
    std::unordered_set<int> seen;
    for (size_t index = offset; index < pending.size(); ++index)
        if (seen.insert(pending[index]).second) result.diagnostics.push_back(pending[index]);
    std::vector<int> stack;
    if (use >= 0) stack.push_back(use);
    std::unordered_set<int> visited;
    if (!drawing) return result;
    std::unordered_set<std::string> module_ids;
    std::unordered_set<std::string> course_ids;
    while (!stack.empty()) {
        int current = stack.back();
        stack.pop_back();
        if (!visited.insert(current).second) continue;
        const Node &node = compilation_.nodes[current];
        if (!node.module.empty()) module_ids.insert(node.module);
        if (!node.course.empty()) course_ids.insert(node.course);
        for (int child : compilation_.nodes[current].children) stack.push_back(child);
    }
    for (const std::string &group : module_ids) {
        auto found = module_summaries_.find(group);
        if (found != module_summaries_.end()) result.modules[group] = found->second;
    }
    std::vector<std::string> ordered(course_ids.begin(), course_ids.end());
    std::sort(ordered.begin(), ordered.end());
    for (const std::string &group : ordered) {
        auto found = coverage_.find(group);
        if (found != coverage_.end()) result.coverage.push_back(found->second);
    }
    return result;
}

int Compiler::reintern_use(int use, const std::vector<int> &children, int extra_diagnostic)
{
    Node piece = compilation_.nodes[use];
    piece.children = children;
    if (extra_diagnostic >= 0) piece.use_diagnostics.push_back(extra_diagnostic);
    int created = (int) compilation_.nodes.size();
    if (drawing) {
        UseRecord record = compilation_.uses[use];
        record.piece = created;
        record.children = children;
        if (extra_diagnostic >= 0) record.diagnostics.push_back(extra_diagnostic);
        compilation_.uses.push_back(std::move(record));
    }
    compilation_.nodes.push_back(std::move(piece));
    return created;
}

Frag Compiler::compile_rule(const Rule &rule, const std::string &module_id,
                            const std::string &version_id, const Path &source,
                            const Path &work_path)
{
    auto ancestors = cycle_ancestors("module", module_id, ancestors_courses, ancestors_modules);
    std::string key = "R|" + module_id + "|" + version_id + "|";
    for (size_t index = 3; index < source.size(); ++index) {
        if (source[index].integer) key += "#" + std::to_string(source[index].number);
        else key += "$" + source[index].text;
        key += ",";
    }
    key += "|" + (ancestors_courses.empty() ? std::string() : ancestors_courses.back()) + "|";
    for (const std::string &value : ancestors.first) key += "c" + value + ";";
    key += "|";
    for (const std::string &value : ancestors.second) key += "m" + value + ";";
    auto cached = rule_memo_.find(key);
    if (cached != rule_memo_.end()) {
        replay(cached->second);
        return cached->second;
    }
    size_t offset = pending.size();
    Frag result = dispatch_rule(rule, module_id, source, work_path);
    Frag fragment = finish_frag(offset, result.use);
    rule_memo_[key] = fragment;
    return fragment;
}

Frag Compiler::dispatch_rule(const Rule &rule, const std::string &module_id, const Path &source,
                             const Path &work_path)
{
    switch (rule.type) {
        case R_COMPOSITE: return compile_composite(rule, module_id, source, work_path);
        case R_CREDITS:
        case R_COUNT: return compile_bounded(rule, module_id, source, work_path);
        case R_COURSE_UNIT: return compile_course_unit(rule, module_id, source);
        case R_MODULE: return compile_module_reference(rule, module_id, source);
        case R_ANY_COURSE:
        case R_ANY_MODULE: return compile_unrestricted(rule, module_id, source);
        default: {
            Frag result;
            result.use = unresolved("malformed_rule", module_id,
                                    std::string(rule_type_name(rule.type))
                                        + ": unsupported module rule node type",
                                    2, source);
            return result;
        }
    }
}

Frag Compiler::compile_composite(const Rule &rule, const std::string &module_id, const Path &source,
                                 const Path &work_path)
{
    std::string offending = unexpected_field(rule, {"require_min", "require_max", "all_mandatory"});
    if (!offending.empty())
        return malformed(rule, module_id,
                         std::string(rule_type_name(rule.type)) + " carries unexpected "
                             + offending,
                         source);
    if (rule.children.empty()) {
        pending.push_back(ignored("unexpandable_content", 2, {}, "blank CompositeRule has no contents",
                                  module_id));
        return {};
    }
    if (rule.all_mandatory == 1) {
        std::vector<Frag> children = compile_rule_children(rule, module_id, source[2].text, source,
                                                           work_path);
        if (children.empty()) return {};
        int expression = children.size() == 1 ? children[0].use : -1;
        if (expression < 0) {
            Node node;
            node.kind = N_AND;
            for (const Frag &child : children) node.children.push_back(child.use);
            node.prov.origin = 0;
            node.prov.official_kind = 2;
            node.module_rule = true;
            expression = add(std::move(node), source);
        }
        if (rule.require_min != -1 || rule.require_max != -1) {
            int diagnostic = ignored(
                "all_mandatory_bounds", 2, {},
                "all-mandatory composite ignored bounds require_min="
                    + optional_number(rule.require_min) + " require_max="
                    + optional_number(rule.require_max),
                module_id);
            expression = reintern_use(expression, compilation_.nodes[expression].children, diagnostic);
        }
        Frag result;
        result.use = expression;
        return result;
    }
    if (rule.require_min == -1)
        return malformed(rule, module_id,
                         "CompositeRule requires explicit require_min unless all-mandatory", source);
    if (rule.require_min > (int32_t) rule.children.size())
        return malformed(rule, module_id, "CompositeRule require_min exceeds child count", source);
    if (rule.require_max != -1 && rule.require_max > (int32_t) rule.children.size())
        return malformed(rule, module_id, "CompositeRule require_max exceeds child count", source);
    if (rule.require_max != -1 && rule.require_min > rule.require_max)
        return malformed(rule, module_id, "CompositeRule require_min exceeds require_max", source);
    std::vector<Frag> children = compile_rule_children(rule, module_id, source[2].text, source,
                                                       work_path);
    Node node;
    node.kind = N_CARDINALITY;
    for (const Frag &child : children) node.children.push_back(child.use);
    node.require_min = rule.require_min;
    node.require_max = rule.require_max;
    node.prov.origin = 0;
    node.prov.official_kind = 2;
    node.module_rule = true;
    Frag result;
    result.use = add(std::move(node), source);
    return result;
}

Frag Compiler::compile_bounded(const Rule &rule, const std::string &module_id, const Path &source,
                               const Path &work_path)
{
    bool credits = rule.type == R_CREDITS;
    const char *lower_name = credits ? "credits_min" : "count_min";
    const char *upper_name = credits ? "credits_max" : "count_max";
    std::string offending = unexpected_field(rule, {lower_name, upper_name});
    if (!offending.empty())
        return malformed(rule, module_id,
                         std::string(rule_type_name(rule.type)) + " carries unexpected "
                             + offending,
                         source);
    int64_t lower = credits ? rule.credits_min : rule.count_min;
    int64_t upper = credits ? rule.credits_max : rule.count_max;
    if (lower < 0)
        return malformed(rule, module_id,
                         std::string(rule_type_name(rule.type)) + " requires " + lower_name, source);
    if (upper >= 0 && lower > upper)
        return malformed(rule, module_id,
                         std::string(rule_type_name(rule.type)) + " " + lower_name + " exceeds "
                             + upper_name,
                         source);
    if (rule.children.size() != 1)
        return malformed(rule, module_id,
                         std::string(rule_type_name(rule.type)) + " requires exactly one child",
                         source);
    const Rule &child_rule = rule.children[0];
    size_t disclosure = pending.size();
    Frag child = compile_rule(child_rule, module_id, source[2].text,
                              extend(source, child_rule.sibling),
                              extend(work_path, child_rule.sibling));
    if (child.empty()) {
        bool real_unexpandable = content_unexpandable(child_rule);
        for (size_t index = disclosure; index < pending.size(); ++index) {
            const std::string &kind = compilation_.diagnostics[pending[index]].kind;
            if (kind == "free_choice" || kind == "unexpandable_content") real_unexpandable = true;
        }
        if (!real_unexpandable) return {};
        if (credits) {
            Node node;
            node.kind = N_OPAQUE;
            node.prov.origin = 0;
            node.prov.official_kind = 2;
            node.module_rule = true;
            node.manual_min = rule.credits_min;
            node.credits_min = rule.credits_min;
            node.credits_max = rule.credits_max;
            node.manual_min_text = rule.credits_min_text;
            node.credits_min_text = rule.credits_min_text;
            node.credits_max_text = rule.credits_max_text;
            node.work_payload = path_payload(module_id, work_path);
            Frag result;
            result.use = add(std::move(node), source);
            return result;
        }
        if (rule.count_min == 0 && rule.count_max == -1) {
            pending.push_back(ignored(
                "unexpandable_content", 2, {},
                std::string(rule_type_name(rule.type)) + " count_min=0 over unexpandable content",
                module_id));
            return {};
        }
        Frag result;
        result.use = unresolved(
            "unknown_course_count", module_id,
            std::string(rule_type_name(rule.type)) + " count_min=" + optional_number(rule.count_min)
                + " count_max=" + optional_number(rule.count_max) + " over unknown content",
            2, source);
        return result;
    }
    Node node;
    node.kind = credits ? N_CREDITS : N_COUNT;
    node.children = {child.use};
    node.prov.origin = 0;
    node.prov.official_kind = 2;
    node.module_rule = true;
    if (credits) {
        node.credits_min = rule.credits_min;
        node.credits_max = rule.credits_max;
        node.credits_min_text = rule.credits_min_text;
        node.credits_max_text = rule.credits_max_text;
    } else {
        node.count_min = rule.count_min;
        node.count_max = rule.count_max;
    }
    Frag result;
    result.use = add(std::move(node), source);
    return result;
}

Frag Compiler::compile_course_unit(const Rule &rule, const std::string &module_id,
                                   const Path &source)
{
    std::string offending = unexpected_field(rule, {"referenced_group_id"});
    if (!offending.empty())
        return malformed(rule, module_id,
                         std::string(rule_type_name(rule.type)) + " carries unexpected "
                             + offending,
                         source);
    if (!rule.children.empty())
        return malformed(rule, module_id, "CourseUnitRule forbids child rules", source);
    if (rule.ref.empty())
        return malformed(rule, module_id,
                         "CourseUnitRule requires a nonblank referenced course ID", source);
    if (!ancestors_courses.empty() && rule.ref == ancestors_courses.back()) return {};
    const CourseFact *fact = course(rule.ref);
    if (fact == nullptr || !fact->has_rep) {
        Frag result;
        result.use = unresolved("missing_course", rule.ref, "", 2, source);
        return result;
    }
    return expand_course_requirement(rule.ref, 0, 2, -1, "", source, true, true);
}

Frag Compiler::compile_module_reference(const Rule &rule, const std::string &module_id,
                                        const Path &source)
{
    std::string offending = unexpected_field(rule, {"referenced_group_id"});
    if (!offending.empty())
        return malformed(rule, module_id,
                         std::string(rule_type_name(rule.type)) + " carries unexpected "
                             + offending,
                         source);
    if (!rule.children.empty())
        return malformed(rule, module_id, "ModuleRule forbids child rules", source);
    if (rule.ref.empty())
        return malformed(rule, module_id,
                         "ModuleRule requires a nonblank referenced module ID", source);
    return expand_module_requirement(rule.ref, 2, source);
}

Frag Compiler::compile_unrestricted(const Rule &rule, const std::string &module_id,
                                    const Path &source)
{
    std::string offending = unexpected_field(rule, {});
    if (!offending.empty())
        return malformed(rule, module_id,
                         std::string(rule_type_name(rule.type)) + " carries unexpected "
                             + offending,
                         source);
    if (!rule.children.empty())
        return malformed(rule, module_id,
                         std::string(rule_type_name(rule.type)) + " forbids child rules", source);
    pending.push_back(ignored("free_choice", 2, {},
                              std::string(rule_type_name(rule.type)) + " ignored in calculation",
                              module_id));
    return {};
}

Frag Compiler::expand_module_requirement(const std::string &module_id, int official_kind,
                                         const Path &source)
{
    size_t offset = pending.size();
    for (const std::string &ancestor : ancestors_modules) {
        if (ancestor != module_id) continue;
        auto filtered = cycle_ancestors("module", module_id, ancestors_courses, ancestors_modules);
        std::vector<std::string> chain = filtered.second;
        chain.push_back(module_id);
        std::string detail = "module cycle: " + join_path(chain);
        int diagnostic = ignored("module_cycle", official_kind, {module_id}, detail, module_id);
        Frag result;
        result.use = unresolved("module_cycle", module_id, detail, official_kind, source,
                                {diagnostic});
        return result;
    }
    const ModuleFact *fact = module(module_id);
    if (fact == nullptr) {
        Frag result;
        result.use = unresolved("missing_module", module_id, "", official_kind, source);
        return result;
    }
    bool fallback = false;
    const Version *version = nullptr;
    std::string reason;
    if (!select_version(*fact, &version, fallback, reason)) {
        Frag result;
        result.use = unresolved(reason, module_id, "", official_kind, source);
        return result;
    }
    if (fallback) {
        pending.push_back(ignored("module_version_fallback", official_kind, {module_id},
                                  "requested year " + std::to_string(year_) + "; selected "
                                      + version->sisu,
                                  module_id));
    }
    ModuleSummaryRec summary;
    summary.group = module_id;
    summary.sisu = version->sisu;
    const char *module_type = module_type_name(version->module_type);
    if (module_type == nullptr) {
        failed = true;
        set_error("module version has an unsupported module type: "
                  + std::to_string(version->module_type));
        return {};
    }
    summary.module_type = module_type;
    summary.code = version->code;
    summary.name_fi = version->name_fi;
    summary.name_en = version->name_en;
    summary.has_code = version->has_code;
    summary.has_name_fi = version->has_name_fi;
    summary.has_name_en = version->has_name_en;
    module_summaries_[module_id] = summary;
    Path module_source{text_part("module"), text_part(module_id), text_part(version->sisu)};
    Path work_path{text_part(version->sisu)};
    Frag compiled;
    if (!version->has_rule) {
        pending.push_back(ignored("unexpandable_content", official_kind, {module_id},
                                  "module version " + version->sisu
                                      + " has no stored rule tree",
                                  module_id));
    } else {
        auto ancestors = cycle_ancestors("module", module_id, ancestors_courses, ancestors_modules);
        std::string owner = ancestors_courses.empty() ? std::string() : ancestors_courses.back();
        std::string key = "M|" + module_id + "|" + version->sisu + "|" + owner + "|";
        for (const std::string &value : ancestors.first) key += "c" + value + ";";
        key += "|";
        for (const std::string &value : ancestors.second) key += "m" + value + ";";
        auto cached = module_memo_.find(key);
        if (cached != module_memo_.end()) {
            replay(cached->second);
            compiled = cached->second;
        } else {
            size_t body_offset = pending.size();
            std::vector<std::string> saved = ancestors_modules;
            ancestors_modules.push_back(module_id);
            compiled = compile_rule(version->rule, module_id, version->sisu, module_source,
                                    work_path);
            ancestors_modules = saved;
            module_memo_[key] = finish_frag(body_offset, compiled.use);
        }
    }
    if (compiled.empty()) {
        bool credited = version->target_min >= 0
            && (!version->has_rule || content_unexpandable(version->rule));
        if (!credited) return {};
        Node node;
        node.kind = N_OPAQUE;
        node.prov.origin = 0;
        node.prov.official_kind = 2;
        node.module_rule = true;
        node.manual_min = version->target_min;
        node.credits_min = version->target_min;
        node.credits_max = version->target_max;
        node.manual_min_text = version->target_min_text;
        node.credits_min_text = version->target_min_text;
        node.credits_max_text = version->target_max_text;
        node.work_payload = path_payload(module_id, work_path);
        compiled.use = add(std::move(node), module_source);
    }
    std::vector<std::string> members = member_group_ids(compiled.use);
    std::vector<int> diagnostics = take_pending(offset);
    module_summaries_[module_id] = summary;
    Node node;
    node.kind = N_MODULE_BLOCK;
    node.children = {compiled.use};
    node.module = module_id;
    node.credits_min = version->target_min;
    node.credits_max = version->target_max;
    node.manual_min = version->target_min;
    node.credits_min_text = version->target_min_text;
    node.credits_max_text = version->target_max_text;
    node.manual_min_text = version->target_min_text;
    node.prov.origin = 0;
    node.prov.official_kind = official_kind;
    node.use_members = std::move(members);
    node.use_diagnostics = std::move(diagnostics);
    Frag result;
    result.use = add(std::move(node), source);
    return result;
}

Frag Compiler::expand_course_requirement(const std::string &group, int origin, int official_kind,
                                         int inferred_category, const std::string &inference,
                                         const Path &source, bool allow_substitutions,
                                         bool allow_equivalences)
{
    size_t offset = pending.size();
    const CourseFact *fact = course(group);
    if (fact == nullptr) {
        failed = true;
        set_error("expanded course is not canonical: " + group);
        return {};
    }
    Prov prov;
    prov.origin = origin;
    prov.official_kind = official_kind;
    prov.inferred_category = inferred_category;
    prov.inference = inference;
    if (!fact->active) {
        if (active_only && retained.count(group) == 0) return {};
        Frag result;
        result.use = leaf_course(group, false, prov, source, take_pending(offset));
        return result;
    }
    for (const std::string &ancestor : ancestors_courses) {
        if (ancestor != group) continue;
        int fact_id = drawing ? intern_fact(prov) : -1;
        int diagnostic = intern_diagnostic("course_cycle", fact_id, {group}, "", "");
        std::vector<int> diagnostics = take_pending(offset);
        diagnostics.push_back(diagnostic);
        Frag result;
        result.use = leaf_course(group, true, prov, source, diagnostics);
        return result;
    }
    if (include_inferred && allow_equivalences && has_ancestor_equivalent(group)) return {};
    if (!fact->has_rep) {
        failed = true;
        set_error("represented course has no selected representative: " + group);
        return {};
    }
    Path local_key{text_part(group), text_part(fact->rep.sisu), text_part("body")};
    Frag child;
    ancestors_courses.push_back(group);
    if (!direct_only) child = compile_course_requirements(*fact);
    std::vector<Frag> substitutions;
    if (allow_substitutions && !fact->rep.substitutions.empty())
        substitutions = compile_substitution_branches(*fact, extend(source, "substitutions"));
    std::vector<Frag> equivalences;
    if (include_inferred && allow_equivalences)
        equivalences = compile_equivalence_branches(group, official_kind, inferred_category,
                                                    extend(source, "equivalences"));
    ancestors_courses.pop_back();
    Frag head;
    head.use = leaf_course(group, false, prov, local_key, take_pending(offset));
    std::vector<int> branches;
    int branch = head.use;
    if (!child.empty()) {
        Node node;
        node.kind = N_EXPANDED;
        node.children = {head.use, child.use};
        node.prov.origin = 2;
        branch = add(std::move(node), local_key);
    }
    branches.push_back(branch);
    for (const Frag &value : substitutions)
        if (!value.empty()) branches.push_back(value.use);
    for (const Frag &value : equivalences)
        if (!value.empty()) branches.push_back(value.use);
    Frag result;
    if (branches.size() == 1) {
        result.use = branch;
        return result;
    }
    Node node;
    node.kind = N_ALTERNATIVES;
    node.children = std::move(branches);
    node.prov.origin = 2;
    result.use = add(std::move(node), local_key);
    return result;
}

bool Compiler::has_ancestor_equivalent(const std::string &group) const
{
    for (std::string_view candidate : equivalence_candidates(group))
        for (const std::string &ancestor : ancestors_courses)
            if (ancestor == candidate) return true;
    return false;
}

std::vector<std::string_view> Compiler::equivalence_candidates(
    const std::string &group) const
{
    std::vector<std::string_view> result;
    auto found = bundle_.equivalence.find(group);
    if (found == bundle_.equivalence.end()) return result;
    for (const EquivGroup &equiv : found->second)
        for (const std::string &member : equiv.members)
            if (member != group) result.push_back(member);
    return result;
}

std::vector<Frag> Compiler::compile_equivalence_branches(const std::string &group,
                                                        int official_kind, int inferred_category,
                                                        const Path &source)
{
    int derived = (official_kind == 1 || inferred_category == 1) ? 1 : 0;
    std::vector<Frag> branches;
    auto groups = bundle_.equivalence.find(group);
    if (groups == bundle_.equivalence.end()) return branches;
    for (const EquivGroup &equiv : groups->second) {
        for (const std::string &candidate : equiv.members) {
            if (candidate == group) continue;
            Path branch_source = extend(extend(source, equiv.id), candidate);
            Frag expanded = expand_course_requirement(candidate, 1, -1, derived, equiv.inference,
                                                      branch_source, false, false);
            if (!expanded.empty()) branches.push_back(std::move(expanded));
        }
    }
    return branches;
}

std::vector<Frag> Compiler::compile_substitution_branches(const CourseFact &fact, const Path &source)
{
    std::vector<Frag> branches;
    std::vector<SubOption> options = fact.rep.substitutions;
    std::sort(options.begin(), options.end(),
              [](const SubOption &left, const SubOption &right) { return left.index < right.index; });
    std::unordered_set<int32_t> seen_options;
    for (const SubOption &option : options) {
        if (!seen_options.insert(option.index).second) {
            failed = true;
            set_error("duplicate substitution option indices");
            return branches;
        }
        std::vector<SubMember> members = option.members;
        std::sort(members.begin(), members.end(), [](const SubMember &left, const SubMember &right) {
            return left.index < right.index;
        });
        std::unordered_set<int32_t> seen_members;
        for (const SubMember &member : members) {
            if (!seen_members.insert(member.index).second) {
                failed = true;
                set_error("duplicate substitution member indices");
                return branches;
            }
        }
        if (members.empty()) {
            pending.push_back(ignored("empty_option", 3, {},
                                      "substitution option " + std::to_string(option.index)
                                          + " is empty",
                                      ""));
            continue;
        }
        std::vector<std::string> missing;
        for (const SubMember &member : members)
            if (course(member.group) == nullptr) missing.push_back(member.group);
        if (!missing.empty()) {
            std::vector<std::string> references;
            for (const SubMember &member : members) references.push_back(member.group);
            std::string detail = "substitution option " + std::to_string(option.index)
                + " dropped: missing " + join_list(missing);
            pending.push_back(ignored("missing_substitution_course", 3, references, detail, ""));
            continue;
        }
        Path option_path = extend(source, option.index);
        std::vector<int> compiled;
        for (const SubMember &member : members) {
            Path member_path = extend(option_path, member.index);
            Frag child = compile_substitution_member(member, member_path);
            if (!child.empty()) compiled.push_back(child.use);
        }
        if (compiled.empty()) continue;
        if (compiled.size() == 1) {
            Frag item;
            item.use = compiled[0];
            branches.push_back(item);
            continue;
        }
        Node node;
        node.kind = N_AND;
        node.children = std::move(compiled);
        node.prov.origin = 0;
        node.prov.official_kind = 3;
        Frag item;
        item.use = add(std::move(node), option_path);
        branches.push_back(item);
    }
    return branches;
}

Frag Compiler::compile_substitution_member(const SubMember &member, const Path &source)
{
    if (!ancestors_courses.empty() && member.group == ancestors_courses.back()) return {};
    const CourseFact *fact = course(member.group);
    if (fact == nullptr || !fact->has_rep) {
        Frag result;
        result.use = unresolved("missing_course", member.group, "", 3, source);
        return result;
    }
    return expand_course_requirement(member.group, 0, 3, -1, "", source, false, true);
}

const InferredFact *Compiler::read_inferred(const CourseFact &fact)
{
    auto found = bundle_.inferred.find(fact.id);
    if (found == bundle_.inferred.end() || !found->second.current) return nullptr;
    const InferredFact &inferred = found->second.fact;
    CoverageRecord record;
    record.target = fact.id;
    record.state = inferred.coverage_state;
    record.eligible = inferred.eligible;
    record.processed = inferred.processed;
    record.accepted = inferred.accepted;
    coverage_[fact.id] = record;
    if (inferred.expression.kind == E_NONE) return nullptr;
    return &inferred;
}

bool Compiler::category_homogeneous(const Expr &expression, int category) const
{
    if (expression.category != -1 && expression.category != category) return false;
    for (const Expr &child : expression.children)
        if (!category_homogeneous(child, category)) return false;
    return true;
}

void Compiler::inferred_option_roots(const Expr &expression, std::vector<Expr> *required,
                                     std::vector<Expr> *recommended)
{
    int category = expression.category;
    if (category < 0) {
        failed = true;
        set_error("inferred option root requires an occurrence category");
        return;
    }
    auto append = [&](const Expr &value) {
        if (category == 0) required->push_back(value);
        else recommended->push_back(value);
    };
    if (expression.kind == E_COURSE) {
        if (!category_homogeneous(expression, category)) {
            failed = true;
            set_error("inferred option branch mixes required and recommended occurrences");
            return;
        }
        append(expression);
        return;
    }
    if (expression.kind == E_OR) {
        for (const Expr &child : expression.children) {
            if (child.category != category) {
                failed = true;
                set_error("inferred option OR mixes categories");
                return;
            }
        }
        for (const Expr &child : expression.children) {
            if (!category_homogeneous(child, category)) {
                failed = true;
                set_error("inferred option branch mixes required and recommended occurrences");
                return;
            }
            append(child);
        }
        return;
    }
    if (expression.kind == E_AND) {
        bool all_same = true;
        for (const Expr &child : expression.children)
            if (child.category != category) all_same = false;
        if (all_same) {
            if (!category_homogeneous(expression, category)) {
                failed = true;
                set_error("inferred option branch mixes required and recommended occurrences");
                return;
            }
            append(expression);
            return;
        }
        bool root_present = false;
        for (const Expr &child : expression.children)
            if (child.category == category) root_present = true;
        if (!root_present) {
            failed = true;
            set_error("inferred option AND does not retain its root category");
            return;
        }
        std::vector<Expr> required_children;
        std::vector<Expr> recommended_children;
        for (const Expr &child : expression.children) {
            if (child.category == 0) required_children.push_back(child);
            else if (child.category == 1) recommended_children.push_back(child);
            else {
                failed = true;
                set_error("inferred option AND mixes an uncategorised child");
                return;
            }
        }
        auto partition = [&](std::vector<Expr> &children, int child_category,
                             std::vector<Expr> *out) {
            if (children.empty()) return;
            if (children.size() == 1) {
                const Expr &child = children[0];
                if (!category_homogeneous(child, child_category)) {
                    failed = true;
                    set_error("inferred option branch mixes required and recommended occurrences");
                    return;
                }
                if (child.kind == E_OR) {
                    for (const Expr &item : child.children) out->push_back(item);
                } else {
                    out->push_back(child);
                }
                return;
            }
            for (const Expr &child : children) {
                if (child.kind == E_OR) {
                    failed = true;
                    set_error("inferred category mixes an OR child with another same-category child");
                    return;
                }
                if (!category_homogeneous(child, child_category)) {
                    failed = true;
                    set_error("inferred option branch mixes required and recommended occurrences");
                    return;
                }
            }
            Expr combined;
            combined.kind = E_AND;
            combined.origin = 2;
            combined.category = -1;
            combined.children = children;
            out->push_back(std::move(combined));
        };
        std::vector<Expr> required_options;
        std::vector<Expr> recommended_options;
        partition(required_children, 0, &required_options);
        partition(recommended_children, 1, &recommended_options);
        for (const Expr &value : required_options) required->push_back(value);
        for (const Expr &value : recommended_options) recommended->push_back(value);
        return;
    }
    failed = true;
    set_error("inferred sets support only course/and/or roots");
}

std::vector<Frag> Compiler::expand_inferred_options(const std::vector<Expr> &roots,
                                                    const Path &source)
{
    std::vector<Frag> result;
    for (size_t index = 0; index < roots.size(); ++index) {
        Frag expanded = expand_inferred_expression(roots[index], extend(source, (int64_t) index));
        if (!expanded.empty()) result.push_back(std::move(expanded));
    }
    return result;
}

Frag Compiler::expand_inferred_expression(const Expr &expression, const Path &source)
{
    if (expression.category == 1 && !include_recommended) return {};
    if (expression.kind == E_COURSE) {
        if (!ancestors_courses.empty() && expression.course == ancestors_courses.back()) return {};
        return expand_course_requirement(expression.course, expression.origin,
                                         expression.official_kind, expression.category,
                                         expression.inference, source, true, true);
    }
    std::vector<int> children;
    for (size_t index = 0; index < expression.children.size(); ++index) {
        Frag child = expand_inferred_expression(expression.children[index],
                                                extend(source, (int64_t) index));
        if (!child.empty()) children.push_back(child.use);
    }
    Frag result;
    if (children.empty()) return result;
    if (children.size() == 1) {
        result.use = children[0];
        return result;
    }
    Node node;
    node.kind = expression.kind == E_OR ? N_OR : N_AND;
    node.children = std::move(children);
    node.prov.origin = expression.origin;
    node.prov.official_kind = expression.official_kind;
    node.prov.inferred_category = expression.category;
    node.prov.inference = expression.inference;
    result.use = add(std::move(node), source);
    return result;
}

Frag Compiler::compile_course_requirements(const CourseFact &fact)
{
    Frag empty;
    if (!fact.active) return empty;
    std::string owner = ancestors_courses.empty() ? std::string() : ancestors_courses.back();
    auto ancestors = cycle_ancestors("course", fact.id, ancestors_courses, ancestors_modules);
    std::string key = "C|" + fact.id + "|" + (fact.has_rep ? fact.rep.sisu : std::string()) + "|"
        + owner + "|";
    for (const std::string &value : ancestors.first) key += "c" + value + ";";
    key += "|";
    for (const std::string &value : ancestors.second) key += "m" + value + ";";
    auto cached = course_memo_.find(key);
    if (cached != course_memo_.end()) {
        replay(cached->second);
        return cached->second;
    }
    size_t offset = pending.size();
    Path body{text_part(fact.id), text_part(fact.rep.sisu), text_part("body")};
    Frag required;
    Frag recommended;
    compile_category_pools(fact, body, false, &required, &recommended);
    std::vector<int> pools;
    if (!required.empty()) pools.push_back(required.use);
    if (!recommended.empty()) pools.push_back(recommended.use);
    Frag result;
    if (pools.size() == 1) {
        result.use = pools[0];
    } else if (pools.size() > 1) {
        Node node;
        node.kind = N_AND;
        node.children = std::move(pools);
        node.prov.origin = 2;
        result.use = add(std::move(node), extend(body, "course_pools"));
    }
    Frag fragment = finish_frag(offset, result.use);
    course_memo_[key] = fragment;
    return fragment;
}

std::vector<Compiler::CompiledOption> Compiler::compile_official_options(
    const CourseFact &fact, int requirement_kind, const Path &source)
{
    std::vector<CompiledOption> compiled_options;
    std::vector<Option> options;
    for (const Option &option : fact.rep.options)
        if ((option.recommended ? 1 : 0) == requirement_kind) options.push_back(option);
    if (options.empty()) return compiled_options;
    std::sort(options.begin(), options.end(),
              [](const Option &left, const Option &right) { return left.index < right.index; });
    std::unordered_set<int32_t> seen_options;
    for (const Option &option : options) {
        if (!seen_options.insert(option.index).second) {
            failed = true;
            set_error("duplicate official option indices");
            return compiled_options;
        }
    }
    int official_kind = requirement_kind;
    for (const Option &option : options) {
        std::vector<Member> members = option.members;
        std::sort(members.begin(), members.end(), [](const Member &left, const Member &right) {
            return left.index < right.index;
        });
        std::unordered_set<int32_t> seen_members;
        for (const Member &member : members) {
            if (!seen_members.insert(member.index).second) {
                failed = true;
                set_error("duplicate prerequisite member indices");
                return compiled_options;
            }
        }
        if (members.empty()) {
            pending.push_back(ignored(
                "empty_option", official_kind, {},
                std::string(requirement_kind == 0 ? "compulsory" : "recommended")
                    + " option " + std::to_string(option.index) + " is empty",
                ""));
            continue;
        }
        Path option_path = extend(source, requirement_kind == 0 ? "compulsory" : "recommended");
        option_path = extend(option_path, option.index);
        std::vector<int> parent_pending = std::move(pending);
        pending.clear();
        auto parent_modules = std::move(module_summaries_);
        module_summaries_.clear();
        auto parent_coverage = std::move(coverage_);
        coverage_.clear();
        std::vector<int> compiled;
        for (const Member &member : members) {
            Path member_path = extend(option_path, member.index);
            Frag child = compile_prerequisite_member(member, official_kind, member_path);
            if (!child.empty()) compiled.push_back(child.use);
        }
        std::vector<int> branch_pending = std::move(pending);
        pending = std::move(parent_pending);
        auto branch_modules = std::move(module_summaries_);
        module_summaries_ = std::move(parent_modules);
        auto branch_coverage = std::move(coverage_);
        coverage_ = std::move(parent_coverage);
        if (compiled.empty()) {
            for (int diagnostic : branch_pending)
                if (ignored_diagnostic_kind(compilation_.diagnostics[diagnostic].kind))
                    pending.push_back(diagnostic);
            for (const auto &[group, summary] : branch_modules) module_summaries_[group] = summary;
            continue;
        }
        for (const auto &[target, record] : branch_coverage) coverage_.emplace(target, record);
        for (const auto &[group, summary] : branch_modules) module_summaries_[group] = summary;
        pending.insert(pending.end(), branch_pending.begin(), branch_pending.end());
        int use;
        if (compiled.size() == 1) {
            use = compiled[0];
        } else {
            Node node;
            node.kind = N_AND;
            node.children = compiled;
            node.prov.origin = 0;
            node.prov.official_kind = official_kind;
            use = add(std::move(node), option_path);
        }
        CompiledOption entry;
        entry.index = option.index;
        entry.frag.use = use;
        for (const Member &member : members) entry.references.push_back(member.ref);
        compiled_options.push_back(std::move(entry));
    }
    return compiled_options;
}

Frag Compiler::finish_official_options(const std::vector<CompiledOption> &options, int official_kind,
                                       bool has_inferred, const Path &source)
{
    std::vector<const CompiledOption *> missing;
    std::vector<const CompiledOption *> usable;
    for (const CompiledOption &option : options) {
        if (contains_missing_module(option.frag.use)) missing.push_back(&option);
        else usable.push_back(&option);
    }
    std::vector<const CompiledOption *> surviving;
    if (!missing.empty() && (!usable.empty() || has_inferred)) {
        for (const CompiledOption *option : missing) {
            pending.push_back(ignored(
                "missing_module_alternative", official_kind, option->references,
                "option " + std::to_string(option->index)
                    + " dropped: missing module; another alternative is available",
                ""));
        }
        surviving = usable;
    } else {
        for (const CompiledOption &option : options) surviving.push_back(&option);
    }
    Frag result;
    if (surviving.empty()) return result;
    if (surviving.size() == 1) {
        result.use = surviving[0]->frag.use;
        return result;
    }
    Node node;
    node.kind = N_OR;
    for (const CompiledOption *option : surviving) node.children.push_back(option->frag.use);
    node.prov.origin = 0;
    node.prov.official_kind = official_kind;
    Path path = extend(source, official_kind == 0 ? "compulsory" : "recommended");
    path = extend(path, "options");
    result.use = add(std::move(node), path);
    return result;
}

Frag Compiler::pool_category(const Frag &official, const std::vector<Frag> &inferred,
                             int official_kind, const Path &source)
{
    if (inferred.empty()) return official;
    std::vector<int> branches;
    if (!official.empty()) {
        const Node &piece = compilation_.nodes[official.use];
        if (piece.kind == N_OR && piece.prov.origin == 0
            && piece.prov.official_kind == official_kind)
            branches = piece.children;
        else
            branches.push_back(official.use);
    }
    for (const Frag &value : inferred)
        if (!value.empty()) branches.push_back(value.use);
    Frag result;
    if (branches.size() == 1) {
        result.use = branches[0];
        return result;
    }
    Node node;
    node.kind = N_OR;
    node.children = std::move(branches);
    node.prov.origin = 2;
    Path path = extend(source, official_kind == 0 ? "compulsory" : "recommended");
    path = extend(path, "pool");
    result.use = add(std::move(node), path);
    return result;
}

void Compiler::compile_category_pools(const CourseFact &fact, const Path &source,
                                      bool treat_inactive_as_active, Frag *required,
                                      Frag *recommended)
{
    if (!fact.active && !treat_inactive_as_active) return;
    std::vector<CompiledOption> official_required =
        compile_official_options(fact, 0, source);
    std::vector<CompiledOption> official_recommended;
    if (include_recommended) official_recommended = compile_official_options(fact, 1, source);
    std::vector<Frag> inferred_required;
    std::vector<Frag> inferred_recommended;
    if (include_inferred && fact.active) {
        const InferredFact *inferred = read_inferred(fact);
        if (inferred != nullptr) {
            Path path = extend(source, "inferred");
            path = extend(path, inferred->set_id);
            std::vector<Expr> required_roots;
            std::vector<Expr> recommended_roots;
            inferred_option_roots(inferred->expression, &required_roots, &recommended_roots);
            inferred_required = expand_inferred_options(required_roots, path);
            if (include_recommended)
                inferred_recommended = expand_inferred_options(recommended_roots, path);
        }
    }
    Frag required_root = finish_official_options(official_required, 0,
                                                 !inferred_required.empty(), source);
    Frag recommended_root = finish_official_options(official_recommended, 1,
                                                    !inferred_recommended.empty(), source);
    *required = pool_category(required_root, inferred_required, 0, source);
    *recommended = pool_category(recommended_root, inferred_recommended, 1, source);
}

Frag Compiler::compile_prerequisite_member(const Member &member, int official_kind,
                                           const Path &source)
{
    if (!member.module) {
        if (!ancestors_courses.empty() && member.ref == ancestors_courses.back()) return {};
        const CourseFact *fact = course(member.ref);
        if (fact == nullptr || !fact->has_rep) {
            Frag result;
            result.use = unresolved("missing_course", member.ref, "", official_kind, source);
            return result;
        }
        return expand_course_requirement(member.ref, 0, official_kind, -1, "", source, true, true);
    }
    if (module(member.ref) == nullptr) {
        Frag result;
        result.use = unresolved("missing_module", member.ref, "", official_kind, source);
        return result;
    }
    return expand_module_requirement(member.ref, official_kind, source);
}

void collect_rule_references(const Rule &rule,
                             std::unordered_set<std::string_view> &courses,
                             std::unordered_set<std::string_view> &modules)
{
    std::vector<const Rule *> stack{&rule};
    while (!stack.empty()) {
        const Rule *node = stack.back();
        stack.pop_back();
        if (!node->ref.empty()) {
            if (node->type == R_COURSE_UNIT) courses.insert(node->ref);
            else if (node->type == R_MODULE) modules.insert(node->ref);
        }
        for (const Rule &child : node->children) stack.push_back(&child);
    }
}

void Compiler::index_expression(const Expr &expression, const std::string &owner,
                                std::vector<Visit> *successors)
{
    if (expression.category == 1 && !include_recommended) return;
    if (expression.kind == E_COURSE) {
        if (expression.course != owner && course(expression.course) != nullptr)
            successors->push_back(Visit{false, expression.course, true, true});
        return;
    }
    for (const Expr &child : expression.children) index_expression(child, owner, successors);
}

void Compiler::index_course_sources(std::string_view group_view, bool allow_substitutions,
                                    bool allow_equivalences, std::vector<Visit> *successors,
                                    std::vector<std::string_view> *equivalents)
{
    const std::string group(group_view);
    const CourseFact *fact = course(group);
    if (fact == nullptr || !fact->has_rep) return;
    bool is_root = group == root_;
    if (!fact->active && !is_root) return;
    if (is_root || !direct_only) {
        for (const Option &option : fact->rep.options) {
            if (option.recommended && !include_recommended) continue;
            for (const Member &member : option.members) {
                if (member.ref == group) continue;
                if (!member.module) {
                    if (course(member.ref) != nullptr)
                        successors->push_back(Visit{false, member.ref, true, true});
                } else if (module(member.ref) != nullptr) {
                    successors->push_back(Visit{true, member.ref, true, true});
                }
            }
        }
        if (include_inferred && fact->active) {
            const InferredFact *inferred = read_inferred(*fact);
            if (inferred != nullptr) index_expression(inferred->expression, group, successors);
        }
    }
    if (!is_root && allow_substitutions) {
        for (const SubOption &option : fact->rep.substitutions) {
            if (option.members.empty()) continue;
            bool missing = false;
            for (const SubMember &member : option.members)
                if (course(member.group) == nullptr) missing = true;
            if (missing) continue;
            for (const SubMember &member : option.members)
                if (member.group != group)
                    successors->push_back(Visit{false, member.group, false, true});
        }
    }
    if (!is_root && include_inferred && allow_equivalences) {
        for (std::string_view candidate : equivalence_candidates(group)) {
            if (candidate == root_ || course(std::string(candidate)) == nullptr) continue;
            equivalents->push_back(candidate);
            successors->push_back(Visit{false, candidate, false, false});
        }
    }
}

void Compiler::index_module_sources(std::string_view group_view, std::vector<Visit> *successors)
{
    const std::string group(group_view);
    const ModuleFact *fact = module(group);
    if (fact == nullptr) return;
    bool fallback = false;
    const Version *version = nullptr;
    std::string reason;
    if (!select_version(*fact, &version, fallback, reason)) return;
    if (!version->has_rule) return;
    std::unordered_set<std::string_view> courses;
    std::unordered_set<std::string_view> modules;
    collect_rule_references(version->rule, courses, modules);
    for (std::string_view course_id : courses)
        if (course(std::string(course_id)) != nullptr)
            successors->push_back(Visit{false, course_id, true, true});
    for (std::string_view module_id : modules)
        if (module(std::string(module_id)) != nullptr)
            successors->push_back(Visit{true, module_id, true, true});
}

void Compiler::build_source_index()
{
    std::unordered_map<SourceKey, std::unordered_set<SourceKey, SourceKeyHash>, SourceKeyHash> edges;
    std::vector<Visit> stack{Visit{false, root_, false, false}};
    std::unordered_set<VisitKey, VisitKeyHash> visited;
    while (!stack.empty()) {
        Visit visit = stack.back();
        stack.pop_back();
        VisitKey key{visit.module, visit.allow_substitutions, visit.allow_equivalences,
                     visit.group};
        if (!visited.insert(std::move(key)).second) continue;
        SourceKey source{visit.module, visit.group};
        std::vector<Visit> successors;
        std::vector<std::string_view> equivalents;
        if (visit.module) {
            index_module_sources(visit.group, &successors);
        } else {
            index_course_sources(visit.group, visit.allow_substitutions,
                                 visit.allow_equivalences, &successors, &equivalents);
        }
        auto &targets = edges[source];
        for (const Visit &successor : successors) targets.insert(SourceKey{successor.module,
                                                                          successor.group});
        for (std::string_view candidate : equivalents)
            edges[SourceKey{false, candidate}].insert(source);
        for (const Visit &successor : successors) {
            VisitKey child{successor.module, successor.allow_substitutions,
                           successor.allow_equivalences, successor.group};
            if (visited.count(child) == 0) stack.push_back(successor);
        }
    }
    std::vector<SourceKey> nodes;
    nodes.reserve(edges.size());
    for (const auto &[key, _] : edges) nodes.push_back(key);
    std::sort(nodes.begin(), nodes.end(), [](const SourceKey &left, const SourceKey &right) {
        if (left.module != right.module) return !left.module;
        return left.group < right.group;
    });
    /* Tarjan runs on integer positions, so the index, low-link, component and on-stack tables hold
     * no identity strings and the sorted node order is fixed. */
    std::unordered_map<SourceKey, int, SourceKeyHash> position;
    position.reserve(nodes.size());
    for (int value = 0; value < (int) nodes.size(); ++value) position.emplace(nodes[value], value);
    std::vector<std::vector<int>> adjacency(nodes.size());
    for (const auto &[key, targets] : edges) {
        auto found = position.find(key);
        if (found == position.end()) continue;
        std::vector<int> &out = adjacency[found->second];
        out.reserve(targets.size());
        for (const SourceKey &target : targets) {
            auto child = position.find(target);
            if (child != position.end()) out.push_back(child->second);
        }
        std::sort(out.begin(), out.end());
        out.erase(std::unique(out.begin(), out.end()), out.end());
    }
    std::vector<int> index(nodes.size(), -1);
    std::vector<int> low(nodes.size(), 0);
    std::vector<int> component(nodes.size(), -1);
    std::vector<char> on_stack(nodes.size(), 0);
    std::vector<int> component_stack;
    std::vector<std::pair<int, size_t>> work;
    int next_index = 0;
    int next_component = 0;
    for (int start = 0; start < (int) nodes.size(); ++start) {
        if (index[start] >= 0) continue;
        work.clear();
        work.emplace_back(start, 0);
        while (!work.empty()) {
            std::pair<int, size_t> &frame = work.back();
            int node = frame.first;
            if (frame.second == 0) {
                index[node] = next_index;
                low[node] = next_index;
                ++next_index;
                component_stack.push_back(node);
                on_stack[node] = 1;
            }
            if (frame.second < adjacency[node].size()) {
                int child = adjacency[node][frame.second];
                ++frame.second;
                if (index[child] < 0) {
                    work.emplace_back(child, 0);
                } else if (on_stack[child] != 0) {
                    low[node] = std::min(low[node], index[child]);
                }
                continue;
            }
            work.pop_back();
            if (!work.empty())
                low[work.back().first] = std::min(low[work.back().first], low[node]);
            if (low[node] == index[node]) {
                while (true) {
                    int member = component_stack.back();
                    component_stack.pop_back();
                    on_stack[member] = 0;
                    component[member] = next_component;
                    if (member == node) break;
                }
                ++next_component;
            }
        }
    }
    std::unordered_map<SourceKey, int, SourceKeyHash> resolved;
    resolved.reserve(nodes.size());
    for (int value = 0; value < (int) nodes.size(); ++value)
        resolved.emplace(nodes[value], component[value]);
    source_components = std::move(resolved);
}

std::unordered_set<std::string> Compiler::mandatory_expanded_heads(int root_use) const
{
    std::unordered_set<std::string> heads;
    if (root_use < 0) return heads;
    struct Entry {
        int use;
        bool mandatory;
    };
    std::vector<Entry> stack{{root_use, true}};
    std::unordered_set<std::string> seen;
    while (!stack.empty()) {
        Entry entry = stack.back();
        stack.pop_back();
        std::string marker = std::to_string(entry.use) + (entry.mandatory ? ":1" : ":0");
        if (!seen.insert(marker).second) continue;
        const Node &node = compilation_.nodes[entry.use];
        if (node.kind == N_MODULE_BLOCK) continue;
        const std::vector<int> &children = compilation_.nodes[entry.use].children;
        if (node.kind == N_EXPANDED && entry.mandatory && !children.empty()) {
            const Node &head = compilation_.nodes[children[0]];
            if (!head.course.empty()) heads.insert(head.course);
        }
        bool child_mandatory = entry.mandatory && is_rule_inherit_kind(node.kind);
        for (int child : children) stack.push_back(Entry{child, child_mandatory});
    }
    return heads;
}

int Compiler::prune_expansions(int use, bool mandatory,
                               const std::unordered_set<std::string> &heads,
                               std::unordered_map<std::string, int> &memo)
{
    std::string key = std::to_string(use) + (mandatory ? ":1" : ":0");
    auto found = memo.find(key);
    if (found != memo.end()) return found->second;
    int kind = compilation_.nodes[use].kind;
    if (kind == N_MODULE_BLOCK) {
        memo.emplace(key, use);
        return use;
    }
    std::vector<int> children = compilation_.nodes[use].children;
    bool inherit = is_rule_inherit_kind(kind);
    if (kind == N_EXPANDED && children.size() == 2) {
        int head = children[0];
        const std::string course_id = compilation_.nodes[head].course;
        if (!course_id.empty() && heads.count(course_id) != 0 && !mandatory) {
            memo.emplace(key, head);
            return head;
        }
        int descendants = prune_expansions(children[1], inherit && mandatory, heads, memo);
        if (descendants == children[1]) {
            memo.emplace(key, use);
            return use;
        }
        int result = reintern_use(use, {head, descendants});
        memo.emplace(key, result);
        return result;
    }
    std::vector<int> pruned;
    pruned.reserve(children.size());
    for (int child : children)
        pruned.push_back(prune_expansions(child, inherit && mandatory, heads, memo));
    if (pruned == children) {
        memo.emplace(key, use);
        return use;
    }
    int result = reintern_use(use, pruned);
    memo.emplace(key, result);
    return result;
}

Frag Compiler::build()
{
    Frag empty;
    const CourseFact *fact = course(root_);
    if (fact == nullptr || !fact->has_rep) {
        failed = true;
        set_error("unknown canonical target course or missing representative: " + root_);
        return empty;
    }
    compilation_.root = root_;
    compilation_.year = year_;
    compilation_.active_only = active_only;
    compilation_.include_inferred = include_inferred;
    compilation_.include_recommended = include_recommended;
    build_source_index();
    Path root_source{text_part(root_), text_part(fact->rep.sisu), text_part("body")};
    Frag required;
    Frag recommended;
    compile_category_pools(*fact, root_source, true, &required, &recommended);
    std::vector<int> pools;
    if (!required.empty()) pools.push_back(required.use);
    if (!recommended.empty()) pools.push_back(recommended.use);
    int probe = -1;
    if (pools.size() == 1) {
        probe = pools[0];
    } else if (pools.size() > 1) {
        Node node;
        node.kind = N_AND;
        node.children = pools;
        node.prov.origin = 2;
        probe = add(std::move(node), extend(root_source, "probe"));
    }
    std::unordered_set<std::string> heads = mandatory_expanded_heads(probe);
    std::unordered_map<std::string, int> memo;
    if (!required.empty()) required.use = prune_expansions(required.use, true, heads, memo);
    if (!recommended.empty())
        recommended.use = prune_expansions(recommended.use, true, heads, memo);
    pools.clear();
    if (!required.empty()) pools.push_back(required.use);
    if (!recommended.empty()) pools.push_back(recommended.use);
    Frag requirements;
    if (pools.size() == 1) {
        requirements.use = pools[0];
    } else if (pools.size() > 1) {
        Node node;
        node.kind = N_AND;
        node.children = pools;
        node.prov.origin = 2;
        requirements.use = add(std::move(node), extend(root_source, "root_pools"));
    }
    compilation_.requirements = requirements.use;
    compilation_.required = required.use;
    compilation_.recommended = recommended.use;

    std::unordered_set<std::string> represented{root_};
    std::vector<int> reachable;
    std::vector<int> stack;
    if (requirements.use >= 0) stack.push_back(requirements.use);
    std::unordered_set<int> seen;
    while (!stack.empty()) {
        int current = stack.back();
        stack.pop_back();
        if (!seen.insert(current).second) continue;
        reachable.push_back(current);
        for (int child : compilation_.nodes[current].children) stack.push_back(child);
    }
    for (int current : reachable) {
        const Node &node = compilation_.nodes[current];
        if (node.kind == N_COURSE && !node.course.empty()) represented.insert(node.course);
    }
    for (const std::string &group : sorted_unique(std::vector<std::string>(
             represented.begin(), represented.end()))) {
        const CourseFact *summary_fact = course(group);
        if (summary_fact == nullptr || !summary_fact->has_rep) {
            failed = true;
            set_error("represented course has no selected representative: " + group);
            return empty;
        }
        CourseSummaryRec summary;
        summary.group = group;
        summary.name_fi = summary_fact->rep.name_fi;
        summary.name_en = summary_fact->rep.name_en;
        summary.has_name_fi = summary_fact->rep.has_name_fi;
        summary.has_name_en = summary_fact->rep.has_name_en;
        summary.code = summary_fact->rep.code;
        summary.official_url = summary_fact->rep.official_url;
        summary.credits_min = summary_fact->rep.credits_min;
        summary.credits_max = summary_fact->rep.credits_max;
        summary.credits_min_text = summary_fact->rep.credits_min_text;
        summary.credits_max_text = summary_fact->rep.credits_max_text;
        summary.has_credits_max = summary_fact->rep.credits_max >= 0;
        summary.active = summary_fact->active;
        compilation_.summaries[group] = summary;
    }

    if (drawing) {
        std::unordered_set<std::string> reachable_modules;
        std::vector<int> roots;
        for (int value : {requirements.use, required.use, recommended.use})
            if (value >= 0) roots.push_back(value);
        std::vector<int> module_stack = roots;
        std::unordered_set<int> module_seen;
        while (!module_stack.empty()) {
            int current = module_stack.back();
            module_stack.pop_back();
            if (!module_seen.insert(current).second) continue;
            const Node &node = compilation_.nodes[current];
            if (!node.module.empty()) reachable_modules.insert(node.module);
            for (int child : compilation_.nodes[current].children) module_stack.push_back(child);
        }
        std::vector<int> root_diagnostics(pending.begin(), pending.end());
        std::sort(root_diagnostics.begin(), root_diagnostics.end());
        root_diagnostics.erase(std::unique(root_diagnostics.begin(), root_diagnostics.end()),
                               root_diagnostics.end());
        for (int diagnostic : root_diagnostics) {
            const std::string &module_id = compilation_.diagnostics[diagnostic].module;
            if (!module_id.empty()) reachable_modules.insert(module_id);
        }
        compilation_.root_diagnostics = root_diagnostics;
        for (const std::string &group : sorted_unique(std::vector<std::string>(
                 reachable_modules.begin(), reachable_modules.end()))) {
            auto found = module_summaries_.find(group);
            if (found != module_summaries_.end()) compilation_.modules[group] = found->second;
        }
        std::vector<std::string> coverage_targets;
        for (const auto &[group, _] : coverage_)
            if (represented.count(group) != 0 || group == root_)
                coverage_targets.push_back(group);
        std::sort(coverage_targets.begin(), coverage_targets.end());
        for (const std::string &group : coverage_targets)
            compilation_.coverage.push_back(coverage_[group]);
        for (const std::string &group : excluded_inputs)
            if (represented.count(group) != 0) compilation_.excluded_group_ids.push_back(group);
        compilation_.excluded_group_ids = sorted_unique(compilation_.excluded_group_ids);
        compilation_.completed_node_keys = sorted_unique(completed_keys);
        compilation_.excluded_node_keys = sorted_unique(excluded_keys);
    }
    return requirements;
}


void *compile_bundle(const Bundle &bundle, const std::vector<std::string> &targets,
                     const std::vector<std::string> &chosen, bool active_only,
                     bool include_recommended, bool include_inferred, bool direct_only,
                     const std::vector<std::string> &excluded,
                     const std::vector<std::string> &completed,
                     const std::vector<std::string> &excluded_keys, int projection,
                     bool project)
{
    auto compiled = std::make_unique<Compiled>();
    compiled->ranks = bundle.ranks;
    for (const std::string &target : targets) {
        auto found = bundle.courses.find(target);
        if (found == bundle.courses.end()) {
            set_error("candidate course is absent from the native fact bundle: " + target);
            return nullptr;
        }
        if (!found->second.has_rep) continue;
        Compilation compilation;
        compilation.summary_only = projection == 1;
        Compiler compiler(bundle, compilation, target, found->second.year);
        compiler.drawing = projection == 0;
        compiler.active_only = active_only;
        compiler.include_recommended = direct_only ? true : include_recommended;
        compiler.include_inferred = include_inferred;
        compiler.direct_only = direct_only;
        compiler.retained.insert(chosen.begin(), chosen.end());
        compiler.excluded_inputs = excluded;
        compiler.completed_keys = completed;
        compiler.excluded_keys = excluded_keys;
        compiler.ancestors_courses.push_back(target);
        compiler.build();
        if (compiler.failed) return nullptr;
        if (projection == 0) {
            if (!finalize_identities(compilation)) return nullptr;
            if (project && !project_compilation(compilation)) return nullptr;
        }
        compiled->compilations.push_back(std::move(compilation));
    }
    return compiled.release();
}

}  // namespace tce
