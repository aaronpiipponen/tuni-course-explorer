/* Shared C entry points of the native prerequisite serving and fixture libraries.
 *
 * Both libraries expose the same format version, error text, structure-record accessor and bundle
 * release, so the ownership and record view live in one unit.
 */

#include <cstdint>

#include "bundle.h"
#include "format_version.h"
#include "support.h"

extern "C" {

int32_t course_prerequisite_version() { return tce::kPrerequisiteFormatVersion; }

const char *course_prerequisite_last_error() { return tce::last_error.c_str(); }

const CourseStructureRecord *course_prerequisite_structures(void *pointer, int *count)
{
    auto holder = static_cast<tce::StructureBundle *>(pointer);
    if (holder == nullptr) {
        tce::set_error("native structure bundle is not open");
        *count = 0;
        return nullptr;
    }
    *count = (int32_t) holder->records.size();
    return holder->records.data();
}

void course_prerequisite_free_bundle(void *pointer)
{
    auto holder = static_cast<tce::StructureBundle *>(pointer);
    if (holder == nullptr) return;
    delete holder->compiled;
    delete holder;
}

}  // extern "C"
