# Reference

The reference area explains the vocabulary of the documentation and holds the glossary and the licence.

## The glossary

The [Glossary](/docs/reference/glossary.md) defines each term once, in tables grouped by subject: [Courses and the catalogue](/docs/reference/glossary.md#courses-and-the-catalogue), [Configuration](/docs/reference/glossary.md#configuration), [Capture and data preparation](/docs/reference/glossary.md#capture-and-data-preparation), [Search and comparison](/docs/reference/glossary.md#search-and-comparison), [Prerequisites and routes](/docs/reference/glossary.md#prerequisites-and-routes), [Discovery and the structure of studies](/docs/reference/glossary.md#discovery-and-the-structure-of-studies), [Browser app](/docs/reference/glossary.md#browser-app), [Inference](/docs/reference/glossary.md#inference), and [Administration](/docs/reference/glossary.md#administration).

A page links a term where the exact definition matters, and it uses the defined term rather than a near synonym. A defined term carries one meaning across the documentation set.

## Identity and version

A course is one course as the app shows it, shared by all of its official versions. A course version is one exact official version of a course, as published for one curriculum period. The representative version is the one course version chosen to stand for a course, and the choice prefers the configured academic year and then a version inside the activity window.

Canonical identity ties together a course's versions, so a selection, a completion, and an exclusion act on the same course in every tab. The displayed code and name come from its representative version. A page that names a course version refers to one exact official record and its curriculum-period memberships.

## Selected and completed

A selected course is a course added to the current profile's selection. A completed course is a course marked **Mark completed**, and a completed course is always selected. The selection and the completion are the two course sets a profile holds, and the completion is a part of the selection.

Either set can serve as the basis, the set of courses that counts as already covered in a calculation. The completed courses leave out a course that is picked but not finished, and the selection counts a picked course as covered.

> [!TIP]
> Marking a course completed adds it to the selection as well. Unmarking the completion leaves the course selected and removes only the completion.

## Official and inferred

Official data is the course and module data as the university publishes it in the public curriculum source. An official prerequisite is a prerequisite that the university publishes.

An inferred prerequisite is a prerequisite found by analysis of teaching text. The app shows inferred prerequisites apart from the official ones, behind **Inferred**, and marks each one **inferred**.

## The meanings of coverage

The word coverage has a defined meaning each time it appears, and each meaning measures a different thing.

- Coverage report: a read-only report on how much of the selected dataset has translations, embeddings, and inferred prerequisites.
- Prerequisite coverage: the share of a next course's prerequisites that the basis covers, shown separately for required and recommended prerequisites.
- Inference coverage: the counts of eligible, retained complete, published, and uncovered target courses that the inference coverage report gives.

## The licence

[Licence](/docs/reference/licence.md) states the software licence, the terms of university material, and the origin of the example dataset.
