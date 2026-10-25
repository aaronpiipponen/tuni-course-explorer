# Exploring prerequisites

The Prerequisites tab draws one course's requirements and finds the cheapest route to that course from your own courses.

## Choose the course

The requirements of one course open at the top of the drawing as the graph root. Until a course is picked, the tab shows a prompt and one button.

1. Open the **Prerequisites** tab.
2. Select **Choose course**.
3. Type part of a course name or a code in the filter box. Matching courses appear below it, and [**Active only**](/docs/guides/search.md#active-only) decides whether inactive courses appear in that list. This is the same **Active only** setting as the graph's, so changing it in the picker also changes the drawing and the route.
4. Select one of the results. Its drawing opens, and the course is named beside **Change** above the drawing.

A [course menu](/docs/guides/README.md#shared-course-state) anywhere in the app also holds **Open prerequisite graph**, which opens that course as the graph root straight away.

Once a course is open, **Change** reopens the picker with the same filter box, and **Recenter** brings the drawing back to the graph root. On a phone the full-width root button at the top of the **Graph options** sheet reopens the picker, and **Recenter** sits in the rail over the drawing.

![The Prerequisites tab with the basis switch, the Recommended, Active only and Inferred toggles and the help button above the drawing, the opened course beside Change and Recenter, and a drawing with course boxes joined by an AND group and an OR group. Every course box holds Complete and Exclude, and the minimum route button sits at the top left.](/docs/screenshots/prerequisite-graph.png)

## Read the drawing

The drawing runs from the graph root at the top down through everything that course requires.

- A course box holds the course code and name, its credits, and an **active** or **inactive** label. **Complete** and **Exclude** sit along the bottom of the box.
- **AND** joins requirements that all have to be met, and **OR** joins requirements of which one is enough. A group that reads **pick 2** states how many of its options are needed, and other group boxes state a number of courses or a credit amount.
- A box such as **5 cr other** is a credit requirement that the official data does not break into courses. It carries the same **Complete** and **Exclude** controls as a module.
- A module box names the module and the number of courses it holds. Select the box to open the list of those member courses. The courses of a module inside another module join the outer module's list, so the drawing shows one box for the outermost module and that box lists every course. For a module, that list ends with **Add all module courses to structure**, which adds every member course to your selection and to your structure of studies, in the same way as the route's add button described below. The action reports the number of courses it added in a bottom notice with a **Structure of studies** link.
- A course that the graph needs outside its module also appears as its own course box with its own prerequisites, even when it is a member of a module. A prerequisite of a member that comes from outside the module joins the module box, and a prerequisite that is another module joins that module's box.
- A small box with a short reason names a part of the official requirement that could not be turned into courses.

Two requirements that connect the same two boxes are drawn as one connection, whether they are official or inferred and whether they are required or recommended. A connection is dashed only when all of its requirements are inferred, and a connection that also holds an official requirement stays solid.

Identical drawn structure under one parent is drawn once for every box kind. Two equal numeric requirements, module boxes, unresolved reasons, or ignored notes share one box and the connections below it, and the calculation counts every requirement the box stands for. The **inferred** mark on a course box and the dashed style of an inferred-only connection are the two ways origin shows.

Marks show on the box. A completed course box is tinted green, an excluded one red, and the graph root is highlighted. An inactive course box is drawn fainter. Hovering a box fades every connection that does not lead to it. Drag inside the drawing to move it, and scroll or pinch to zoom in and out.

On a phone the drawing fills the pane from the top of the window to the bottom bar. The name of the root course and the names of the course boxes wrap to their full text, and a box grows to fit them. A header across the top names the root and opens **Graph options**, and a rail at the top right holds **Recenter**, **Zoom in** and **Zoom out**. Drag and pinch inside the drawing with a finger to move and zoom the drawing without moving the page, and neither gesture moves the page or changes the tab.

## Graph options

On desktop the controls above the drawing decide what the drawing shows and what the calculation reads, and the root name, **Change** and **Recenter** stay in that row. On a phone the same controls sit in the **Graph options** sheet, which the header opens. The sheet begins with one full-width button that shows the course code, its name on one line with an ellipsis, and a swap icon, and the whole button reopens the root picker. The controls follow in two columns: the route basis switch takes a full row, **Recommended** and **Inferred** share the row below on a site that serves the inference features, and the **?** sits at the bottom right. [Using the app on a phone](/docs/guides/phone.md) describes the phone shell and this sheet.

| Control | What it changes |
|---|---|
| **Completed** and **Selected** | Which of your courses count as covered: only the ones you marked completed, or everything you have selected. The two options sit in the switch that reads **Counts as covered** on hover. |
| **Recommended** | Adds recommended prerequisites to the drawing and to the route calculation. Required and recommended prerequisites draw with the same line style. |
| **Inferred** | On a site that serves the inference features, adds prerequisites found by analysis to the drawing and to the route calculation. A connection is dashed only when all of its prerequisites are inferred. |
| **Active only** | Leaves inactive courses out of the drawing and out of the route. Your selected or completed inactive courses and the graph root are shown either way. |

The two toggles work separately on a site that serves both: an inferred recommended prerequisite takes part in the drawing only while both **Recommended** and **Inferred** are on. The **?** button opens a drawer that explains the options the site serves and ends with an **Exploring prerequisites** link to this guide.

A completed course is always selected, so **Selected** counts every completed course as covered as well. The [Discover tab](/docs/guides/discover.md#set-the-basis) reads the same two options as its basis.

## Official and inferred prerequisites

> [!IMPORTANT]
> Official prerequisites are the ones the university publishes. Where the site serves the inference features, prerequisites found by analysis are also shown and appear only while **Inferred** is on, and each of those course boxes carries the **inferred** mark.

A course that both an official requirement and an inferred one reach is drawn as an official course and carries no mark. Turning **Inferred** off leaves the official drawing and the official calculation in place, and a site that serves no inference features draws the official requirements alone, because no inferred prerequisite reaches it.

The drawing and the route use the same requirements, described in [Prerequisite graph](/docs/backend/prerequisites/prerequisite-graph.md).

## Completed, selected and excluded marks

### Mark a course, module or requirement as completed

On a course box, **Complete** marks that course completed. That completion is shared with every other tab. A selected course is completed in place. For a course that is not selected, the dialog **Mark completed?** offers **Cancel** and **Add and complete**, and **Add and complete** adds the course to Unplaced studies and completes it. **Cancel** changes nothing. This is described in [shared course state](/docs/guides/README.md#shared-course-state). The shared course menu's **Mark completed** runs the same action.

On a module box or a requirement box, **Complete** settles that one requirement for the drawing and the route without changing your selected or completed courses. A module that your own courses satisfy carries the **fulfilled** mark. A module you mark yourself reads **Completed**.

A shared box can stand for several source requirements. Its one saved mark covers every one of them, and one click clears it again. A saved mark whose box the drawing does not include applies again when the box returns.

Select the button again to remove the mark.

### Exclude a course or a requirement

1. Select **Exclude** on a course box, a module box or a requirement box.
2. The box is marked **Excluded**, and no route passes through it.
3. Select **Excluded** again to remove the exclusion.

> [!WARNING]
> An excluded course never counts as covered, and no route passes through it. The graph shows the excluded course and its own prerequisites, and those prerequisites can contribute through another branch. Excluding the graph root leaves no route at all.

When the route basis is **Selected**, a course box that counts as covered through your selection rather than through completion is highlighted.

## When the drawing is too large

A very large drawing is not drawn. The tab reports "This prerequisite tree is too large to draw." together with the number of drawing elements and the drawing limit, and it suggests turning off **Recommended** or **Inferred**, or turning on **Active only**, to shrink the graph. On a site that serves no inference features the suggestion names **Recommended** and **Active only** alone.

The refusal affects the drawing only. The route reads the same requirements whether the drawing is shown or refused, and **Find minimum route** is available on the same screen.

## Find the minimum route

The minimum route is the set of courses that meets the requirements with the fewest new credits. Courses in your basis cost nothing and skip their own prerequisites. A course that several branches need is counted once.

1. Set the graph options the way the calculation should read them. The route uses the same graph root, toggles, marks and basis as the drawing.
2. Select **Find minimum route**. The button reads **Calculating…** while your browser calculates the route.
3. Read the highlight through the drawing. The route is lit and everything outside it is faded.

The calculation runs in your browser. Selecting **Find minimum route** again with the same options, graph root, course sets and marks shows the result at once. Changing the graph root, an option, your course sets or a mark clears the shown route and returns the plain drawing, and returning to the earlier choices leaves the plain drawing until you select **Find minimum route** again.

## Read the route panel

The panel reports the result. On a desktop it sits at the top right of the drawing. On a phone **Find minimum route** is a wide button above the bottom of the drawing, and its result opens as a sheet over the bottom of the drawing. The sheet scrolls inside itself, the lit path is visible above it, and a clear control in its header returns to the plain drawing. Its header gives the new credits first and the credits of the whole route second, for example "6 cr new · 14 cr full route", where the full route also counts the courses on the route that your basis already covers. When there is no total to show, the header carries the outcome name itself. Selecting **Expand** grows the sheet over the drawing so the course list scrolls inside it, with **Add all missing courses to structure** fixed at the foot below the list.

![The drawing after Find minimum route, with the route button reading Clear minimum route, the chosen branch of the OR group lit and the other branch faded, and the route panel showing the new and full credits with the exact tag and an Expand button.](/docs/screenshots/minimum-route.png)

| Outcome | What the panel shows |
|---|---|
| **Exact minimum route** | The route with the fewest new credits that the rules allow, its credits, and the tag **exact**. |
| **Approximate route** | A route from a quicker search, because the exact search was too large. The panel gives its credits, the tag **approximate**, and the note **Not guaranteed to be the minimum.** |
| **No route found** | No route and no total, with the tag **timeout**, which the graph root box also shows. The note states that the exact search was too large and that the second search gave up, and it names the root failure. |
| **Route unresolved** | No route and no total, with the tag **unresolved**, because a requirement cannot be resolved to courses and a cheaper route may exist. Each unresolved requirement is named below the note with its reason. |
| **No route exists** | No route and no total, with the tag **no solution**. The note states that no route meets every requirement, and each blocked requirement is named below it with its reason. |
| **Shortfall** | A route that is only as large as the active courses allow, with the tag **shortfall**, because a module rule falls below its own bound while **Active only** is on. Each module rule that falls short is named with its achieved and required count or credits. |

An exact route that adds nothing shows the note **Nothing new**.

Select **Expand** to list the courses of the route, with the courses your basis already covers carrying the **completed** or **selected** badge, and any credit amount that the official data does not break into courses on its own line. Select **Collapse** to hide the list again. For an outcome with no route, the panel names each blocked or unresolved requirement and its reason instead of listing courses, and those entries are visible while the course list is collapsed.

![The expanded route panel, with the header reading 5 cr new and 10 cr full route, the exact tag, Collapse, a course row at 5 cr and one carrying the completed badge, each with its activity label, and the Add all missing courses to structure button at the foot below the list.](/docs/screenshots/minimum-route-expanded.png)

The credits, the preference between routes of equal cost, and the treatment of exclusions are described in [Minimum route](/docs/backend/prerequisites/minimum-route.md).

## Add route courses to your structure

1. Select **Find minimum route**.
2. Select **Expand** in the route panel.
3. Select **Add all missing courses to structure**. Every course of the route that is not in your selection is added to it, and each added course appears in the Structure of studies tab, under [**Unplaced studies**](/docs/guides/structure-of-studies.md#unplaced-studies) when no module places it.

The action adds the courses whether or not the programme list of the structure of studies holds a programme. It reports the number of courses it added in a bottom notice with a **Structure of studies** link, or that every route course is already in your selection.

## Clear the route

The route is temporary and is not saved. The app clears it and returns the plain drawing when you do any of the following.

- Select **Clear minimum route** on a desktop, or the clear control in the header of the phone route sheet.
- Open the graph of another course with **Change**.
- Change the basis, or the **Recommended**, **Inferred** or **Active only** option.
- Change your selected or completed courses anywhere in the app, or mark a course, a module or a requirement box as completed or excluded.
- Leave the **Prerequisites** tab.

Select **Find minimum route** again to calculate a fresh route.
