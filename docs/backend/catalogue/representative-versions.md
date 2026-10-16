# Representative versions and activity

Every feature reads one representative version per course, chosen by a fixed preference from the versions listed in the curriculum periods.

## One representative per course

A course is one canonical identity shared by all of its official versions. A [Course version](/docs/reference/glossary.md#courses-and-the-catalogue) is one exact official version as published for one [Curriculum period](/docs/reference/glossary.md#courses-and-the-catalogue), with its own code, names, credits, official URL, teaching text, prerequisite options, and substitution options.

Every feature reads one of those versions, the representative version, so search, comparison, prerequisites, discovery, and the structure of studies describe the same official data for a course. The selection runs on every read that needs a representative, over the versions and the period memberships the database holds.

## Choosing the representative

A version takes part through each curriculum-period membership whose academic year is at or before the current academic year. A version listed only in years after the current academic year has no eligible year, and a course whose every version is listed only after the current year has no representative.

Each version is reduced to its greatest eligible year. The candidates are then ordered in three steps.

1. A version whose greatest eligible year is the current academic year.
2. Otherwise a version whose greatest eligible year lies in the activity window, the greatest such year first.
3. Otherwise a version whose greatest eligible year is the greatest earlier year.

Two candidates that agree on the step and on the year are separated by the greater source modification ordinal, and a version with no recorded ordinal ranks below a version that has one. When the ordinals also agree, the lexicographically greatest exact source version identity is chosen.

The selection reads the academic year and the window stored with each course, so a course's representative is chosen under the same values that decide its active state.

![Each version of a course keeps its greatest year at or before the current academic year. A version listed only after the current academic year is left out, and a course with no remaining version has no representative. The candidates are then ordered by the current academic year, the greatest year inside the activity window, and the greatest earlier year, with a final box that breaks a tie by the greater source modification ordinal and then by the greatest exact source version identity.](/docs/diagrams/representative-selection.svg)

## Activity and the window

An active course has at least one version listed in a curriculum period whose academic year lies inside the inclusive activity window. The window runs from the current academic year minus the window length plus one, up to and including the current academic year. A course with no version in the window is an inactive course.

`CURRENT_ACADEMIC_YEAR` sets the current academic year and `ACTIVE_ACADEMIC_YEAR_WINDOW` sets the window length, both in `config/curriculum.toml`. The example sets the window to three academic years, so a version listed in the current academic year or in either of the two before it keeps its course active.

The active state is stored with the canonical course record, together with the first and the last academic year in which any version of the course is listed, and with the year and window that were in force when that record was last written. A catalogue read takes the stored state as it stands and never recounts it.

[Normalization](/docs/backend/catalogue/ingestion.md) recomputes the active state and the listing years for every course its batch touches, from the period memberships of the versions stored for that course. Normalization and the reads apply one shared window bound, so a course is active or inactive by the same rule in every place that decides it.

## Modules for an academic year

A module read takes an academic year and selects one module version from that module's versions. A version takes part when it is a member of that exact academic year's curriculum periods.

When a module has no version with that exact membership, a reader also accepts a version with no period membership whose own validity bounds contain the requested year. An empty candidate set means the module has no version for that year, and more than one candidate is ambiguous. The structure of studies requires exactly one candidate and fails with the requested year when the set is empty or holds more than one version. Module search fails when the query matches a module that holds more than one candidate version for the academic year.

The [Prerequisite graph](/docs/backend/prerequisites/prerequisite-graph.md) is the one reader that also accepts a single nearest dated version when the strict candidate set is empty, and the graph discloses that fallback.

## Courses without a representative

These cases decide what the catalogue holds and what a read returns.

| Case | Outcome |
|---|---|
| Every version is listed only after the current academic year | The course has no representative and is inactive. A read that returns whole courses returns it with no representative attached, and a read that returns one summary per represented course omits it. A request for the summary of the course fails loudly. |
| The official code is null | Normalization leaves the version out of the catalogue with its teaching text, its curriculum-period memberships, and its options, and reports it as excluded. Its stored response and source snapshot stay, the other versions of the course are stored as usual, and the course record is dropped only when no coded version remains. |
| The official code is missing or blank | Normalization fails. |
| No stated credit maximum | The version keeps no maximum, and a summary of the version reports the minimum credit value only. |

The reads themselves are described in [Curriculum reads](/docs/backend/catalogue/curriculum-reads.md), and the stored course and version records are described in [Data model](/docs/backend/catalogue/data-model.md).
