/* Structure bundle writer for the native prerequisite interface.
 *
 * Holds one compiled structure set together with its record views for the lifetime of a request
 * bundle.
 */

#include <utility>
#include <vector>

#include "bundle.h"
#include "pipeline.h"

namespace tce {

void *write_structure_bundle(std::unique_ptr<Compiled> compiled)
{
    auto holder = std::make_unique<StructureBundle>();
    holder->compiled = compiled.release();
    holder->views.resize(holder->compiled->compilations.size());
    for (size_t index = 0; index < holder->compiled->compilations.size(); ++index)
        build_view(holder->compiled->compilations[index], holder->views[index]);
    holder->records.reserve(holder->views.size());
    for (StructureView &view : holder->views) holder->records.push_back(view.record);
    return holder.release();
}

}  // namespace tce
