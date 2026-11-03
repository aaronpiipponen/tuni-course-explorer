/* Satisfaction and coverage evaluation over one compiled prerequisite structure.
 *
 * Folds the zero-suppressed course-identity families and reports covered fractions per category.
 * The same evaluator answers the native eligibility and coverage outcomes.
 */

#include "pipeline.h"
#include <cmath>
#include <cstring>
#include <cstdint>
#include <string>
#include <unordered_map>
#include <vector>
#include "records.h"
#include "support.h"

namespace tce {

/* Zero-suppressed families of course-identity sets, folded to covered fractions per category. */
class Family {
public:
    static constexpr int ZERO = 0;
    static constexpr int ONE = 1;

    struct Node {
        int var;
        int low;
        int high;
    };

    int singleton(int var)
    {
        return make(var, ZERO, ONE);
    }

    int get_var(int handle) const { return nodes_[handle - 2].var; }
    int get_low(int handle) const { return nodes_[handle - 2].low; }
    int get_high(int handle) const { return nodes_[handle - 2].high; }

    int make(int var, int low, int high)
    {
        if (high == ZERO) return low;
        std::string key;
        key.resize(12);
        std::memcpy(&key[0], &var, 4);
        std::memcpy(&key[4], &low, 4);
        std::memcpy(&key[8], &high, 4);
        auto found = unique_.find(key);
        if (found != unique_.end()) return found->second;
        int handle = (int) nodes_.size() + 2;
        nodes_.push_back({var, low, high});
        unique_.emplace(std::move(key), handle);
        return handle;
    }

    int top(int first, int second) const
    {
        if (first < 2) return nodes_[second - 2].var;
        if (second < 2) return nodes_[first - 2].var;
        int left = nodes_[first - 2].var;
        int right = nodes_[second - 2].var;
        return left <= right ? left : right;
    }

    void split(int handle, int var, int &low, int &high) const
    {
        if (handle < 2) {
            low = handle;
            high = ZERO;
            return;
        }
        const Node &node = nodes_[handle - 2];
        if (node.var == var) {
            low = node.low;
            high = node.high;
        } else {
            low = handle;
            high = ZERO;
        }
    }

    int union_of(int first, int second)
    {
        if (first == ZERO) return second;
        if (second == ZERO) return first;
        if (first == second) return first;
        uint64_t key = pair_key(first, second);
        auto found = union_memo_.find(key);
        if (found != union_memo_.end()) return found->second;
        int var = top(first, second);
        int first_low, first_high, second_low, second_high;
        split(first, var, first_low, first_high);
        split(second, var, second_low, second_high);
        int result = make(var, union_of(first_low, second_low),
                          union_of(first_high, second_high));
        union_memo_.emplace(key, result);
        return result;
    }

    int join(int first, int second)
    {
        if (first == ZERO || second == ZERO) return ZERO;
        if (first == ONE) return second;
        if (second == ONE) return first;
        uint64_t key = pair_key(first, second);
        auto found = join_memo_.find(key);
        if (found != join_memo_.end()) return found->second;
        int var = top(first, second);
        int first_low, first_high, second_low, second_high;
        split(first, var, first_low, first_high);
        split(second, var, second_low, second_high);
        int high = union_of(union_of(join(first_high, second_low),
                                     join(first_low, second_high)),
                            join(first_high, second_high));
        int result = make(var, join(first_low, second_low), high);
        join_memo_.emplace(key, result);
        return result;
    }

    int filter(int handle, const std::unordered_map<int, int64_t> &weights, int64_t lower,
               bool has_upper, int64_t upper)
    {
        ranges_.clear();
        weight_cache_.clear();
        memo_.clear();
        filter_lower_ = lower;
        filter_upper_ = upper;
        filter_has_upper_ = has_upper;
        filter_weights_ = &weights;
        if (!compute_ranges(handle)) return ZERO;
        return keep(handle, lower, upper, has_upper);
    }

private:
    static uint64_t pair_key(int first, int second)
    {
        uint32_t low = (uint32_t) (first < second ? first : second);
        uint32_t high = (uint32_t) (first < second ? second : first);
        return ((uint64_t) low << 32) | high;
    }

    int64_t weight(int var) const
    {
        auto found = filter_weights_->find(var);
        return found == filter_weights_->end() ? 0 : found->second;
    }

    bool compute_ranges(int handle)
    {
        if (handle == ZERO) {
            ranges_[ZERO] = {false, 0, 0};
            return false;
        }
        if (handle == ONE) {
            ranges_[ONE] = {true, 0, 0};
            return true;
        }
        auto found = ranges_.find(handle);
        if (found != ranges_.end()) return found->second.present;
        const Node &node = nodes_[handle - 2];
        int64_t var_weight = weight(node.var);
        Range low_range, high_range;
        bool low_present = compute_ranges(node.low);
        if (low_present) low_range = ranges_[node.low];
        bool high_present = compute_ranges(node.high);
        if (high_present) {
            high_range = ranges_[node.high];
            high_range.min += var_weight;
            high_range.max += var_weight;
        }
        Range result;
        if (low_present && high_present) {
            result.present = true;
            result.min = std::min(low_range.min, high_range.min);
            result.max = std::max(low_range.max, high_range.max);
        } else if (low_present) {
            result = low_range;
        } else if (high_present) {
            result = high_range;
        }
        ranges_[handle] = result;
        return result.present;
    }

    int keep(int handle, int64_t lower, int64_t upper, bool has_upper)
    {
        if (has_upper && upper < 0) return ZERO;
        if (handle == ZERO) return ZERO;
        if (handle == ONE) return lower > 0 ? ZERO : ONE;
        const Range &range = ranges_[handle];
        if (!range.present) return ZERO;
        if (range.max < lower || (has_upper && range.min > upper)) return ZERO;
        if (range.min >= lower && (!has_upper || range.max <= upper)) return handle;
        FilterKey key{handle, lower, has_upper ? upper : 0, has_upper};
        auto found = memo_.find(key);
        if (found != memo_.end()) return found->second;
        const Node &node = nodes_[handle - 2];
        int64_t var_weight = weight(node.var);
        int64_t next_lower = std::max<int64_t>(lower - var_weight, 0);
        int64_t next_upper = has_upper ? upper - var_weight : 0;
        int result = make(node.var, keep(node.low, lower, upper, has_upper),
                          keep(node.high, next_lower, next_upper, has_upper));
        memo_.emplace(key, result);
        return result;
    }

    struct Range {
        bool present = false;
        int64_t min = 0;
        int64_t max = 0;
    };
    struct FilterKey {
        int handle;
        int64_t lower;
        int64_t upper;
        bool has_upper;
        bool operator==(const FilterKey &other) const
        {
            return handle == other.handle && lower == other.lower && upper == other.upper
                && has_upper == other.has_upper;
        }
    };
    struct FilterKeyHash {
        size_t operator()(const FilterKey &key) const
        {
            size_t value = std::hash<int>()(key.handle);
            value ^= std::hash<int64_t>()(key.lower) + 0x9e3779b9 + (value << 6) + (value >> 2);
            value ^= std::hash<int64_t>()(key.upper) + 0x9e3779b9 + (value << 6) + (value >> 2);
            value ^= std::hash<bool>()(key.has_upper) + 0x9e3779b9 + (value << 6) + (value >> 2);
            return value;
        }
    };

    std::vector<Node> nodes_;
    std::unordered_map<std::string, int> unique_;
    std::unordered_map<uint64_t, int> union_memo_;
    std::unordered_map<uint64_t, int> join_memo_;
    std::unordered_map<int, Range> ranges_;
    std::unordered_map<int, int64_t> weight_cache_;
    std::unordered_map<FilterKey, int, FilterKeyHash> memo_;
    const std::unordered_map<int, int64_t> *filter_weights_ = nullptr;
    int64_t filter_lower_ = 0;
    int64_t filter_upper_ = 0;
    bool filter_has_upper_ = false;
};

struct EvalRes {
    int family = 0;
    bool unresolved = false;
    bool known() const { return family != 0; }
};

class Evaluator {
public:
    Evaluator(const Compilation &compilation, const Compiled &compiled, Family &family,
              const std::unordered_set<std::string> &basis)
        : compilation_(compilation), compiled_(compiled), family_(family), basis_(basis)
    {
        for (const auto &[group, summary] : compilation.summaries) {
            auto rank = compiled.ranks->find(group);
            if (rank != compiled.ranks->end()) weights_[rank->second] = summary.credits_min;
        }
        count_weights_.reserve(weights_.size());
        for (const auto &[rank, credits] : weights_) {
            (void) credits;
            count_weights_[rank] = 1;
        }
    }

    EvalRes evaluate(int node)
    {
        auto found = memo_.find(node);
        if (found != memo_.end()) return found->second;
        EvalRes result = fold(compilation_.nodes[node]);
        memo_.emplace(node, result);
        return result;
    }

    int rank(const std::string &group) const
    {
        auto found = compiled_.ranks->find(group);
        return found == compiled_.ranks->end() ? -1 : found->second;
    }

    bool failed = false;

private:
    EvalRes fold(const Node &node)
    {
        switch (node.kind) {
            case N_COURSE: {
                auto summary = compilation_.summaries.find(node.course);
                if (summary == compilation_.summaries.end()) {
                    failed = true;
                    return {Family::ZERO, false};
                }
                if (basis_.count(node.course) != 0) {
                    int var = rank(node.course);
                    if (var < 0) {
                        failed = true;
                        return {Family::ZERO, false};
                    }
                    return {family_.singleton(var), false};
                }
                if (compilation_.active_only && !summary->second.active)
                    return {Family::ZERO, false};
                return {Family::ZERO, node.cycle};
            }
            case N_MODULE_BLOCK:
            case N_EXPANDED: {
                if (node.kind == N_MODULE_BLOCK) return evaluate(node.children[0]);
                EvalRes head = evaluate(node.children[0]);
                const Node &head_node = compilation_.nodes[node.children[0]];
                if (basis_.count(head_node.course) != 0) return head;
                if (!head.known() && !head.unresolved) return head;
                EvalRes descendants = evaluate(node.children[1]);
                EvalRes projected{descendants.family != Family::ZERO ? Family::ONE : Family::ZERO,
                                  descendants.unresolved};
                EvalRes children[2] = {head, projected};
                return combine_required(children, 2);
            }
            case N_OPAQUE:
                return {node.credits_min == 0 ? Family::ONE : Family::ZERO, false};
            case N_UNRESOLVED:
                return {Family::ZERO, true};
            case N_CREDITS: {
                EvalRes child = evaluate(node.children[0]);
                int64_t lower = node.credits_min < 0 ? 0 : node.credits_min;
                bool has_upper = node.credits_max >= 0;
                int filtered = family_.filter(child.family, weights_, lower, has_upper,
                                              node.credits_max);
                return {filtered, child.unresolved};
            }
            case N_COUNT: {
                EvalRes child = evaluate(node.children[0]);
                int64_t lower = node.count_min < 0 ? 0 : node.count_min;
                bool has_upper = node.count_max >= 0;
                int filtered = family_.filter(child.family, count_weights_, lower, has_upper,
                                              node.count_max);
                return {filtered, child.unresolved};
            }
            default:
                break;
        }
        std::vector<EvalRes> children;
        children.reserve(node.children.size());
        for (int child : node.children) children.push_back(evaluate(child));
        if (node.kind == N_AND) return combine_required(children.data(), children.size());
        if (node.kind == N_OR || node.kind == N_ALTERNATIVES) {
            int family = Family::ZERO;
            bool unresolved = false;
            for (const EvalRes &child : children) {
                family = family_.union_of(family, child.family);
                unresolved = unresolved || child.unresolved;
            }
            return {family, unresolved};
        }
        if (node.kind == N_CARDINALITY) {
            int upper = node.require_max < 0 ? (int) children.size()
                                             : std::min<int>(node.require_max, children.size());
            std::vector<int> rows(upper + 1, Family::ZERO);
            rows[0] = Family::ONE;
            for (const EvalRes &child : children) {
                std::vector<int> next(upper + 1, Family::ZERO);
                for (int count = 0; count <= upper; ++count) {
                    int selected = rows[count];
                    if (count > 0)
                        selected = family_.union_of(selected,
                                                    family_.join(rows[count - 1], child.family));
                    next[count] = selected;
                }
                rows.swap(next);
            }
            int family = Family::ZERO;
            int lower = node.require_min < 0 ? 0 : node.require_min;
            for (int count = lower; count <= upper; ++count)
                family = family_.union_of(family, rows[count]);
            int viable = 0;
            int unresolved_children = 0;
            for (const EvalRes &child : children) {
                if (child.known() || child.unresolved) ++viable;
                if (child.unresolved) ++unresolved_children;
            }
            bool unresolved = unresolved_children > 0
                && std::max(lower, 1) <= std::min(upper, viable);
            return {family, unresolved};
        }
        failed = true;
        return {Family::ZERO, false};
    }

    EvalRes combine_required(const EvalRes *children, size_t count)
    {
        int family = Family::ONE;
        bool all_viable = true;
        bool any_unresolved = false;
        for (size_t index = 0; index < count; ++index) {
            family = family_.join(family, children[index].family);
            if (!(children[index].known() || children[index].unresolved)) all_viable = false;
            any_unresolved = any_unresolved || children[index].unresolved;
        }
        return {family, all_viable && any_unresolved};
    }

    const Compilation &compilation_;
    const Compiled &compiled_;
    Family &family_;
    const std::unordered_set<std::string> &basis_;
    std::unordered_map<int, EvalRes> memo_;
    std::unordered_map<int, int64_t> weights_;
    std::unordered_map<int, int64_t> count_weights_;
};

struct Coverage {
    std::vector<uint32_t> slots;
    int unresolved = 0;

    int denominator() const { return (int) slots.size() + unresolved; }
    int covered() const
    {
        int count = 0;
        for (uint32_t slot : slots)
            if (slot & 1U) ++count;
        return count;
    }
    double fraction() const
    {
        int total = denominator();
        return total == 0 ? 0.0 : (double) covered() / (double) total;
    }
};

Coverage merge_coverage(Coverage left, const Coverage &right)
{
    left.slots.insert(left.slots.end(), right.slots.begin(), right.slots.end());
    std::sort(left.slots.begin(), left.slots.end());
    left.slots.erase(std::unique(left.slots.begin(), left.slots.end()), left.slots.end());
    left.unresolved += right.unresolved;
    return left;
}


class CoverageEvaluator {
public:
    CoverageEvaluator(const Compilation &compilation, Evaluator &evaluator)
        : compilation_(compilation), evaluator_(evaluator)
    {
    }

    Coverage evaluate(int node)
    {
        auto found = memo_.find(node);
        if (found != memo_.end()) return found->second;
        Coverage result = fold(node);
        memo_.emplace(node, result);
        return result;
    }

private:
    Coverage fold(int index)
    {
        const Node &node = compilation_.nodes[index];
        switch (node.kind) {
            case N_COURSE: {
                uint32_t rank = (uint32_t) evaluator_.rank(node.course);
                bool covered = evaluator_.evaluate(index).known();
                Coverage result;
                result.slots.push_back((rank << 1) | (covered ? 1U : 0U));
                return result;
            }
            case N_MODULE_BLOCK:
            case N_CREDITS:
            case N_COUNT:
                return evaluate(node.children[0]);
            case N_OPAQUE:
                return {};
            case N_UNRESOLVED: {
                Coverage result;
                result.unresolved = 1;
                return result;
            }
            case N_EXPANDED:
                return merge_coverage(evaluate(node.children[0]), evaluate(node.children[1]));
            case N_ALTERNATIVES: {
                if (node.children.empty()) return {};
                int head = node.children[0];
                const Node &head_node = compilation_.nodes[head];
                int course_node = head;
                if (head_node.kind == N_EXPANDED) course_node = head_node.children[0];
                const Node &course = compilation_.nodes[course_node];
                if (course.kind != N_COURSE) return {};
                bool covered = evaluator_.evaluate(index).known();
                Coverage result;
                result.slots.push_back(((uint32_t) evaluator_.rank(course.course) << 1)
                                       | (covered ? 1U : 0U));
                return result;
            }
            case N_OR: {
                if (node.children.empty()) return {};
                int best = -1;
                double best_fraction = -1.0;
                for (int child : node.children) {
                    Coverage value = evaluate(child);
                    double fraction = value.fraction();
                    if (fraction > best_fraction) {
                        best_fraction = fraction;
                        best = child;
                    }
                }
                return evaluate(best);
            }
            case N_AND:
            case N_CARDINALITY: {
                Coverage result;
                for (int child : node.children)
                    result = merge_coverage(std::move(result), evaluate(child));
                return result;
            }
            default:
                return {};
        }
    }

    const Compilation &compilation_;
    Evaluator &evaluator_;
    std::unordered_map<int, Coverage> memo_;
};


int evaluate_bundle(const StructureBundle &holder, const std::unordered_set<std::string> &basis,
                    int mode, NativeOutcome *outcomes, int capacity)
{
    const Compiled &compiled = *holder.compiled;
    if ((int) compiled.compilations.size() > capacity) {
        set_error("native outcome buffer is too small");
        return -1;
    }
    int written = 0;
    for (const Compilation &compilation : compiled.compilations) {
        NativeOutcome &outcome = outcomes[written];
        outcome = {};
        outcome.root = compilation.root.c_str();
        outcome.has_outcome = 0;
        outcome.required_coverage = -1.0;
        outcome.recommended_coverage = -1.0;
        outcome.has_required = compilation.required >= 0 ? 1 : 0;
        outcome.has_recommended = compilation.recommended >= 0 ? 1 : 0;
        ++written;
        if (basis.count(compilation.root) != 0) continue;
        auto summary = compilation.summaries.find(compilation.root);
        if (summary == compilation.summaries.end()) continue;
        if (compilation.active_only && !summary->second.active) continue;
        if (compilation.required < 0 && compilation.recommended < 0) continue;
        Family family;
        Evaluator evaluator(compilation, compiled, family, basis);
        CoverageEvaluator coverage(compilation, evaluator);
        Coverage required;
        Coverage recommended;
        if (compilation.required >= 0) required = coverage.evaluate(compilation.required);
        if (compilation.recommended >= 0) recommended = coverage.evaluate(compilation.recommended);
        if (required.denominator() == 0 && recommended.denominator() == 0) continue;
        if (mode == 1) {
            bool any_covered = false;
            for (uint32_t slot : required.slots)
                if (slot & 1U) any_covered = true;
            for (uint32_t slot : recommended.slots)
                if (slot & 1U) any_covered = true;
            if (!any_covered) continue;
        } else {
            bool satisfied = true;
            if (compilation.required >= 0 && !evaluator.evaluate(compilation.required).known())
                satisfied = false;
            if (compilation.recommended >= 0 && !evaluator.evaluate(compilation.recommended).known())
                satisfied = false;
            if (!satisfied) continue;
        }
        if (evaluator.failed) {
            set_error("native satisfaction failed on an absent course summary");
            return -1;
        }
        outcome.has_outcome = 1;
        outcome.required_coverage = required.denominator() == 0
            ? -1.0 : required.fraction();
        outcome.recommended_coverage = recommended.denominator() == 0
            ? -1.0 : recommended.fraction();
    }
    return written;
}

}  // namespace tce
