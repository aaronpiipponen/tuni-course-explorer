# Next courses

A next course is a course whose prerequisites the chosen basis covers, selected by the prerequisite mode and ordered by coverage or by name.

## What a discovery request reads

A discovery request carries the selected course set, the completed course set, the chosen [basis](/docs/reference/glossary.md#prerequisites-and-routes), the [prerequisite mode](/docs/reference/glossary.md#discovery-and-the-structure-of-studies), the display language, the inference toggle, and the activity scope. Each course entry is a canonical identity or an exact official code, and one bulk lookup resolves the whole request into canonical courses.

The basis is either the completed courses or every selected course. When the request names no selected course, the completed set is also the selected set, so a list of completed courses alone drives discovery. A completed course that is not selected fails the request. A blank identity, an unknown basis, an unknown mode, or a display language other than Finnish or English fails before any settings read and before any database read.

An empty chosen basis returns an empty report, and that request reads no candidate and compiles none.

Discovery reads the two course sets and the request policy, and those inputs decide the whole list.

The diagram follows one request through the stages this page describes.

![The chosen basis supplies source identities to a bounded reverse read, and each candidate is compiled to its direct prerequisite options. The prerequisite mode decides eligibility, and the eligible candidates carry their prerequisite coverage and their inferred dependence into an ordered list.](/docs/diagrams/discovery-coverage.svg)

## Report reuse

The serving supervisor creates one next-course report region before it forks the workers, and every worker reads and writes the same region. The region is bounded by `WEB_NEXT_COURSE_REPORT_CACHE_BYTES`, and clock eviction removes complete reports when a new report needs space. The key is the canonical selected set, the canonical completed set, the chosen basis, the mode, the display language, the inference flag and the activity flag. A second key holds the request's raw selected and completed inputs with the same policy fields, and it answers a repeated request before any input is resolved. An alias names the canonical report it resolves to, and it answers only while that report is retained. Both **All** and **Partially covered** use the region under separate keys, and a repeated canonical request returns the held report before candidate discovery or compilation runs.

The recommendation command reads the same region for the exclusion set. A report computed for the next-course list therefore answers the recommendation request with the same canonical inputs without another eligibility pass.

The region belongs to one serving supervisor. A restart replaces it, and an in-place change to served data reaches it only after a restart.

## Candidate discovery

Candidate discovery is a bounded reverse read from the basis, and the compiler decides eligibility afterwards. The official read returns every canonical course whose stored official prerequisite option names a source course, either directly or through a module that can contain one, under the request's activity scope. With the inference toggle on, the read also returns every active course whose stored inferred prerequisites name a source course.

The read is a superset over the stored course versions, so it can name a course whose matching prerequisite option belongs to a version that is not the representative version. Such a candidate is dropped when the current representative version carries no matching option.

The source identities are the basis courses and, when the inference toggle is on, the members of each basis course's equivalence groups. The courses whose official substitution option names a source course join them. The candidate set leaves out the chosen basis courses before compilation. [Next-course coverage](/docs/backend/search-and-discovery/next-course-coverage.md#candidate-reads) states the two reverse reads and how module containment and the inference read are scoped.

## Eligibility under the mode

**All** lists a course when every enabled prerequisite category of that course is satisfied by the basis, and a category the course does not carry is neutral. **Partially covered** lists a course when the basis covers at least one of its course slots. The mode value in the request and the report is `at_least_one`, and its eligibility and ordering are the ones below.

| Mode | Lists a course when | Order of the list |
|---|---|---|
| **All** | Every enabled prerequisite category of the course is satisfied by the basis, and a category the course does not carry is neutral. | Displayed official name, then official code, then canonical identity. |
| **Partially covered** | The basis covers at least one course slot of the course, in either the required or the recommended category. | Required coverage descending, then recommended coverage descending, then displayed name and code. |

Both the required and the recommended prerequisite options of a candidate are enabled, so a recommended prerequisite takes part in eligibility exactly like a required one.

A candidate is never returned in these cases:

- It is a basis course.
- It carries no enabled prerequisite category.
- Its requirements supply no course slot, which happens when a requirement is empty, when it names free-choice studies alone, and when it is a credit obligation alone.
- The rule of the chosen mode leaves it ineligible.
- It is an inactive course and the activity scope is active only.

## Coverage and the inferred dependence mark

Each result carries two prerequisite coverage values, one over its required prerequisites and one over its recommended ones. Each value is a fraction from 0 to 1, and a category whose slot set is empty carries no value at all rather than 0.0. The two categories are measured apart, so a course that carries no recommended prerequisite reports no recommended coverage, and a course that carries no required prerequisite reports no required coverage. A category that carries course prerequisites but covers none of them reports the real 0.0, and the app draws that meter under **Partially covered**. Under **All** the app draws no coverage meter, whatever values the result carries.

[Satisfaction evaluation](/docs/backend/prerequisites/satisfaction-evaluation.md#coverage) states how the slots of a branch are counted and what each requirement kind adds, and [Next-course coverage](/docs/backend/search-and-discovery/next-course-coverage.md#coverage-values-and-the-marks) states how the discovery path reads those values.

The inferred dependence mark distinguishes an official result from one that rests on inference. With the inference toggle off, no result carries the mark. With it on, a result carries the mark when it is eligible with the published inferred prerequisites and equivalence groups in force and the same candidate is ineligible when it is compiled from official prerequisites alone. A course whose official prerequisite the basis satisfies only through an inferred equivalence group carries the mark, and a course that is already eligible from its official prerequisites never does.

## The activity scope

Active only is the default scope. Under it an inactive candidate is left out, and an inactive basis course takes part in the calculation, so it satisfies the courses that depend on it and it is never proposed itself.

Under the all-courses scope every candidate takes part, and an inactive result is returned with its inactive marking. The activity state is stored with the course, as [Representative versions and activity](/docs/backend/catalogue/representative-versions.md) describes.

## Ordering

In **All** the list is ordered by the displayed official name for the requested display language, then by the official code, then by the canonical identity. A course with no name in the requested language takes the name of the other language.

In **Partially covered** the required coverage decides the order in descending value first, the recommended coverage decides it next, and the displayed name and code key settles a tie.

## The report

The report carries the two canonical course sets, the chosen basis, the mode, the display language, the inference flag, the activity flag, and the ordered results. Each result carries the shared course summary, the two coverage values, and the inferred dependence mark. The list has no configured length limit, so every eligible candidate is returned.

## Availability on a site

Next courses read official prerequisites and the prerequisite inference stores, so a site serves them under either switch. A site whose `WEB_INFERENCE_ENABLED` is false in `config/web.toml` never reads inferred prerequisites for the request, whatever the request asked for: the route forwards the inference toggle combined with the site switch, so the toggle is effectively off, no result carries the inferred dependence mark, and no equivalence group joins the source identities. The command, its inputs, its eligibility rules and the script adapter are the same on both kinds of site.

The service, the candidate reads, the eligibility decision, the coverage fold, and the tests that cover them are described in [Next-course coverage](/docs/backend/search-and-discovery/next-course-coverage.md).
