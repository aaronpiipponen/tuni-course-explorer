/* Native drawing projection over one compiled prerequisite structure.
 *
 * Derives display nodes, edges, support bindings, projection contexts and relationship members from
 * the identified calculation records. Every display identity comes from the same canonical payload
 * convention as the calculation identities.
 */

#include "canonical_json.h"
#include <algorithm>
#include <map>
#include <set>
#include <string>
#include <tuple>
#include <unordered_map>
#include <utility>
#include <vector>
#include "pipeline.h"
#include "records.h"
#include "support.h"

namespace tce {

/* One normalized display recipe shared by every equal drawing context. */
struct Recipe {
    bool has_key = false;
    std::string key;
    bool has_fingerprint = false;
    std::string fingerprint;
    std::set<std::string> attachment;
    std::string fact_id;
    std::vector<std::tuple<std::string, std::string, bool>> bindings;
    std::vector<int> children;
    std::vector<std::pair<int, int>> decorations;
    std::string use_id;
    std::string owner;
    std::string piece_id;
    std::string context_key;
    bool has_binding_key = false;
    std::string binding_key;
    bool has_descendant_anchor = false;
    std::string descendant_anchor;
    bool via_inferred = false;
    bool via_recommended = false;
};

struct RawEdge {
    std::string source;
    std::string target;
    std::string fact_id;
    bool has_context = false;
    std::string context_id;
};

struct RawBinding {
    std::string support;
    std::string owner;
    std::string piece;
    std::set<std::string> use_ids;
    std::set<std::string> node_ids;
    std::set<std::string> mark_node_ids;
};

bool contains_group(const std::vector<std::string> *members, const std::string &group)
{
    if (members == nullptr) return false;
    return std::find(members->begin(), members->end(), group) != members->end();
}

class Projector {
public:
    explicit Projector(const Compilation &compilation)
        : compilation_(compilation), ids_(compilation.identified)
    {
        nodes_.emplace("course:" + compilation.root,
                       make_root_node(compilation.root));
        emitted_.insert("course:" + compilation.root);
    }

    bool run(ProjectionRecords &output)
    {
        if (compilation_.requirements >= 0) {
            int root = build(ids_.use_id[compilation_.requirements], compilation_.root,
                             nullptr, false, false, 0, false, false);
            if (failed_) return false;
            root_context_id_ = emit(root);
            if (failed_) return false;
            has_root_context_ = true;
        }
        finalize();
        if (failed_) return false;
        intern_edges();
        if (failed_) return false;
        assemble(output);
        return true;
    }

private:
    static ProjNodeRec make_root_node(const std::string &root)
    {
        ProjNodeRec node;
        node.node_id = "course:" + root;
        node.kind = D_COURSE;
        node.course_group_id = root;
        node.is_root = true;
        return node;
    }

    const UseRecord &use(const std::string &use_id) const
    {
        return compilation_.uses.at(ids_.use_index.at(use_id));
    }

    std::string child_id(int index) const { return ids_.use_id[(size_t) index]; }

    const Node &piece_of_use(const std::string &use_id) const
    {
        return compilation_.nodes[(size_t) use(use_id).piece];
    }

    const FactRecord &fact_of_use(const std::string &use_id) const
    {
        return compilation_.facts[(size_t) use(use_id).fact];
    }

    ProjNodeRec &add_node(const ProjNodeRec &node)
    {
        auto found = nodes_.find(node.node_id);
        if (found == nodes_.end()) {
            auto inserted = nodes_.emplace(node.node_id, node);
            return inserted.first->second;
        }
        ProjNodeRec &existing = found->second;
        existing.via_inferred = existing.via_inferred || node.via_inferred;
        existing.via_recommended = existing.via_recommended || node.via_recommended;
        existing.has_official_provenance =
            existing.has_official_provenance || node.has_official_provenance;
        existing.has_inferred_provenance =
            existing.has_inferred_provenance || node.has_inferred_provenance;
        std::set<std::string> diagnostics(existing.diagnostic_ids.begin(),
                                          existing.diagnostic_ids.end());
        diagnostics.insert(node.diagnostic_ids.begin(), node.diagnostic_ids.end());
        existing.diagnostic_ids.assign(diagnostics.begin(), diagnostics.end());
        existing.display_as_inferred =
            existing.kind == D_COURSE && !existing.is_root
            && (existing.has_inferred_provenance || node.has_inferred_provenance)
            && !(existing.has_official_provenance || node.has_official_provenance);
        return existing;
    }

    int new_recipe()
    {
        recipes_.push_back(Recipe());
        return (int) recipes_.size() - 1;
    }

    int build(const std::string &use_id, const std::string &owner,
              const std::vector<std::string> *members, bool module_body, bool structural_module,
              int parent_operator, bool via_inferred, bool via_recommended)
    {
        std::string memo;
        memo.push_back('[');
        append_json_string(memo, owner);
        memo.push_back(',');
        append_json_string(memo, use_id);
        memo += ',';
        if (members == nullptr) {
            memo += "null";
        } else {
            memo.push_back('[');
            for (size_t index = 0; index < members->size(); ++index) {
                if (index > 0) memo.push_back(',');
                append_json_string(memo, (*members)[index]);
            }
            memo.push_back(']');
        }
        memo += module_body ? ",true," : ",false,";
        memo += structural_module ? "true," : "false,";
        if (parent_operator == 1) memo += "\"and\"";
        else if (parent_operator == 2) memo += "\"or\"";
        else memo += "null";
        memo += via_inferred ? ",true," : ",false,";
        memo += via_recommended ? "true]" : "false]";
        auto cached = memo_.find(memo);
        if (cached != memo_.end()) return cached->second;

        const UseRecord &source = use(use_id);
        const Node &piece = piece_of_use(use_id);
        const FactRecord &fact = fact_of_use(use_id);
        std::string support = "s:" + owner + ":" + ids_.piece_id[(size_t) source.piece];
        support_parts_[support] = std::make_pair(owner, ids_.piece_id[(size_t) source.piece]);
        bool node_inferred = via_inferred || fact.origin == 1;
        bool node_recommended =
            via_recommended || fact.official_kind == 1 || fact.inferred_category == 1;
        int result;
        if (piece.kind == N_COURSE && !piece.course.empty()) {
            result = course(use_id, source, fact, piece, support, members, node_inferred,
                            node_recommended);
        } else if (piece.kind == N_MODULE_BLOCK) {
            result = module(use_id, source, piece, fact, owner, support, members,
                            structural_module, node_inferred, node_recommended);
        } else if (piece.kind == N_EXPANDED) {
            result = expanded(use_id, source, support, owner, members, module_body, node_inferred,
                              node_recommended);
        } else {
            result = connector(use_id, source, piece, fact, owner, support, members, module_body,
                               structural_module, parent_operator, node_inferred,
                               node_recommended);
        }
        if (failed_) return -1;
        Recipe &recipe = recipes_[(size_t) result];
        recipe.use_id = use_id;
        recipe.owner = owner;
        recipe.piece_id = ids_.piece_id[(size_t) source.piece];
        recipe.context_key = digest_payload(memo);
        memo_[memo] = result;
        return result;
    }

    int course(const std::string &use_id, const UseRecord &source, const FactRecord &fact,
               const Node &piece, const std::string &support,
               const std::vector<std::string> *members, bool via_inferred, bool via_recommended)
    {
        std::string node_id = "course:" + piece.course;
        std::string fingerprint = digest_strings({"course", piece.course});
        bool is_card = contains_group(members, piece.course);
        if (!is_card) {
            ProjNodeRec node;
            node.node_id = node_id;
            node.kind = D_COURSE;
            node.course_group_id = piece.course;
            node.is_root = piece.course == compilation_.root;
            node.via_inferred = via_inferred;
            node.via_recommended = via_recommended;
            node.has_official_provenance = fact.origin == 0;
            node.has_inferred_provenance = fact.origin == 1;
            node.display_as_inferred =
                piece.course != compilation_.root && fact.origin == 1;
            add_node(node);
        }
        int index = new_recipe();
        Recipe &recipe = recipes_[(size_t) index];
        recipe.has_key = !is_card;
        if (!is_card) {
            recipe.key = node_id;
            recipe.attachment.insert(fingerprint);
        }
        recipe.has_fingerprint = true;
        recipe.fingerprint = fingerprint;
        recipe.fact_id = ids_.fact_id[(size_t) source.fact];
        recipe.bindings.emplace_back(support, use_id, false);
        recipe.via_inferred = via_inferred;
        recipe.via_recommended = via_recommended;
        return index;
    }

    int expanded(const std::string &use_id, const UseRecord &source, const std::string &support,
                 const std::string &owner, const std::vector<std::string> *members,
                 bool module_body, bool via_inferred, bool via_recommended)
    {
        if (source.children.size() != 2) {
            set_error("native expanded course does not carry its head and descendants");
            failed_ = true;
            return -1;
        }
        const std::string head_use = child_id(source.children[0]);
        const std::string descendants_use = child_id(source.children[1]);
        const Node &head_piece = piece_of_use(head_use);
        const std::string head_owner = head_piece.course.empty() ? owner : head_piece.course;
        int head = build(head_use, head_owner, members, module_body, false, 0, via_inferred,
                         via_recommended);
        const std::vector<std::string> *descendant_members = members;
        if (members != nullptr && !head_piece.course.empty()
            && !contains_group(members, head_piece.course))
            descendant_members = nullptr;
        bool path_inferred = via_inferred || recipes_[(size_t) head].via_inferred;
        bool path_recommended = via_recommended || recipes_[(size_t) head].via_recommended;
        int descendants = build(descendants_use, head_owner, descendant_members, module_body,
                                false, 0, path_inferred, path_recommended);
        const bool visible_head = recipes_[(size_t) head].has_key;
        const std::string head_fingerprint = recipes_[(size_t) head].fingerprint;
        const std::string head_key = recipes_[(size_t) head].key;
        const std::set<std::string> descendant_attachment =
            recipes_[(size_t) descendants].attachment;
        const std::vector<std::tuple<std::string, std::string, bool>> head_bindings =
            recipes_[(size_t) head].bindings;
        int index = new_recipe();
        Recipe &recipe = recipes_[(size_t) index];
        if (visible_head) {
            recipe.has_fingerprint = true;
            recipe.fingerprint = head_fingerprint;
            recipe.attachment.insert(head_fingerprint);
        } else {
            recipe.attachment = descendant_attachment;
        }
        recipe.fact_id = ids_.fact_id[(size_t) source.fact];
        recipe.bindings = head_bindings;
        recipe.bindings.emplace_back(support, use_id, false);
        recipe.children = {head, descendants};
        if (visible_head) {
            recipe.has_binding_key = true;
            recipe.binding_key = head_key;
            recipe.has_descendant_anchor = true;
            recipe.descendant_anchor = head_key;
        }
        recipe.via_inferred = path_inferred;
        recipe.via_recommended = path_recommended;
        return index;
    }

    int module(const std::string &use_id, const UseRecord &source, const Node &piece,
               const FactRecord &fact, const std::string &owner, const std::string &support,
               const std::vector<std::string> *members, bool structural_module, bool via_inferred,
               bool via_recommended)
    {
        if (source.children.size() != 1) {
            set_error("native module block does not carry its body");
            failed_ = true;
            return -1;
        }
        const std::string body_use = child_id(source.children[0]);
        if (structural_module) {
            int body = build(body_use, owner, members, true, true, 0, via_inferred,
                             via_recommended);
            for (int diagnostic : source.diagnostics) {
                contained_.insert(ids_.diagnostic_id[(size_t) diagnostic]);
            }
            int index = new_recipe();
            Recipe &recipe = recipes_[(size_t) index];
            recipe.attachment = recipes_[(size_t) body].attachment;
            recipe.fact_id = ids_.fact_id[(size_t) source.fact];
            recipe.bindings.emplace_back(support, use_id, false);
            recipe.children = {body};
            recipe.via_inferred = via_inferred;
            recipe.via_recommended = via_recommended;
            return index;
        }
        const std::vector<std::string> member_ids = source.members;
        int body = build(body_use, owner, &member_ids, true, true, 0, via_inferred,
                         via_recommended);
        for (int diagnostic : source.diagnostics) {
            const DiagnosticRecord &record =
                compilation_.diagnostics[(size_t) diagnostic];
            if (!record.module.empty() && record.module != piece.module)
                contained_.insert(ids_.diagnostic_id[(size_t) diagnostic]);
        }
        std::vector<std::string> body_diagnostics;
        for (int diagnostic : source.diagnostics)
            body_diagnostics.push_back(ids_.diagnostic_id[(size_t) diagnostic]);
        const std::set<std::string> body_attachment = recipes_[(size_t) body].attachment;
        std::string payload = "[";
        append_json_string(payload, "module");
        payload.push_back(',');
        append_json_optional_string(payload, piece.module);
        payload.push_back(',');
        const auto module = compilation_.modules.find(piece.module);
        if (module == compilation_.modules.end()) payload += "null";
        else append_json_string(payload, module->second.module_type);
        payload.push_back(',');
        append_json_optional_string(payload, canonical_decimal_text(piece.credits_min_text));
        payload.push_back(',');
        append_json_optional_string(payload, canonical_decimal_text(piece.credits_max_text));
        payload += ",[";
        for (size_t slot = 0; slot < member_ids.size(); ++slot) {
            if (slot > 0) payload.push_back(',');
            append_json_string(payload, member_ids[slot]);
        }
        payload.push_back(']');
        for (const std::string &fingerprint : body_attachment) {
            payload.push_back(',');
            append_json_string(payload, fingerprint);
        }
        payload.push_back(']');
        std::string fingerprint = digest_payload(payload);
        std::string node_id = "s:" + owner + ":d:" + fingerprint;
        ProjNodeRec node;
        node.node_id = node_id;
        node.kind = D_MODULE;
        node.owner_group_id = owner;
        node.module_group_id = piece.module;
        node.credits_min = piece.credits_min_text;
        node.credits_max = piece.credits_max_text;
        node.member_group_ids = member_ids;
        node.diagnostic_ids = body_diagnostics;
        node.via_inferred = via_inferred;
        node.via_recommended = via_recommended;
        node.has_official_provenance = fact.origin == 0;
        node.has_inferred_provenance = fact.origin == 1;
        node.markable = true;
        add_node(node);
        int index = new_recipe();
        Recipe &recipe = recipes_[(size_t) index];
        recipe.has_key = true;
        recipe.key = node_id;
        recipe.has_fingerprint = true;
        recipe.fingerprint = fingerprint;
        recipe.attachment.insert(fingerprint);
        recipe.fact_id = ids_.fact_id[(size_t) source.fact];
        recipe.bindings.emplace_back(support, use_id, true);
        recipe.children = {body};
        recipe.via_inferred = via_inferred;
        recipe.via_recommended = via_recommended;
        return index;
    }

    int connector(const std::string &use_id, const UseRecord &source, const Node &piece,
                  const FactRecord &fact, const std::string &owner, const std::string &support,
                  const std::vector<std::string> *members, bool module_body, bool structural_module,
                  int parent_operator, bool via_inferred, bool via_recommended)
    {
        bool logical = piece.kind == N_AND || piece.kind == N_OR || piece.kind == N_ALTERNATIVES;
        int own_operator = piece.kind == N_AND ? 1 : (logical ? 2 : 0);
        std::vector<int> children;
        for (int child : source.children)
            children.push_back(build(child_id(child), owner, members, module_body,
                                     structural_module, own_operator, via_inferred,
                                     via_recommended));
        std::vector<std::pair<int, int>> decorations;
        if (module_body && piece.kind != N_AND) {
            for (size_t slot = 0; slot < source.children.size(); ++slot) {
                const Recipe &child = recipes_[(size_t) children[slot]];
                if (!child.attachment.empty()) continue;
                std::vector<std::string> member_ids =
                    module_member_group_ids(child_id(source.children[slot]));
                if (!member_ids.empty())
                    decorations.emplace_back((int) slot,
                                             internal_requirement(owner, member_ids,
                                                                  ids_.fact_id[(size_t) source.fact]));
            }
        }
        std::set<std::string> child_targets;
        for (int child : children) child_targets.insert(recipes_[(size_t) child].attachment.begin(),
                                                        recipes_[(size_t) child].attachment.end());
        for (const auto &[slot, decoration] : decorations)
            child_targets.insert(recipes_[(size_t) decoration].attachment.begin(),
                                 recipes_[(size_t) decoration].attachment.end());
        if (logical && parent_operator == own_operator) {
            int index = new_recipe();
            Recipe &recipe = recipes_[(size_t) index];
            recipe.attachment = child_targets;
            recipe.fact_id = ids_.fact_id[(size_t) source.fact];
            recipe.bindings.emplace_back(support, use_id, false);
            recipe.children = children;
            recipe.decorations = decorations;
            recipe.via_inferred = via_inferred;
            recipe.via_recommended = via_recommended;
            return index;
        }
        if (logical && child_targets.size() <= 1) {
            int index = new_recipe();
            Recipe &recipe = recipes_[(size_t) index];
            recipe.attachment = child_targets;
            recipe.fact_id = ids_.fact_id[(size_t) source.fact];
            recipe.bindings.emplace_back(support, use_id, false);
            recipe.children = children;
            recipe.decorations = decorations;
            recipe.via_inferred = via_inferred;
            recipe.via_recommended = via_recommended;
            return index;
        }
        std::string payload = display_payload(piece);
        for (const std::string &target : child_targets) {
            payload.push_back(',');
            append_json_string(payload, target);
        }
        payload.push_back(']');
        std::string fingerprint = digest_payload(payload);
        std::string node_id = "s:" + owner + ":d:" + fingerprint;
        int display_kind = display_kind_of(piece.kind);
        ProjNodeRec node;
        node.node_id = node_id;
        node.kind = display_kind;
        node.owner_group_id = owner;
        node.require_min = piece.require_min;
        node.require_max = piece.require_max;
        node.credits_min = piece.credits_min_text;
        node.credits_max = piece.credits_max_text;
        node.count_min = piece.count_min;
        node.count_max = piece.count_max;
        node.referenced_group_id = piece.referenced;
        node.reason = piece.reason;
        node.detail = piece.detail;
        node.member_group_ids = source.members;
        for (int diagnostic : source.diagnostics)
            node.diagnostic_ids.push_back(ids_.diagnostic_id[(size_t) diagnostic]);
        node.via_inferred = via_inferred;
        node.via_recommended = via_recommended;
        node.has_official_provenance = fact.origin == 0;
        node.has_inferred_provenance = fact.origin == 1;
        node.markable = markable(display_kind);
        add_node(node);
        int index = new_recipe();
        Recipe &recipe = recipes_[(size_t) index];
        recipe.has_key = true;
        recipe.key = node_id;
        recipe.has_fingerprint = true;
        recipe.fingerprint = fingerprint;
        recipe.attachment.insert(fingerprint);
        recipe.fact_id = ids_.fact_id[(size_t) source.fact];
        recipe.bindings.emplace_back(support, use_id, node.markable);
        recipe.children = children;
        recipe.decorations = decorations;
        recipe.via_inferred = via_inferred;
        recipe.via_recommended = via_recommended;
        return index;
    }

    int internal_requirement(const std::string &owner, const std::vector<std::string> &member_ids,
                             const std::string &fact_id)
    {
        std::string payload = "[";
        append_json_string(payload, "internal_requirement");
        payload += ",[";
        for (size_t index = 0; index < member_ids.size(); ++index) {
            if (index > 0) payload.push_back(',');
            append_json_string(payload, member_ids[index]);
        }
        payload += "]]";
        std::string fingerprint = digest_payload(payload);
        std::string node_id = "s:" + owner + ":d:" + fingerprint;
        ProjNodeRec node;
        node.node_id = node_id;
        node.kind = D_INTERNAL;
        node.owner_group_id = owner;
        node.member_group_ids = member_ids;
        add_node(node);
        int index = new_recipe();
        Recipe &recipe = recipes_[(size_t) index];
        recipe.has_key = true;
        recipe.key = node_id;
        recipe.has_fingerprint = true;
        recipe.fingerprint = fingerprint;
        recipe.attachment.insert(fingerprint);
        recipe.fact_id = fact_id;
        return index;
    }

    static std::string display_payload(const Node &piece)
    {
        int kind = piece.kind;
        std::string payload = "[";
        if (kind == N_EXPANDED || kind == N_ALTERNATIVES) {
            payload += "\"or\"";
        } else if (kind == N_AND || kind == N_OR) {
            append_json_string(payload, piece_kind_name(kind));
        } else {
            append_json_string(payload, piece_kind_name(kind));
            payload.push_back(',');
            append_canonical_bound(payload, piece.require_min);
            payload.push_back(',');
            append_canonical_bound(payload, piece.require_max);
            payload.push_back(',');
            append_json_optional_string(payload, canonical_decimal_text(piece.credits_min_text));
            payload.push_back(',');
            append_json_optional_string(payload, canonical_decimal_text(piece.credits_max_text));
            payload.push_back(',');
            append_canonical_bound(payload, piece.count_min);
            payload.push_back(',');
            append_canonical_bound(payload, piece.count_max);
            payload.push_back(',');
            append_json_optional_string(payload, piece.reason);
            payload.push_back(',');
            append_json_optional_string(payload, piece.referenced);
            payload.push_back(',');
            append_json_optional_string(payload, piece.detail);
        }
        return payload;
    }

    static int display_kind_of(int kind)
    {
        switch (kind) {
            case N_AND: return D_AND;
            case N_OR:
            case N_ALTERNATIVES: return D_OR;
            case N_CARDINALITY: return D_CARDINALITY;
            case N_CREDITS: return D_CREDITS;
            case N_COUNT: return D_COUNT;
            case N_OPAQUE: return D_OPAQUE;
            case N_UNRESOLVED: return D_UNRESOLVED;
            default: return D_AND;
        }
    }

    static bool markable(int display_kind)
    {
        return display_kind == D_MODULE || display_kind == D_CARDINALITY
            || display_kind == D_CREDITS || display_kind == D_COUNT || display_kind == D_OPAQUE;
    }

    std::vector<std::string> module_member_group_ids(const std::string &use_id)
    {
        auto cached = member_memo_.find(use_id);
        if (cached != member_memo_.end()) return cached->second;
        std::set<std::string> found;
        std::vector<std::string> pending{use_id};
        while (!pending.empty()) {
            std::string current = pending.back();
            pending.pop_back();
            const Node &piece = piece_of_use(current);
            const UseRecord &source = use(current);
            if (piece.kind == N_COURSE) {
                if (!piece.course.empty()) found.insert(piece.course);
                continue;
            }
            if (piece.kind == N_EXPANDED) {
                if (!source.children.empty()) {
                    const Node &head = piece_of_use(child_id(source.children[0]));
                    if (!head.course.empty()) found.insert(head.course);
                }
                continue;
            }
            if (piece.kind == N_ALTERNATIVES) {
                if (!source.children.empty()) pending.push_back(child_id(source.children[0]));
                continue;
            }
            for (int child : source.children) pending.push_back(child_id(child));
        }
        std::vector<std::string> result(found.begin(), found.end());
        member_memo_[use_id] = result;
        return result;
    }

    std::string context_id(const Recipe &recipe, const std::string &parent,
                           const std::string &nearest) const
    {
        std::string payload = "[";
        append_json_string(payload, recipe.context_key);
        payload.push_back(',');
        append_json_string(payload, parent);
        payload.push_back(',');
        append_json_string(payload, nearest);
        payload.push_back(']');
        return "c:" + digest_payload(payload);
    }

    void bind(const std::string &support, const std::string &use_id,
              const std::vector<std::string> &node_ids, bool mark)
    {
        auto found = binding_index_.find(support);
        if (found == binding_index_.end()) {
            binding_index_[support] = (int) bindings_.size();
            RawBinding entry;
            entry.support = support;
            entry.owner = support_parts_.at(support).first;
            entry.piece = support_parts_.at(support).second;
            bindings_.push_back(std::move(entry));
            found = binding_index_.find(support);
        }
        RawBinding &entry = bindings_[(size_t) found->second];
        entry.use_ids.insert(use_id);
        for (const std::string &node_id : node_ids) {
            entry.node_ids.insert(node_id);
            if (mark) entry.mark_node_ids.insert(node_id);
        }
    }

    std::string emit(int root)
    {
        std::string root_anchor = "course:" + compilation_.root;
        std::vector<std::tuple<int, std::string, std::string>> pending;
        pending.emplace_back(root, root_anchor, root_anchor);
        std::string root_context;
        while (!pending.empty()) {
            auto [recipe_index, parent, nearest] = pending.back();
            pending.pop_back();
            const Recipe &current = recipes_[(size_t) recipe_index];
            std::string current_context = context_id(current, parent, nearest);
            if (contexts_.find(current_context) != contexts_.end()) continue;
            if (current.has_key) {
                emitted_.insert(current.key);
                std::vector<std::string> node_ids{current.key};
                for (const auto &[support, use_id, mark] : current.bindings)
                    bind(support, use_id, node_ids, mark);
                if (parent != current.key) {
                    RawEdge edge;
                    edge.source = parent;
                    edge.target = current.key;
                    edge.fact_id = current.fact_id;
                    edge.has_context = true;
                    edge.context_id = current_context;
                    edges_.push_back(std::move(edge));
                }
            } else {
                const std::string &anchor =
                    current.has_binding_key ? current.binding_key : nearest;
                std::vector<std::string> node_ids{anchor};
                for (const auto &[support, use_id, mark] : current.bindings)
                    bind(support, use_id, node_ids, mark);
            }
            std::string drawn_parent = current.has_key ? current.key : parent;
            std::string drawn_nearest = current.has_key ? current.key : nearest;
            std::vector<ProjContextChildRec> children;
            for (size_t slot = 0; slot < current.children.size(); ++slot) {
                std::string child_parent = drawn_parent;
                std::string child_nearest = drawn_nearest;
                if (!current.has_key && current.has_descendant_anchor && slot == 1) {
                    child_parent = current.descendant_anchor;
                    child_nearest = current.descendant_anchor;
                }
                const Recipe &child = recipes_[(size_t) current.children[slot]];
                children.push_back(
                    ProjContextChildRec{(int32_t) slot, context_id(child, child_parent,
                                                                  child_nearest)});
                pending.emplace_back(current.children[slot], child_parent, child_nearest);
            }
            for (const auto &[slot, decoration] : current.decorations) {
                std::string selected;
                for (const ProjContextChildRec &child : children) {
                    if (child.slot == slot) {
                        selected = child.context_id;
                        break;
                    }
                }
                if (selected.empty()) {
                    set_error("a display decoration has no native child slot");
                    failed_ = true;
                    return root_context;
                }
                decoration_edge(recipes_[(size_t) decoration], drawn_parent, selected);
            }
            ProjContextRec context;
            context.context_id = current_context;
            context.owner_group_id = current.owner;
            context.piece_id = current.piece_id;
            context.children = std::move(children);
            contexts_.emplace(current_context, std::move(context));
            if (root_context.empty()) root_context = current_context;
        }
        return root_context;
    }

    void decoration_edge(const Recipe &decoration, const std::string &parent,
                         const std::string &context_id)
    {
        if (!decoration.has_key) {
            set_error("a display decoration has no drawn node");
            failed_ = true;
            return;
        }
        emitted_.insert(decoration.key);
        if (parent != decoration.key) {
            RawEdge edge;
            edge.source = parent;
            edge.target = decoration.key;
            edge.fact_id = decoration.fact_id;
            edge.has_context = true;
            edge.context_id = context_id;
            edges_.push_back(std::move(edge));
        }
    }

    static bool ignored_kind(const std::string &kind)
    {
        return kind == "empty_option" || kind == "missing_module_alternative"
            || kind == "module_version_fallback" || kind == "free_choice"
            || kind == "unexpandable_content" || kind == "all_mandatory_bounds";
    }

    static bool disappeared_kind(const std::string &kind)
    {
        return kind == "unexpandable_content" || kind == "free_choice";
    }

    void finalize()
    {
        std::map<std::string, std::set<std::string>> anchors;
        std::map<std::string, std::string> owners;
        for (const RawBinding &binding : bindings_) {
            for (const std::string &use_id : binding.use_ids) {
                const UseRecord &source = use(use_id);
                for (int diagnostic : source.diagnostics) {
                    const std::string &diagnostic_id = ids_.diagnostic_id[(size_t) diagnostic];
                    anchors[diagnostic_id].insert(binding.node_ids.begin(),
                                                  binding.node_ids.end());
                    owners.emplace(diagnostic_id, binding.owner);
                }
            }
        }
        for (int diagnostic : compilation_.root_diagnostics) {
            const std::string &diagnostic_id = ids_.diagnostic_id[(size_t) diagnostic];
            anchors[diagnostic_id].insert("course:" + compilation_.root);
            owners.emplace(diagnostic_id, compilation_.root);
        }
        for (const auto &[diagnostic_id, anchor_set] : anchors) {
            const DiagnosticRecord &diagnostic =
                compilation_.diagnostics.at(ids_.diagnostic_index.at(diagnostic_id));
            if (!ignored_kind(diagnostic.kind)) continue;
            std::vector<std::string> node_ids;
            for (const std::string &node_id : anchor_set)
                if (emitted_.find(node_id) != emitted_.end()) node_ids.push_back(node_id);
            if (node_ids.empty()) continue;
            const std::string parent = node_ids.front();
            std::string module_type;
            if (!diagnostic.module.empty()) {
                const auto module = compilation_.modules.find(diagnostic.module);
                if (module != compilation_.modules.end()) module_type = module->second.module_type;
            }
            bool already_drawn = false;
            for (const auto &[node_id, node] : nodes_) {
                if (node.kind == D_MODULE && node.module_group_id == diagnostic.module
                    && emitted_.find(node_id) != emitted_.end()) {
                    already_drawn = true;
                    break;
                }
            }
            std::string current_parent = parent;
            if (contained_.find(diagnostic_id) == contained_.end()
                && disappeared_kind(diagnostic.kind) && !diagnostic.module.empty()
                && !module_type.empty() && !already_drawn) {
                std::string owner = owners.at(diagnostic_id);
                std::string payload = "[";
                append_json_string(payload, "module_disappeared");
                payload.push_back(',');
                append_json_string(payload, diagnostic.module);
                payload.push_back(',');
                append_json_string(payload, module_type);
                payload.push_back(']');
                std::string fingerprint = digest_payload(payload);
                std::string module_id = "s:" + owner + ":d:" + fingerprint;
                ProjNodeRec node;
                node.node_id = module_id;
                node.kind = D_MODULE;
                node.owner_group_id = owner;
                node.module_group_id = diagnostic.module;
                node.diagnostic_ids = {diagnostic_id};
                add_node(node);
                emitted_.insert(module_id);
                RawEdge edge;
                edge.source = current_parent;
                edge.target = module_id;
                edge.fact_id = ids_.fact_id[(size_t) diagnostic.fact];
                edges_.push_back(std::move(edge));
                current_parent = module_id;
            }
            std::string owner = owners.at(diagnostic_id);
            std::string payload = "[";
            append_json_string(payload, "ignored");
            payload.push_back(',');
            append_json_string(payload, diagnostic.kind);
            payload += ",[";
            for (size_t index = 0; index < diagnostic.referenced.size(); ++index) {
                if (index > 0) payload.push_back(',');
                append_json_string(payload, diagnostic.referenced[index]);
            }
            payload += "],";
            append_json_optional_string(payload, diagnostic.detail);
            payload.push_back(',');
            append_json_optional_string(payload, diagnostic.module);
            payload.push_back(',');
            append_json_optional_string(payload, module_type);
            payload.push_back(']');
            std::string fingerprint = digest_payload(payload);
            std::string ignored_id = "s:" + owner + ":d:" + fingerprint;
            ProjNodeRec node;
            node.node_id = ignored_id;
            node.kind = D_IGNORED;
            node.owner_group_id = owner;
            node.referenced_group_id = diagnostic.module;
            node.reason = diagnostic.kind;
            node.detail = diagnostic.detail;
            node.diagnostic_ids = {diagnostic_id};
            add_node(node);
            emitted_.insert(ignored_id);
            RawEdge edge;
            edge.source = current_parent;
            edge.target = ignored_id;
            edge.fact_id = ids_.fact_id[(size_t) diagnostic.fact];
            edges_.push_back(std::move(edge));
        }
    }

    void intern_edges()
    {
        std::map<std::pair<std::string, std::string>, std::map<std::string, std::set<std::string>>>
            grouped;
        for (const RawEdge &edge : edges_) {
            if (emitted_.find(edge.source) == emitted_.end()) {
                set_error("display edge source is not emitted");
                failed_ = true;
                return;
            }
            if (emitted_.find(edge.target) == emitted_.end()) {
                set_error("display edge target is not emitted");
                failed_ = true;
                return;
            }
            if (edge.source == edge.target) continue;
            std::set<std::string> &contexts = grouped[{edge.source, edge.target}][edge.fact_id];
            if (edge.has_context) contexts.insert(edge.context_id);
        }
        for (const auto &[endpoints, facts] : grouped) {
            std::vector<std::string> member_ids;
            for (const auto &[fact_id, context_ids] : facts) {
                std::string member_id = "m:" + digest_strings({endpoints.first, endpoints.second,
                                                               fact_id});
                member_ids.push_back(member_id);
                ProjMemberRec member;
                member.member_id = member_id;
                member.source_node_id = endpoints.first;
                member.target_node_id = endpoints.second;
                member.fact_id = fact_id;
                members_.push_back(std::move(member));
                for (const std::string &context_id : context_ids)
                    selections_[context_id].insert(member_id);
            }
            std::sort(member_ids.begin(), member_ids.end());
            ProjEdgeRec record;
            record.edge_id = "e:" + digest_strings({endpoints.first, endpoints.second});
            record.source_node_id = endpoints.first;
            record.target_node_id = endpoints.second;
            record.member_ids = member_ids;
            record.inferred_only = true;
            for (const auto &[fact_id, _contexts] : facts) {
                if (compilation_.facts.at(ids_.fact_index.at(fact_id)).origin != 1)
                    record.inferred_only = false;
            }
            edge_records_.push_back(std::move(record));
        }
        std::sort(edge_records_.begin(), edge_records_.end(),
                  [](const ProjEdgeRec &left, const ProjEdgeRec &right) {
                      return left.edge_id < right.edge_id;
                  });
        std::sort(members_.begin(), members_.end(),
                  [](const ProjMemberRec &left, const ProjMemberRec &right) {
                      return left.member_id < right.member_id;
                  });
    }

    void assemble(ProjectionRecords &output)
    {
        std::set<std::string> markable_nodes;
        for (const auto &[node_id, node] : nodes_)
            if (node.markable && emitted_.find(node_id) != emitted_.end())
                markable_nodes.insert(node_id);
        output.has_root_context = has_root_context_;
        output.root_context_id = root_context_id_;
        for (const RawBinding &binding : bindings_) {
            ProjBindingRec record;
            record.support_id = binding.support;
            record.owner_group_id = binding.owner;
            record.piece_id = binding.piece;
            record.use_ids.assign(binding.use_ids.begin(), binding.use_ids.end());
            record.node_ids.assign(binding.node_ids.begin(), binding.node_ids.end());
            for (const std::string &node_id : binding.mark_node_ids)
                if (markable_nodes.find(node_id) != markable_nodes.end())
                    record.mark_node_ids.push_back(node_id);
            output.bindings.push_back(std::move(record));
        }
        std::sort(output.bindings.begin(), output.bindings.end(),
                  [](const ProjBindingRec &left, const ProjBindingRec &right) {
                      return left.support_id < right.support_id;
                  });
        for (const auto &[context_id, context] : contexts_) {
            ProjContextRec record = context;
            auto selection = selections_.find(context_id);
            if (selection != selections_.end())
                record.member_ids.assign(selection->second.begin(), selection->second.end());
            output.contexts.push_back(std::move(record));
        }
        std::sort(output.contexts.begin(), output.contexts.end(),
                  [](const ProjContextRec &left, const ProjContextRec &right) {
                      return left.context_id < right.context_id;
                  });
        output.members = members_;
        for (const auto &[node_id, node] : nodes_) {
            if (emitted_.find(node_id) == emitted_.end()) continue;
            output.nodes.push_back(node);
        }
        std::sort(output.nodes.begin(), output.nodes.end(),
                  [](const ProjNodeRec &left, const ProjNodeRec &right) {
                      return left.node_id < right.node_id;
                  });
        output.edges = edge_records_;
        output.ready = true;
    }

    const Compilation &compilation_;
    const IdentifiedRecords &ids_;
    std::unordered_map<std::string, ProjNodeRec> nodes_;
    std::set<std::string> emitted_;
    std::vector<RawEdge> edges_;
    std::vector<Recipe> recipes_;
    std::unordered_map<std::string, int> memo_;
    std::unordered_map<std::string, std::pair<std::string, std::string>> support_parts_;
    std::vector<RawBinding> bindings_;
    std::unordered_map<std::string, int> binding_index_;
    std::unordered_map<std::string, ProjContextRec> contexts_;
    std::unordered_map<std::string, std::vector<std::string>> member_memo_;
    std::set<std::string> contained_;
    std::map<std::string, std::set<std::string>> selections_;
    std::vector<ProjMemberRec> members_;
    std::vector<ProjEdgeRec> edge_records_;
    std::string root_context_id_;
    bool has_root_context_ = false;
    bool failed_ = false;
};


bool project_compilation(Compilation &compilation)
{
    Projector projector(compilation);
    return projector.run(compilation.projection);
}

}  // namespace tce
