# Searching for courses

The Search tab matches one query against the catalogue through the methods its site serves, and this page explains how to run a search and how to read its results.

## Running a search

Type a code fragment, a course name, or a description of a topic into the field. On a desktop screen the field sits at the top of the tab, with **Active only** inside the bar at its right and the magnifier beside it. On a phone the field is centred in the tab while no report, loading state or error is shown. A submitted search puts the field in the fixed header at the top of the tab, with **Active only**, the **?** button and the result count in a secondary row under the field and the results scrolling below. Press Enter, or select the magnifier beside the field, to run the search.

A search runs on submit alone, so the results follow the text you submitted rather than the text that sits in the field afterwards. An empty field submits nothing. The app searches the official code, the name it shows for the course, and, on a site that serves topic matching, the meaning of the teaching text in one pass, so one query can match a course by code, by name, and by topic at the same time.

### Active only

**Active only** starts on, so a search returns active courses alone. Turn the option off to bring inactive courses into the results as well. A change to the option or to the app language runs the submitted query again, so the results follow the setting in force.

## The match methods

The app runs every method its site serves for the submitted query and merges their results into one entry per course, so a course that several methods match appears once with every method that matched it. A site that serves the embedding features runs all four methods, and a site that does not serves the three name and code methods alone.

| Method | What it finds |
|---|---|
| **Exact code** | A course whose official code is one token of the query. A list of codes separated by commas or spaces finds each course in the list. |
| **Substring** | A course whose official code or shown name contains the query, ignoring case. |
| **Fuzzy search** | A course whose shown name is close to the query, so a typo or a different word order can match it. |
| **Semantic** | A course whose teaching text is about the topic the query describes, even when the text shares no word with the query. Available with the embedding features. |

The **?** button opens **About these options**, which explains the activity option and the match methods of the site, and ends with a **Searching for courses** link to this guide.

## Reading the results

Above the results is the number of courses that matched. The results are grouped, and each group is headed by the name of the method that matched its courses, in the method order of the app. Within a group the active courses come first.

![The Search tab after a query, with the number of courses found, the group heading that names the method, and five results that each show a code, a name, a match mark, credits, and an active label](/docs/screenshots/search-course-list.png)

On a desktop screen the field, the group headings and every result row line up in one wide column. A course name is shown on one line with an ellipsis when the row cuts it, and the [course menu](/docs/guides/README.md#shared-course-state) shows the complete name. In a narrower desktop window a result row sets the code and the comparison badge on the first line, the title on the second, the credits with the activity and the state on the third, and the match marks on the fourth, and all four lines share the left edge of the card.

On a phone the fixed header holds the field and the secondary row, the results scroll below it, and the number of matches sits at the right of the secondary row. A result puts its code, comparison slot letter and selected or completed badge on the first line, with activity at the right. The name occupies the next line with an ellipsis when needed and credits at the right, and the match marks close the row. [Using the app on a phone](/docs/guides/phone.md) describes the phone shell and the course sheet that a result opens.

Each result is one course and shows its official code, its name, its credits, and whether the course is active or inactive. The match marks name every method that matched the course, and the first mark is the method that placed the course in its group. A result is the same course card as everywhere else, so it also carries a **selected** or **completed** mark when the course belongs to your course sets, and, on a site that serves comparison, the letter of its comparison slot when it holds one.

## Loading, empty, and error states

| State | What the tab shows |
|---|---|
| A search is under way | Placeholder rows where the results appear |
| Semantic search is unavailable | **Semantic search is unavailable. Showing matches by code and name only.** The code and name matches the search found are listed. |
| No course matched | **No courses match this search.** |
| No course matched while semantic search is unavailable | The notice about semantic search, then **No courses match this search.** |
| The search failed | A notice with a short summary and the supplied detail under **Original technical detail** |

A topic match needs the embedding service. When that service does not answer, the tab shows the notice and lists the matches it found by code, by code fragment, and by name, with the usual count, groups, and course cards. The notice belongs to the report of that search alone, so running the search again, changing the app language or the **Active only** option replaces it, and a search that reaches the service shows no notice. An unavailable topic match is not a failed search, so the tab shows the results rather than an error.

A site that serves no topic matching never asks the embedding service for a query vector, so its tab shows no notice about an unavailable topic match and lists the name and code matches alone. The **?** drawer of such a site explains the three methods it serves.

Before the first search the tab holds the search field with **Active only** and the magnifier, and the **?** button.

## What the app remembers

The query and the **Active only** option belong to the [profile](/docs/guides/profiles-and-language.md), so they are in place after a reload and in every tab, and each profile has its own. The results themselves are held across a move between tabs, so a look at another tab and back finds the same list. A reload of the page or a switch of profile starts the tab with no results until you search again.

## Acting on a result

Every result opens the shared [course menu](/docs/guides/README.md#shared-course-state), with **Add to comparison** on a site that serves comparison, **Open prerequisite graph**, **Add to Unplaced studies**, **Mark completed**, and **Open in Sisu**. From the menu a course joins the [Compare tab](/docs/guides/compare.md), opens as the root of the [prerequisite graph](/docs/guides/prerequisites.md), joins [Unplaced studies](/docs/guides/structure-of-studies.md#unplaced-studies), gains or loses its completion, or opens the official page of the course outside the app. **Add to Unplaced studies** reports the number of courses it added in a bottom notice with a **Structure of studies** link. **Mark completed** completes a selected course in place. For a course that is not selected, the dialog **Mark completed?** offers **Cancel** and **Add and complete**, and **Add and complete** adds the course to Unplaced studies and completes it. **Cancel** changes nothing. This is described in [shared course state](/docs/guides/README.md#shared-course-state).

How the four methods match a query and how their results are merged is described in [Search](/docs/backend/search-and-discovery/search.md).
