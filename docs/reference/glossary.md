# Glossary

This glossary defines the terms the documentation uses for courses, search, comparison, prerequisites, discovery, the structure of studies, inference, and administration.

## Courses and the catalogue

| Term | Meaning |
|---|---|
| Course | One course as the app shows it, shared by all of its official versions. Each course has one canonical identity. |
| Course version | One exact official version of a course, as published for one curriculum period. |
| Representative version | The one course version chosen to stand for a course. The selection prefers the configured academic year, then a version inside the activity window. |
| Curriculum period | One official academic period with a starting academic year. Every course version and module version belongs to curriculum periods. |
| Activity window | The number of academic years, set by `ACTIVE_ACADEMIC_YEAR_WINDOW`, inside which a listed version makes a course active. |
| Active course | A course with a version listed inside the activity window. The app labels it **active**. |
| Inactive course | A course with no version listed inside the activity window. The app labels it **inactive**. |
| Module | A degree programme, study module, or other official grouping of courses, shared by all of its official versions. |
| Module version | One exact official version of a module, with its type, target credits, validity, and rule tree. |
| Minimal official catalogue | The list of courses, with their canonical identities, codes, names, credits and activity flags, and modules with their eligible versions, that the browser caches by serving dataset identity and filters locally. |
| Narrowing | The browser's local filtering of the minimal official catalogue by name or code as text is typed into a course or module box. |
| Projected read | A database read that selects only the columns its caller consumes rather than loading whole rows. For those columns it returns the same value as the full read. |
| Credits | The credit range of a course version, or the target credits of a module version. The app abbreviates credits as **cr**. |
| Official data | Data as the university publishes it in the public curriculum source. |
| Teaching text | The name, content, and learning outcomes text of a course version. |
| Official text | Teaching text as the university publishes it. Official text always takes precedence over a translation. |
| Translation | A translated teaching text field, stored apart from official text with the source text it was made from. |
| Stale translation | A translation whose recorded source text differs from the official text. A stale translation is reported and never used. |
| Effective text | The teaching text used for one field and language: the official text when it exists, otherwise a translation that is not stale. |
| Name-only course | A course whose representative version has an effective name but no effective content or learning outcomes in either language. |
| Unembeddable course | A course whose representative version has no effective name, content, or learning outcomes in either language. |

## Configuration

| Term | Meaning |
|---|---|
| Subsystem file | One TOML file under `config/` that holds the portable settings of one subsystem, copied from a tracked template under `examples/config/`. |
| Environment file | The `.env` file at the repository root, ignored by Git, that holds the values that must change per machine. |
| Settings family | The group of settings that one settings class loads and validates. |
| Settings owner | The configuration module that reads the subsystem files and the environment file for every settings family. |
| Compose environment file | The temporary environment file that the administration command generates for each Docker Compose run and deletes afterwards. |
| Feature read | The one `POST /api/features` read the browser app makes before its shell mounts. It reports the two feature switches and the serving dataset identity, and runs no command. |
| Serving dataset identity | The opaque digest of the serving generation and the selected dataset id, or of the serving generation and a null selection when the site reads its configured database. Every cached web response reports it, and the browser's memory cache and derived structure store are scoped to it. |
| Serving generation | The random value that the web server's supervisor creates once at startup and that every front router and worker process it starts inherits. A restart of the web server creates a new one. |
| Feature switch | One of the two settings in `config/web.toml` that decide which features a site serves: `WEB_EMBEDDINGS_ENABLED` for comparison, recommendations and semantic search, and `WEB_INFERENCE_ENABLED` for inferred prerequisites. |

## Capture and data preparation

| Term | Meaning |
|---|---|
| Capture | One run that downloads course and module data from the public curriculum source and stores it unchanged. |
| Manifest | The record of one capture: every response, object, curriculum period, and content hash it holds. |
| Stored response | One file that holds the exact bytes of one response from the public curriculum source, named by its content and never overwritten. |
| Source snapshot | The stored position and hash of one captured source object. |
| Normalization | The step that validates the current capture and converts it into official courses, modules, versions, and rules. |
| Embedding | A vector that represents the meaning of a piece of teaching text. |
| Chunk | One overlapping piece of the teaching text of a representative version, embedded and stored with its vector. |
| Embedding hub | The mean of the catalogue's unit vectors. Search and comparison subtract it from every vector before measuring similarity, so unrelated courses score close to zero. |
| Outcomes hub | The embedding hub computed over learning outcomes text only, used when comparing learning outcomes. |

## Search and comparison

| Term | Meaning |
|---|---|
| Search method | One of the four ways a query matches a course: **Exact code**, **Substring**, **Fuzzy search**, and **Semantic**. **Semantic** runs only on a site that serves the embedding features. |
| Exact code match | A query token that equals a course's official code. |
| Substring match | A query found inside a course name or official code, ignoring case. |
| Fuzzy match | A course name close to the query, scored from 0 to 100 and kept above a configured cutoff. |
| Semantic match | A course whose embedded teaching text is close in meaning to the query, kept above a configured minimum score. |
| Unified search | The search that runs every search method the site serves for one query and merges their results into one entry per course. |
| Match source | A search method that returned a given result. One result can have several match sources. |
| Tier order | The configured order of the search methods that sorts merged results, with active courses before inactive ones. |
| Comparison meter | One of the five percentages that compare two courses: **Overall relatedness**, **Content similarity**, **Learning-outcome similarity**, and **Overlap** in each direction. |
| Overlap | The share of one course's teaching text that has a close match in the other course. |
| Verdict | The one label that summarizes a comparison: **Heavily overlapping**, **Partly overlapping**, **Same area, different content**, **Loosely related**, or **Unrelated**. |
| Not available | The state of a comparison meter that has no value to show. |

## Prerequisites and routes

| Term | Meaning |
|---|---|
| Prerequisite | A course or other requirement that a course expects before it is taken. |
| Required prerequisite | A prerequisite that must be met. The app labels these **Required**. |
| Recommended prerequisite | A prerequisite that the course advises but does not demand. The app labels these **Recommended**. |
| Official prerequisite | A prerequisite that the university publishes. |
| Inferred prerequisite | A prerequisite found by analysis of teaching text and stored separately from official prerequisites. It draws in the same graph, and a course reached only through inferred occurrences carries the **inferred** label. |
| Prerequisite expression | The source form of a prerequisite requirement, built from course, AND, OR, cardinality, credit and course-count nodes, with module and unresolved nodes in official requirements only. An inferred set stores it, and the compiler reads it. It is not the calculation representation. |
| Solver structure | The calculation representation of one graph root, built from calculation pieces. The graph report carries it beside the drawing, and the satisfaction evaluator and the minimum route read it. |
| Calculation piece | One provenance-free node of the solver structure, interned once by its kind, its values, its ordered child piece IDs and its evaluation flags. |
| Display piece | One drawn box identified within its course subtree by its displayed kind, values and drawn children. A saved node mark names one display piece. |
| Support binding | The link in the graph report from one calculation support to the drawn node identities and the markable box identities it stands for. |
| Drawing allowance | The counts of courses, nodes and connections that one graph read reports against the configured drawing limit `PREREQUISITE_GRAPH_MAX_ELEMENTS`, with whether the browser may draw them. |
| Allocation limit | The configured bound `PREREQUISITE_PATH_MAX_COMPACT_NODES` on the exact minimum route search. A calculation past it restarts once with the greedy search. |
| AND group | A group whose every member must be met. |
| OR group | A group of options of which one must be met. |
| Option pool | The OR group that collects every official and inferred option of one category, required or recommended, for one course. |
| Equivalence group | A group of two or more courses that analysis of teaching text treats as interchangeable. Membership in one group does not carry over to another group. |
| Graph root | The course whose prerequisite graph is open in the **Prerequisites** tab. |
| Basis | The set of courses that counts as already covered in a calculation: either the completed courses, or every selected course. The app shows it as **Route basis** and **Discovery basis**. |
| Exclusion | A course marked **Excluded**. It never counts as covered and no route passes through it, and the graph shows it and its own prerequisites. |
| Node mark | A profile setting that completes or excludes one drawn module or numeric requirement node in the prerequisite graph without changing the selected or completed course sets. A shared drawn node covers every source requirement it represents, and the mark applies to every calculation piece that node stands for. |
| Active only | The setting that leaves inactive courses out of search results, the prerequisite graph and route, and the Discover lists. |
| Minimum route | The set of courses that meets a course's prerequisites with the fewest new credits. The app finds it with **Find minimum route**. |
| New credits | The credits of every course in a route that is not in the basis, each course counted once. |
| Route outcome | The result of a minimum route calculation: **Exact minimum route**, **Approximate route**, **No route found**, **Route unresolved**, **No route exists**, or **Shortfall**. |
| Shortfall | The route outcome in which a module rule is below its bound because only active courses are allowed. |
| Substitution | A set of courses that the university accepts in place of one course. A substitution applies in one direction only. |
| Unresolved requirement | An official requirement that cannot be resolved to courses, such as a reference to a missing course. |
| Unexpandable content | An official module or credit requirement whose contents cannot be expanded into courses. The minimum route charges its minimum credits once. |
| Free-choice content | An official requirement for freely chosen studies, shown in the graph and not expanded into courses. |

## Discovery and the structure of studies

| Term | Meaning |
|---|---|
| Next courses | The courses whose prerequisites the basis covers, listed in the **Discover** tab. |
| Prerequisite mode | The rule for next courses: **All** lists a course when all of its prerequisites are covered, and **Partially covered** lists it when any one prerequisite is covered, including a course whose prerequisites are all covered. |
| Prerequisite coverage | The share of a next course's prerequisites that the basis covers, shown separately for required and recommended prerequisites. |
| Inferred dependence | The mark on a next course that is listed only because of inferred prerequisites. |
| Recommendations | Courses with teaching text similar to the basis, ranked by similarity and listed in the **Discover** tab as **Recommended for you** on a site that serves the embedding features. |
| Near-duplicate | A candidate recommendation that overlaps a basis course above a configured share. Near-duplicates are left out of recommendations. |
| Structure of studies | The official structure of each programme in the **Structure of studies** tab, shown as modules, courses, and rules. |
| Programme | A degree programme or a bare module at the top level of the structure of studies. The app adds one with **Add programme** and orders them in the tab. The row's kind label follows the official type, so a top-level bare module reads **module** while its position gives it the programme menu and reset. |
| Holder | The programme or module that a structure operation acts on: the one an addition or replacement places, a move relocates, and a reset or delete clears. |
| Unplaced studies | The part of the structure of studies that holds selected courses not placed under any programme or module. |

## Browser app

| Term | Meaning |
|---|---|
| Tab | One of the five views of the app: **Search**, **Compare**, **Prerequisites**, **Discover**, and **Structure of studies**. **Compare** appears only on a site that serves the embedding features. |
| Selected course | A course added to the current profile's selection. |
| Completed course | A course marked with **Mark completed**. A completed course is always selected. |
| Course menu | The menu of actions on a course: **Add to comparison** on a site that serves the embedding features, **Open prerequisite graph**, **Add to Unplaced studies**, **Mark completed**, and **Open in Sisu**. |
| Sisu capture | The file the Sisu import script downloads from a plan in Sisu's structure of studies view, which the app imports as one profile. It is separate from a capture of the curriculum source. |
| Profile | A named set of the app's state in the browser: language, selected and completed courses, and the state of each tab. |
| Open tab | The tab a browser tab shows. It belongs to that browser tab's session storage rather than to a profile. |
| App language | The language of the app's interface and course names in a profile, either Finnish or English. |
| Browser state | The saved state of every profile, kept in the browser's local storage. |
| Read cache | The bounded in-memory store of successful reads and calculations above the tab panes, scoped to the serving dataset identity and never part of a profile or of browser storage. Successful study structures also persist in a derived IndexedDB store under that identity, their root and their module-version selection. |
| Bottom bar | The bar at the bottom of the app at a phone width, with one button for each served tab and **More**. |
| Bottom notice | A temporary message at the bottom of the app that reports an action's result and can offer a button for a related action. |
| Docs | The documentation wiki inside the app, opened from **Docs**. |

## Inference

| Term | Meaning |
|---|---|
| Inference | The stage that reads teaching text with a language model and proposes inferred prerequisites and equivalence groups. |
| Target course | The course whose prerequisites one inference run proposes. |
| Label safety | The rule that keeps official prerequisite structure out of candidate selection and model inputs. |
| Rerank | The step that scores a pool of candidate courses against the target course and keeps the strongest candidates for the language model. |
| Proposal | One validated inference result for one target course. |
| Finding flag | A mark of uncertainty that the language model attaches to one proposed option or equivalence group. |
| Publication | The step that writes the accepted proposals into the stored inferred prerequisites and equivalence groups, replacing the stored result as a whole. |
| Inferred set | The stored inferred prerequisites of one course, with their coverage state. |
| Inference coverage | The counts of eligible, retained complete, published, and uncovered target courses that the inference coverage report gives. |
| Disposition | An operator decision recorded for one target course: done, failed, or automatic. |

## Administration

| Term | Meaning |
|---|---|
| Administration command | The command `scripts/admin.py`, which runs the operator menu and the machine commands for the stages, datasets, reports and maintenance. |
| Operator menu | The numbered interactive menu of the administration command, used to set up, run, and report on the stages. |
| Stage | One of the four kinds of preparation work: ingestion, embedding, translation, and inference. |
| Local stage | A stage that runs on the machine that runs the administration command: ingestion and embedding. |
| Remote stage | A stage that runs on the worker: translation and inference. |
| Lifecycle | The state of a stage: idle, starting, running, paused, stopped, completed, or failed. A status read reports a starting or running stage with no live process as interrupted. |
| Worker | The separate machine that runs the remote stages on its own copy of the selected dataset. |
| Request path | The route from the browser app through the web server to the database and the embedding service. |
| Front router | The web server process that listens on the configured loopback port, admits each request, forwards it to one worker process and writes its request record. |
| Worker process | One of the `WEB_WORKERS` web server processes that serve dataset reads behind the front router. |
| Admission control | The front router's limits on API requests when `ADMISSION_ENABLED` is true: the light rate and concurrency limits, the heavy budget, the heavy slots and the heavy queue, each scaled by the load regime. |
| Admission class | The class the front router gives one API request: free, light or heavy. A heavy request carries an estimated cost in core-seconds and passes the heavy limits. |
| Load score | The configured weighted sum of whole-host CPU utilisation and the front router's light and heavy request activity over the configured load window. |
| Load regime | The admission state derived from the load score: headroom, middle or saturated. Saturation holds until the score falls below the configured release line. The regime controls the request limits, the heavy budget, the heavy slots and the queue capacity. |
| Heavy budget | The core-seconds of heavy requests one user may spend in one window. It moves linearly from `ADMISSION_HEAVY_BUDGET_CORE_SECONDS` at the headroom position to `ADMISSION_HEAVY_BUDGET_SATURATED_CORE_SECONDS` at saturation. |
| Preparation path | The route from the administration command through the four stages to the database. |
| Worker session | One run of a remote stage on the worker, from its prepared database copy to the return of the result. |
| Checkout identity | The branch and the HEAD revision of one Git checkout, which setup and preflight read on the server and on the worker. |
| Dataset | One complete database of courses, modules, and derived data. |
| Dataset receipt | The record kept for one dataset that names its dataset id, database name, enrollment kind, retained dump digest, and the verification read from the database. |
| Selected dataset | The dataset that the web server and the stages read. |
| Database snapshot | A verified dump of one dataset, taken when a worker session starts and when it returns. |
| Dataset return | The step that brings the worker's finished database back and makes it the selected dataset. |
| Dataset rotation | The step after a dataset return that keeps the selected dataset and the one before it, and deletes older datasets. |
| Catalogue summary | A read-only report of the counts of curriculum periods, courses, active courses, course versions, modules, and module versions in a dataset. |
| Coverage report | A read-only report on how much of the selected dataset has translations, embeddings, and inferred prerequisites. |
| Periodic reboot | A restart of the worker after a configured amount of model run time. |
| Administration surface | The administration console and the administration backend, with their own package, configuration and process beside the web server. |
| Administration console | The separate signed-in browser application with the tabs **Dashboard**, **Data preparation**, **Inference**, **Logs** and **Settings**, which runs fixed administration commands. |
| Administration backend | The separate loopback process that signs an operator in, admits each console request and runs the fixed command behind it. |
| Administration session | One signed-in grant of the administration backend, held in that process's memory until it reaches its configured idle or total lifetime, the operator signs out, the stored credential changes, or the backend restarts. |
| Anonymous session | An in-memory grant of the administration backend that carries the CSRF token used to sign in and grants no administration access. |
| Anonymous session creation limit | The server-wide count of fresh anonymous sessions the administration backend admits in a sliding window. Reusing a live session consumes none of the count. |
| Administration lock | The file `data/admin-web/lock` that three consecutive failed sign-ins create. While it exists, the administration backend refuses every request. |
| Command log | The administration backend's bounded record of its explicit commands, its failed automatic reads, and its sign-in, failed sign-in and lock events. |
| Request record | One line the web server appends for one HTTP request: its hour, route, status and duration. |
| Usage report | The report of the request records in one window of hours, with the request count, the mean duration and one row per route. Each report prunes the records older than the configured retention. |
| Backup file | One file under `data/backups` that the backup cleanup lists and can delete. |
| App rebuild | The maintenance command that builds the browser app, recreates the database and embedding containers, restarts the web server and checks its bind. |
| Administration rebuild | The maintenance action that builds the administration console and then queues a restart of the administration backend, which signs every operator out. |
