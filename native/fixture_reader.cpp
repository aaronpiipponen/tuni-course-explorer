/* Fixture record reader for hand-built prerequisite structures.
 *
 * Reads an ordered record bundle and constructs the compiled structures that the native identity,
 * projection and record-view path consumes without a database handle. Test fixtures supply the
 * records.
 */

#include <cstdint>
#include <string>
#include <utility>
#include <vector>

#include "fact_model.h"
#include "fixture_reader.h"
#include "records.h"
#include "support.h"

namespace tce {

/* Record-bundle reader for hand-built fixture structures. The production compiler builds the same
 * `Compilation` in memory. This adapter lets a caller supply equivalent ordered records and then
 * runs the one finalize, projection and view path. */
class RecordReader {
public:
    RecordReader(const char *data, size_t size) : data_(data), size_(size) {}

    bool ok() const { return ok_; }

    uint8_t u8()
    {
        if (position_ + 1 > size_) return fail();
        return (uint8_t) data_[position_++];
    }
    uint32_t u32()
    {
        if (position_ + 4 > size_) return fail32();
        uint32_t value = 0;
        for (int index = 0; index < 4; ++index)
            value |= (uint32_t) (uint8_t) data_[position_ + (size_t) index] << (8 * index);
        position_ += 4;
        return value;
    }
    int32_t i32() { return (int32_t) u32(); }
    int64_t i64()
    {
        uint64_t value = 0;
        for (int index = 0; index < 8; ++index) value |= (uint64_t) u8() << (8 * index);
        return (int64_t) value;
    }
    std::string text()
    {
        uint32_t length = u32();
        if (!ok_ || position_ + length > size_) return fail_text();
        std::string value(data_ + position_, length);
        position_ += length;
        return value;
    }
    std::vector<std::string> strings()
    {
        std::vector<std::string> values;
        uint32_t count = u32();
        if (count > size_) return fail_strings();
        values.reserve(count);
        for (uint32_t index = 0; index < count; ++index) values.push_back(text());
        return values;
    }

private:
    uint8_t fail() { ok_ = false; return 0; }
    uint32_t fail32() { ok_ = false; return 0; }
    int64_t fail64() { ok_ = false; return 0; }
    std::string fail_text() { ok_ = false; return {}; }
    std::vector<std::string> fail_strings() { ok_ = false; return {}; }

    const char *data_;
    size_t size_;
    size_t position_ = 0;
    bool ok_ = true;
};

std::unique_ptr<Compiled> read_records(const char *data, size_t size)
{
    RecordReader reader(data, size);
    if (reader.u32() != 1) {
        set_error("fixture record bundle has an unknown format version");
        return nullptr;
    }
    uint32_t count = reader.u32();
    if (count == 0 || count > 4096) {
        set_error("fixture record bundle has an unsupported structure count");
        return nullptr;
    }
    auto compiled = std::make_unique<Compiled>();
    for (uint32_t item = 0; item < count; ++item) {
        Compilation compilation;
        compilation.root = reader.text();
        compilation.year = reader.i32();
        compilation.active_only = reader.u8() != 0;
        compilation.include_recommended = reader.u8() != 0;
        compilation.include_inferred = reader.u8() != 0;
        compilation.requirements = reader.i32();
        uint32_t extra_root_count = reader.u32();
        for (uint32_t index = 0; index < extra_root_count; ++index)
            compilation.extra_roots.push_back(reader.i32());
        uint32_t node_count = reader.u32();
        if (!reader.ok() || node_count > 200000) {
            set_error("fixture record bundle has an unsupported node count");
            return nullptr;
        }
        for (uint32_t index = 0; index < node_count; ++index) {
            Node node;
            node.kind = reader.u8();
            uint32_t child_count = reader.u32();
            for (uint32_t child = 0; child < child_count; ++child)
                node.children.push_back(reader.i32());
            node.course = reader.text();
            node.module = reader.text();
            std::string work_key = reader.text();
            node.referenced = reader.text();
            node.detail = reader.text();
            node.reason = reader.text();
            node.credits_min_text = reader.text();
            node.credits_max_text = reader.text();
            node.manual_min_text = reader.text();
            node.require_min = reader.i32();
            node.require_max = reader.i32();
            node.count_min = reader.i32();
            node.count_max = reader.i32();
            node.module_rule = reader.u8() != 0;
            node.cycle = reader.u8() != 0;
            node.prov.origin = reader.u8();
            int official_kind = reader.u8();
            node.prov.official_kind = official_kind == 255 ? -1 : official_kind;
            int inferred_category = reader.u8();
            node.prov.inferred_category = inferred_category == 255 ? -1 : inferred_category;
            node.prov.inference = reader.text();
            uint32_t part_count = reader.u32();
            Path source;
            for (uint32_t part = 0; part < part_count; ++part) {
                bool integer = reader.u8() != 0;
                if (integer) source.push_back(number_part(reader.i64()));
                else source.push_back(text_part(reader.text()));
            }
            node.use_members = reader.strings();
            node.use_diagnostics = {};
            if (!reader.ok()) {
                set_error("fixture record bundle is truncated");
                return nullptr;
            }
            compilation.nodes.push_back(std::move(node));
            compilation.fixture_work_keys.push_back(std::move(work_key));
            FactRecord fact;
            const Node &stored = compilation.nodes.back();
            fact.origin = stored.prov.origin;
            fact.official_kind = stored.prov.official_kind;
            fact.inferred_category = stored.prov.inferred_category;
            fact.inference = stored.prov.inference;
            compilation.facts.push_back(std::move(fact));
            UseRecord use;
            use.piece = (int) index;
            use.fact = (int) index;
            use.children = compilation.nodes.back().children;
            use.source = std::move(source);
            use.members = compilation.nodes.back().use_members;
            compilation.uses.push_back(std::move(use));
        }
        uint32_t course_count = reader.u32();
        for (uint32_t index = 0; index < course_count; ++index) {
            CourseSummaryRec summary;
            summary.group = reader.text();
            summary.has_name_fi = reader.u8() != 0;
            summary.name_fi = reader.text();
            summary.has_name_en = reader.u8() != 0;
            summary.name_en = reader.text();
            summary.code = reader.text();
            summary.official_url = reader.text();
            summary.credits_min_text = reader.text();
            summary.credits_min = -1;
            summary.has_credits_max = reader.u8() != 0;
            summary.credits_max_text = reader.text();
            summary.credits_max = -1;
            summary.active = reader.u8() != 0;
            compilation.summaries[summary.group] = std::move(summary);
        }
        uint32_t module_count = reader.u32();
        for (uint32_t index = 0; index < module_count; ++index) {
            ModuleSummaryRec summary;
            summary.group = reader.text();
            summary.sisu = reader.text();
            summary.module_type = reader.text();
            summary.has_code = reader.u8() != 0;
            summary.code = reader.text();
            summary.has_name_fi = reader.u8() != 0;
            summary.name_fi = reader.text();
            summary.has_name_en = reader.u8() != 0;
            summary.name_en = reader.text();
            compilation.modules[summary.group] = std::move(summary);
        }
        uint32_t coverage_count = reader.u32();
        for (uint32_t index = 0; index < coverage_count; ++index) {
            CoverageRecord record;
            record.target = reader.text();
            record.state = reader.text();
            record.eligible = reader.i64();
            record.processed = reader.i64();
            record.accepted = reader.i64();
            compilation.coverage.push_back(std::move(record));
        }
        compilation.excluded_group_ids = reader.strings();
        compilation.completed_node_keys = reader.strings();
        compilation.excluded_node_keys = reader.strings();
        uint32_t root_diagnostic_count = reader.u32();
        for (uint32_t index = 0; index < root_diagnostic_count; ++index)
            compilation.root_diagnostics.push_back(reader.i32());
        if (!reader.ok()) {
            set_error("fixture record bundle is truncated");
            return nullptr;
        }
        compiled->compilations.push_back(std::move(compilation));
    }
    if (!reader.ok()) {
        set_error("fixture record bundle is truncated");
        return nullptr;
    }
    return compiled;
}


}  // namespace tce
