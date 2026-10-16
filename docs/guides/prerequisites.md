# Exploring prerequisites

The Prerequisites tab draws one course's requirements and finds the cheapest route to that course from your own courses.

## Choose the course

The requirements of one course open at the top of the drawing as the graph root. Until a course is picked, the tab shows a prompt and one button.

1. Open the **Prerequisites** tab.
2. Select **Choose course**.
3. Type part of a course name or a code in the filter box. Matching courses appear below it, and [**Active only**](/docs/guides/search.md#active-only) decides whether inactive courses appear in that list. This is the same **Active only** setting as the graph's, so changing it in the picker also changes the drawing and the route.
4. Select one of the results. Its drawing opens, and the course is named beside **Change** above the drawing.

A [course menu](/docs/guides/README.md#shared-course-state) anywhere in the app also holds **Open prerequisite graph**, which opens that course as the graph root straight away.

Once a course is open, **Change** reopens the picker with the same filter box, and **Recenter** brings the drawing back to the graph root.

![The Prerequisites tab with the basis switch, the Recommended, Active only and Inferred toggles and the help button above the drawing, the opened course beside Change and Recenter, and a drawing with course boxes joined by an AND group and an OR group. Every course box holds Complete and Exclude, and the minimum route button sits at the top left.](/docs/screenshots/prerequisite-graph.png)

## Read the drawing

The drawing runs from the graph root at the top down through everything that course requires.

- A course box holds the course code and name, its credits, and an **active** or **inactive** label. **Complete** and **Exclude** sit along the bottom of the box.
- **AND** joins requirements that all have to be met, and **OR** joins requirements of which one is enough. A group that reads **pick 2** states how many of its options are needed, and other group boxes state a number of courses or a credit amount.
- A box such as **5 cr other** is a credit requirement that the official data does not break into courses. It carries the same **Complete** and **Exclude** controls as a module.
- A module box names the module and the number of courses it holds. Select the box to open the list of those member courses. For a module, that list ends with **Add all module courses to structure**, which adds every member course to your selection and to your structure of studies, in the same way as the route's add button described below.
- A small box with a short reason names a part of the official requirement that could not be turned into courses.

Marks show on the box. A completed course box is tinted green, an excluded one red, and the graph root is highlighted. An inactive course box is drawn fainter. Hovering a box fades every connection that does not lead to it. Drag inside the drawing to move it, and scroll or pinch to zoom in and out.

## Graph options

The controls above the drawing decide what the drawing shows and what the calculation reads.

| Control | What it changes |
|---|---|
| **Completed** and **Selected** | Which of your courses count as covered: only the ones you marked completed, or everything you have selected. The two options sit in the switch that reads **Counts as covered** on hover. |
| **Recommended** | Adds recommended prerequisites to the drawing and to the route calculation. They form their own group, with dashed connections. |
| **Inferred** | Adds prerequisites found by analysis to the drawing and to the route calculation. |
| **Active only** | Leaves inactive courses out of the drawing and out of the route. Your selected or completed inactive courses and the graph root are shown either way. |

The two toggles work separately. An inferred recommended prerequisite takes part in the drawing only while both **Recommended** and **Inferred** are on. The **?** button opens a drawer that explains each option.

A completed course is always selected, so **Selected** counts every completed course as covered as well. The [Discover tab](/docs/guides/discover.md#set-the-basis) reads the same two options as its basis.

## Official and inferred prerequisites

> [!IMPORTANT]
> Official prerequisites are the ones the university publishes. Prerequisites found by analysis are shown apart from them and appear only while **Inferred** is on, and each of those course boxes carries the **inferred** mark.

A course that both an official requirement and an inferred one reach is drawn as an official course and carries no mark. Turning **Inferred** off leaves the official drawing and the official calculation in place.

The drawing and the route read the same requirements, described in [Prerequisite graph](/docs/backend/prerequisites/prerequisite-graph.md).

## Completed, selected and excluded marks

### Mark a course, module or requirement as completed

On a course box, **Complete** marks that course completed. That completion is shared with every other tab, and the course is selected as well.

On a module box or a requirement box, **Complete** settles that one requirement for the drawing and the route without changing your selected or completed courses. A module that your own courses satisfy carries the **fulfilled** mark. A module you mark yourself reads **Completed**.

Select the button again to remove the mark.

### Exclude a course or a requirement

1. Select **Exclude** on a course box, a module box or a requirement box.
2. The box is marked **Excluded**, and no route passes through it.
3. Select **Excluded** again to remove the exclusion.

> [!WARNING]
> An excluded course never counts as covered, and no route passes through it. The graph shows the excluded course and its own prerequisites, and those prerequisites can contribute through another branch. Excluding the graph root leaves no route at all.

When the route basis is **Selected**, a course box that counts as covered through your selection rather than through completion is highlighted.

## When the drawing is too large

A very large requirement tree is not drawn. The tab reports "This prerequisite tree is too large to draw." together with the number of elements in the tree and the drawing limit, and it suggests turning off **Recommended** or **Inferred**, or turning on **Active only**, to shrink the tree.

The refusal affects the drawing only. **Find minimum route** is available on the same screen.

## Find the minimum route

The minimum route is the set of courses that meets the requirements with the fewest new credits. Courses in your basis cost nothing, a course that several branches need is counted once, and a completed course also skips its own prerequisites.

1. Set the graph options the way the calculation should read them. The route uses the same graph root, toggles, marks and basis as the drawing.
2. Select **Find minimum route**. The button reads **Calculating…** while the request runs.
3. Read the highlight through the drawing. The route is lit and everything outside it is faded.

## Read the route panel

The panel at the top right of the drawing reports the result. Its header gives the new credits first and the credits of the whole route second, for example "6 cr new · 14 cr full route", where the full route also counts the courses on the route that your basis already covers. When there is no total to show, the header carries the outcome name itself.

![The drawing after Find minimum route, with the route button reading Clear minimum route, the chosen branch of the OR group lit and the other branch faded, and the route panel showing the new and full credits with the exact tag and an Expand button.](/docs/screenshots/minimum-route.png)

| Outcome | What the panel shows |
|---|---|
| **Exact minimum route** | The route with the fewest new credits that the rules allow, its credits, and the tag **exact**. |
| **Approximate route** | A route from a quicker search, because the exact search was too large. The panel gives its credits, the tag **approximate**, and the note **Not guaranteed to be the minimum.** |
| **No route found** | No route and no total, with the tag **timeout**, which the graph root box also shows. The note states that the exact search was too large and that the second search gave up. |
| **Route unresolved** | No route and no total, with the tag **unresolved**, because a requirement cannot be resolved to courses and a cheaper route may exist. |
| **No route exists** | No route and no total, with the tag **no solution**. The note states that every route is blocked by excluded or unavailable courses. |
| **Shortfall** | A route that is only as large as the active courses allow, with the tag **shortfall**, because a module rule falls below its own bound while **Active only** is on. |

An exact route that adds nothing shows the note **Nothing new**.

Select **Expand** to list the courses of the route, with the ones your basis already covers marked **done**, and any credit amount that the official data does not break into courses on its own line. Select **Collapse** to hide the list again. For an outcome with no route, the panel explains the outcome instead of listing courses.

![The route panel beside the drawing, with the header reading 5 cr new and 10 cr full route, the exact tag, Collapse, two course rows of which the covered one is marked done, and the Add all missing courses to structure button at the end of the list.](/docs/screenshots/minimum-route-expanded.png)

The credits, the preference between routes of equal cost, and the treatment of exclusions are described in [Minimum route](/docs/backend/prerequisites/minimum-route.md).

## Add route courses to your structure

1. Select **Find minimum route**.
2. Select **Expand** in the route panel.
3. Select **Add all missing courses to structure**. Every course of the route that is not in your selection is added to it, and each added course appears in the Structure of studies tab, under [**Unplaced studies**](/docs/guides/structure-of-studies.md#unplaced-studies) when no module places it.

When no structure root is chosen, the app asks for a degree programme or module first and adds the courses once one is chosen.

## Clear the route

The route is temporary and is not saved. The app clears it and returns the plain drawing when you do any of the following.

- Select **Clear minimum route**, the button that **Find minimum route** becomes while a route is shown.
- Open the graph of another course with **Change**.
- Change the basis, or the **Recommended**, **Inferred** or **Active only** option.
- Change your selected or completed courses anywhere in the app, or mark a course, a module or a requirement box as completed or excluded.
- Leave the **Prerequisites** tab.

Select **Find minimum route** again to calculate a fresh route.
