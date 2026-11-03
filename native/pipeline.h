/* Internal interfaces between the native prerequisite translation units. */

#pragma once

#include <initializer_list>
#include <memory>
#include <string>
#include <string_view>
#include <unordered_set>
#include <vector>

#include "fact_model.h"
#include "bundle.h"
#include "c_records.h"
#include "records.h"

namespace tce {

/* Hash the reachable records and freeze the identity tables in identity order, returning false with
 * the error text set when a graph is not topologically ordered. */
bool finalize_identities(Compilation &compilation);

/* Return the 24-character SHA-256 prefix of one canonical payload. */
std::string digest_payload(const std::string &canonical);

/* Return the digest of the JSON array that holds the given strings in order. */
std::string digest_strings(std::initializer_list<std::string> values);

/* Append a bound as a JSON string, or null when the value is negative. */
void append_canonical_bound(std::string &out, int32_t value);

/* Return key ``index`` of a packed blob, which spans offsets[index] to offsets[index + 1]. */
std::string_view decode_key(const char *blob, const int64_t *offsets, int index);

/* Open one libpq connection and return its nonzero handle, or -1 with the error text set. */
int open_database_handle(const std::string &conninfo);

/* Close one open handle and release its connection. An unknown handle is ignored. */
void close_database_handle(int handle);

/* Load the fact closure of the target and chosen keys. The returned bundle belongs to the open
 * handle and is valid until that handle closes. */
Bundle *load_database_facts(int handle, const std::vector<std::string> &targets,
                            const std::vector<std::string> &chosen);

/* Compile one loaded bundle into a new structure bundle. ``projection`` 0 builds the full structure
 * and 1 the discovery summary, and ``project`` adds the drawing records of a full structure. A null
 * return leaves any failure text in the shared error state. */
void *compile_bundle(
    const Bundle &bundle, const std::vector<std::string> &targets,
    const std::vector<std::string> &chosen, bool active_only, bool include_recommended,
    bool include_inferred, bool direct_only, const std::vector<std::string> &excluded,
    const std::vector<std::string> &completed, const std::vector<std::string> &excluded_keys,
    int projection, bool project);

/* Derive the drawing nodes, edges and bindings of one compiled structure, returning false with the
 * error text set. */
bool project_compilation(Compilation &compilation);

/* Wrap one compiled structure set in its record views and return the bundle pointer. */
void *write_structure_bundle(std::unique_ptr<Compiled> compiled);

/* Write one outcome per compiled structure and return the count. ``mode`` 0 keeps a structure whose
 * requirements are all covered and 1 keeps one with any requirement covered. Returns -1 when the
 * outcome buffer is too small or a course summary is absent. */
int evaluate_bundle(const StructureBundle &holder, const std::unordered_set<std::string> &basis,
                    int mode, NativeOutcome *outcomes, int capacity);

}  // namespace tce
