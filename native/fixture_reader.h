/* Fixture-only entry point into the native compiler's ordered record reader. */

#pragma once

#include <cstddef>
#include <memory>

#include "records.h"

namespace tce {

std::unique_ptr<Compiled> read_records(const char *data, std::size_t size);

}  // namespace tce
