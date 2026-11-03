/* Canonical JSON text and SHA-256 helpers shared by the native identity payloads. */

#pragma once

#include "sha256.h"

#include <cstdio>
#include <string>
#include <string_view>

namespace tce {

/* Canonical identity payloads use sorted, compact UTF-8 JSON with a fixed field order and number
 * text, so one payload always yields a byte-identical piece, use, fact or diagnostic identity. */
inline void append_json_string(std::string &out, const std::string &value)
{
    out.push_back('"');
    for (unsigned char character : value) {
        switch (character) {
            case '"': out += "\\\""; break;
            case '\\': out += "\\\\"; break;
            case '\n': out += "\\n"; break;
            case '\r': out += "\\r"; break;
            case '\t': out += "\\t"; break;
            case '\b': out += "\\b"; break;
            case '\f': out += "\\f"; break;
            default:
                if (character < 0x20) {
                    char buffer[7];
                    std::snprintf(buffer, sizeof(buffer), "\\u%04x", character);
                    out += buffer;
                } else {
                    out.push_back((char) character);
                }
        }
    }
    out.push_back('"');
}

inline void append_json_optional_string(std::string &out, const std::string &value)
{
    if (value.empty()) out += "null";
    else append_json_string(out, value);
}

inline std::string sha256_hex(std::string_view data)
{
    unsigned char digest[32];
    sha256_digest(data.data(), data.size(), digest);
    static const char digits[] = "0123456789abcdef";
    std::string out;
    out.resize(32 * 2);
    for (int index = 0; index < 32; ++index) {
        out[2 * index] = digits[digest[index] >> 4];
        out[2 * index + 1] = digits[digest[index] & 0x0f];
    }
    return out;
}

/* Return one numeric bound as plain fixed-point text without trailing fractional zeroes, with
 * canonical zero "0", the same text `_decimal_json` in `prerequisite/domain.py` writes. */
inline std::string canonical_decimal_text(const std::string &text)
{
    if (text.empty()) return {};
    std::string result = text;
    bool negative = false;
    size_t start = 0;
    if (result[start] == '-') {
        negative = true;
        ++start;
    }
    size_t dot = result.find('.', start);
    std::string whole = result.substr(start, dot == std::string::npos ? std::string::npos
                                                                     : dot - start);
    std::string fraction = dot == std::string::npos ? std::string() : result.substr(dot + 1);
    size_t first = whole.find_first_not_of('0');
    whole = first == std::string::npos ? "0" : whole.substr(first);
    while (!fraction.empty() && fraction.back() == '0') fraction.pop_back();
    std::string out = (negative && !(whole == "0" && fraction.empty()) ? "-" : "") + whole;
    if (!fraction.empty()) out += "." + fraction;
    return out;
}


}  // namespace tce
