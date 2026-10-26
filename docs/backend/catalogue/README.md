# Catalogue

The catalogue holds the official courses, modules, and curriculum periods that the preparation path captures, validates, normalizes, and prepares for every read.

## Capture and normalization

Ingestion runs as one stage with two steps. The capture reads the anonymous public curriculum source and stores each response unchanged, so a stored response always holds the same bytes. Normalization validates one completed capture and converts it into official courses, modules, their versions, and their rule trees in one transaction, and it reports a version whose official code is null as an exclusion. [Ingestion](/docs/backend/catalogue/ingestion.md) describes the stage, its pause and stop boundaries, and the configuration keys that steer the source reads. [Curriculum capture and replay](/docs/experiments/runtime-storage-and-serving/curriculum-capture-and-replay.md) records the scale of a full-catalogue capture and two source-free replays of it.

## Canonical identity, versions, and activity

A course and a module each have one canonical identity that all of their official versions share. Every read that needs a course reads one representative version, chosen from the versions the curriculum periods list, and the activity window stored with the course decides whether the app marks it active. [Representative versions and activity](/docs/backend/catalogue/representative-versions.md) states the selection order and the window rule that normalization and the reads share.

## The stored catalogue

[Data model](/docs/backend/catalogue/data-model.md) describes the catalogue entities, the capture records, and the tables that hold the inferred side apart from official data. One Alembic chain owns the schema, and a database at any other revision is refused.

## The official structure projection

[Structure of studies in the catalogue](/docs/backend/catalogue/study-structure.md) projects the official rule trees of the requested roots into modules, courses, and rules exactly as the university states them, so it runs no inference and applies no activity filter. The minimal official catalogue read serves the one list that the browser's narrowing boxes filter locally, and the structure read projects several roots over one shared module and summary map.

The capture and normalization internals, the read seam, the table detail, and the projection traversal are described in [Capture and normalization](/docs/backend/catalogue/capture-and-normalization.md), [Curriculum reads](/docs/backend/catalogue/curriculum-reads.md), [Tables and migrations](/docs/backend/catalogue/tables-and-migrations.md), and [Structure projection](/docs/backend/catalogue/structure-projection.md).
