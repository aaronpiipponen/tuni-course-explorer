/* Native recommendation scorer: candidate scoring, overlap filtering and ordering.
 *
 * The caller marshals the prepared basis units, the trimmed basis profile and the candidate
 * descriptive chunks. The scorer recomputes each candidate's unit rows, cumulative dots, per-basis
 * coverage, near-duplicate test, score and ordering with float64 arithmetic. It reports a candidate
 * index, the meters and the two derived flags.
 */

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <string>
#include <string_view>
#include <vector>

#if defined(__aarch64__)
#include <arm_neon.h>
#endif

#include "support.h"

namespace {

/* Dot product whose four accumulator lanes keep the scalar reduction order.
 *
 * The two vector accumulators hold lanes 0/1 and 2/3, so each lane sums the same elements in the
 * same order as the scalar form and the final `(s0 + s1) + (s2 + s3)` gives the same value. The
 * explicit two-lane form keeps that result bit-identical and uses the NEON multiply/add pipes.
 */
double dot_product(const double *left, const double *right, int dim)
{
#if defined(__aarch64__)
    float64x2_t low = vdupq_n_f64(0.0);
    float64x2_t high = vdupq_n_f64(0.0);
    int d = 0;
    for (; d + 4 <= dim; d += 4) {
        low = vaddq_f64(low, vmulq_f64(vld1q_f64(left + d), vld1q_f64(right + d)));
        high = vaddq_f64(high, vmulq_f64(vld1q_f64(left + d + 2), vld1q_f64(right + d + 2)));
    }
    double lanes[2];
    vst1q_f64(lanes, low);
    double s0 = lanes[0], s1 = lanes[1];
    vst1q_f64(lanes, high);
    double s2 = lanes[0], s3 = lanes[1];
    for (; d < dim; ++d) s0 += left[d] * right[d];
    return (s0 + s1) + (s2 + s3);
#else
    double s0 = 0.0, s1 = 0.0, s2 = 0.0, s3 = 0.0;
    int d = 0;
    for (; d + 4 <= dim; d += 4) {
        s0 += left[d] * right[d];
        s1 += left[d + 1] * right[d + 1];
        s2 += left[d + 2] * right[d + 2];
        s3 += left[d + 3] * right[d + 3];
    }
    for (; d < dim; ++d) s0 += left[d] * right[d];
    return (s0 + s1) + (s2 + s3);
#endif
}

}  // namespace

extern "C" {
const int32_t course_recommendation_version() { return 2; }

const char *course_recommendation_last_error() { return tce::last_error.c_str(); }

struct ScoreRequest {
    int32_t dim;
    int32_t basis_rows;
    int32_t basis_courses;
    int32_t candidate_count;
    int32_t chunk_count;
    int32_t basis_derived;
    double min_relatedness;
    double near_duplicate_percent;
    double overlap_floor;
    double overlap_ceiling;
    double overlap_weight;
    const double *basis_units;
    const int32_t *basis_course_of_row;
    const double *profile;
    const double *hub;
    const double *outcomes_hub;
    const int32_t *candidate_offsets;
    const double *chunk_embeddings;
    const int32_t *chunk_field;
    const int64_t *chunk_characters;
    const uint8_t *chunk_derived;
    const char *key_blob;
    const int64_t *key_offsets;
};

struct ScoreResult {
    int32_t candidate_index;
    double relatedness;
    double score;
    double overlap;
    uint8_t has_overlap;
    uint8_t uses_derived;
};

static double overlap_percent(double mean_cosine, double floor, double ceiling)
{
    if (ceiling <= floor) return 0.0;
    double value = (mean_cosine - floor) / (ceiling - floor);
    if (value < 0.0) value = 0.0;
    if (value > 1.0) value = 1.0;
    return 100.0 * value;
}

static bool unit_row(const double *centred, int dim, double *out)
{
    double sum = 0.0;
    for (int i = 0; i < dim; ++i) sum += centred[i] * centred[i];
    double norm = std::sqrt(sum);
    if (norm == 0.0) {
        tce::set_error("cannot compare a zero-length centred embedding");
        return false;
    }
    for (int i = 0; i < dim; ++i) out[i] = centred[i] / norm;
    return true;
}

struct KeyView {
    bool missing;
    std::string_view name;
    std::string_view code;
    std::string_view group;
};

static bool read_key(const char *blob, int64_t begin, int64_t end, KeyView &key)
{
    if (blob == nullptr || end - begin < 13) return false;
    const unsigned char *p = reinterpret_cast<const unsigned char *>(blob + begin);
    key.missing = p[0] != 0;
    uint32_t nlen;
    uint32_t clen;
    uint32_t glen;
    std::memcpy(&nlen, p + 1, 4);
    std::memcpy(&clen, p + 5, 4);
    std::memcpy(&glen, p + 9, 4);
    int64_t needed = 13 + static_cast<int64_t>(nlen) + clen + glen;
    if (needed > end - begin) return false;
    key.name = std::string_view(reinterpret_cast<const char *>(p + 13), nlen);
    key.code = std::string_view(reinterpret_cast<const char *>(p + 13 + nlen), clen);
    key.group = std::string_view(reinterpret_cast<const char *>(p + 13 + nlen + clen), glen);
    return true;
}

int course_recommendation_score(const ScoreRequest *request, ScoreResult *results,
                                int32_t capacity)
{
    if (request == nullptr || results == nullptr) {
        tce::set_error("null scorer request or result buffer");
        return -1;
    }
    const int dim = request->dim;
    const int candidates = request->candidate_count;
    if (dim <= 0 || candidates < 0 || request->basis_rows < 0 || request->basis_courses < 0) {
        tce::set_error("invalid scorer dimensions");
        return -1;
    }
    if (candidates > capacity) {
        tce::set_error("scorer result buffer is smaller than the candidate count");
        return -1;
    }
    std::vector<KeyView> keys(candidates);
    for (int c = 0; c < candidates; ++c) {
        if (!read_key(request->key_blob, request->key_offsets[c], request->key_offsets[c + 1],
                      keys[c])) {
            tce::set_error("invalid candidate ordering key");
            return -1;
        }
    }
    std::vector<double> basis_copy;
    if (request->basis_rows > 0)
        basis_copy.assign(request->basis_units,
                          request->basis_units + (size_t) request->basis_rows * dim);
    std::vector<int> course_start(request->basis_courses + 1, 0);
    for (int row = 0; row < request->basis_rows; ++row) {
        int course = request->basis_course_of_row[row];
        if (course < 0 || course >= request->basis_courses) {
            tce::set_error("basis course position is out of range");
            return -1;
        }
        course_start[course + 1] += 1;
    }
    for (int c = 0; c < request->basis_courses; ++c) course_start[c + 1] += course_start[c];
    std::vector<int> row_by_course(request->basis_rows);
    {
        std::vector<int> cursor(course_start.begin(), course_start.end() - 1);
        for (int row = 0; row < request->basis_rows; ++row) {
            int course = request->basis_course_of_row[row];
            row_by_course[cursor[course]++] = row;
        }
    }
    std::vector<double> candidate_units;
    std::vector<double> point(dim);
    std::vector<double> dots;
    std::vector<ScoreResult> kept;
    kept.reserve(candidates);
    bool any_basis_derived = request->basis_derived != 0;
    for (int c = 0; c < candidates; ++c) {
        int begin = request->candidate_offsets[c];
        int end = request->candidate_offsets[c + 1];
        if (begin < 0 || end < begin || end > request->chunk_count) {
            tce::set_error("candidate chunk offsets are invalid");
            return -1;
        }
        int chunks = end - begin;
        if (chunks == 0) continue;
        candidate_units.resize((size_t) chunks * dim);
        std::vector<double> mean(dim, 0.0);
        bool uses_derived = false;
        int64_t total_characters = 0;
        for (int i = 0; i < chunks; ++i) {
            int chunk = begin + i;
            const double *hub = request->chunk_field[chunk] == 1 ? request->outcomes_hub
                                                                : request->hub;
            const double *raw = request->chunk_embeddings + (size_t) chunk * dim;
            double *centre = candidate_units.data() + (size_t) i * dim;
            for (int d = 0; d < dim; ++d) centre[d] = raw[d] - hub[d];
            if (!unit_row(centre, dim, centre)) return -1;
            for (int d = 0; d < dim; ++d) mean[d] += centre[d];
            total_characters += request->chunk_characters[chunk];
            uses_derived = uses_derived || request->chunk_derived[chunk] != 0;
        }
        for (int d = 0; d < dim; ++d) mean[d] /= chunks;
        if (!unit_row(mean.data(), dim, point.data())) return -1;
        double relatedness_dot = dot_product(point.data(), request->profile, dim);
        if (relatedness_dot < 0.0) relatedness_dot = 0.0;
        double relatedness = 100.0 * relatedness_dot;
        if (relatedness < request->min_relatedness * 100.0) continue;
        dots.resize((size_t) chunks * request->basis_rows);
        for (int i = 0; i < chunks; ++i) {
            const double *unit = candidate_units.data() + (size_t) i * dim;
            double *row = dots.data() + (size_t) i * request->basis_rows;
            for (int b = 0; b < request->basis_rows; ++b) {
                const double *basis = basis_copy.data() + (size_t) b * dim;
                row[b] = dot_product(unit, basis, dim);
            }
        }
        double coverage_sum = 0.0;
        for (int i = 0; i < chunks; ++i) {
            const double *row = dots.data() + (size_t) i * request->basis_rows;
            double best = 0.0;
            for (int b = 0; b < request->basis_rows; ++b)
                if (row[b] > best) best = row[b];
            coverage_sum += (double) request->chunk_characters[begin + i] * best;
        }
        double strongest_course = 0.0;
        for (int course = 0; course < request->basis_courses; ++course) {
            double covered = 0.0;
            for (int i = 0; i < chunks; ++i) {
                const double *row = dots.data() + (size_t) i * request->basis_rows;
                double best = 0.0;
                for (int k = course_start[course]; k < course_start[course + 1]; ++k) {
                    int b = row_by_course[k];
                    if (row[b] > best) best = row[b];
                }
                covered += (double) request->chunk_characters[begin + i] * best;
            }
            double percent = 0.0;
            if (total_characters > 0)
                percent = overlap_percent(covered / (double) total_characters,
                                          request->overlap_floor, request->overlap_ceiling);
            if (percent > strongest_course) strongest_course = percent;
        }
        if (strongest_course >= request->near_duplicate_percent) continue;
        bool has_overlap = total_characters > 0;
        double covered_fraction = has_overlap ? coverage_sum / (double) total_characters : 0.0;
        double overlap = has_overlap
                             ? overlap_percent(covered_fraction, request->overlap_floor,
                                               request->overlap_ceiling)
                             : 0.0;
        double score = 100.0 * std::max(0.0, relatedness / 100.0
                                                 - request->overlap_weight * overlap / 100.0);
        kept.push_back({c, relatedness, score, overlap, (uint8_t) (has_overlap ? 1 : 0),
                        (uint8_t) ((uses_derived || any_basis_derived) ? 1 : 0)});
    }
    std::sort(kept.begin(), kept.end(), [&keys](const ScoreResult &left, const ScoreResult &right) {
        if (left.score != right.score) return left.score > right.score;
        if (left.relatedness != right.relatedness) return left.relatedness > right.relatedness;
        const KeyView &a = keys[left.candidate_index];
        const KeyView &b = keys[right.candidate_index];
        if (a.missing != b.missing) return !a.missing;
        if (a.name != b.name) return a.name < b.name;
        if (a.code != b.code) return a.code < b.code;
        return a.group < b.group;
    });
    for (size_t i = 0; i < kept.size(); ++i) results[i] = kept[i];
    return (int) kept.size();
}

}  // extern "C"
