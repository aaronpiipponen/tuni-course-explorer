/* Native prerequisite record-format version shared by the serving and fixture libraries. */

#pragma once

#include <cstdint>

namespace tce {

/* Mirrors `FORMAT_VERSION` in `prerequisite/native_compiler.py`. A mismatch refuses the library. */
constexpr int32_t kPrerequisiteFormatVersion = 5;

}  // namespace tce
