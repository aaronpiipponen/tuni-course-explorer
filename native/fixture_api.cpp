/* C interface of the fixture-only native prerequisite projector.
 *
 * Test support supplies an ordered record bundle. The library runs the same finalize, projection
 * and record-view path as a database compilation and returns the owned structure bundle under the
 * shared record view.
 */

#include <cstddef>
#include <utility>

#include "fixture_reader.h"
#include "pipeline.h"
#include "support.h"

extern "C" {

void *course_prerequisite_project_records(const char *data, int length)
{
    if (data == nullptr || length <= 0) {
        tce::set_error("fixture record bundle is empty");
        return nullptr;
    }
    auto compiled = tce::read_records(data, (size_t) length);
    if (!compiled) return nullptr;
    for (tce::Compilation &compilation : compiled->compilations) {
        if (!tce::finalize_identities(compilation)) return nullptr;
        if (!tce::project_compilation(compilation)) return nullptr;
    }
    return tce::write_structure_bundle(std::move(compiled));
}

}  // extern "C"
