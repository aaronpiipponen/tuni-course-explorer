/* The SHA-256 digest the native identity payloads hash. */

#pragma once

#include <cstddef>
#include <cstdint>
#include <cstring>
#include <string>

namespace tce {

/* One SHA-256 digest of the given bytes.
 *
 * The implementation follows FIPS 180-4 and is the only hash the native libraries need, so they
 * carry no OpenSSL runtime dependency. */
inline void sha256_digest(const void *data, std::size_t size, unsigned char out[32])
{
    static const std::uint32_t round[64] = {
        0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4,
        0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe,
        0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f,
        0x4a7484aa, 0x5cb0a9dc, 0x76f988da, 0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7,
        0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc,
        0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b,
        0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070, 0x19a4c116,
        0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
        0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7,
        0xc67178f2};
    std::uint32_t state[8] = {0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
                              0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19};
    const auto *bytes = static_cast<const unsigned char *>(data);
    const auto rotate = [](std::uint32_t value, int count) {
        return (value >> count) | (value << (32 - count));
    };
    std::uint64_t bit_length = static_cast<std::uint64_t>(size) * 8;
    std::size_t padded = ((size + 8) / 64 + 1) * 64;
    std::string buffer(padded, '\0');
    std::memcpy(buffer.data(), bytes, size);
    buffer[size] = static_cast<char>(0x80);
    for (int index = 0; index < 8; ++index) {
        buffer[padded - 1 - index] = static_cast<char>((bit_length >> (8 * index)) & 0xff);
    }
    for (std::size_t offset = 0; offset < padded; offset += 64) {
        std::uint32_t words[64];
        for (int index = 0; index < 16; ++index) {
            const auto *block = reinterpret_cast<const unsigned char *>(buffer.data() + offset);
            words[index] = (static_cast<std::uint32_t>(block[4 * index]) << 24) |
                           (static_cast<std::uint32_t>(block[4 * index + 1]) << 16) |
                           (static_cast<std::uint32_t>(block[4 * index + 2]) << 8) |
                           static_cast<std::uint32_t>(block[4 * index + 3]);
        }
        for (int index = 16; index < 64; ++index) {
            std::uint32_t s0 = rotate(words[index - 15], 7) ^ rotate(words[index - 15], 18) ^
                               (words[index - 15] >> 3);
            std::uint32_t s1 = rotate(words[index - 2], 17) ^ rotate(words[index - 2], 19) ^
                               (words[index - 2] >> 10);
            words[index] = words[index - 16] + s0 + words[index - 7] + s1;
        }
        std::uint32_t a = state[0], b = state[1], c = state[2], d = state[3];
        std::uint32_t e = state[4], f = state[5], g = state[6], h = state[7];
        for (int index = 0; index < 64; ++index) {
            std::uint32_t s1 = rotate(e, 6) ^ rotate(e, 11) ^ rotate(e, 25);
            std::uint32_t choice = (e & f) ^ (~e & g);
            std::uint32_t temp1 = h + s1 + choice + round[index] + words[index];
            std::uint32_t s0 = rotate(a, 2) ^ rotate(a, 13) ^ rotate(a, 22);
            std::uint32_t majority = (a & b) ^ (a & c) ^ (b & c);
            std::uint32_t temp2 = s0 + majority;
            h = g;
            g = f;
            f = e;
            e = d + temp1;
            d = c;
            c = b;
            b = a;
            a = temp1 + temp2;
        }
        state[0] += a;
        state[1] += b;
        state[2] += c;
        state[3] += d;
        state[4] += e;
        state[5] += f;
        state[6] += g;
        state[7] += h;
    }
    for (int index = 0; index < 8; ++index) {
        out[4 * index] = static_cast<unsigned char>((state[index] >> 24) & 0xff);
        out[4 * index + 1] = static_cast<unsigned char>((state[index] >> 16) & 0xff);
        out[4 * index + 2] = static_cast<unsigned char>((state[index] >> 8) & 0xff);
        out[4 * index + 3] = static_cast<unsigned char>(state[index] & 0xff);
    }
}

}  // namespace tce
