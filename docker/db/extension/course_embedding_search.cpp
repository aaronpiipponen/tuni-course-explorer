/* Exact semantic scan over the packed course embedding block relation.
 *
 * The query vector is already hub-centred, and its dimension sets the width of every score. Each
 * stored block holds up to 128 centred float32 vectors, the group number of each vector and its
 * precomputed squared norm. The scan keeps the best cosine score of each group and returns every
 * group that a stored vector names.
 */

extern "C" {
#include "postgres.h"
#include "fmgr.h"
#include "funcapi.h"
#include "access/table.h"
#include "access/tableam.h"
#include "executor/tuptable.h"
#include "utils/array.h"
#include "utils/builtins.h"
#include "utils/rel.h"
#include "utils/snapmgr.h"
#include "utils/tuplestore.h"
#include "vector/vector.h"
#include "miscadmin.h"
PG_MODULE_MAGIC;
PG_FUNCTION_INFO_V1(course_embedding_search_scan);
}

#include <cmath>
#include <cstring>

#if defined(__aarch64__)
#include <arm_neon.h>
#endif

namespace {

inline double score_vector(const float *centred, const float *query, double norm, double qnorm,
                           int dim)
{
#if defined(__aarch64__)
    float32x4_t acc = vdupq_n_f32(0);
    int j = 0;
    for (; j + 4 <= dim; j += 4)
        acc = vfmaq_f32(acc, vld1q_f32(centred + j), vld1q_f32(query + j));
    float dot = vaddvq_f32(acc);
    for (; j < dim; ++j)
        dot = std::fma(centred[j], query[j], dot);
#else
    double dot = 0.0;
    for (int j = 0; j < dim; ++j)
        dot += (double) centred[j] * (double) query[j];
#endif
    double score = (double) dot / std::sqrt(norm * qnorm);
    if (score > 1) score = 1;
    else if (score < -1) score = -1;
    // The pgvector cosine-distance operator returns 1 - cosine_similarity, and a read that needs
    // the similarity converts it back as 1 - distance. That subtraction rounds the value twice, so
    // the same round trip here keeps every packed score bit-identical to the score such a read
    // returns.
    return 1.0 - (1.0 - score);
}

inline void keep_best(double *best, int group, double score, int groups)
{
    if (group < 0 || group >= groups)
        ereport(ERROR,
                (errcode(ERRCODE_DATA_EXCEPTION),
                 errmsg("course embedding group %d is outside the %d-group identity map", group,
                        groups)));
    if (score > best[group]) best[group] = score;
}

}  // namespace

extern "C" Datum course_embedding_search_scan(PG_FUNCTION_ARGS)
{
    Oid oid = PG_GETARG_OID(0);
    Vector *query = PG_GETARG_VECTOR_P(1);
    double qnorm = PG_GETARG_FLOAT8(2);
    int groups = PG_GETARG_INT32(3);
    if (query->dim <= 0 || groups <= 0 || !(qnorm > 0.0))
        ereport(ERROR,
                (errcode(ERRCODE_INVALID_PARAMETER_VALUE),
                 errmsg("invalid query dimension, norm or group count")));
    const int dim = query->dim;
    InitMaterializedSRF(fcinfo, 0);
    ReturnSetInfo *rs = (ReturnSetInfo *) fcinfo->resultinfo;
    double *best = (double *) palloc(sizeof(double) * groups);
    for (int i = 0; i < groups; ++i) best[i] = -INFINITY;
    Relation rel = table_open(oid, AccessShareLock);
    TableScanDesc scan = table_beginscan(rel, GetActiveSnapshot(), 0, nullptr);
    TupleTableSlot *slot = table_slot_create(rel, nullptr);
    while (table_scan_getnextslot(scan, ForwardScanDirection, slot)) {
        CHECK_FOR_INTERRUPTS();
        bool isnull;
        int n = DatumGetInt32(slot_getattr(slot, 2, &isnull));
        if (isnull || n <= 0)
            ereport(ERROR, (errcode(ERRCODE_DATA_EXCEPTION),
                            errmsg("invalid packed block length")));
        Datum group_datum = slot_getattr(slot, 3, &isnull);
        if (isnull)
            ereport(ERROR, (errcode(ERRCODE_DATA_EXCEPTION),
                            errmsg("null packed group array")));
        ArrayType *group_array = DatumGetArrayTypeP(group_datum);
        Datum norm_datum = slot_getattr(slot, 4, &isnull);
        if (isnull)
            ereport(ERROR, (errcode(ERRCODE_DATA_EXCEPTION),
                            errmsg("null packed norm array")));
        ArrayType *norm_array = DatumGetArrayTypeP(norm_datum);
        Datum vector_datum = slot_getattr(slot, 5, &isnull);
        if (isnull)
            ereport(ERROR, (errcode(ERRCODE_DATA_EXCEPTION),
                            errmsg("null packed vectors")));
        bytea *vectors = DatumGetByteaPP(vector_datum);
        if (VARSIZE_ANY_EXHDR(vectors) != (Size) n * dim * sizeof(float))
            ereport(ERROR,
                    (errcode(ERRCODE_DATA_EXCEPTION),
                     errmsg("packed block payload is not %d float32 vectors", n)));
        Datum *group_values;
        Datum *norm_values;
        bool *group_nulls;
        bool *norm_nulls;
        int group_count;
        int norm_count;
        deconstruct_array(group_array, INT4OID, 4, true, 'i', &group_values, &group_nulls,
                          &group_count);
        deconstruct_array(norm_array, FLOAT8OID, 8, true, 'd', &norm_values, &norm_nulls,
                          &norm_count);
        if (group_count != n || norm_count != n)
            ereport(ERROR,
                    (errcode(ERRCODE_DATA_EXCEPTION),
                     errmsg("packed block arrays disagree with its vector count")));
        const float *packed = (const float *) VARDATA_ANY(vectors);
        for (int i = 0; i < n; ++i) {
            if (group_nulls[i] || norm_nulls[i])
                ereport(ERROR,
                        (errcode(ERRCODE_DATA_EXCEPTION),
                         errmsg("null packed identity or norm")));
            keep_best(best, DatumGetInt32(group_values[i]),
                      score_vector(packed + (Size) i * dim, query->x,
                                   DatumGetFloat8(norm_values[i]), qnorm, dim),
                      groups);
        }
        pfree(group_values);
        pfree(norm_values);
        pfree(group_nulls);
        pfree(norm_nulls);
        if ((Pointer) group_array != DatumGetPointer(group_datum)) pfree(group_array);
        if ((Pointer) norm_array != DatumGetPointer(norm_datum)) pfree(norm_array);
        if ((Pointer) vectors != DatumGetPointer(vector_datum)) pfree(vectors);
        ExecClearTuple(slot);
    }
    ExecDropSingleTupleTableSlot(slot);
    table_endscan(scan);
    table_close(rel, AccessShareLock);
    for (int i = 0; i < groups; ++i) {
        if (best[i] == -INFINITY) continue;
        Datum values[2] = {Int32GetDatum(i), Float8GetDatum(best[i])};
        bool nulls[2] = {false, false};
        tuplestore_putvalues(rs->setResult, rs->setDesc, values, nulls);
    }
    pfree(best);
    PG_RETURN_NULL();
}
