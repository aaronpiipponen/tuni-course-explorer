# Comparison arithmetic

The comparison service turns two courses' stored chunk vectors into five percentage meters and one verdict, from the values its caller supplies.

## Chunk carriers and centring

`TeachingEmbeddingChunk` in `src/course_explorer/embeddings/read.py` is the request-local carrier: `chunk_id`, `group_id`, `sisu_course_unit_id`, `representative_source_hash`, `field`, `language`, `chunk_index`, `text_origin`, `character_count`, and `embedding`. `TeachingEmbeddingRepository.get_chunks(represented, *, embedding_configuration_hash, descriptive_only=False, shared_store=None)` returns the completed, vector-backed rows whose `(group_id, sisu_course_unit_id, representative_source_hash)` triple matches a requested record and whose configuration hash equals the digest. With `descriptive_only` the read uses the shared serving store and returns the content and outcomes rows. The comparison command reads every field from the database projection and passes no shared store. An empty request returns before opening a session, and a requested identity with no compatible row contributes no chunk.

`centre_chunks(chunks, hub, *, outcomes_hub=None)` in the same module replaces each chunk's vector with `subtract_hub(vector, hub)`, and with `subtract_hub_for_field` when an outcomes hub is supplied, so an outcomes chunk is centred on the outcomes hub and every other chunk on the embedding hub.

## The centroid

`_centroid(chunks)` in `src/course_explorer/comparison/service.py` returns the character-count-weighted mean of the chunks' unit vectors:

```text
unit(v)     = v / sqrt(sum(v[i] ** 2))
centroid    = sum(unit(chunk.embedding) * chunk.character_count for chunk in chunks)
              / sum(chunk.character_count for chunk in chunks)
```

`_unit` raises `ValueError` for a vector whose norm is zero, and `_centroid` raises `ValueError` when the total character count is not positive. Weighting by the stored character count means a long chunk contributes more of its text than a short one.

Two helpers sit under every meter. `_cosine(left, right)` returns the dot product of the two unit vectors clipped to `[-1, 1]`, and `_percent(cosine)` returns `100 * max(0, cosine)`, so a negative similarity reads as 0 percent. The arithmetic runs on float64 NumPy arrays: `_unit` uses `unit_row` from `src/course_explorer/embeddings/vector_math.py`, `_cosine` uses `numpy.dot`, `_centroid` and `_weighted_sum` weight one row matrix and sum its rows, and every chunk-centring call goes through `centre_chunks`, which applies `subtract_hub` and, when an outcomes hub is supplied, `subtract_hub_for_field` from `src/course_explorer/embeddings/hub.py`.

## Field and whole-text meters

`_field_chunks(chunks, field, language)` selects one exact field and language, so the content and outcome text are never mixed in a similarity meter.

`_field_similarity(a, b, field)` walks `TeachingTextLanguage` and, for each language with chunks on both sides, takes `_cosine(_centroid(a_chunks), _centroid(b_chunks))`. The result is `_percent` of the equal-weight mean of those per-language cosines, or `None` when no language qualifies. Content similarity and Learning-outcome similarity are the same computation over `TeachingTextField.CONTENT` and `TeachingTextField.OUTCOMES`.

`_overall_similarity(a, b, settings)` combines the three fields per language:

```text
weight  = {NAME: comparison_name_weight, CONTENT: comparison_content_weight,
           OUTCOMES: comparison_outcomes_weight}
per language with at least one field on both sides:
    combined(side) = sum(unit(centroid(field chunks of side)) * weight[field]
                         for each qualifying field) / sum(weight[field])
    cosines.append(_cosine(combined(a), combined(b)))
result = _percent(equal-weight mean of cosines)   # None when no language qualifies
```

The weight of a field that one side lacks is left out of both sums and out of the divisor, so the other weights are renormalized over the fields the pair shares. The meter compares the two weighted centroids as a whole, so it reflects the whole text of each course rather than the best matching passage.

`compare_teaching_chunks(a, b, *, settings, hub, outcomes_hub)` centres both sides once with `centre_chunks`, builds the three meters from the centred chunks, and adds the overlap result from the same centred chunks, so the overlap reuses the centring instead of repeating it, and returns one `ComparisonMeters`.

## Directional overlap and the verdict

`DESCRIPTIVE_TEACHING_TEXT_FIELDS` is `(CONTENT, OUTCOMES)`, so a name chunk takes no part in an overlap. `_prepare_descriptive_chunks(chunks)` groups those chunks by language into one unit matrix and one character-weight row, and `PreparedTeachingOverlap(chunks)` holds that projection for the side that stays fixed across comparisons. `PreparedTeachingOverlap.compare` takes one `a_units @ b_units.T` score matrix per language, clamps it to `[-1, 1]`, and applies the row and column maxima with the same weight sums.

`PreparedTeachingOverlap.compare(chunks, *, floor, ceiling)` returns one `DirectionalOverlap`. For each language with descriptive chunks on both sides:

```text
score[i][j] = clamp(dot(a[i].unit, b[j].unit), -1, 1)   # a = supplied side, b = prepared side
a_total     = sum(a[i].weight)                          # must be positive
b_total     = sum(b[j].weight)                          # must be positive
a_mean      = sum(a[i].weight * max(0, max over j of score[i][j]) for i) / a_total
b_mean      = sum(b[j].weight * max(0, max over i of score[i][j]) for j) / b_total
```

Each per-language `a_mean` is the character-weighted mean of each source chunk's best cosine against the destination chunks, and each `b_mean` is the same statistic in the other direction. The per-language values of one direction are averaged with equal weight, and that mean is mapped through `overlap_percent` to become `a_in_b` or `b_in_a`. With no common language both values are `None`. `a_in_b` measures A's chunks against B's and `b_in_a` measures B's against A's.

`overlap_percent(mean_cosine, *, floor, ceiling)` is the calibration:

```text
percent = 100 * clamp((mean_cosine - floor) / (ceiling - floor), 0, 1)
```

and it raises `ValueError` when `ceiling <= floor`.

`comparison_verdict(meters, *, settings)` returns the first label that matches:

1. `strongest = max` of the non-`None` values of `meters.overlap.a_in_b` and `meters.overlap.b_in_a`. At or above `comparison_heavy_overlap_percent` the verdict is `heavily_overlapping`, and at or above `comparison_partial_overlap_percent` it is `partly_overlapping`.
2. `meters.overall_relatedness` at or above `comparison_same_area_percent` is `same_area_different_content`, and at or above `comparison_loose_related_percent` it is `loosely_related`. A value below that threshold is `unrelated`.
3. With no overlap value and a `None` overall relatedness the verdict is `None`.

## Input resolution and the read

`run_course_comparison_command(course_a, course_b)` in `src/course_explorer/comparison/commands.py` is the one composition path:

1. It raises `ValueError` for a blank `course_a` or `course_b` before it loads any settings.
2. It loads `SearchSettings` and `EmbeddingRuntimeSettings` and receives the opened serving artifact build's hub pair.
3. It resolves both inputs through the [course resolver](/docs/reference/glossary.md#search-and-comparison), so each input is an exact canonical identity first and an exact official code second, an unknown or ambiguous input raises, and the two inputs may resolve to the same course.
4. It reads `TeachingEmbeddingRepository.get_chunks(resolved, embedding_configuration_hash=embedding_configuration_sha256(embedding_settings))` inside one database context, then groups the rows by `group_id` and takes one tuple per side.
5. It calls `compare_teaching_chunks` with the build's catalogue and outcomes hubs and the floor and ceiling from the search settings, then `comparison_verdict`.
6. It sets `uses_derived_text` by testing every chunk of both sides for `text_origin is TeachingTextOrigin.DERIVED`.
7. It returns a `CourseComparisonReport` carrying both `CourseSummary` values, the meters, the verdict, and the flag.

`scripts/compare_courses.py` is the `argparse` adapter that prints `report.model_dump_json()`, and `POST /api/comparison` returns the report with the serving dataset identity. A site whose `WEB_EMBEDDINGS_ENABLED` is false answers that route with status 403 and the detail `Feature disabled` before the command runs.

## Settings

`SearchSettings` in `src/course_explorer/config.py` holds the comparison policy, read from `config/search.toml`. [Comparison](/docs/backend/search-and-discovery/comparison.md#languages-and-fields) lists the keys and example values of the three weights, and [Comparison](/docs/backend/search-and-discovery/comparison.md#overlap-calibration-and-the-verdict) lists the six threshold keys and example values.

`SearchSettings.validate_comparison_threshold_order` refuses a floor at or above the ceiling, a partial threshold at or above the heavy threshold, and a loose threshold at or above the same-area threshold.

## Tests

| File | Covers |
|---|---|
| `tests/comparison/test_comparison_service.py` | Hub subtraction that removes a shared component, identical content text at 100 on Content similarity, Overall relatedness, and both overlaps, directional containment where one course sits inside a larger one, a partial match that stays partial, orthogonal text at 0, a name-only pair with the descriptive meters `None`, disjoint languages with every meter `None`, common languages averaged equally, and the configured verdict thresholds. |
| `tests/comparison/test_comparison_command.py` | Blank inputs refused before any settings load, and both CLI and report round-tripping. |
| `tests/search/test_semantic_search_repository.py` | The command over a real database: a self-comparison of a derived-content course reads 100 on content, overall relatedness, and both overlaps, with `uses_derived_text` true. |

The meters and the verdict as the app presents them are described in [Comparison](/docs/backend/search-and-discovery/comparison.md).
