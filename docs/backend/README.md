# Backend

The backend prepares the official catalogue, derives text, vectors, and inferred prerequisites from it, and serves read-only course data.

## What the backend owns

Every backend subject works on one PostgreSQL database with pgvector that holds the selected dataset: the official catalogue, the teaching text and its translations, the embedding chunks with their vectors, and the inferred prerequisites and equivalence groups. The preparation stages write that database, and the web server reads it. The settings that select the dataset, reach the embedding service, and configure each stage live in the subsystem files under `config/`, described in [Configuration](/docs/backend/configuration.md).

## The catalogue and its derived data

[Catalogue](/docs/backend/catalogue/README.md) covers how the public curriculum source becomes official courses, modules, versions, and rules, and how one representative version and one official structure projection follow from that catalogue. [Text and vectors](/docs/backend/text-and-vectors/README.md) covers the effective text of a representative version, the translations stored beside the official text, and the chunk vectors that every similarity read measures.

## The reads over the prepared data

[Search and discovery](/docs/backend/search-and-discovery/README.md) covers query search, the comparison of two chosen courses, and the discovery of next courses and recommendations from a chosen basis. [Prerequisites](/docs/backend/prerequisites/README.md) covers the compiled requirement expression, the graph, and the minimum route. [Inference processing](/docs/backend/inference/README.md) covers the inference stage, which runs on the worker and reads teaching text with a language model to propose inferred prerequisites and equivalence groups apart from the official catalogue.

## The read interface

The web server answers a fixed set of read routes over the prepared data. [Interfaces](/docs/backend/interfaces/README.md) describes them.
