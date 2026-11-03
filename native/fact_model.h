/* Fact bundle the native prerequisite compiler reads.
 *
 * Holds the course, version, option, rule, module, inferred-set and equivalence facts plus the typed
 * source-position parts. The PostgreSQL loader fills one bundle per open handle.
 */

#pragma once

#include <cstdint>
#include <cstdio>
#include <memory>
#include <string>
#include <unordered_map>
#include <vector>

namespace tce {

enum RuleCode { R_COMPOSITE = 0, R_CREDITS = 1, R_COURSE_UNIT = 2, R_MODULE = 3,
                R_ANY_COURSE = 4, R_ANY_MODULE = 5, R_COUNT = 6 };

struct Member {
    int32_t index = 0;
    bool module = false;
    std::string ref;
};

struct Option {
    int32_t index = 0;
    bool recommended = false;
    std::vector<Member> members;
};

struct SubMember {
    int32_t index = 0;
    std::string group;
    int64_t credits = -1;
};

struct SubOption {
    int32_t index = 0;
    std::vector<SubMember> members;
};

struct Rule {
    int type = -1;
    int32_t sibling = 0;
    int32_t require_min = -1;
    int32_t require_max = -1;
    int32_t all_mandatory = -1;
    int64_t credits_min = -1;
    int64_t credits_max = -1;
    std::string credits_min_text;
    std::string credits_max_text;
    int32_t count_min = -1;
    int32_t count_max = -1;
    std::string ref;
    std::vector<Rule> children;
};

struct Version {
    std::string sisu;
    int32_t validity_start = 0;
    int32_t validity_end = 0;
    std::vector<int32_t> periods;
    int module_type = 0;
    std::string code;
    std::string name_fi;
    std::string name_en;
    bool has_code = false;
    bool has_name_fi = false;
    bool has_name_en = false;
    int64_t target_min = -1;
    int64_t target_max = -1;
    std::string target_min_text;
    std::string target_max_text;
    bool has_rule = false;
    Rule rule;
};

struct CourseRep {
    std::string sisu;
    std::string code;
    std::string name_fi;
    std::string name_en;
    std::string official_url;
    bool has_name_fi = false;
    bool has_name_en = false;
    int64_t credits_min = -1;
    int64_t credits_max = -1;
    std::string credits_min_text;
    std::string credits_max_text;
    std::vector<Option> options;
    std::vector<SubOption> substitutions;
};

struct CourseFact {
    std::string id;
    bool active = false;
    int32_t year = 0;
    bool has_rep = false;
    CourseRep rep;
};

struct ModuleFact {
    std::string id;
    std::vector<Version> versions;
};

enum ExprKind { E_COURSE = 0, E_AND = 1, E_OR = 2, E_NONE = 3 };

struct Expr {
    int kind = E_NONE;
    int origin = 1;              // 0 official, 1 inferred, 2 composed
    int official_kind = -1;      // 0 compulsory, 1 recommended, 2 module_rule, 3 substitution
    int category = -1;           // 0 required, 1 recommended, -1 none
    std::string course;
    std::string inference;       // canonical JSON of InferenceNodeMetadata, empty when absent
    std::vector<Expr> children;
};

struct InferredFact {
    std::string target;
    std::string set_id;
    std::string coverage_state;
    int64_t eligible = 0;
    int64_t processed = 0;
    int64_t accepted = 0;
    bool current = false;
    Expr expression;
};

struct EquivGroup {
    std::string id;
    std::string inference;
    std::vector<std::string> members;
};

struct InferredEntry {
    std::string state;
    bool current = false;
    InferredFact fact;
};

struct Bundle {
    std::unordered_map<std::string, CourseFact> courses;
    std::unordered_map<std::string, ModuleFact> modules;
    std::unordered_map<std::string, InferredEntry> inferred;
    std::unordered_map<std::string, std::vector<EquivGroup>> equivalence;
    /* The evaluator's group ranks index the loaded course set in canonical order. The loader
     * builds them once the closure is complete, and the bundle is read-only afterwards. */
    std::shared_ptr<const std::unordered_map<std::string, int>> ranks;
};

/* One typed source-position part. The native identity payload consumes the same string/integer
 * tuple, so the bundle preserves both the order and the exact value type. */
struct Part {
    bool integer = false;
    std::string text;
    int64_t number = 0;
};

using Path = std::vector<Part>;

inline Part text_part(const std::string &value)
{
    Part part;
    part.text = value;
    return part;
}

inline Part number_part(int64_t value)
{
    Part part;
    part.integer = true;
    part.number = value;
    return part;
}

inline Path extend(Path path, const std::string &value)
{
    path.push_back(text_part(value));
    return path;
}

inline Path extend(Path path, int64_t value)
{
    path.push_back(number_part(value));
    return path;
}

/* Encode one path as the compact JSON payload of an opaque work key. The decoder derives the
 * canonical work identity from it, so the digest algorithm stays in one place. */
inline std::string path_payload(const std::string &module_id, const Path &path)
{
    std::string out = "[";
    auto append_text = [&out](const std::string &value) {
        out.push_back('"');
        for (unsigned char character : value) {
            switch (character) {
                case '"': out += "\\\""; break;
                case '\\': out += "\\\\"; break;
                case '\n': out += "\\n"; break;
                case '\r': out += "\\r"; break;
                case '\t': out += "\\t"; break;
                default:
                    if (character < 0x20) {
                        char buffer[7];
                        std::snprintf(buffer, sizeof(buffer), "\\u%04x", character);
                        out += buffer;
                    } else {
                        out.push_back((char) character);
                    }
            }
        }
        out.push_back('"');
    };
    append_text(module_id);
    out += ",[";
    for (size_t index = 0; index < path.size(); ++index) {
        if (index > 0) out.push_back(',');
        if (path[index].integer) out += std::to_string(path[index].number);
        else append_text(path[index].text);
    }
    out += "]]";
    return out;
}


}  // namespace tce
