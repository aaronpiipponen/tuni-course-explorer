# Text and vectors

The teaching text of each representative version becomes effective text and the overlapping chunk vectors that every similarity read measures.

## Official text and stored translations

Official text is teaching text as the university publishes it, and it is stored with the exact course version it belongs to. A translation is stored apart from it, one row per version, field, and target language, with the hash of the source text it was made from. Official text always takes precedence, and a translation whose recorded source text differs from the official text is stale, reported, and never used. [Teaching text and effective text](/docs/backend/text-and-vectors/teaching-text.md) describes the resolution, and [Translation](/docs/backend/text-and-vectors/translation.md) describes the remote stage that fills the missing cells on the worker.

## Effective text

The effective text of one cell is the official text when the version holds one, otherwise a translation that is not stale, otherwise nothing. Each of the six cells of a representative version resolves on its own. The embedding stage reads those cells, and the coverage report counts them. [Teaching text store](/docs/backend/text-and-vectors/teaching-text-store.md) describes the derived table and the one import that writes it.

## Chunks and vectors

The embedding stage splits the effective text of each representative version into overlapping chunks and stores one vector per chunk, with the lifecycle state of the chunk and the identity of its inputs. A vector has 1024 components, and a read uses only completed chunks written under the embedding configuration in force. Two hub files hold the means that centre every similarity measurement. [Embeddings](/docs/backend/text-and-vectors/embeddings.md) describes the service, the generation run, the hubs, and the keys that pin the runtime.

The provider contract, the chunk assembly, the reconciliation, and the hub arithmetic are described in [Embedding generation](/docs/backend/text-and-vectors/embedding-generation.md).

The translation and semantic retrieval measurements behind those vectors are recorded in [Machine translation as retrieval-preserving transformation](/docs/experiments/search-and-translation/translation-and-retrieval.md) and [Exact and approximate semantic retrieval](/docs/experiments/search-and-translation/semantic-retrieval.md).
