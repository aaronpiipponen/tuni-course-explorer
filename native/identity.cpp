/* Canonical identity payloads for the native prerequisite records.
 *
 * Hashes the piece, fact, diagnostic and use payloads with SHA-256 and freezes the reachable tables
 * in identity order. Each payload is sorted, compact UTF-8 JSON written by `canonical_json.h`.
 */

#include "canonical_json.h"
#include <algorithm>
#include <string>
#include <unordered_set>
#include <vector>
#include "records.h"
#include "support.h"

namespace tce {

std::string digest_payload(const std::string &canonical)
{
    return sha256_hex(canonical).substr(0, 24);
}

std::string digest_strings(std::initializer_list<std::string> values)
{
    std::string out = "[";
    bool first = true;
    for (const std::string &value : values) {
        if (!first) out.push_back(',');
        first = false;
        append_json_string(out, value);
    }
    out.push_back(']');
    return digest_payload(out);
}

std::string node_work_key(const Node &node)
{
    if (node.work_payload.empty()) return {};
    return sha256_hex(node.work_payload).substr(0, 40);
}

void append_bound(std::string &out, int32_t value)
{
    if (value < 0) out += "null";
    else out += std::to_string(value);
}

/* Display payloads render every numeric bound through the canonical text form, so the JSON value is
 * a string rather than a number. */
void append_canonical_bound(std::string &out, int32_t value)
{
    if (value < 0) out += "null";
    else append_json_string(out, std::to_string(value));
}

std::string piece_identity_payload(const Node &node, const std::vector<std::string> &children,
                                   const std::string &work_key)
{
    std::string out = "[";
    append_json_string(out, piece_kind_name(node.kind));
    out += ",{";
    auto name = [&out](const char *field) {
        append_json_string(out, field);
        out.push_back(':');
    };
    name("count_max");
    append_bound(out, node.count_max);
    out.push_back(',');
    name("count_min");
    append_bound(out, node.count_min);
    out.push_back(',');
    name("course_group_id");
    append_json_optional_string(out, node.course);
    out.push_back(',');
    name("credits_max");
    append_json_optional_string(out, canonical_decimal_text(node.credits_max_text));
    out.push_back(',');
    name("credits_min");
    append_json_optional_string(out, canonical_decimal_text(node.credits_min_text));
    out.push_back(',');
    name("detail");
    append_json_optional_string(out, node.detail);
    out.push_back(',');
    name("module_group_id");
    append_json_optional_string(out, node.module);
    out.push_back(',');
    name("reason");
    append_json_optional_string(out, node.reason);
    out.push_back(',');
    name("referenced_group_id");
    append_json_optional_string(out, node.referenced);
    out.push_back(',');
    name("require_max");
    append_bound(out, node.require_max);
    out.push_back(',');
    name("require_min");
    append_bound(out, node.require_min);
    out.push_back(',');
    name("work_key");
    append_json_optional_string(out, work_key);
    out += "},[";
    for (size_t index = 0; index < children.size(); ++index) {
        if (index > 0) out.push_back(',');
        append_json_string(out, children[index]);
    }
    out += "],";
    append_json_optional_string(out, canonical_decimal_text(node.manual_min_text));
    out += node.module_rule ? ",true," : ",false,";
    out += node.cycle ? "true]" : "false]";
    return out;
}

std::string fact_identity_payload(const FactRecord &fact, const std::string &inference)
{
    std::string out = "[";
    append_json_string(out, origin_name(fact.origin));
    out.push_back(',');
    append_json_optional_string(out, official_kind_name(fact.official_kind));
    out.push_back(',');
    append_json_optional_string(out, category_name(fact.inferred_category));
    out.push_back(',');
    if (inference.empty()) out += "null";
    else out += inference;
    out.push_back(']');
    return out;
}

bool finalize_identities(Compilation &compilation)
{
    IdentifiedRecords &ids = compilation.identified;
    if (ids.ready) return true;
    const std::vector<Node> &nodes = compilation.nodes;
    const std::vector<UseRecord> &uses = compilation.uses;
    ids.piece_id.assign(nodes.size(), std::string());
    ids.work_key.assign(nodes.size(), std::string());
    for (size_t index = 0; index < nodes.size(); ++index)
        ids.work_key[index] = compilation.fixture_work_keys.empty()
            ? node_work_key(nodes[index]) : compilation.fixture_work_keys[index];
    for (size_t index = 0; index < nodes.size(); ++index) {
        std::vector<std::string> children;
        for (int child : nodes[index].children) {
            if (child < 0 || (size_t) child >= index) {
                set_error("native calculation graph is not topologically ordered");
                return false;
            }
            children.push_back(ids.piece_id[child]);
        }
        ids.piece_id[index] = "p:" + digest_payload(piece_identity_payload(
            nodes[index], children, ids.work_key[index]));
    }
    ids.fact_id.assign(compilation.facts.size(), std::string());
    for (size_t index = 0; index < compilation.facts.size(); ++index)
        ids.fact_id[index] = "f:" + digest_payload(
            fact_identity_payload(compilation.facts[index], compilation.facts[index].inference));
    ids.diagnostic_id.assign(compilation.diagnostics.size(), std::string());
    for (size_t index = 0; index < compilation.diagnostics.size(); ++index) {
        const DiagnosticRecord &diagnostic = compilation.diagnostics[index];
        if (diagnostic.fact < 0 || (size_t) diagnostic.fact >= ids.fact_id.size()) {
            set_error("native diagnostic has no provenance fact");
            return false;
        }
        std::string payload = "[";
        append_json_string(payload, diagnostic.kind);
        payload.push_back(',');
        append_json_string(payload, ids.fact_id[diagnostic.fact]);
        payload += ",[";
        for (size_t part = 0; part < diagnostic.referenced.size(); ++part) {
            if (part > 0) payload.push_back(',');
            append_json_string(payload, diagnostic.referenced[part]);
        }
        payload += "],";
        append_json_optional_string(payload, diagnostic.detail);
        payload.push_back(',');
        append_json_optional_string(payload, diagnostic.module);
        payload.push_back(']');
        ids.diagnostic_id[index] = "i:" + digest_payload(payload);
    }
    ids.use_id.assign(uses.size(), std::string());
    for (size_t index = 0; index < uses.size(); ++index) {
        const UseRecord &use = uses[index];
        if (use.piece < 0 || (size_t) use.piece >= nodes.size()) {
            set_error("native source use has no calculation piece");
            return false;
        }
        std::string payload = "[";
        append_json_string(payload, ids.piece_id[use.piece]);
        payload.push_back(',');
        append_json_string(payload, ids.fact_id[use.fact]);
        payload += ",[";
        for (size_t slot = 0; slot < use.children.size(); ++slot) {
            int child = use.children[slot];
            if (child < 0 || (size_t) child >= index) {
                set_error("native source use graph is not topologically ordered");
                return false;
            }
            if (slot > 0) payload.push_back(',');
            append_json_string(payload, ids.use_id[child]);
        }
        payload += "],[";
        for (size_t part = 0; part < use.source.size(); ++part) {
            if (part > 0) payload.push_back(',');
            if (use.source[part].integer) payload += std::to_string(use.source[part].number);
            else append_json_string(payload, use.source[part].text);
        }
        payload += "],[";
        for (size_t slot = 0; slot < use.diagnostics.size(); ++slot) {
            int diagnostic = use.diagnostics[slot];
            if (diagnostic < 0 || (size_t) diagnostic >= ids.diagnostic_id.size()) {
                set_error("native source use references an absent diagnostic");
                return false;
            }
            if (slot > 0) payload.push_back(',');
            append_json_string(payload, ids.diagnostic_id[diagnostic]);
        }
        payload += "],[";
        for (size_t slot = 0; slot < use.members.size(); ++slot) {
            if (slot > 0) payload.push_back(',');
            append_json_string(payload, use.members[slot]);
        }
        payload += "]]";
        ids.use_id[index] = "u:" + digest_payload(payload);
    }

    std::unordered_set<int> reachable_uses;
    std::vector<int> stack;
    for (int root : {compilation.requirements, compilation.required, compilation.recommended})
        if (root >= 0) stack.push_back(root);
    for (int root : compilation.extra_roots)
        if (root >= 0) stack.push_back(root);
    while (!stack.empty()) {
        int current = stack.back();
        stack.pop_back();
        if (current < 0 || (size_t) current >= uses.size()) {
            set_error("native calculation root is absent from the use table");
            return false;
        }
        if (!reachable_uses.insert(current).second) continue;
        for (int child : uses[current].children) stack.push_back(child);
    }
    std::unordered_set<int> reachable_pieces;
    std::unordered_set<int> reachable_diagnostics;
    std::unordered_set<int> reachable_facts;
    for (int use : reachable_uses) {
        reachable_pieces.insert(uses[use].piece);
        reachable_facts.insert(uses[use].fact);
        for (int diagnostic : uses[use].diagnostics) reachable_diagnostics.insert(diagnostic);
    }
    for (int diagnostic : compilation.root_diagnostics) reachable_diagnostics.insert(diagnostic);
    for (int diagnostic : reachable_diagnostics) reachable_facts.insert(
        compilation.diagnostics[diagnostic].fact);

    auto sorted_unique_ids = [](std::vector<int> indices, const std::vector<std::string> &table) {
        std::stable_sort(indices.begin(), indices.end(),
                         [&table](int left, int right) { return table[left] < table[right]; });
        std::vector<int> result;
        for (int index : indices)
            if (result.empty() || table[result.back()] != table[index]) result.push_back(index);
        return result;
    };
    ids.pieces = sorted_unique_ids(
        std::vector<int>(reachable_pieces.begin(), reachable_pieces.end()), ids.piece_id);
    ids.uses = sorted_unique_ids(
        std::vector<int>(reachable_uses.begin(), reachable_uses.end()), ids.use_id);
    ids.facts = sorted_unique_ids(
        std::vector<int>(reachable_facts.begin(), reachable_facts.end()), ids.fact_id);
    ids.diagnostics = sorted_unique_ids(
        std::vector<int>(reachable_diagnostics.begin(), reachable_diagnostics.end()),
        ids.diagnostic_id);
    ids.piece_index.clear();
    for (int index : ids.pieces) ids.piece_index.emplace(ids.piece_id[index], index);
    ids.use_index.clear();
    for (int index : ids.uses) ids.use_index.emplace(ids.use_id[index], index);
    ids.fact_index.clear();
    for (int index : ids.facts) ids.fact_index.emplace(ids.fact_id[index], index);
    ids.diagnostic_index.clear();
    for (int index : ids.diagnostics) ids.diagnostic_index.emplace(ids.diagnostic_id[index], index);
    ids.root_use = compilation.requirements;
    ids.required_use = compilation.required;
    ids.recommended_use = compilation.recommended;
    ids.ready = true;
    return true;
}


}  // namespace tce
