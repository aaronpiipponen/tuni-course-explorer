/* C interface of the native prerequisite serving library.
 *
 * Exposes the database fact handle, one compile call and one eligibility evaluation call. The
 * shared library interface unit holds the format version, error text, structure-record accessor
 * and bundle release. The entry points decode the caller's key blobs and hand the work to the
 * loader and the compiler. The returned bundle owns the compiled structures.
 */

#include <cstdint>
#include <memory>
#include <string>
#include <string_view>
#include <unordered_set>
#include <utility>
#include <vector>

#include "bundle.h"
#include "pipeline.h"
#include "support.h"

namespace tce {

std::string_view decode_key(const char *blob, const int64_t *offsets, int index)
{
    return std::string_view(blob + offsets[index], offsets[index + 1] - offsets[index]);
}

namespace {

std::vector<std::string> keys(const char *blob, const int64_t *offsets, int count)
{
    std::vector<std::string> values;
    values.reserve(count);
    for (int index = 0; index < count; ++index)
        values.emplace_back(decode_key(blob, offsets, index));
    return values;
}

}  // namespace

}  // namespace tce

extern "C" {

/* Open one libpq connection and return the handle that names it, or -1 with the error text set. */
int course_prerequisite_open(const char *conninfo)
{
    if (conninfo == nullptr) {
        tce::set_error("native database loader needs a connection string");
        return -1;
    }
    return tce::open_database_handle(conninfo);
}

/* Close one open handle and release its connection. An unknown handle is ignored. */
void course_prerequisite_close(int handle) { tce::close_database_handle(handle); }

/* Evaluate one opened bundle against a basis and write one outcome per structure.
 *
 * ``basis_blob`` packs ``basis_count`` keys as bytes and ``basis_offsets`` holds
 * ``basis_count + 1`` byte offsets, so key i spans offsets[i] to offsets[i + 1]. ``outcomes`` holds
 * ``capacity`` records. The call returns -1 with the error text set when the bundle is null or not
 * open, when the bundle holds more structures than ``capacity``, or when a course summary is
 * absent. ``mode`` 0 keeps a structure whose requirements are all covered and 1 keeps one with any
 * requirement covered. The return value is the number of records written.
 */
int course_prerequisite_evaluate(const void *pointer, const char *basis_blob,
                                 const int64_t *basis_offsets, int basis_count, int mode,
                                 NativeOutcome *outcomes, int capacity)
{
    auto holder = static_cast<const tce::StructureBundle *>(pointer);
    if (holder == nullptr || holder->compiled == nullptr) {
        tce::set_error("native structure bundle is not open");
        return -1;
    }
    std::unordered_set<std::string> basis;
    for (int index = 0; index < basis_count; ++index)
        basis.emplace(tce::decode_key(basis_blob, basis_offsets, index));
    return tce::evaluate_bundle(*holder, basis, mode, outcomes, capacity);
}

/* Load the fact closure for one candidate array and return a new structure bundle.
 *
 * ``handle`` is an open database handle. ``targets``, ``chosen``, ``excluded``, ``completed`` and
 * ``excluded_keys`` are packed key arrays, each with ``count`` keys and ``count + 1`` offsets.
 * Every flag argument is nonzero for true, and ``direct_only`` also includes the recommended
 * prerequisites. ``projection`` 0 builds the full structure and 1 the discovery summary, and
 * ``project`` adds the drawing records of a full structure. The caller owns the returned bundle and
 * releases it with course_prerequisite_free_bundle. A null return leaves any failure text in
 * course_prerequisite_last_error.
 */
void *course_prerequisite_compile_bundle(
    int handle, const char *target_blob, const int64_t *target_offsets, int target_count,
    const char *chosen_blob, const int64_t *chosen_offsets, int chosen_count, int active_only,
    int include_recommended, int include_inferred, int direct_only, const char *excluded_blob,
    const int64_t *excluded_offsets, int excluded_count, const char *completed_blob,
    const int64_t *completed_offsets, int completed_count, const char *excluded_keys_blob,
    const int64_t *excluded_keys_offsets, int excluded_keys_count, int projection, int project)
{
    std::vector<std::string> targets = tce::keys(target_blob, target_offsets, target_count);
    std::vector<std::string> chosen = tce::keys(chosen_blob, chosen_offsets, chosen_count);
    std::vector<std::string> excluded = tce::keys(excluded_blob, excluded_offsets, excluded_count);
    std::vector<std::string> completed =
        tce::keys(completed_blob, completed_offsets, completed_count);
    std::vector<std::string> excluded_keys =
        tce::keys(excluded_keys_blob, excluded_keys_offsets, excluded_keys_count);
    const tce::Bundle *bundle = tce::load_database_facts(handle, targets, chosen);
    if (bundle == nullptr) return nullptr;
    std::unique_ptr<tce::Compiled> compiled(static_cast<tce::Compiled *>(tce::compile_bundle(
        *bundle, targets, chosen, active_only != 0, include_recommended != 0,
        include_inferred != 0, direct_only != 0, excluded, completed, excluded_keys, projection,
        project != 0)));
    if (!compiled) return nullptr;
    return tce::write_structure_bundle(std::move(compiled));
}

}  // extern "C"
