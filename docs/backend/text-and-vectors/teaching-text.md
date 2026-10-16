# Teaching text and effective text

Teaching text is the name, content, and learning outcomes of a course version, and every read resolves it from the official text and the stored translations.

## Teaching text and its languages

The teaching text of a course version has three fields: the name, the content, and the learning outcomes. Each field exists in Finnish and in English, and one field in one language is one cell.

Official text is teaching text as the university publishes it. [Ingestion](/docs/backend/catalogue/ingestion.md) captures it from the public curriculum source, and it is stored with the exact course version it belongs to.

A course version also carries prerequisite text and additional information. Those two are not teaching text, so no translation is made for them and no resolution reads them.

Every read works on the representative version of a course, so the teaching text of one course comes from one exact version.

## Official text, translation, and effective text

Official text always wins. When the version holds a non-blank official value for a cell, that value is the effective text of the cell, and no stored translation is read for it.

A translation is stored apart from the official text, one row per course version, field, and target language. Each row records the source language it was made from and the hash of the exact official source text. A translation is usable only while the official text of the same field in its recorded source language hashes to that recorded value.

A [Stale translation](/docs/reference/glossary.md#courses-and-the-catalogue) is a stored translation whose recorded source value differs from the current official text of the same field in its recorded source language. That field holds a different value, or it holds no official text. A stale translation yields no effective text, it is reported, and it is never used. The read leaves the stored row in place, and the report lists it.

The [Effective text](/docs/reference/glossary.md#courses-and-the-catalogue) of a cell is the official text when the version holds one, otherwise a translation that is not stale, otherwise nothing. Official and translated text are never merged into one field, and a translated value is never presented as official.

## How one cell resolves

The resolution reads one cell at a time, in a fixed order.

1. A non-blank official value for the field and language makes the cell official.
2. Otherwise a stored translation for that cell is usable when the current official text of the same field in the translation's recorded source language hashes to the recorded source hash. The cell then holds that translation.
3. Otherwise, when a stored translation exists and the official text of the same field in its recorded source language differs from the recorded value, the cell is stale. The cell yields no effective text and one reported stale row, which names the stored source hash and the current one.
4. Otherwise the cell is missing.

![The flow resolves one field and one language of a representative version. A non-blank official value is used as it stands, a stored translation is used when the official text of the same field in its recorded source language hashes to the recorded source hash, and a stored translation whose recorded value differs is reported as stale and yields no effective text. A cell with neither text nor a usable translation yields no effective text.](/docs/diagrams/effective-text-resolution.svg)

Every represented course has six cells, three fields in two languages, and each cell falls into exactly one of the four classes. The four counts of a cell therefore sum to the number of represented courses, and the resolution of one cell never changes another.

A resolved cell reports its text, its origin, the hash of the text it holds, and the hash of the official source it came from. A cell that holds a translation also reports the method it was made by, the model identity of a machine translation, and the time it was produced.

## Who reads effective text

The embedding stage reads the effective text of every represented course, cell by cell, and turns it into overlapping chunks and vectors. [Embeddings](/docs/backend/text-and-vectors/embeddings.md) describes that stage. Semantic search and comparison measure those vectors, so they read effective text through them, and [Inference](/docs/backend/inference/inference.md) reads the effective text itself when it builds its packets.

Because official text always wins in the resolution, a read of a course never presents a translated value as official, and a cell with no effective text contributes no text at all.

## The coverage report

A coverage report is a read-only report over the selected dataset. For each of the six cells it counts how many represented courses hold official text, a translation, a stale translation, or nothing, and it lists the stale rows in a fixed order with their stored and current source hashes. It also counts canonical courses, represented courses, and courses with no representative. A represented course with an effective name and no effective content or learning outcomes in either language is a Name-only course, and a represented course with no effective name, content, or learning outcomes in either language is an Unembeddable course.

The report reads the same resolution as the effective catalogue, so its counts and the resolved text always agree. It reads the teaching text of the representatives without materializing whole courses.

The [Operator menu](/docs/operations/operator-menu.md) reports it for the selected dataset, and a dataset verification records it together with the embedding and inference coverage of that dataset. [Datasets](/docs/operations/datasets.md) describes the verification.

## Where the store is written

Translations live in one derived store, apart from the official tables, and the store has one write path: an import of validated entries for the selected representatives. The import requires a represented version, no official text in the target cell, and the exact official source text of the source cell. The store refuses the whole batch when one entry breaks those conditions, so a failed import writes no row.

[Teaching text store](/docs/backend/text-and-vectors/teaching-text-store.md) describes the table, the entry contract, and the import conditions. The [Translation](/docs/backend/text-and-vectors/translation.md) stage produces those entries on the worker, and its import is the only way a derived row appears in the store.
