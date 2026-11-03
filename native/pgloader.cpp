/* Native PostgreSQL fact loader for the prerequisite compiler.
 *
 * The loader reads the canonical course, version, period, prerequisite, substitution, module, rule,
 * inferred-set and equivalence facts through bounded parameterized queries. It retains one fact
 * bundle per open handle, so repeated requests issue no query. The product compiler and evaluator
 * consume that bundle. The loader writes no data and logs no connection string.
 */

#include <libpq-fe.h>

#include <chrono>
#include <cstdlib>
#include <cstring>
#include <memory>
#include <set>
#include <string>
#include <tuple>
#include <unordered_map>
#include <vector>

#include "canonical_json.h"
#include "fact_model.h"
#include "pipeline.h"
#include "support.h"

using namespace tce;

namespace {

int64_t parse_cents(const char *text)
{
    if (text == nullptr || *text == '\0') return -1;
    bool negative = false;
    const char *cursor = text;
    if (*cursor == '-') {
        negative = true;
        ++cursor;
    }
    int64_t value = 0;
    int digits = 0;
    int fraction = 0;
    while (*cursor >= '0' && *cursor <= '9') {
        value = value * 10 + (*cursor - '0');
        ++cursor;
        ++digits;
    }
    if (*cursor == '.') {
        ++cursor;
        while (*cursor >= '0' && *cursor <= '9' && fraction < 2) {
            value = value * 10 + (*cursor - '0');
            ++cursor;
            ++fraction;
        }
        while (*cursor >= '0' && *cursor <= '9') ++cursor;
        while (fraction < 2) {
            value *= 10;
            ++fraction;
        }
    } else {
        value *= 100;
    }
    if (digits == 0) return -1;
    return negative ? -value : value;
}

int32_t parse_year(const char *text)
{
    if (text == nullptr || *text == '\0') return 0;
    return std::atoi(text);
}

/* A JSON reader for the stored inferred expression tree. */
struct Json {
    enum Kind { NUL, BOOL, NUMBER, STRING, ARRAY, OBJECT } kind = NUL;
    std::string text;
    std::vector<Json> items;
    std::vector<std::pair<std::string, Json>> fields;

    const Json *field(const std::string &name) const
    {
        for (const auto &entry : fields)
            if (entry.first == name) return &entry.second;
        return nullptr;
    }
};

class JsonReader {
public:
    explicit JsonReader(const std::string &text) : text_(text) {}

    bool read(Json &value)
    {
        skip();
        if (!value_at(value)) return false;
        skip();
        return true;
    }

private:
    void skip()
    {
        while (position_ < text_.size()
               && (text_[position_] == ' ' || text_[position_] == '\n'
                   || text_[position_] == '\r' || text_[position_] == '\t'))
            ++position_;
    }

    bool value_at(Json &value)
    {
        skip();
        if (position_ >= text_.size()) return false;
        char current = text_[position_];
        if (current == '{') return object(value);
        if (current == '[') return array(value);
        if (current == '"') {
            value.kind = Json::STRING;
            return string(value.text);
        }
        if (current == 't' || current == 'f') {
            value.kind = Json::BOOL;
            return literal(current == 't' ? "true" : "false");
        }
        if (current == 'n') {
            value.kind = Json::NUL;
            return literal("null");
        }
        value.kind = Json::NUMBER;
        size_t start = position_;
        while (position_ < text_.size()
               && (std::strchr("+-0123456789.eE", text_[position_]) != nullptr))
            ++position_;
        value.text = text_.substr(start, position_ - start);
        return position_ > start;
    }

    bool literal(const char *word)
    {
        size_t length = std::strlen(word);
        if (text_.compare(position_, length, word) != 0) return false;
        position_ += length;
        return true;
    }

    bool string(std::string &out)
    {
        if (text_[position_] != '"') return false;
        ++position_;
        while (position_ < text_.size()) {
            char current = text_[position_++];
            if (current == '"') return true;
            if (current == '\\') {
                if (position_ >= text_.size()) return false;
                char escape = text_[position_++];
                switch (escape) {
                    case 'n': out.push_back('\n'); break;
                    case 't': out.push_back('\t'); break;
                    case 'r': out.push_back('\r'); break;
                    case 'b': out.push_back('\b'); break;
                    case 'f': out.push_back('\f'); break;
                    case 'u': {
                        if (position_ + 4 > text_.size()) return false;
                        unsigned code = (unsigned) std::strtoul(
                            text_.substr(position_, 4).c_str(), nullptr, 16);
                        position_ += 4;
                        if (code < 0x80) {
                            out.push_back((char) code);
                        } else if (code < 0x800) {
                            out.push_back((char) (0xC0 | (code >> 6)));
                            out.push_back((char) (0x80 | (code & 0x3F)));
                        } else {
                            out.push_back((char) (0xE0 | (code >> 12)));
                            out.push_back((char) (0x80 | ((code >> 6) & 0x3F)));
                            out.push_back((char) (0x80 | (code & 0x3F)));
                        }
                        break;
                    }
                    default: out.push_back(escape); break;
                }
            } else {
                out.push_back(current);
            }
        }
        return false;
    }

    bool array(Json &value)
    {
        value.kind = Json::ARRAY;
        ++position_;
        skip();
        if (position_ < text_.size() && text_[position_] == ']') {
            ++position_;
            return true;
        }
        while (position_ < text_.size()) {
            Json item;
            if (!value_at(item)) return false;
            value.items.push_back(std::move(item));
            skip();
            if (position_ >= text_.size()) return false;
            if (text_[position_] == ',') {
                ++position_;
                continue;
            }
            if (text_[position_] == ']') {
                ++position_;
                return true;
            }
            return false;
        }
        return false;
    }

    bool object(Json &value)
    {
        value.kind = Json::OBJECT;
        ++position_;
        skip();
        if (position_ < text_.size() && text_[position_] == '}') {
            ++position_;
            return true;
        }
        while (position_ < text_.size()) {
            skip();
            std::string name;
            if (!string(name)) return false;
            skip();
            if (position_ >= text_.size() || text_[position_] != ':') return false;
            ++position_;
            Json member;
            if (!value_at(member)) return false;
            value.fields.emplace_back(std::move(name), std::move(member));
            skip();
            if (position_ >= text_.size()) return false;
            if (text_[position_] == ',') {
                ++position_;
                continue;
            }
            if (text_[position_] == '}') {
                ++position_;
                return true;
            }
            return false;
        }
        return false;
    }

    std::string text_;
    size_t position_ = 0;
};

/* Render one stored inference object in the exact JSON form Pydantic's
 * `InferenceNodeMetadata.model_dump(mode="json")` produces for identity payloads: sorted keys,
 * default collections written, confidence as canonical fixed-point text. */
bool inference_json(const Json &value, std::string &out)
{
    const Json *confidence = value.field("confidence");
    if (confidence == nullptr
        || (confidence->kind != Json::STRING && confidence->kind != Json::NUMBER))
        return false;
    std::string text = canonical_decimal_text(confidence->text);
    if (text.empty()) return false;
    out = "{\"confidence\":";
    append_json_string(out, text);
    out += ",\"evidence\":[";
    const Json *evidence = value.field("evidence");
    if (evidence != nullptr) {
        if (evidence->kind != Json::ARRAY) return false;
        for (size_t index = 0; index < evidence->items.size(); ++index) {
            const Json &item = evidence->items[index];
            if (item.kind != Json::OBJECT) return false;
            const Json *kind = item.field("kind");
            const Json *reference = item.field("reference_id");
            if (kind == nullptr || kind->kind != Json::STRING || reference == nullptr
                || reference->kind != Json::STRING)
                return false;
            if (index > 0) out.push_back(',');
            out += "{\"kind\":";
            append_json_string(out, kind->text);
            out += ",\"reference_id\":";
            append_json_string(out, reference->text);
            out.push_back('}');
        }
    }
    out += "],\"requirement_ids\":[";
    const Json *requirements = value.field("requirement_ids");
    if (requirements != nullptr) {
        if (requirements->kind != Json::ARRAY) return false;
        for (size_t index = 0; index < requirements->items.size(); ++index) {
            const Json &item = requirements->items[index];
            if (item.kind != Json::STRING) return false;
            if (index > 0) out.push_back(',');
            append_json_string(out, item.text);
        }
    }
    out += "]}";
    return true;
}

std::string canonical_inference(const std::string &text)
{
    if (text.empty()) return text;
    Json value;
    JsonReader reader(text);
    std::string out;
    if (!reader.read(value) || value.kind != Json::OBJECT || !inference_json(value, out))
        return std::string();
    return out;
}

bool parse_expression(const Json &value, Expr &target)
{
    target = Expr();
    const Json *type = value.field("type");
    if (type == nullptr || type->kind != Json::STRING) return false;
    const Json *origin = value.field("origin");
    if (origin != nullptr && origin->kind == Json::STRING) {
        if (origin->text == "official") target.origin = 0;
        else if (origin->text == "inferred") target.origin = 1;
        else if (origin->text == "composed") target.origin = 2;
    }
    const Json *official_kind = value.field("official_kind");
    if (official_kind != nullptr && official_kind->kind == Json::STRING) {
        if (official_kind->text == "compulsory") target.official_kind = 0;
        else if (official_kind->text == "recommended") target.official_kind = 1;
        else if (official_kind->text == "module_rule") target.official_kind = 2;
        else if (official_kind->text == "substitution") target.official_kind = 3;
    }
    const Json *category = value.field("inferred_category");
    if (category != nullptr && category->kind == Json::STRING) {
        if (category->text == "required") target.category = 0;
        else if (category->text == "recommended") target.category = 1;
    }
    const Json *inference = value.field("inference");
    if (inference != nullptr && inference->kind == Json::OBJECT) {
        if (!inference_json(*inference, target.inference)) return false;
    }
    if (type->text == "course") {
        target.kind = E_COURSE;
        const Json *course = value.field("course_group_id");
        if (course == nullptr || course->kind != Json::STRING || course->text.empty())
            return false;
        target.course = course->text;
        return true;
    }
    if (type->text != "and" && type->text != "or") return false;
    target.kind = type->text == "and" ? E_AND : E_OR;
    const Json *children = value.field("children");
    if (children == nullptr || children->kind != Json::ARRAY) return false;
    for (const Json &child : children->items) {
        Expr expression;
        if (!parse_expression(child, expression)) return false;
        target.children.push_back(std::move(expression));
    }
    return true;
}

std::string array_literal(const std::vector<std::string> &values)
{
    std::string result = "{";
    for (size_t index = 0; index < values.size(); ++index) {
        if (index > 0) result.push_back(',');
        result.push_back('"');
        for (char character : values[index]) {
            if (character == '"' || character == '\\') result.push_back('\\');
            result.push_back(character);
        }
        result.push_back('"');
    }
    result.push_back('}');
    return result;
}

bool module_type_code(const char *text, int32_t &code)
{
    if (text == nullptr) {
        set_error("module version has no module type");
        return false;
    }
    std::string value(text);
    if (value == "DegreeProgramme") {
        code = 0;
        return true;
    }
    if (value == "StudyModule") {
        code = 1;
        return true;
    }
    if (value == "GroupingModule") {
        code = 2;
        return true;
    }
    set_error("module version has an unsupported module type: " + value);
    return false;
}


int rule_code(const char *type)
{
    if (type == nullptr) return 255;
    std::string value(type);
    if (value == "CompositeRule") return 0;
    if (value == "CreditsRule") return 1;
    if (value == "CourseUnitRule") return 2;
    if (value == "ModuleRule") return 3;
    if (value == "AnyCourseUnitRule") return 4;
    if (value == "AnyModuleRule") return 5;
    if (value == "CourseUnitCountRule") return 6;
    return 255;
}

bool within_window(int32_t year, int32_t current, int32_t window)
{
    return current - window + 1 <= year && year <= current;
}

struct PgHandle;

struct PackedCacheView {
    PgHandle *handle = nullptr;
};

struct PgHandle {
    PGconn *connection = nullptr;
    Bundle cache;
    std::set<std::string> loaded_courses;
    std::set<std::string> loaded_modules;
    std::set<std::string> inferred_loaded;
    std::set<std::string> equivalence_loaded;
};

std::unordered_map<int, std::unique_ptr<PgHandle>> pg_handles;
int next_pg_handle = 1;

void collect_expression_leaves(const Expr &expression, std::set<std::string> &leaves)
{
    if (expression.kind == E_COURSE) {
        leaves.insert(expression.course);
        return;
    }
    for (const Expr &child : expression.children) collect_expression_leaves(child, leaves);
}

class Loader {
public:
    Loader(PGconn *connection, Bundle &bundle, PackedCacheView cache)
        : connection_(connection), bundle_(bundle), cache_(cache) {}

    bool load(const std::vector<std::string> &candidates, const std::vector<std::string> &chosen)
    {
        std::set<std::string> courses(candidates.begin(), candidates.end());
        courses.insert(chosen.begin(), chosen.end());
        if (cache_.handle != nullptr)
            for (const auto &entry : cache_.handle->cache.courses)
                courses.insert(entry.first);
        if (!load_closure(courses)) return false;
        if (!bundle_.ranks || bundle_.ranks->size() != bundle_.courses.size()) build_ranks();
        return true;
    }

    /* Index every loaded course in canonical order, so the evaluator reads the ranks of the
     * immutable loaded bundle. */
    void build_ranks()
    {
        auto ranks = std::make_shared<std::unordered_map<std::string, int>>();
        std::vector<std::string> ordered;
        ordered.reserve(bundle_.courses.size());
        for (const auto &entry : bundle_.courses) ordered.push_back(entry.first);
        std::sort(ordered.begin(), ordered.end());
        ranks->reserve(ordered.size());
        for (int rank = 0; rank < (int) ordered.size(); ++rank)
            ranks->emplace(ordered[rank], rank);
        bundle_.ranks = std::move(ranks);
    }

private:
    bool load_closure(std::set<std::string> &courses)
    {
        std::set<std::string> module_ids;
        for (;;) {
            bool changed = false;
            std::vector<std::string> missing_courses;
            for (const std::string &course : courses)
                if (bundle_.courses.find(course) == bundle_.courses.end())
                    missing_courses.push_back(course);
            if (!missing_courses.empty()) {
                std::set<std::string> discovered;
                std::set<std::string> discovered_courses;
                if (!load_courses(missing_courses, discovered, discovered_courses)) return false;
                for (const std::string &module : discovered)
                    if (module_ids.insert(module).second) changed = true;
                for (const std::string &course : discovered_courses)
                    if (courses.insert(course).second) changed = true;
            }
            for (;;) {
                std::vector<std::string> pending_modules;
                for (const std::string &module : module_ids)
                    if (bundle_.modules.find(module) == bundle_.modules.end()
                        && modules_done_.count(module) == 0)
                        pending_modules.push_back(module);
                if (pending_modules.empty()) break;
                std::set<std::string> more_modules;
                std::set<std::string> more_courses;
                if (!load_modules(pending_modules, more_modules, more_courses)) return false;
                for (const std::string &module : pending_modules) modules_done_.insert(module);
                for (const std::string &module : more_modules)
                    if (module_ids.insert(module).second) changed = true;
                for (const std::string &course : more_courses)
                    if (courses.insert(course).second) changed = true;
            }
            std::vector<std::string> all(courses.begin(), courses.end());
            if (!load_inferred(all)) return false;
            if (!load_equivalence(all)) return false;
            std::set<std::string> extra;
            for (const std::string &course : all) {
                auto inferred = bundle_.inferred.find(course);
                if (inferred != bundle_.inferred.end() && inferred->second.current)
                    collect_expression_leaves(inferred->second.fact.expression, extra);
                auto groups = bundle_.equivalence.find(course);
                if (groups != bundle_.equivalence.end())
                    for (const EquivGroup &group : groups->second)
                        for (const std::string &member : group.members) extra.insert(member);
            }
            for (const std::string &member : extra)
                if (courses.insert(member).second) changed = true;
            if (!changed) break;
        }
        return true;
    }

    bool load_courses(const std::vector<std::string> &group_ids,
                      std::set<std::string> &module_refs,
                      std::set<std::string> &course_refs);
    bool load_modules(const std::vector<std::string> &group_ids,
                      std::set<std::string> &module_refs,
                      std::set<std::string> &course_refs);
    bool load_inferred(const std::vector<std::string> &group_ids);
    bool load_equivalence(const std::vector<std::string> &group_ids);
    std::set<std::string> inferred_done_;
    std::set<std::string> equivalence_done_;
    std::set<std::string> modules_done_;
    bool query(const char *statement, const std::vector<std::string> &values, PGresult **result);

    PGconn *connection_;
    Bundle &bundle_;
    PackedCacheView cache_;
};

bool Loader::query(const char *statement, const std::vector<std::string> &values,
                   PGresult **result)
{
    std::string literal = array_literal(values);
    const char *parameters[1] = {literal.c_str()};
    *result = PQexecParams(connection_, statement, 1, nullptr, parameters, nullptr, nullptr, 0);
    if (*result == nullptr || PQresultStatus(*result) != PGRES_TUPLES_OK) {
        last_error = *result == nullptr ? PQerrorMessage(connection_)
                                        : PQresultErrorMessage(*result);
        if (*result != nullptr) PQclear(*result);
        *result = nullptr;
        return false;
    }
    return true;
}

bool Loader::load_courses(const std::vector<std::string> &group_ids,
                          std::set<std::string> &module_refs,
                          std::set<std::string> &course_refs)
{
    PGresult *result = nullptr;
    const char *statement =
        "SELECT c.group_id, c.is_active, c.activity_as_of_academic_year_start, "
        "c.activity_window_years, v.id::text, v.sisu_course_unit_id, v.credits_min::text, "
        "v.credits_max::text, v.code, v.name_fi, v.name_en, v.official_url, "
        "v.source_modification_ordinal, cp.academic_year_start "
        "FROM courses c "
        "LEFT JOIN course_versions v ON v.course_id = c.id "
        "LEFT JOIN course_version_curriculum_periods p ON p.course_version_id = v.id "
        "LEFT JOIN curriculum_periods cp ON cp.id = p.curriculum_period_id "
        "WHERE c.group_id = ANY($1::text[]) "
        "ORDER BY c.group_id, v.sisu_course_unit_id, cp.academic_year_start";
    if (!query(statement, group_ids, &result)) return false;

    struct VersionRow {
        std::string id;
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
        int64_t ordinal = -1;
        std::vector<int32_t> periods;
    };
    struct CourseRow {
        bool active = false;
        int32_t year = 0;
        int32_t window = 1;
        std::vector<VersionRow> versions;
    };
    std::unordered_map<std::string, CourseRow> rows;
    for (int index = 0; index < PQntuples(result); ++index) {
        std::string group = PQgetvalue(result, index, 0);
        CourseRow &row = rows[group];
        row.active = PQgetvalue(result, index, 1)[0] == 't';
        row.year = parse_year(PQgetvalue(result, index, 2));
        row.window = std::atoi(PQgetvalue(result, index, 3));
        if (PQgetisnull(result, index, 4)) continue;
        VersionRow version;
        version.id = PQgetvalue(result, index, 4);
        version.sisu = PQgetvalue(result, index, 5);
        if (!PQgetisnull(result, index, 6)) {
            version.credits_min_text = PQgetvalue(result, index, 6);
            version.credits_min = parse_cents(version.credits_min_text.c_str());
        }
        if (!PQgetisnull(result, index, 7)) {
            version.credits_max_text = PQgetvalue(result, index, 7);
            version.credits_max = parse_cents(version.credits_max_text.c_str());
        }
        if (!PQgetisnull(result, index, 8)) version.code = PQgetvalue(result, index, 8);
        if (!PQgetisnull(result, index, 9)) {
            version.name_fi = PQgetvalue(result, index, 9);
            version.has_name_fi = true;
        }
        if (!PQgetisnull(result, index, 10)) {
            version.name_en = PQgetvalue(result, index, 10);
            version.has_name_en = true;
        }
        if (!PQgetisnull(result, index, 11)) version.official_url = PQgetvalue(result, index, 11);
        if (!PQgetisnull(result, index, 12))
            version.ordinal = std::atoll(PQgetvalue(result, index, 12));
        if (!PQgetisnull(result, index, 13))
            version.periods.push_back(parse_year(PQgetvalue(result, index, 13)));
        row.versions.push_back(std::move(version));
    }
    PQclear(result);

    std::unordered_map<std::string, std::string> representative;
    for (const auto &[group, row] : rows) {
        bool found = false;
        std::string best_source;
        std::string best_version;
        std::tuple<int, int32_t, int64_t, std::string> best;
        for (const VersionRow &version : row.versions) {
            int32_t year = -1;
            for (int32_t period : version.periods)
                if (period <= row.year && period > year) year = period;
            if (year < 0) continue;
            int kind = year == row.year ? 2 : (within_window(year, row.year, row.window) ? 1 : 0);
            auto candidate = std::make_tuple(kind, year, version.ordinal, version.sisu);
            if (!found || candidate > best) {
                found = true;
                best = candidate;
                best_source = version.sisu;
                best_version = version.id;
            }
        }
        if (found) representative[group] = best_version;
    }

    std::vector<std::string> version_ids;
    for (const auto &[group, version] : representative) version_ids.push_back(version);

    std::unordered_map<std::string, std::vector<Option>> options;
    std::unordered_map<std::string, std::vector<SubOption>> substitutions;
    if (!version_ids.empty()) {
        const char *option_statement =
            "SELECT o.target_course_version_id::text, o.id::text, o.option_index, "
            "o.requirement_kind, m.member_index, m.member_type, m.referenced_group_id "
            "FROM official_prerequisite_options o "
            "LEFT JOIN official_prerequisite_option_members m "
            "ON m.prerequisite_option_id = o.id "
            "WHERE o.target_course_version_id = ANY($1::uuid[]) "
            "ORDER BY o.target_course_version_id, o.requirement_kind, o.option_index, "
            "m.member_index";
        if (!query(option_statement, version_ids, &result)) return false;
        std::unordered_map<std::string, std::unordered_map<std::string, size_t>> by_option;
        for (int index = 0; index < PQntuples(result); ++index) {
            std::string version = PQgetvalue(result, index, 0);
            std::string option_id = PQgetvalue(result, index, 1);
            auto &items = options[version];
            auto found = by_option[version].find(option_id);
            size_t slot;
            if (found == by_option[version].end()) {
                Option option;
                option.index = std::atoi(PQgetvalue(result, index, 2));
                option.recommended = std::string(PQgetvalue(result, index, 3)) == "recommended";
                items.push_back(std::move(option));
                slot = items.size() - 1;
                by_option[version][option_id] = slot;
            } else {
                slot = found->second;
            }
            if (PQgetisnull(result, index, 4)) continue;
            Option &option = items[slot];
            Member member;
            member.index = std::atoi(PQgetvalue(result, index, 4));
            member.module = std::string(PQgetvalue(result, index, 5)) == "module";
            member.ref = PQgetvalue(result, index, 6);
            if (member.module) module_refs.insert(member.ref);
            else course_refs.insert(member.ref);
            option.members.push_back(std::move(member));
        }
        PQclear(result);

        const char *substitution_statement =
            "SELECT o.source_course_version_id::text, o.id::text, o.option_index, "
            "m.member_index, m.course_group_id, m.credits::text "
            "FROM official_substitution_options o "
            "LEFT JOIN official_substitution_option_members m "
            "ON m.substitution_option_id = o.id "
            "WHERE o.source_course_version_id = ANY($1::uuid[]) "
            "ORDER BY o.source_course_version_id, o.option_index, m.member_index";
        if (!query(substitution_statement, version_ids, &result)) return false;
        std::unordered_map<std::string, std::unordered_map<std::string, size_t>> by_sub;
        for (int index = 0; index < PQntuples(result); ++index) {
            std::string version = PQgetvalue(result, index, 0);
            std::string option_id = PQgetvalue(result, index, 1);
            auto &items = substitutions[version];
            auto found = by_sub[version].find(option_id);
            size_t slot;
            if (found == by_sub[version].end()) {
                SubOption option;
                option.index = std::atoi(PQgetvalue(result, index, 2));
                items.push_back(std::move(option));
                slot = items.size() - 1;
                by_sub[version][option_id] = slot;
            } else {
                slot = found->second;
            }
            if (PQgetisnull(result, index, 3)) continue;
            SubOption &option = items[slot];
            SubMember member;
            member.index = std::atoi(PQgetvalue(result, index, 3));
            member.group = PQgetvalue(result, index, 4);
            member.credits = PQgetisnull(result, index, 5) ? -1
                                                           : parse_cents(PQgetvalue(result, index, 5));
            course_refs.insert(member.group);
            option.members.push_back(std::move(member));
        }
        PQclear(result);
    }

    for (const auto &[group, row] : rows) {
        CourseFact course;
        course.id = group;
        course.active = row.active;
        course.year = row.year;
        auto rep = representative.find(group);
        if (rep != representative.end()) {
            const VersionRow *selected = nullptr;
            for (const VersionRow &version : row.versions)
                if (version.id == rep->second) selected = &version;
            if (selected != nullptr) {
                course.has_rep = true;
                course.rep.sisu = selected->sisu;
                course.rep.code = selected->code;
                course.rep.name_fi = selected->name_fi;
                course.rep.name_en = selected->name_en;
                course.rep.has_name_fi = selected->has_name_fi;
                course.rep.has_name_en = selected->has_name_en;
                course.rep.official_url = selected->official_url;
                course.rep.credits_min = selected->credits_min;
                course.rep.credits_max = selected->credits_max;
                course.rep.credits_min_text = selected->credits_min_text;
                course.rep.credits_max_text = selected->credits_max_text;
                auto option_rows = options.find(selected->id);
                if (option_rows != options.end()) {
                    course.rep.options = option_rows->second;
                    std::sort(course.rep.options.begin(), course.rep.options.end(),
                              [](const Option &left, const Option &right) {
                                  return left.index < right.index;
                              });
                }
                auto substitution_rows = substitutions.find(selected->id);
                if (substitution_rows != substitutions.end())
                    course.rep.substitutions = substitution_rows->second;
            }
        }
        bundle_.courses.emplace(group, std::move(course));
    }
    return true;
}

bool Loader::load_modules(const std::vector<std::string> &group_ids,
                          std::set<std::string> &module_refs,
                          std::set<std::string> &course_refs)
{
    PGresult *result = nullptr;
    const char *statement =
        "SELECT mo.group_id, mv.id::text, mv.sisu_module_id, mv.module_type, mv.code, "
        "mv.name_fi, mv.name_en, mv.validity_start::text, mv.validity_end::text, "
        "mv.target_credits_min::text, mv.target_credits_max::text, cp.academic_year_start "
        "FROM modules mo "
        "JOIN module_versions mv ON mv.module_id = mo.id "
        "LEFT JOIN module_version_curriculum_periods p ON p.module_version_id = mv.id "
        "LEFT JOIN curriculum_periods cp ON cp.id = p.curriculum_period_id "
        "WHERE mo.group_id = ANY($1::text[]) "
        "ORDER BY mo.group_id, mv.sisu_module_id, cp.academic_year_start";
    if (!query(statement, group_ids, &result)) return false;

    struct VersionRow {
        std::string id;
        std::string sisu;
        std::string code;
        std::string name_fi;
        std::string name_en;
        bool has_code = false;
        bool has_name_fi = false;
        bool has_name_en = false;
        int32_t module_type = 1;
        int32_t start = 0;
        int32_t end = 0;
        int64_t target_min = -1;
        int64_t target_max = -1;
        std::string target_min_text;
        std::string target_max_text;
        std::vector<int32_t> periods;
    };
    std::unordered_map<std::string, std::vector<VersionRow>> rows;
    std::vector<std::string> version_ids;
    for (int index = 0; index < PQntuples(result); ++index) {
        std::string group = PQgetvalue(result, index, 0);
        auto &items = rows[group];
        std::string id = PQgetvalue(result, index, 1);
        if (items.empty() || items.back().id != id) {
            VersionRow version;
            version.id = id;
            version.sisu = PQgetvalue(result, index, 2);
            if (!module_type_code(PQgetvalue(result, index, 3), version.module_type)) {
                PQclear(result);
                return false;
            }
            if (!PQgetisnull(result, index, 4)) {
                version.code = PQgetvalue(result, index, 4);
                version.has_code = true;
            }
            if (!PQgetisnull(result, index, 5)) {
                version.name_fi = PQgetvalue(result, index, 5);
                version.has_name_fi = true;
            }
            if (!PQgetisnull(result, index, 6)) {
                version.name_en = PQgetvalue(result, index, 6);
                version.has_name_en = true;
            }
            version.start = parse_year(PQgetvalue(result, index, 7));
            version.end = parse_year(PQgetvalue(result, index, 8));
            if (!PQgetisnull(result, index, 9)) {
                version.target_min_text = PQgetvalue(result, index, 9);
                version.target_min = parse_cents(version.target_min_text.c_str());
            }
            if (!PQgetisnull(result, index, 10)) {
                version.target_max_text = PQgetvalue(result, index, 10);
                version.target_max = parse_cents(version.target_max_text.c_str());
            }
            items.push_back(std::move(version));
            version_ids.push_back(id);
        }
        if (!PQgetisnull(result, index, 11))
            items.back().periods.push_back(parse_year(PQgetvalue(result, index, 11)));
    }
    PQclear(result);

    struct RuleRow {
        std::string id;
        std::string parent;
        int32_t sibling = 0;
        int type = 255;
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
    };
    std::unordered_map<std::string, std::vector<RuleRow>> rules;
    if (!version_ids.empty()) {
        const char *rule_statement =
            "SELECT module_version_id::text, id::text, parent_node_id::text, sibling_position, "
            "node_type, require_min, require_max, all_mandatory, credits_min::text, "
            "credits_max::text, count_min, count_max, referenced_group_id "
            "FROM module_rule_nodes WHERE module_version_id = ANY($1::uuid[]) "
            "ORDER BY module_version_id, parent_node_id NULLS FIRST, sibling_position";
        if (!query(rule_statement, version_ids, &result)) return false;
        for (int index = 0; index < PQntuples(result); ++index) {
            RuleRow row;
            std::string version = PQgetvalue(result, index, 0);
            row.id = PQgetvalue(result, index, 1);
            if (!PQgetisnull(result, index, 2)) row.parent = PQgetvalue(result, index, 2);
            row.sibling = std::atoi(PQgetvalue(result, index, 3));
            row.type = rule_code(PQgetvalue(result, index, 4));
            if (!PQgetisnull(result, index, 5)) row.require_min = std::atoi(PQgetvalue(result, index, 5));
            if (!PQgetisnull(result, index, 6)) row.require_max = std::atoi(PQgetvalue(result, index, 6));
            if (!PQgetisnull(result, index, 7))
                row.all_mandatory = std::string(PQgetvalue(result, index, 7)) == "t" ? 1 : 0;
            if (!PQgetisnull(result, index, 8)) {
                row.credits_min_text = PQgetvalue(result, index, 8);
                row.credits_min = parse_cents(row.credits_min_text.c_str());
            }
            if (!PQgetisnull(result, index, 9)) {
                row.credits_max_text = PQgetvalue(result, index, 9);
                row.credits_max = parse_cents(row.credits_max_text.c_str());
            }
            if (!PQgetisnull(result, index, 10)) row.count_min = std::atoi(PQgetvalue(result, index, 10));
            if (!PQgetisnull(result, index, 11)) row.count_max = std::atoi(PQgetvalue(result, index, 11));
            if (!PQgetisnull(result, index, 12)) row.ref = PQgetvalue(result, index, 12);
            if (row.type == 2) course_refs.insert(row.ref);
            else if (row.type == 3) module_refs.insert(row.ref);
            rules[version].push_back(std::move(row));
        }
        PQclear(result);
    }

    auto build = [&](const std::vector<RuleRow> &rows, const std::string &id,
                     auto &&self) -> Rule {
        const RuleRow *row = nullptr;
        for (const RuleRow &candidate : rows)
            if (candidate.id == id) row = &candidate;
        Rule rule;
        if (row == nullptr) return rule;
        rule.type = row->type;
        rule.sibling = row->sibling;
        rule.require_min = row->require_min;
        rule.require_max = row->require_max;
        rule.all_mandatory = row->all_mandatory;
        rule.credits_min = row->credits_min;
        rule.credits_max = row->credits_max;
        rule.credits_min_text = row->credits_min_text;
        rule.credits_max_text = row->credits_max_text;
        rule.count_min = row->count_min;
        rule.count_max = row->count_max;
        rule.ref = row->ref;
        std::vector<const RuleRow *> children;
        for (const RuleRow &candidate : rows)
            if (candidate.parent == row->id && candidate.id != row->id) children.push_back(&candidate);
        std::sort(children.begin(), children.end(), [](const RuleRow *left, const RuleRow *right) {
            return left->sibling < right->sibling;
        });
        for (const RuleRow *child : children) rule.children.push_back(self(rows, child->id, self));
        return rule;
    };

    for (const auto &[group, versions] : rows) {
        ModuleFact module;
        module.id = group;
        for (const VersionRow &row : versions) {
            Version version;
            version.sisu = row.sisu;
            version.module_type = row.module_type;
            version.code = row.code;
            version.name_fi = row.name_fi;
            version.name_en = row.name_en;
            version.has_code = row.has_code;
            version.has_name_fi = row.has_name_fi;
            version.has_name_en = row.has_name_en;
            version.validity_start = row.start;
            version.validity_end = row.end;
            version.periods = row.periods;
            version.target_min = row.target_min;
            version.target_max = row.target_max;
            version.target_min_text = row.target_min_text;
            version.target_max_text = row.target_max_text;
            auto rule_rows = rules.find(row.id);
            if (rule_rows != rules.end()) {
                const RuleRow *root = nullptr;
                for (const RuleRow &candidate : rule_rows->second)
                    if (candidate.parent.empty()) {
                        root = &candidate;
                        break;
                    }
                if (root != nullptr) {
                    version.has_rule = true;
                    version.rule = build(rule_rows->second, root->id, build);
                }
            }
            module.versions.push_back(std::move(version));
        }
        bundle_.modules.emplace(group, std::move(module));
    }
    return true;
}

bool Loader::load_inferred(const std::vector<std::string> &group_ids)
{
    std::vector<std::string> pending;
    for (const std::string &group : group_ids)
        if (inferred_done_.count(group) == 0
            && (cache_.handle == nullptr || cache_.handle->inferred_loaded.count(group) == 0))
            pending.push_back(group);
    if (pending.empty()) return true;
    PGresult *result = nullptr;
    const char *statement =
        "SELECT c.group_id, c.is_active, c.activity_as_of_academic_year_start, "
        "c.activity_window_years, s.id::text, s.producer_kind, "
        "s.activity_as_of_academic_year_start, s.activity_window_years, s.expression::text, "
        "s.coverage_state, s.eligible_source_count, s.processed_source_count, "
        "s.accepted_source_count "
        "FROM courses c JOIN inferred_prerequisite_sets s ON s.target_course_id = c.id "
        "WHERE c.group_id = ANY($1::text[])";
    if (!query(statement, pending, &result)) return false;
    for (int index = 0; index < PQntuples(result); ++index) {
        std::string group = PQgetvalue(result, index, 0);
        bool active = PQgetvalue(result, index, 1)[0] == 't';
        int32_t course_year = parse_year(PQgetvalue(result, index, 2));
        int32_t course_window = std::atoi(PQgetvalue(result, index, 3));
        std::string producer = PQgetvalue(result, index, 5);
        int32_t set_year = parse_year(PQgetvalue(result, index, 6));
        int32_t set_window = std::atoi(PQgetvalue(result, index, 7));
        bool context_matches = set_year == course_year && set_window == course_window;
        InferredEntry entry;
        bool stale = !active || (producer != "inference" && !context_matches);
        entry.state = stale ? "stale_activity_context" : "current";
        entry.current = !stale;
        if (!stale) {
            entry.fact.target = group;
            entry.fact.set_id = PQgetvalue(result, index, 4);
            entry.fact.current = true;
            entry.fact.coverage_state = PQgetvalue(result, index, 9);
            entry.fact.eligible = std::atoll(PQgetvalue(result, index, 10));
            entry.fact.processed = std::atoll(PQgetvalue(result, index, 11));
            entry.fact.accepted = std::atoll(PQgetvalue(result, index, 12));
            if (!PQgetisnull(result, index, 8)) {
                Json json;
                JsonReader reader(PQgetvalue(result, index, 8));
                if (!reader.read(json)) {
                    std::string snippet(PQgetvalue(result, index, 8));
                    if (snippet.size() > 400) snippet.resize(400);
                    last_error = "stored inferred expression is not valid JSON: " + snippet;
                    PQclear(result);
                    return false;
                }
                if (!parse_expression(json, entry.fact.expression)) {
                    last_error = "stored inferred expression has an unsupported node";
                    PQclear(result);
                    return false;
                }
            }
        }
        bundle_.inferred[group] = std::move(entry);
    }
    PQclear(result);
    for (const std::string &group : pending) {
        if (bundle_.inferred.find(group) == bundle_.inferred.end()) {
            InferredEntry entry;
            entry.state = "unavailable";
            bundle_.inferred[group] = std::move(entry);
        }
        inferred_done_.insert(group);
        if (cache_.handle != nullptr) cache_.handle->inferred_loaded.insert(group);
    }
    return true;
}

bool Loader::load_equivalence(const std::vector<std::string> &group_ids)
{
    std::vector<std::string> pending;
    for (const std::string &group : group_ids)
        if (equivalence_done_.count(group) == 0
            && (cache_.handle == nullptr || cache_.handle->equivalence_loaded.count(group) == 0))
            pending.push_back(group);
    if (pending.empty()) return true;
    PGresult *result = nullptr;
    const char *statement =
        "SELECT cm.group_id, g.id::text, g.inference::text, cm2.group_id "
        "FROM inferred_equivalence_group_members m "
        "JOIN courses cm ON cm.id = m.course_id "
        "JOIN inferred_equivalence_groups g ON g.id = m.equivalence_group_id "
        "JOIN inferred_equivalence_group_members m2 ON m2.equivalence_group_id = g.id "
        "JOIN courses cm2 ON cm2.id = m2.course_id "
        "WHERE cm.group_id = ANY($1::text[]) "
        "ORDER BY cm.group_id, g.id, cm2.group_id";
    if (!query(statement, pending, &result)) return false;
    std::unordered_map<std::string, std::vector<EquivGroup>> groups;
    std::unordered_map<std::string, std::unordered_map<std::string, size_t>> index;
    for (int index_row = 0; index_row < PQntuples(result); ++index_row) {
        std::string member = PQgetvalue(result, index_row, 0);
        std::string group = PQgetvalue(result, index_row, 1);
        std::string inference = PQgetisnull(result, index_row, 2) ? ""
            : PQgetvalue(result, index_row, 2);
        if (!inference.empty()) {
            std::string canonical = canonical_inference(inference);
            if (canonical.empty()) {
                last_error = "stored equivalence-group inference is not a valid metadata object";
                PQclear(result);
                return false;
            }
            inference = std::move(canonical);
        }
        std::string other = PQgetvalue(result, index_row, 3);
        auto &values = groups[member];
        auto found = index[member].find(group);
        size_t slot;
        if (found == index[member].end()) {
            EquivGroup entry;
            entry.id = group;
            entry.inference = inference;
            values.push_back(std::move(entry));
            slot = values.size() - 1;
            index[member][group] = slot;
        } else {
            slot = found->second;
        }
        values[slot].members.push_back(other);
    }
    PQclear(result);
    for (const std::string &group : pending) {
        auto found = groups.find(group);
        if (found != groups.end()) bundle_.equivalence[group] = found->second;
        equivalence_done_.insert(group);
        if (cache_.handle != nullptr) cache_.handle->equivalence_loaded.insert(group);
    }
    return true;
}

}  // namespace

namespace tce {

namespace {

PgHandle *handle_of(int handle)
{
    auto found = pg_handles.find(handle);
    if (found == pg_handles.end()) {
        last_error = "native database loader handle is not open";
        return nullptr;
    }
    return found->second.get();
}

}  // namespace

int open_database_handle(const std::string &conninfo)
{
    PGconn *connection = PQconnectdb(conninfo.c_str());
    if (connection == nullptr || PQstatus(connection) != CONNECTION_OK) {
        last_error = connection == nullptr ? "libpq could not allocate a connection"
                                           : PQerrorMessage(connection);
        if (connection != nullptr) PQfinish(connection);
        return -1;
    }
    auto handle = std::make_unique<PgHandle>();
    handle->connection = connection;
    int value = next_pg_handle++;
    pg_handles.emplace(value, std::move(handle));
    return value;
}

void close_database_handle(int handle)
{
    auto found = pg_handles.find(handle);
    if (found == pg_handles.end()) return;
    PQfinish(found->second->connection);
    pg_handles.erase(found);
}

/* Load the fact closure for one candidate array and return the retained bundle. */
Bundle *load_database_facts(int handle, const std::vector<std::string> &targets,
                            const std::vector<std::string> &chosen)
{
    PgHandle *state = handle_of(handle);
    if (state == nullptr) return nullptr;
    std::set<std::string> closure(targets.begin(), targets.end());
    closure.insert(chosen.begin(), chosen.end());
    std::vector<std::string> candidates(closure.begin(), closure.end());
    PackedCacheView view;
    view.handle = state;
    Loader loader(state->connection, state->cache, view);
    if (!loader.load(candidates, chosen)) return nullptr;
    return &state->cache;
}

}  // namespace tce
