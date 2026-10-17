# Discovering courses

The Discover tab proposes courses to study next and courses whose teaching text resembles the courses you have.

## The two lists

The tab opens on **Next courses**, the first of the two lists, chosen by the tabs above the results.

- **Next courses** lists courses whose prerequisites your own courses cover.
- **Recommended** lists courses whose teaching text is close to your courses, ranked by how close they are. A course that overlaps one of your own courses too closely is left out.

The **Next courses** list opens with a header holding its name and the number of results, and the **Recommended** list opens with a header reading "recommended for you" and the same count.

![The Discover tab on the At least one mode, with the list switch, the mode switch, the Completed and Selected basis switch, the Active only toggle and the help button. The basis line counts three completed courses with their chips, and the two next-course rows each carry a Required meter, at 100 % and 50 %.](/docs/screenshots/discover-next-courses.png)

## Set the basis

Both lists read one basis, which is either your completed courses or every selected course.

The switch beside the list chooses the basis. **Completed** counts only the courses you marked completed, and **Selected** counts everything you have selected. The line under the controls names the basis and counts its courses, for example "basis · Completed · 2 courses". Up to four of those courses appear beside the line as chips, and the chip that counts the remaining courses opens the full list, with the total credits and every course in the basis.

The basis is the same selection and completion as in every other tab, and the chosen basis is saved with your [profile](/docs/guides/profiles-and-language.md). When the chosen set is empty, the line ends in "empty" in place of the course count, and the tab shows the sentence "Select or complete courses in any tab to get suggestions." with no results.

## Coverage and activity

| Setting | What it does |
|---|---|
| **All** | Lists a course only when your basis covers every one of its prerequisites, in name order. |
| **At least one** | Lists a course when your basis covers any one of its prerequisites, ordered by how much of its required prerequisites are covered and then by how much of its recommended ones are covered. |

The **All** and **At least one** switch belongs to the **Next courses** list, and the **Recommended** list leaves out every course that **Next courses** lists under **All** and every course in your basis.

**Active only** is on by default. While it is on, only active courses are proposed, and turning it off adds inactive courses to both lists. An inactive course that you have selected or completed counts as done either way, so it can cover a prerequisite.

The **?** button opens a drawer that explains the basis, the mode under **Next courses**, **Active only**, and the percentages of the open list: what **Required** and **Recommended** measure under **Next courses**, and what **Similarity** measures under **Recommended**. The drawer also explains the three marks a row can carry: **inferred** means the course is listed only because of inferred prerequisites, **selected** means the course is in your selection but not completed, and **completed** means you marked it completed. The coverage rule behind next courses is described in [Next courses](/docs/backend/search-and-discovery/next-courses.md).

## Read a result row

Every row is a course card with its code, its name, its credits, an **active** or **inactive** label, and a **completed** or **selected** badge when the course is in your own sets.

- A next course row carries a coverage meter for each category that holds course prerequisites. **Required** is the share of the courses of the required prerequisite option your basis covers best, and **Recommended** does the same over its recommended options. Each is shown as a whole percentage, and a category with no course prerequisites shows no meter at all. Under **All** a row carries no coverage meter, because that list shows only courses whose prerequisite requirements your basis satisfies, and a numeric choice requirement can be satisfied by fewer than all of its options. The freed width goes to the course name.
- A next course that is listed only because of inferred prerequisites carries the **inferred** mark.
- A recommended row carries one meter, **Similarity**, with the percentage of how close its teaching text is to your whole basis. Hovering the meter shows the note "Teaching text includes derived translations" when the text compared on either side comes from a translation rather than from official text.

> [!NOTE]
> The **inferred** mark means that prerequisites found by analysis are what bring the course onto the list. The rest of the row is official course data.

The similarity ranking and the rule that leaves out courses overlapping your own are described in [Recommendations](/docs/backend/search-and-discovery/recommendations.md).

![The Recommended list with a basis of one completed course, the recommended for you header with its count, and one result row showing the course and its Similarity meter at 37%.](/docs/screenshots/discover-recommended.png)

## Act on a result

1. Select the row. The [course menu](/docs/guides/README.md#shared-course-state) opens.
2. Pick an action: **Add to comparison**, **Open prerequisite graph**, [**Add to Unplaced studies**](/docs/guides/structure-of-studies.md#unplaced-studies), **Mark completed**, or **Open in Sisu**. A completed course offers **Mark not completed** instead, and a course already in the comparison shows **Already in comparison**.

**Open prerequisite graph** switches to the Prerequisites tab with that course at the top of the drawing, described in [Exploring prerequisites](/docs/guides/prerequisites.md). **Mark completed** selects the course as well.

## Loading and empty states

While a list is calculated, the tab shows "Calculating next courses…" or "Calculating recommendations…" above placeholder rows.

When nothing qualifies, the tab shows "No course matches these options." Switching between **All** and **At least one**, or changing the basis, can fill the list again. If a request fails, an alert appears in place of the list.
