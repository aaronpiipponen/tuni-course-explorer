# Discovering courses

The Discover tab proposes courses to study next and, on a site that serves the embedding features, courses whose teaching text resembles the courses you have.

## The two lists

The tab opens on the list the profile last showed, which is **Next courses** for a profile that has not chosen one. On a desktop screen the list is chosen by the tabs above the results. On a phone the **Next courses** and **Recommended** buttons sit in the sticky header above the results.

- **Next courses** lists courses whose prerequisites your own courses cover.
- **Recommended**, on a site that serves the embedding features, lists courses whose teaching text is close to your courses, ranked by how close they are. A course that overlaps one of your own courses too closely is left out.

A site that serves no embedding features serves **Next courses** alone.

The **Next courses** list opens with a header holding its name and the number of results, and the **Recommended** list opens with a header reading "recommended for you" and the same count.

![The Discover tab on the Partially covered mode, with the list switch, the mode switch, the Completed and Selected basis switch, the Active only toggle and the help button. The basis line counts three completed courses with their chips, and the two next-course rows each carry a Required meter, at 100 % and 50 %.](/docs/screenshots/discover-next-courses.png)

## Set the basis

Both lists read one basis, which is either your completed courses or every selected course.

The basis switch sits beside the list on a desktop screen and in the **Discover options** sheet on a phone. **Completed** counts only the courses you marked completed, and **Selected** counts everything you have selected. The line under the controls names the basis and counts its courses, for example "basis · Completed · 2 courses". Up to four of those courses appear beside the line as chips, and the chip that counts the remaining courses opens the full list, with the total credits and every course in the basis.

The basis is the same selection and completion as in every other tab, and the chosen basis is saved with your [profile](/docs/guides/profiles-and-language.md). When the chosen set is empty, the line ends in "empty" in place of the course count, and the tab shows the sentence "Select or complete courses in any tab to get suggestions." with no results.

## Coverage and activity

| Setting | What it does |
|---|---|
| **All** | Lists a course only when your basis covers every one of its prerequisites, in name order. |
| **Partially covered** | Lists a course when your basis covers any one of its prerequisites, including a course with every prerequisite covered, ordered by how much of its required prerequisites are covered and then by how much of its recommended ones are covered. |

The **All** and **Partially covered** switch belongs to the **Next courses** list, and the **Recommended** list leaves out every course that **Next courses** lists under **All** and every course in your basis.

**Active only** is on by default. While it is on, only active courses are proposed, and turning it off adds inactive courses to the lists the site serves. An inactive course that you have selected or completed counts as done either way, so it can cover a prerequisite.

The **?** button beside the desktop controls, or in the **Discover options** sheet on a phone, opens a drawer that explains the basis, the mode under **Next courses**, **Active only**, the percentages of the open list, and the marks a row can carry, and it ends with a **Discovering courses** link to this guide. The percentages cover what **Required** and **Recommended** measure under **Next courses** and, on a site that serves the embedding features, what **Similarity** measures there. The marks are **inferred**, **selected**, and **completed**. On a site that serves the inference features, **inferred** means the course is listed only because of inferred prerequisites. **selected** means the course is in your selection but not completed, and **completed** means you marked it completed. The coverage rule behind next courses is described in [Next courses](/docs/backend/search-and-discovery/next-courses.md).

## Read a result row

Every row is a course card with its code, its name, its credits, an **active** or **inactive** label, and a **completed** or **selected** badge when the course is in your own sets. The rows fill one wide column, and each course name is shown on one line.

A row that carries meters shows the card and the meters side by side at a wide window, with the meters in their own column. In a narrower window the card and the meters stack in one column, and the code, the name and each meter label share one left edge.

On a phone the sticky header holds the **Next courses** and **Recommended** buttons, with a settings icon at its right. The icon opens a sheet with the basis, the activity scope and the **?** help at the bottom right. While **Next courses** is open, the sheet also holds the **All** and **Partially covered** choice.

The course card and its meters stack in one column inside the row's border. The card puts its code at the name's left edge, shows the title on one line with an ellipsis before the credits, shows the course code alone in the basis chips, and wraps each name in the expanded basis list instead of cutting it. The whole row, meters included, opens the [course menu](/docs/guides/README.md#shared-course-state), which shows the complete name when the row cuts it. [Using the app on a phone](/docs/guides/phone.md) describes the phone shell and this sheet.

- A next course row carries a coverage meter for each category that holds course prerequisites. **Required** is the share of the courses of the required prerequisite option your basis covers best, and **Recommended** does the same over its recommended options. Each is shown as a whole percentage, and a category with no course prerequisites shows no meter at all. Under **All** a row carries no coverage meter, because that list shows only courses whose prerequisite requirements your basis satisfies, and a numeric choice requirement can be satisfied by fewer than all of its options. The freed width goes to the course name.
- A next course that is listed only because of inferred prerequisites carries the **inferred** mark in its row, beside the code on a phone and with the credits and activity on a wider screen, on a site that serves the inference features.
- A recommended row carries one meter, **Similarity**, with the percentage of how close its teaching text is to your whole basis. Hovering the meter shows the note "Teaching text includes derived translations" when the text compared on either side comes from a translation rather than from official text.

> [!NOTE]
> The **inferred** mark means that prerequisites found by analysis are what bring the course onto the list. The rest of the row is official course data.

The similarity ranking and the rule that leaves out courses overlapping your own are described in [Recommendations](/docs/backend/search-and-discovery/recommendations.md).

![The Recommended list with a basis of one completed course, the recommended for you header with its count, and one result row showing the course and its Similarity meter at 37%.](/docs/screenshots/discover-recommended.png)

## Act on a result

1. Select anywhere in the row. On a desktop screen the [course menu](/docs/guides/README.md#shared-course-state) opens below the complete row when the screen has room below it, and above the row when the space below cannot hold it. On a phone it opens as a sheet above the bottom bar.
2. Pick an action: **Add to comparison** on a site that serves comparison, **Open prerequisite graph**, [**Add to Unplaced studies**](/docs/guides/structure-of-studies.md#unplaced-studies), which reports the number of courses it added in a bottom notice with a **Structure of studies** link, **Mark completed**, or **Open in Sisu**. A completed course offers **Mark not completed** instead, and a course already in the comparison shows **Already in comparison**.

**Open prerequisite graph** switches to the Prerequisites tab with that course at the top of the drawing, described in [Exploring prerequisites](/docs/guides/prerequisites.md). **Mark completed** completes a selected course in place. For a course that is not selected, the dialog **Mark completed?** offers **Cancel** and **Add and complete**, and **Add and complete** adds the course to Unplaced studies and completes it. **Cancel** changes nothing. This is described in [shared course state](/docs/guides/README.md#shared-course-state). **Add to comparison** gives the course its slot letter on the card and starts no Discover read. The result rows stay in place, with no loading placeholder.

## When a site serves fewer features

On a site that serves no embedding features the row above the results holds **Next courses** alone, and the drawer explains that list's settings without a similarity percentage. The **Recommended** choice your profile saved is its own value, so a site that serves the list opens on the saved choice, and the course sets are the same either way.

On a site that serves no inference features no row carries the **inferred** mark, and the drawer explains **selected** and **completed** alone. The next courses then come from the official prerequisites alone. Where the site serves the embedding features, **Recommended** is ranked by similarity.

## Loading and empty states

While a list is calculated, the tab shows "Calculating next courses…" or "Calculating recommendations…" above placeholder rows.

When nothing qualifies, the tab shows "No course matches these options." Switching between **All** and **Partially covered**, or changing the basis, can fill the list again. If a request fails, an alert appears in place of the list.
