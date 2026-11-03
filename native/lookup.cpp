/* Native fuzzy-name token coverage: the weighted query-token score over precomputed title tokens.
 *
 * The caller supplies one token table per catalogue order and the query's word tokens. The function
 * computes the normalized Indel similarity of every query token against the table's vocabulary,
 * then raises each candidate's whole-title score by its weighted query-token coverage. Each
 * candidate's coverage sums the best ratio of every query token in query-token order, and the ratio
 * is the same normalized Indel similarity RapidFuzz reports for `fuzz.ratio`.
 */

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <string>
#include <vector>

#include "support.h"

namespace {

/* Longest common subsequence length over two code-point sequences in one reusable scratch
 * buffer. */
int lcs_length(const int32_t *left, int left_length, const int32_t *right, int right_length,
               int32_t *previous, int32_t *current)
{
    for (int j = 0; j <= right_length; ++j) previous[j] = 0;
    for (int i = 0; i < left_length; ++i) {
        current[0] = 0;
        for (int j = 0; j < right_length; ++j) {
            if (left[i] == right[j])
                current[j + 1] = previous[j] + 1;
            else
                current[j + 1] = std::max(previous[j + 1], current[j]);
        }
        std::copy(current, current + right_length + 1, previous);
    }
    return previous[right_length];
}

}  // namespace

extern "C" {
int32_t course_lookup_version() { return 1; }

const char *course_lookup_last_error() { return tce::last_error.c_str(); }

int32_t course_lookup_token_coverage(const int32_t *row_positions, int32_t slots,
                                     const int32_t *token_offsets, int32_t rows,
                                     const int32_t *token_indices, int32_t token_count,
                                     const int32_t *vocabulary_codepoints,
                                     const int32_t *vocabulary_offsets, int32_t vocabulary_count,
                                     const int32_t *query_codepoints, const int32_t *query_offsets,
                                     int32_t query_count, double *scores, double threshold,
                                     double token_weight)
{
    if (query_count <= 0 || threshold > 100.0 * token_weight) return 0;
    if (scores == nullptr || row_positions == nullptr || token_offsets == nullptr ||
        query_offsets == nullptr) {
        tce::set_error("invalid fuzzy-name token coverage request");
        return -1;
    }
    if (query_codepoints == nullptr && query_offsets[query_count] > 0) {
        tce::set_error("invalid fuzzy-name query token buffer");
        return -1;
    }
    const double token_cutoff =
        std::max(0.0, query_count * threshold / token_weight - 100.0 * (query_count - 1));
    int max_word = 0;
    for (int v = 0; v < vocabulary_count; ++v)
        max_word = std::max(max_word, vocabulary_offsets[v + 1] - vocabulary_offsets[v]);
    for (int q = 0; q < query_count; ++q)
        max_word = std::max(max_word, query_offsets[q + 1] - query_offsets[q]);
    std::vector<int32_t> previous(static_cast<size_t>(max_word) + 1);
    std::vector<int32_t> current(static_cast<size_t>(max_word) + 1);
    std::vector<double> ratios(static_cast<size_t>(query_count) * vocabulary_count, 0.0);
    for (int q = 0; q < query_count; ++q) {
        const int qbegin = query_offsets[q];
        const int qlength = query_offsets[q + 1] - qbegin;
        const int32_t *query = query_codepoints + qbegin;
        for (int v = 0; v < vocabulary_count; ++v) {
            const int vbegin = vocabulary_offsets[v];
            const int vlength = vocabulary_offsets[v + 1] - vbegin;
            if (qlength == 0 || vlength == 0) continue;
            const int shorter = std::min(qlength, vlength);
            const double bound =
                100.0 * (1.0 - (double) (std::max(qlength, vlength) - shorter) /
                                  (double) (qlength + vlength));
            if (bound < token_cutoff) continue;
            const int common = lcs_length(query, qlength, vocabulary_codepoints + vbegin, vlength,
                                          previous.data(), current.data());
            const int distance = qlength + vlength - 2 * common;
            const double ratio =
                100.0 * (1.0 - (double) distance / (double) (qlength + vlength));
            if (ratio >= token_cutoff) ratios[(size_t) q * vocabulary_count + v] = ratio;
        }
    }
    for (int s = 0; s < slots; ++s) {
        double score = scores[s];
        if (score > 100.0 * token_weight) continue;
        const int row = row_positions[s];
        if (row < 0 || row >= rows) {
            tce::set_error("fuzzy-name row position is out of range");
            return -1;
        }
        const int begin = token_offsets[row];
        const int end = token_offsets[row + 1];
        if (begin < 0 || end < begin || (end > begin && token_indices == nullptr)) {
            tce::set_error("invalid fuzzy-name title token buffer");
            return -1;
        }
        if (end == begin) continue;
        const double required = query_count * std::max(threshold, score) / token_weight;
        double total = 0.0;
        bool complete = true;
        for (int q = 0; q < query_count; ++q) {
            double best = 0.0;
            const double *row_scores = ratios.data() + (size_t) q * vocabulary_count;
            for (int k = begin; k < end; ++k) {
                const int v = token_indices[k];
                if (v < 0 || v >= vocabulary_count) {
                    tce::set_error("fuzzy-name token index is out of range");
                    return -1;
                }
                if (row_scores[v] > best) best = row_scores[v];
            }
            total += best;
            if (total + 100.0 * (query_count - q - 1) < required) {
                complete = false;
                break;
            }
        }
        if (complete) {
            const double value = token_weight * total / query_count;
            if (value > score) scores[s] = value;
        }
    }
    return 0;
}

}  // extern "C"
