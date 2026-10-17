# Next courses

A next course is a course whose prerequisites the chosen basis covers, selected by the prerequisite mode and ordered by coverage or by name.

## What a discovery request reads

A discovery request carries the selected course set, the completed course set, the chosen [basis](/docs/reference/glossary.md#prerequisites-and-routes), the [prerequisite mode](/docs/reference/glossary.md#discovery-and-the-structure-of-studies), the display language, the inference toggle, and the activity scope. Each course entry is a canonical identity or an exact official code, and one bulk lookup resolves the whole request into canonical courses.

The basis is either the completed courses or every selected course. When the request names no selected course, the completed set is also the selected set, so a list of completed courses alone drives discovery. A completed course that is not selected fails the request. A blank identity, an unknown basis, an unknown mode, or a display language other than Finnish or English fails before any settings read and before any database read.

An empty chosen basis returns an empty report, and that request reads no candidate and compiles none.

Discovery reads the two course sets and the request policy, and those inputs decide the whole list.

The diagram follows one request through the stages this page describes.

![The chosen basis supplies source identities to a bounded reverse read, and each candidate is compiled to its direct prerequisite options. The prerequisite mode decides eligibility, and the eligible candidates carry their prerequisite coverage and their inferred dependence into an ordered list.](/docs/diagrams/discovery-coverage.svg)

## Candidate discovery

Candidate discovery is a bounded reverse read from the basis, and the compiler decides eligibility afterwards. The read is a superset over the stored course versions, so it can name a course whose matching prerequisite option belongs to a version that is not the representative version. Such a candidate is dropped when the current representative version carries no matching option.

The source identities are the basis courses and, when the inference toggle is on, the members of each basis course's equivalence groups. The courses whose official substitution option names a source course join them.

The official read returns every canonical course whose stored official prerequisite option names a source course, either directly or through a module that can contain one. Module containment follows the module rules of every stored module version, and a cycle in those rules terminates. With the inference toggle on, the read also returns every active course whose stored inferred prerequisites name a source course.

The chosen basis courses are removed from the candidate set before compilation.

## Eligibility under the mode

**All** lists a course when every enabled prerequisite category of that course is satisfied by the basis, and a category the course does not carry is neutral. **At least one** lists a course when the basis covers at least one of its course slots.

| Mode | Lists a course when | Order of the list |
|---|---|---|
| **All** | Every enabled prerequisite category of the course is satisfied by the basis, and a category the course does not carry is neutral. | Displayed official name, then official code, then canonical identity. |
| **At least one** | The basis covers at least one course slot of the course, in either the required or the recommended category. | Required coverage descending, then recommended coverage descending, then displayed name and code. |

Both the required and the recommended prerequisite options of a candidate are enabled, so a recommended prerequisite takes part in eligibility exactly like a required one.

A candidate is never returned in these cases:

- It is a basis course.
- It carries no enabled prerequisite category.
- Its requirements supply no course slot, which happens when a requirement is empty, when it names free-choice studies alone, and when it is a credit obligation alone.
- The rule of the chosen mode leaves it ineligible.
- It is an inactive course and the activity scope is active only.

## Coverage and the inferred dependence mark

Each result carries two prerequisite coverage values, one over its required prerequisites and one over its recommended ones. A value is the share of the course slots of the option the basis covers best within its category, so a partly covered option reads as the covered part of it. Each value is a fraction from 0 to 1, a category whose slot set is empty carries no value at all rather than 0.0, and under **At least one** the app shows each value it receives as the **Required** or the **Recommended** meter.

- A direct course is one slot, and the basis covers it when it satisfies the course.
- A course that a substitution replaces is one slot for that course, and the basis covers it only when the whole substitution is met.
- A requirement that cannot be resolved to a course is one uncovered slot.
- A free-choice requirement and a credit obligation supply no slot.
- A course that several branches of one requirement name is one slot, so a repeated requirement does not raise a coverage value.

The two categories are measured apart, so a course that carries no recommended prerequisite reports no recommended coverage, and a course that carries no required prerequisite reports no required coverage. A category that carries course prerequisites but covers none of them reports the real 0.0, and the app draws that meter under **At least one**. Under **All** the app draws no coverage meter, whatever values the result carries.

The inferred dependence mark distinguishes an official result from one that rests on inference. With the inference toggle off, no result carries the mark. With it on, a result carries the mark when it is eligible with the published inferred prerequisites and equivalence groups in force and the same candidate is ineligible when it is compiled from official prerequisites alone. A course whose official prerequisite the basis satisfies only through an inferred equivalence group carries the mark, and a course that is already eligible from its official prerequisites never does.

## The activity scope

Active only is the default scope. Under it an inactive candidate is left out, and an inactive basis course takes part in the calculation, so it satisfies the courses that depend on it and it is never proposed itself.

Under the all-courses scope every candidate takes part, and an inactive result is returned with its inactive marking. The activity state is stored with the course, as [Representative versions and activity](/docs/backend/catalogue/representative-versions.md) describes.

## Ordering

In **All** the list is ordered by the displayed official name for the requested display language, then by the official code, then by the canonical identity. A course with no name in the requested language takes the name of the other language.

In **At least one** the required coverage decides the order in descending value first, the recommended coverage decides it next, and the displayed name and code key settles a tie.

## The report

The report carries the two canonical course sets, the chosen basis, the mode, the display language, the inference flag, the activity flag, and the ordered results. Each result carries the shared course summary, the two coverage values, and the inferred dependence mark. The list has no configured length limit, so every eligible candidate is returned.

The service, the candidate reads, the eligibility decision, the coverage fold, and the tests that cover them are described in [Coverage and ranking](/docs/backend/search-and-discovery/coverage-and-ranking.md).
