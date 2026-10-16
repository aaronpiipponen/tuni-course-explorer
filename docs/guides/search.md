# Searching for courses

The Search tab matches one query against the catalogue through four methods, and this page explains how to run a search and how to read its results.

## Running a search

Type a code fragment, a course name, or a description of a topic into the field at the top of the tab. Press Enter, or select the magnifier beside the field, to run the search.

A search runs on submit alone, so the results follow the text you submitted rather than the text that sits in the field afterwards. An empty field submits nothing. The app searches the official code, the name it shows for the course, and the meaning of the teaching text in one pass, so one query can match a course by code, by name, and by topic at the same time.

### Active only

**Active only** starts on, so a search returns active courses alone. Turn the option off to bring inactive courses into the results as well. A change to the option or to the app language runs the submitted query again, so the results follow the setting in force.

## The four match methods

The app runs all four methods for the submitted query and merges their results into one entry per course, so a course that several methods match appears once with every method that matched it.

| Method | What it finds |
|---|---|
| **Exact code** | A course whose official code is one token of the query. A list of codes separated by commas or spaces finds each course in the list. |
| **Substring** | A course whose official code or shown name contains the query, ignoring upper and lower case. |
| **Fuzzy search** | A course whose shown name is close to the query, so a typo or a different word order can match it. |
| **Semantic** | A course whose teaching text is about the topic the query describes, even when the text shares no word with the query. |

The **?** button beside the field opens **About these options**, which explains the activity option and the four methods.

## Reading the results

Above the results is the number of courses that matched. The results are grouped, and each group is headed by the name of the method that matched its courses, in the method order of the app. Within a group the active courses come first.

![The Search tab after a query, with the number of courses found, the group heading that names the method, and five results that each show a code, a name, a match mark, credits, and an active label](/docs/screenshots/search-course-list.png)

Each result is one course and shows its official code, its name, its credits, and whether the course is active or inactive. The match marks name every method that matched the course, and the first mark is the method that placed the course in its group. A result is the same course card as everywhere else, so it also carries a **selected** or **completed** mark when the course belongs to your course sets, and the letter of its comparison slot when it holds one.

## Loading, empty, and error states

| State | What the tab shows |
|---|---|
| A search is under way | Placeholder rows where the results appear |
| No course matched | **No courses match this search.** |
| The search failed | A notice with a short summary and the supplied detail under **Original technical detail** |

Before the first search the tab holds the search field with **Active only** and the magnifier, and the **?** button.

## What the app remembers

The query and the **Active only** option belong to the [profile](/docs/guides/profiles-and-language.md), so they are in place after a reload and in every tab, and each profile has its own. The results themselves are held across a move between tabs, so a look at another tab and back finds the same list. A reload of the page or a switch of profile starts the tab with no results until you search again.

## Acting on a result

Every result opens the shared [course menu](/docs/guides/README.md#shared-course-state), with **Add to comparison**, **Open prerequisite graph**, **Add to Unplaced studies**, **Mark completed**, and **Open in Sisu**. From the menu a course joins the [Compare tab](/docs/guides/compare.md), opens as the root of the [prerequisite graph](/docs/guides/prerequisites.md), joins [Unplaced studies](/docs/guides/structure-of-studies.md#unplaced-studies), gains or loses its completion, or opens the official page of the course outside the app.

How the four methods match a query and how their results are merged is described in [Search](/docs/backend/search-and-discovery/search.md).
