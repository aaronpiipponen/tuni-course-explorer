# Prerequisite graph

The prerequisite graph presents one course's requirements as one solver structure and
one derived drawing.

The graph report is the input of the browser route worker. The machine route command compiles its
own solver structure through the shared command owner and consumes no web graph report or web-only
metadata.

## Two structures per graph root

The **Prerequisites** tab opens a [graph root](/docs/reference/glossary.md#prerequisites-and-routes),
the course at the top of the drawing. One graph read compiles that root's requirements into one
`PrerequisiteSolverStructure` and projects the drawing from it alone. The solver structure holds
each identical calculation piece once, with ordered child slots and every source position as a
compact use. The display holds the drawn boxes and connections. The compact bindings map each scoped
calculation support to the boxes it stands for, so the client never converts one identity into the
other.

One graph read returns the solver structure, the drawing, the bindings and the drawing allowance.
The browser worker reads the held structure with the live profile inputs and calculates the route,
which ends in one route outcome.

![One graph read returns the solver structure with its support bindings, the drawing and the drawing allowance. The browser route calculation reads the held structure with the live profile inputs and returns a route outcome.](/docs/diagrams/prerequisite-graph-report.svg)

Finding the least expensive set of courses is a separate explicit calculation described in
[Minimum route](/docs/backend/prerequisites/minimum-route.md). The machine route command compiles
the same kind of structure through the same command module. The web response adds the serving
dataset identity and the configured
[allocation limit](/docs/reference/glossary.md#prerequisites-and-routes), so the browser needs no
second read to calculate. A cached route passes directly to the route result and panel without a
worker. The compiler, its calculation tables and the projector are described in
[Prerequisite compiler](/docs/backend/prerequisites/prerequisite-compiler.md).

## Categories and toggles

Required prerequisites are drawn by default. The **Recommended** and **Inferred** toggles are off
by default.

- Enabling **Recommended** adds recommended prerequisites to the drawing and to the route calculation.
- Enabling **Inferred** adds inferred prerequisites to the drawing and to the route calculation.

The two toggles are independent. An inferred recommended prerequisite takes part only when both
toggles are enabled. A disabled category is left out before its own requirements are compiled, so it
contributes no piece, no course and no read. The activity scope is a further input of the same read.

A site bounds the inference toggle. When `WEB_INFERENCE_ENABLED` is false in that site's
`config/web.toml`, the web read forwards the toggle as off whatever a request asks for. The switch
bounds that one read alone: official data, the saved profile toggle, and the command and compiler
match the source.

## Official and inferred pools

Official data is what the university publishes. An inferred prerequisite is found by analysis of
teaching text, is stored apart from official data, and is marked **inferred**.

For each enabled category, every official option and every inferred option of that category forms
one flat OR, and one complete option satisfies the category. The required and recommended pools are
separate and join through one AND.

A non-root course node is marked **inferred** only when inferred provenance reaches it and no
official provenance does. A node reached by both is drawn as official. The marker is presentation
only. The machine facts keep each relationship's provenance.

## Equivalence groups and substitutions

An equivalence group is a group of two or more courses that analysis of teaching text treats as
interchangeable. A substitution is a set of courses that the university accepts in place of one
course.

When inference is enabled, an equivalence group containing a prerequisite course adds the group's
other members as inferred alternatives beside that course and its substitution options. The course
itself, its substitution options and its inferred equivalents form one flat OR, so any one of them
meets the requirement. Membership is not transitive: an offered equivalent brings its own ordinary
prerequisites and never its own substitutes or further groups. The root and any ancestor are never
offered. An occurrence offered inferred equivalents that shares a group with the root or an ancestor
is ignored where it occurs.

## Modules in the graph

A prerequisite module becomes one module box that carries the module's official identity and the
official member course cards it collects. The module version is selected for the root's academic
year. When no version is listed for that exact year, the graph accepts one nearest dated version and
shows a located reason naming the requested year and the selected version.

A module inside another module is structural content of the enclosing module. Its courses join the
outer box's card list, and the drawing holds no nested module box. An external prerequisite of a
collected member attaches to the outer box, because its module has to provide it. Cards are not
course nodes: a course reached as an ordinary prerequisite elsewhere draws its own canonical course
box with its own prerequisites, even when it is a mandatory member of a module.

A member's prerequisite that belongs to the same module draws no line, because the module holds that
course already. This rule covers a mandatory member and an optional member alike. A member's
prerequisite that belongs to another module draws a standalone course box, never a connection into
that other module's box. A member's prerequisite that is a whole module draws that module's box. Two
modules that share a member each draw their own connection to the member's external prerequisite,
and the shared course is charged once. Those external connections belong to the member and expanded
occurrences, so a basis-covered member does not light its unselected closure. A member's
prerequisite choice keeps its OR box under the whole-course sharing rule, and an inferred-only
connection is dashed.

An unexpandable module that is a direct requirement becomes one box with no member cards and a
located reason. A module with no stored rule tree inside another module draws no module box, and its
ignored annotation sits beside the enclosing box. Freely chosen studies are shown as an ignored
annotation and are not expanded into courses. A hidden member head contributes no global course box
and no origin flag, so an independently inferred-only card of that course is drawn inferred. An
independently visible official occurrence suppresses that marker. A member also reached
independently draws its own canonical course box, and the visible official and inferred facts
aggregate there without relabeling an official occurrence as inferred.

## Nodes, sharing and marks

One canonical course is one global box. A logical group whose children reach exactly one unique
drawn target collapses to that target, even when several source occurrences lead to it, and nested
groups with the same operator fold together before any attachment is emitted. A visible module,
numeric, expanded-course or internal-requirement boundary is its own box.

The drawing holds at most one connection between any two boxes, and no box carries two identical
drawn subtrees, whatever the origin or required/recommended category of the relationships behind
them. An official and an inferred relationship between one pair are one connection, and so are a
required and a recommended relationship or two routes through folded connectors. Every connection
keeps every relationship it stands for: one member per complete source fact, and each projected
context records the members its occurrences select. A member lights only when the chosen derivation
selects one of its occurrences. It is dashed only when all of those relationships are inferred, and any official
relationship makes it solid. Required and recommended relationships draw with the same line style.

Every drawn kind follows one identity rule within its whole course subtree: an AND or OR group, a
numeric constraint, a module box, an internal requirement, an ignored annotation and the subtree
below any of them is drawn once when an identical drawn structure occurs under the same course,
whatever its origin. Courses are shared globally.

Display identity depends only on what the drawing shows: the displayed kind, the displayed values and
the drawn children a box leads to. Provenance, mark state, child order and multiplicity never
separate equal drawings, so one box can stand for several source occurrences while the calculation
keeps its ordered, multiplicity-preserving pieces.
[Shared drawing identity](/docs/backend/prerequisites/prerequisite-compiler.md#shared-drawing-identity)
describes the identity and the compact bindings.

A saved node mark names one drawn box. It never changes a display identity. A box may stand for
several calculation pieces, including opposite child orders or repeated numeric slots, and the mark
applies to every one of them. A box that the normalized drawing does not emit keeps its saved key
and applies again when the same identity returns. A structurally nested module has no box, so a
saved key for one is inert. Course selection, completion and exclusion stay separate from node
marks.

Sharing changes the drawing only. The calculation and the answer are the same with or without
sharing. The inferred card marker and the dashing of an all-inferred connection are the two displays
that distinguish origin.

## Route lighting

A route lights the boxes and connections of one chosen drawn occurrence per alternative. Mandatory
occurrences of one route light together, so two modules that share a member light both of their
connections to the shared course. A shared drawing context holds the union of the members its chosen
occurrences own. An unchosen alternative stays dim even when its calculation support occurs in the
route's evidence. The calculation, the credit total, the public facts and the drawing identities do
not depend on the drawing scope, and the route operation reports its result when the drawing itself
is refused.

## Box states and the drawing inputs

The graph report carries the requirement structure and the drawing, and the browser evaluates each
drawn box's state from them. A course box reads the profile's completed set, its excluded courses
and the chosen basis. A module or numeric box is automatically fulfilled only when every calculation
piece bound to it is satisfied in the unmarked completed-only and chosen-basis contexts, and its own
manual mark applies to the whole box. `evaluateNodeStates` in `web/src/solver/satisfaction.ts` owns
that evaluation, and the page reads the held report without changing it.

A graph request carries the root, the selected and completed course sets, the **Recommended** and
**Inferred** toggles and the activity scope. It carries no marks, no calculation basis and no
excluded courses, and the two course sets serve only the retention of inactive courses under
**Active only**. The browser reads the basis, the excluded courses and the node marks from the profile
and combines them with the held solver structure. Because the drawing does not depend on box state, changing a mark redraws the same boxes
in the same places.

## Basis, completed courses, exclusions and activity

The calculation basis is the set of courses that already counts as covered, either the completed
courses or every selected course. The app shows it as **Route basis**. A course in the basis
satisfies its requirement at no cost and its own prerequisites are not expanded below it. A
completed course is always selected, so it is in either basis.

A course marked **Excluded** is drawn with a mark, together with its own prerequisites. Exclusion is
a calculation rule: an excluded course never counts as covered and no route passes through it, while
its descendants are usable through another route. Excluding the graph root blocks the whole route
calculation, and the drawing keeps the root and its requirements. Exclusions and node marks stay in the
browser and never enter a graph request.

Under **Active only**, an inactive course that is not part of the request's selected courses is left
out of the compiled structure, so it appears in neither the drawing nor the route. The graph root
compiles its own official structure in either activity scope.

## Unresolved requirements and ignored parts

An unresolved requirement is an official requirement that cannot be resolved to courses, such as a
reference to a missing course, an ambiguous module version, a malformed module rule or a course
cycle. The graph draws it as a located box with its reason.

An ignored part is official source structure that the calculation leaves out, such as freely chosen
studies, an empty option or a module version fallback. The graph shows a located annotation beside
the box it belongs to. A substitution option that names a missing course is a structure diagnostic
and draws no annotation.

Both kinds of reason belong to the graph report, so they are readable without a route calculation. A
minimum route is a separate explicit calculation in the browser.

## The drawing limit

`PREREQUISITE_GRAPH_MAX_ELEMENTS` in `config/web.toml` sets the largest number of drawing elements,
counted as every node plus every edge. The example sets 500.

The read reports its counts in the
[drawing allowance](/docs/reference/glossary.md#prerequisites-and-routes), which carries the
configured limit, the course, node, edge and element counts and whether the browser may draw them.

A graph whose element count is above the limit is reported with `display=null`, and the report
carries the solver structure, the counts and the located reasons. The refusal affects the
drawing only: the calculation and the separate route calculation give the same result either way.
