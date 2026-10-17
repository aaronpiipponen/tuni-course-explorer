# Architecture

TUNI Course Explorer serves the app from a read-only request path and prepares its course data along a separate preparation path.

## The request path and the preparation path

A read starts in the browser app and ends in the web server. The web server serves the two shell documents and the compiled assets of the browser app, and it answers ten read commands over the prepared data. Nothing on this path writes data, starts a stage, or reaches the worker.

The preparation path starts at the administration command. Its four stages fill the data that the reads consume. Ingestion captures the public curriculum source, validates the capture, and writes official courses, modules, versions, and rules. Embedding writes the teaching-text chunks and their vectors. Translation writes translated teaching text beside the official text. Inference writes inferred prerequisites and equivalence groups. Ingestion and embedding run on the machine that runs the administration command, and translation and inference run on the worker.

The two paths meet at one thing. The PostgreSQL database with pgvector holds the selected dataset, the stages write it, and the web server reads it. [System context](/docs/architecture/system-context.md) describes the parts of the system, what each part does, and the settings that decide which database a process reads.

## One behavior behind every surface

A read in the browser and the equivalent machine command reach the same command function. Search is one function that both the search route and the search script call, and the prerequisite graph read and the minimum route read are two operations over one prepared calculation that the prerequisite route and the prerequisite script both call. A web route validates its inputs and returns the report of the command. A machine adapter parses its arguments and delegates once. One implementation therefore answers the browser app and the machine commands alike, and neither surface restates the behavior of the other.

## Course state in the browser

The selected and completed courses, the exclusions, and the app language belong to a profile in the browser state, which the browser holds in local storage. A profile holds the settings of each tab as well, so switching the profile rebuilds every tab from the state of the chosen profile. The open tab belongs to the browser tab that shows it.

The web server stores no profile and returns none. The selected and completed courses reach it only as request inputs, and a read that needs courses accepts the canonical course identities and the toggles the browser sends. A course carries one canonical identity, so a selection made in one tab counts the same in every other tab and in every request.

## Official data and inferred data

Official data is what the ingestion stage writes from the public curriculum source. Inferred prerequisites and equivalence groups are stored in their own tables with their own coverage state, and the inference stage writes inferred output without modifying an official row. The inferred store refuses an expression whose nodes do not all carry inferred origin, so a derived claim cannot appear as an official statement.

A translation is stored beside the text it was made from and does not replace it. Official text takes precedence, and a translation whose recorded source text differs from the official text is stale, reported, and left out of the effective text.

The inference stage runs language models on the worker, and the web server holds no model credential and no worker connection value.

## Where the separations are enforced

The separations above are structural, and each one is enforced in code. [System boundaries](/docs/architecture/boundaries.md) describes the read-only web surface, the browser-held state, the split between official and inferred data, the local-only inference, configuration ownership, and the single schema and format. [Invariants and their enforcement](/docs/architecture/invariants.md) names the module that owns each rule and the tests that cover it.
