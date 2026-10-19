# Prerequisite graph

The prerequisite graph draws one course's requirements from a single compiled expression that the minimum route calculation also reads.

## One compiled expression per graph root

The **Prerequisites** tab opens a [graph root](/docs/reference/glossary.md#prerequisites-and-routes), the course at the top of the drawing. One graph read compiles that root's requirements into one [prerequisite expression](/docs/reference/glossary.md#prerequisites-and-routes) and derives the drawing from that expression alone. A course that a requirement needs is compiled together with its own requirements, so the drawing shows that course once with its own requirements below it.

The drawing and the minimum route read the same compiled expression, so the two cannot describe different requirement sets. The graph read performs no route optimization. Finding the least expensive set of courses is a separate operation, described in [Minimum route](/docs/backend/prerequisites/minimum-route.md), and it reads the same expression.

The compiler that builds the expression, its node vocabulary, and the projection that turns it into the drawing are described in [Prerequisite compiler](/docs/backend/prerequisites/prerequisite-compiler.md).

## Categories and toggles

Required prerequisites are drawn by default. The **Recommended** and **Inferred** toggles are off by default.

- Enabling **Recommended** adds recommended prerequisites to the drawing and to the route calculation.
- Enabling **Inferred** adds inferred prerequisites to the drawing and to the route calculation.

The two toggles are independent. An inferred recommended prerequisite takes part only when both toggles are enabled. A disabled category is left out before its own requirements are compiled, so it contributes no node, no course, and no read. The activity scope is a further input of the same read.

A site bounds the inference toggle. When `WEB_INFERENCE_ENABLED` is false in that site's `config/web.toml`, the web read forwards the toggle as off whatever a request asks for, so no inferred prerequisite reaches the drawing. The switch bounds that one read alone: official data is untouched, the toggle the browser saved in the profile is untouched, and the command, the compiler and the script adapter are the same on both kinds of site.

## Official and inferred pools

Official data is what the university publishes. An inferred prerequisite is found by analysis of teaching text, is stored apart from official data, and is marked **inferred**.

For each enabled category, every official option and every inferred option of that category forms one flat OR group, and one complete option satisfies the category. The required pool and the recommended pool are separate, and they join through one AND group.

![A graph root compiles to one AND group that joins a required pool and a recommended pool, each an OR group. The required pool holds an official option AND of two courses and one inferred course drawn with a dashed outline. The recommended pool holds one official course.](/docs/diagrams/prerequisite-expression.svg)

A non-root course node is marked **inferred** only when at least one inferred occurrence reaches it and no official occurrence does. A node reached by both an official occurrence and an inferred occurrence is drawn as official.

## Equivalence groups and substitutions

An equivalence group is a group of two or more courses that analysis of teaching text treats as interchangeable. A substitution is a set of courses that the university accepts in place of one course.

When inference is enabled, an equivalence group that contains a prerequisite course adds the group's other members as inferred alternatives beside that course and beside its substitution options. The course itself, its substitution options, and its inferred equivalents form one flat OR group, so any one of them meets the requirement.

Membership is not transitive. An offered equivalent brings its own ordinary prerequisites and never its own substitutes or further groups, and overlapping groups stay separate entries. The graph root and any ancestor already drawn are never offered as an alternative.

## Modules in the graph

A prerequisite module becomes one module node that carries the module's official identity and its official member courses. The module version is selected for the root's academic year. When no version is listed for that exact year, the graph accepts one nearest dated version and shows a located reason that names the requested year and the selected version.

A module whose contents cannot be expanded into courses becomes one node with no member courses and a located reason. Freely chosen studies are shown in the graph and are not expanded into courses.

## Nodes and drawing compaction

One canonical course is one drawing node. Every occurrence of that course shares the node, and only the graph root is marked as the root. A group left with exactly one drawn child collapses to that child, and nested groups with the same operator fold together.

An unmarked logical AND or OR group reached under the same canonical course as an identical group is drawn once. The connections that reach that group and leave it carry every occurrence and condition chain of the groups they stand for, so the drawing shows one such group while the compiled expression holds every occurrence.

Compaction changes the drawing only. The compiled expression and the calculation that reads it are the same with or without the collapse, so the drawing can hold fewer nodes than the expression without changing any answer. A module boundary, a numeric constraint, an expanded course, and an excluded or manually marked node each keep their own drawn node and never collapse.

## Basis, completed courses, exclusions and activity

The calculation basis is the set of courses that already counts as covered, either the completed courses or every selected course. The app shows it as **Route basis**. A route uses one basis, with the same effect either way: a course in the basis satisfies its requirement at no cost and its own prerequisites are not expanded below it. A completed course is always selected, so it is in either basis.

A course marked **Excluded** is drawn with a mark, together with its own prerequisites. Exclusion is a calculation rule: an excluded course never counts as covered and no route passes through it, while its descendants are usable through another route. Excluding the graph root blocks the whole request, and the graph draws the root and its requirements.

Under **Active only**, an inactive course that is not part of the request's selected courses is left out of the compiled expression, so it appears in neither the drawing nor the route. The graph root compiles its own official structure in either activity scope.

## Unresolved requirements and ignored parts

An unresolved requirement is an official requirement that cannot be resolved to courses, such as a reference to a missing course, an ambiguous module version, a malformed module rule, or a course cycle. The graph draws it as a located node with its reason.

An ignored part is an official source structure that the calculation leaves out, such as freely chosen studies, an empty option, a dropped substitution, or a module version fallback. The graph shows a located reason for each one beside the node it belongs to.

Both kinds of reason belong to the graph read, so they are readable without asking for a route. A minimum route is a separate request.

## The drawing limit

`PREREQUISITE_GRAPH_MAX_ELEMENTS` in `config/web.toml` sets the largest number of drawing elements, counted as every node plus every edge. The example sets 500.

A graph whose element count is above the limit is reported with its drawing refused, and the report carries the node count, the edge count, and the element count. The refusal affects the drawing only. The compiled expression and the separate minimum route give the same result either way.
