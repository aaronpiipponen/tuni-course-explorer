# Serving artifact build

One build writes a dataset's serving files and, when the site serves the embedding features, replaces its embedding directory and derived tables.

## What a build writes

`build_serving_artifacts()` in `src/course_explorer/serving_build.py` is the one builder. It writes every file of one build into the family's build directory and, on a site that serves the embedding features, the embedding files into that configuration's embedding directory. The entry point resolves `WEB_EMBEDDINGS_ENABLED` in `config/web.toml` once through `embedding_configuration_for_site(web)` and passes the resolved configuration or `None`, so the build reads no switch of its own and the configuration identity comes from that one value.

| File | Holds | Directory | Written when |
|---|---|---|---|
| `catalogue.json` | The plain catalogue artifact, which a worker serves after appending the serving identity. | Build | Always |
| `study-fragments.bin` | One study fragment per module root, or a marker that the root is unavailable or needs a version selection, with the fragment counts and cost facts. | Build | Always |
| `embedding-hub.json` | The authoritative embedding hub, written as one compact JSON number array. | Embedding | Embeddings on |
| `embedding-outcomes-hub.json` | The authoritative outcomes hub, in the same form. | Embedding | Embeddings on |
| `hub-pair.json` | The names of the two hub files, which is the pair an artifact open reads. | Embedding | Embeddings on |
| `centroids.f64` | The shared centroid store: one unit-length course centroid per represented course with a descriptive chunk, as a raw little-endian float64 matrix. | Embedding | Embeddings on |
| `centroids.json` | The centroid index: the dataset key, the academic year, the dimension, and the representative triple of each centroid row. | Embedding | Embeddings on |
| `chunks.f64.bin` | The shared descriptive chunk store: each representative triple's ordered content and outcomes chunk carriers with their field, language, origin, character count and float64 vector. | Embedding | Embeddings on |

With the switch off, the build writes `catalogue.json` and `study-fragments.bin` alone. It reads no stored vector, checks no embedding coverage, replaces no derived table and leaves every embedding directory and its tables as they are.

A dataset with no represented course writes both hub files as empty JSON arrays. Its shared centroid store holds zero rows of the fixed embedding dimension, its chunk file carries the header and no record, and it writes no packed group, block or meta row.

With the switch on, the build's one transaction replaces five derived tables of the dataset. `CourseCentroidRepository.replace_all_in` rewrites the centroid rows. `neighbors.replace_all` rewrites the stored nearest-neighbour rows. `CourseEmbeddingSearchRepository.replace_all` rewrites the packed search groups, the blocks and the meta row. The blocks hold hub-centred chunk vectors with their group numbers and squared norms. [Tables and migrations](/docs/backend/catalogue/tables-and-migrations.md) lists the columns and constraints of each table. An empty build clears those five tables and leaves them empty.

A build writes its own build directory and, on an embeddings-on site, the embedding directory of the running embedding configuration and that table set. On an embeddings-on site the embedding directory is the one copy of the hub pair, and every similarity read takes the pair from the directory the opened set maps.

On a site that serves the embedding features, every packed search group is one `(group_id, sisu_course_unit_id, representative_source_hash)` triple. A group can have several chunk vectors, and the blocks hold 128 chunk vectors each except the last. A search computes the greatest centred cosine of each group's chunks for its query. The meta row carries the group count alone, and the opened artifact set retains that count without a request reading or re-verifying the row. An empty build writes no meta row, and the opened set retains a zero group count from the empty catalogue hub.

## The artifact family, the build directory and the embedding directory

`serving_key(settings)` resolves one artifact family key from the serving database name and the configured academic year. `serving_database_root` places the family under `serving/db-<encoded database name>/` beneath `ADMIN_STATE_ROOT`, and `serving_artifact_root` appends the key, so a database and a year each get their own directory.

`create_build_directory` makes one fresh directory inside that family for a build, and the family's `current` symlink names the build readers open. The builder reads the current `current` target before it writes anything and switches the symlink last, so a reader sees one complete build and never a partial build. A build directory that no `current` names is never served.

`embedding_directory(family, configuration_hash)` names the family's `embedding-<configuration hash>` directory. It holds the hub pair and the shared centroid and chunk stores of one embedding configuration, and its existence is the only record that the configuration has been built for the family. The key names the family across a mode change, so a site keeps one family whether the embedding features are on or off.

A prune preserves the active family's current build, unknown names and other database namespaces. It removes the target database's obsolete builds and owned temporary files. While the active family holds a valid current build, it also removes the builds and `current` link of every other year family. It receives the site's embedding mode, which the command resolves once through `embedding_configuration_for_site`.

On a site that serves the embedding features, the prune keeps the configured embedding directory. It removes every other embedding directory with its staging and replaced copies, removes the configured directory's staging and replaced copies, and removes any other year family that the removals leave empty. On a site with the features off, the prune keeps every owned `embedding-<hash>` directory with its staging and replaced copies in every family, so any family that holds one keeps that directory and is left in place.

When the active family holds no valid current build, every family keeps its own current build and `current` link, and the mode decides its embedding directories by the same rule.

`src/course_explorer/serving_artifacts.py` owns the read-only side of the same layout: the artifact key, the family, build and embedding paths, and the opened set of one build. [Serving state](/docs/backend/interfaces/serving-state.md#the-artifact-set-and-the-catalogue-artifact) describes what the opened set maps.

## The embedding switch

The entry point resolves the switch once and passes the resolved configuration to the build and to `ServingArtifacts.open`. The switch behaves as follows.

| Situation | Startup | Artifact step |
|---|---|---|
| Embedding features off | The supervisor opens the current build and reads no embedding directory. | A build writes the catalogue and the study fragments alone and leaves every embedding directory and its tables as they are. |
| Embedding features on, the running configuration has an embedding directory | The supervisor opens the current build and that embedding directory. | A build replaces that directory and the five derived tables. |
| Embedding features on, the running configuration has no embedding directory | The supervisor refuses to start and names `scripts/admin.py serving-artifacts`. | The build writes the directory and the tables. |

Turning the embedding features off therefore needs a restart and no build. Turning them on reuses the directory the running configuration already has, and needs a build when the family holds none for it. A change to the embedding configuration values changes the directory name, so the first start after that change needs a build.

An open reads the family's `current` build, the configured embedding directory and the packed search meta row once. A hub file holds either one finite vector of the fixed embedding dimension or, for an empty dataset, an empty array. A hub file that is not a JSON array, or a nonempty hub of another length, a non-numeric component or a non-finite component refuses the open with the build guidance. A missing directory for the running configuration refuses it the same way. A meta row whose dataset holds no stored neighbour row refuses the open, because the neighbour read has nothing to rank. A missing meta row opens zero retained groups beside an empty catalogue hub and refuses beside a nonempty one. The supervisor performs the one open before it forks its workers, appends the serving identity to the catalogue artifact and compresses that body, and each worker inherits the opened set and both bodies.

## The hubs and the centroids

A build writes these files only on a site that serves the embedding features, and a prune keeps every embedding directory while the switch is off. `src/course_explorer/embeddings/hub_files.py` owns the hub computation over current chunk vectors. `read_current_chunk_vectors(factory, embedding)` builds the effective-text catalogue, builds the desired chunks with `build_course_embedding_chunks`, requires them through `CourseEmbeddingRepository.require_current_chunks`, reads the stored vectors through `TeachingEmbeddingRepository.read_stored_chunks` with `embedding_configuration_sha256(embedding)`, keys them by `(group_id, field, language, chunk_index)` and raises `ValueError` when a desired key has no compatible stored vector.

`compute_embedding_hubs(current)` selects the outcomes-field rows and returns an `EmbeddingHubs` of the catalogue mean and the outcomes mean through `mean_unit_vectors`, which normalizes each vector, averages the components and rejects empty input, a mismatched dimension, a non-finite component and a zero-norm vector. A current vector set with no chunk returns two empty hubs and zero counts, and `write_hub_file(path, hub)` creates the parent directory and writes one compact JSON number array with `ensure_ascii=True` and a trailing newline, so an empty hub is `[]` with that newline.

`compute_course_centroids` in `src/course_explorer/embeddings/centroids.py` returns one `CourseCentroid` per represented course with a descriptive chunk. Its centroid is the unit mean of the course's hub-centred, unit-normalized chunk vectors, with the outcomes hub subtracted from an outcomes chunk, and the row carries the representative triple and the chunk count.

## The build

The builder receives the resolved embedding configuration from its entry point, resolves the artifact key, creates the build directory inside the family, and opens the target database context. On a site that serves the embedding features it resolves the embedding directory of that configuration with its staging and replaced copies, clears a staging or replaced copy an interrupted build left behind, reads the current vectors through `read_current_chunk_vectors(factory, embedding)`, computes both hubs and every centroid, and writes the hub pair and the shared centroid and chunk stores into the staging directory. It then builds the study fragments and the catalogue artifact in the build directory, and it opens the fragment store it wrote so a malformed fragment file fails before the transaction.

It then runs one transaction. On an embeddings-on site that transaction replaces the centroid rows, the neighbour rows and the packed search groups, blocks and meta row, moves the embedding directory aside to its replaced name and moves the staging directory into place. On an embeddings-off site it replaces no table and moves no embedding directory. The family's `current` symlink switches inside the transaction and commits with it.

A failure before that commit restores the family's `current` target to the build it named when the build started, or deletes the link when it named none, and restores the replaced embedding directory whenever that copy exists, including when the staging directory never reached the configured path. A published directory with no replaced copy belongs to a failed first build of the configuration and is removed, and any remaining staging directory is removed. The table changes roll back and the incomplete build directory is deleted. A restore or deletion failure is attached to the raised error as a note, so a directory that cannot be deleted is left for a prune to collect.

An error after the commit, such as engine disposal, propagates as it is and leaves the committed tables, the build files, the embedding directory, the `current` target and the completed build directory in place. The replaced embedding directory is removed after the commit, and a removal failure raises and leaves it for a prune to collect.

`scripts/admin.py serving-artifacts` brings the artifacts and the derived tables to the stored vectors of the dataset it builds. The four preparation stages write only the Working dataset, so an embedding run changes no served vector, artifact file or serving identity. The site serves a dataset's vectors after that dataset is assigned to Selected and its serving artifacts are built for it. The build reads the stored vectors each time and compares them with no earlier build.

On an embeddings-on site the builder requires complete current embedding coverage of a dataset with current chunks. Every desired chunk of the represented courses must be a completed chunk with a compatible stored vector, and at least one learning-outcomes chunk must exist, so a build of a populated dataset runs after an embedding run that completes that dataset's coverage. A dataset with no represented course has no desired chunk and builds empty hubs, an empty shared store and zero derived rows. A missing or stale desired chunk raises `ValueError` before any artifact file or derived table is written, and the readiness read names the group, field, language and chunk index. The builder deletes the incomplete build directory, leaves every embedding directory as it was, the family's `current` link points at its previous build or is absent when there was none, and no table changes. A deployment that runs the build therefore stops before it restarts any serving process.

Inference has no serving artifact and no coverage gate in the build. The inference switch decides only whether the site serves inferred data, and partial inference coverage is served while that switch is on. Operators read inference coverage in the administration console.

The builder returns `ServingArtifactsReport`. It carries `embeddings_enabled` and the two mandatory paths, `catalogue_artifact_path` and `study_fragment_path`, with the seven study-fragment values: the root, projectable, unavailable and selection-required counts, the file size and the two build costs. On an embeddings-on site it adds the five embedding paths, `chunk_count`, `outcomes_chunk_count`, `centroid_count`, `neighbor_count`, `search_group_count` and `search_block_count`, and the five embedding paths name files in the embedding directory. An empty dataset reports zero for each of those embedding counts and keeps every embedding path. Every embedding path and count is `null` on an embeddings-off site. A prune returns `ServingArtifactsPruneReport`, whose `build_id` is `null` when the family has no valid current build.

## The command

`run_administrative_serving_artifacts()` in `src/course_explorer_admin/commands.py` resolves the target settings and delegates once to the builder or the prune. An unnamed build targets the Selected dataset, which is the configured database in bootstrap, and a named `--dataset` targets that receipt's database. [Administration commands](/docs/backend/interfaces/administration-commands.md#the-serving-artifact-command) states the command's flags, its operator-menu entry and its failure guidance.

Promotion in `src/course_explorer_admin/datasets.py` calls the same `build_serving_artifacts()` owner for its copy before it publishes the Selected pointer. `copy_to_selected` resolves the site's embedding configuration once through `embedding_configuration_for_site(load_web_settings())`, builds the copy, then switches Selected, restarts only the site's web unit through `restart_web` with the website status it validated before the copy, and proves the served catalogue and a changed identity through the feature and catalogue reads. A failed build leaves the pointer and the running process alone. A failed restart or proof restores the previous pointer, restarts the unit and proves the previous catalogue. The standalone `serving-artifacts` command is the setup and maintenance path, and promotion performs no prune.

`write_mock_artifacts` in `src/course_explorer/mock_data.py` prepares the example fixture, retains its identity guard and calls the same `build_serving_artifacts()` owner for the set the site's switch selects. It writes no tracked file, so a deployment leaves the checkout unchanged. The example and administrative paths share one artifact implementation. `scripts/mock_data.py` exposes it as the `write-artifacts` action. The separate `write-bundle` action rewrites the tracked bundled vector file from the stored vectors, and no build or deploy path runs it.

## Removing a database namespace

`require_removable_serving_database_artifacts(admin_state_root, database_name)` validates and returns one database's owned artifact namespace, and `remove_serving_database_artifacts(namespace)` removes that returned path across every academic year. The path is derived solely through `serving_database_root` from a validated database name. A symlinked state root, `serving` directory or database namespace, and a non-directory namespace each refuse before removal. A missing namespace succeeds, and the internal `current` symlinks are not followed. Dataset deletion saves the validated path before it drops the exact database and removes the retained dump, then passes that same path to removal without a second validation. The prune remains the separate builder-owned housekeeping path and is not this deletion.

## Tests

| File | Covers |
|---|---|
| `tests/embeddings/test_embedding_hub_files.py` | The hub arithmetic of the `serving-artifacts` command, the descriptive-field centroid arithmetic and the representative identity, the compact JSON output with its trailing newline, and the rejection of a dataset without outcome chunks. |
| `tests/web/test_serving_artifacts.py` | A real build over a normalized catalogue, the empty migrated database that builds and opens empty hubs with a zero-row shared store, an empty catalogue and zero retained groups, table changes that a pre-commit failure leaves uncommitted, the embedding directory that a pre-commit failure restores, the committed build and embedding directory that a post-commit failure leaves in place, the prune that preserves the active build and the configured embedding directory with the features on, the prune with them off that preserves every owned embedding directory, the unknown names and other database namespaces, the prune of a family with no current build, the build guidance of a state root that holds no artifact family, an embeddings-off build over incomplete vector coverage that writes the catalogue and study fragments alone and leaves the embedding directory and the tables as they were, the embeddings-on open that reuses that directory, the open that refuses a non-array hub, a nonempty hub of another length or with a non-finite component, a changed embedding configuration that refuses until a build, and an embeddings-on build of incomplete coverage that fails before the target changes. |
| `tests/embeddings/test_centroid_repository.py` | The complete replacement of the centroid set in one transaction, including an empty set that leaves the table empty, and the stored row's representative identity, configuration hash, chunk count and 8192-byte centroid. |
| `tests/embeddings/test_shared_store.py` | The shared store opened under another dataset identity or another academic year is refused. |
| `tests/admin/test_operator_menu.py` | The `embedding-build-serving-artifacts` case of the `serving-artifacts` command path: choosing the build entry invokes the builder once and performs no other action. |
| `tests/admin/test_dataset_database.py` | The confirmed promotion of a Working or older retained source: a verified copy, a new artifact family that opens, one authoritative Selected role and one Working role, a changed serving identity, and retained old families and data. A failed build, restart, feature proof or rollback: no switch and no restart on a build failure, restored previous selection and serving on a post-switch failure, both errors on a failed rollback, and preserved failed-copy resources. |
| `tests/web/test_launcher.py` | The real supervisor, router and workers starting on an embeddings-off build that holds the catalogue and the study fragments alone. |

The generation that fills the chunk vectors is described in [Embedding generation](/docs/backend/text-and-vectors/embedding-generation.md), and the restarted supervisor that reads a completed build is described in [Web supervisor](/docs/backend/interfaces/web-supervisor.md#startup-and-validation).
