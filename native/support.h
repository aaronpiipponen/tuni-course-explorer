/* Shared native error state. */

#pragma once

#include <string>

namespace tce {

inline thread_local std::string last_error;

inline void set_error(const char *message)
{
    last_error = message;
}

inline void set_error(const std::string &message)
{
    last_error = message;
}

}  // namespace tce
