# Quickstart

TUNI Course Explorer is a read-only web app for exploring a university course catalogue, and a first session touches its tabs and their shared state.

## What the app is for

The app shows one university course catalogue as the university publishes it. Its tabs read that catalogue in different ways: **Search** finds a course by code, name, or topic, **Compare** measures two courses against each other, **Prerequisites** draws what a course expects before it is taken, **Discover** suggests courses that follow from a chosen basis, and **Structure of studies** follows the official structure of each of its ordered programmes. A site serves the features its operator enables: **Compare**, the **Recommended** list and topic matching arrive with the embedding features, and the **Inferred** mark and its control with the inference features. Information that analysis produced, such as a verdict on two courses or a prerequisite found in teaching text, is labeled apart from the [official data](/docs/README.md#official-and-inferred-information).

## A first session

The session below uses the features a site serves, so a step that names **Compare** or **Recommended** applies on a site that serves the embedding features.

1. **Search for a course.** Type a code fragment, a name, or a topic into the field on the **Search** tab and press Enter. The results name every method that matched each course. [Searching for courses](/docs/guides/search.md) explains the four methods and how to read a result.

2. **Mark a course completed.** Activating a course card opens its [course menu](/docs/reference/glossary.md#browser-app), which holds the same actions in every tab. Choose **Mark completed**. A selected course is completed in place. For a course that is not selected, the dialog **Mark completed?** asks whether to add the course to **Unplaced studies** and complete it, with **Cancel** and **Add and complete**. **Add and complete** adds the course and completes it, so the course counts as covered in the other tabs. **Cancel** changes nothing.

3. **Compare two courses.** Choose **Add to comparison** from the course menu of one course, then of a second course. The two take the slots A and B on the **Compare** tab, which reports five percentages and one verdict. [Comparing two courses](/docs/guides/compare.md) explains the meters and the verdict.

4. **Open a prerequisite graph.** Choose **Open prerequisite graph** from any course menu. The **Prerequisites** tab opens with that course at the top and follows the requirements the catalogue lists before it. [Exploring prerequisites](/docs/guides/prerequisites.md) covers the graph and the route with the fewest new credits.

5. **Look at what comes next.** Open the **Discover** tab to see the courses that your completed or selected courses reach, and, on a site that serves the embedding features, the courses whose teaching text resembles them. [Discovering courses](/docs/guides/discover.md) explains the lists and the basis they share.

6. **Start a structure of studies.** Open the **Structure of studies** tab and select **Add programme** to append a degree programme or module to the end of the ordered programme list, before **Unplaced studies**. While the list is empty, the same area offers the **Import** control described in [Profiles and language](/docs/guides/profiles-and-language.md#importing-a-file). [Planning a structure of studies](/docs/guides/structure-of-studies.md) covers the official structure and your own places in it.

## Shared course state

The selection and the completion belong to the profile and are read by every tab, so a course selected on **Search** is selected on **Compare**, **Prerequisites**, **Discover**, and **Structure of studies** as well.

The app keeps the eight most recent successful reads, so returning to one of them shows its result at once.

![The course menu open on a search result, with the course code, credit value and active status on the first row above the full course name and a grey divider above the entries Add to comparison, Open prerequisite graph, Add to Unplaced studies, Mark completed, and Open in Sisu](/docs/screenshots/course-actions-menu.png)

Every course card opens that same menu. Its title shows the course code in purple, with the credits and the active or inactive status on the same row, above the course's full name. The name follows the chosen language when the catalogue holds one for it, and it wraps to its full text. A grey divider separates the title from the actions: **Add to comparison** on a site that serves comparison, **Open prerequisite graph**, **Add to Unplaced studies**, **Mark completed**, and **Open in Sisu**.

**Mark completed** completes a selected course in place. For a course that is not selected it opens the dialog **Mark completed?**, which asks whether to add the course to **Unplaced studies** and complete it. **Add and complete** does both, and **Cancel** changes nothing. Clearing the completion leaves the course selected.

![The Mark completed? dialog over a search result, asking to add the course to Unplaced studies and mark it completed, above Cancel and Add and complete](/docs/screenshots/mark-completed-dialog.png)

In **Structure of studies**, the **Complete** control on a course card completes the course directly, and in a module drawer it places the course in the rule and completes it, without that dialog.

Marking a course completed records the completion in the profile and changes nothing in the catalogue, so the completion serves the app's own calculations. **Open in Sisu** is the one action that leaves the app, and it opens the official page of the course. **Add to Unplaced studies** selects a course and places it under [**Unplaced studies**](/docs/guides/structure-of-studies.md#unplaced-studies) in the structure of studies, whether or not the programme list holds a programme. The action reports how many courses it added in a bottom notice, or that the courses were already selected, and the notice carries a **Structure of studies** link that opens the tab.

The **?** buttons of **Search**, **Prerequisites** and **Discover** open their help drawers. Each drawer ends with a link to that screen's guide: **Searching for courses**, **Exploring prerequisites** or **Discovering courses**. The link opens the guide in the same browser tab and follows the language control.

## The top bar and the tab controls

![The five tab buttons, Docs, the profile control, and the FI and EN language control in the top bar, above the Search tab's query field and result list](/docs/screenshots/app-shell.png)

On desktop the top bar holds a button for each tab the site serves, **Docs**, the profile control, and the language control.

On a phone the app has no top bar and no footer. A bar at the bottom holds one button for each served tab and **More**, and the tab content begins at the top of the window. **More** opens a sheet with the profile control, a row for the language control and **Docs**, and the footer notice, and the sheet grows upward when you open the profile list. The bar hides while the open tab scrolls down and returns at the top, on an upward scroll, or after an overlay closes. [Using the app on a phone](/docs/guides/phone.md) describes the bar, the **More** sheet and the option sheets of each tab.

At a desktop width an arrow at each side of the tab area moves one tab back or forward, and the left and right arrow keys do the same. At a phone width the arrows are absent: swipe horizontally in the tab content to move between the tabs. The tabs form a ring, so the last tab leads back to the first, and a move takes the shorter way round. A tab the site does not serve is absent from the top bar and from the ring, and a stored **Compare** opens **Search** on a site that serves no comparison.

**Docs** opens the documentation wiki inside the app. On desktop its one-row header carries the search and **GitHub**, and the page list sits beside the article. On a phone the header keeps the brand, **Docs** and **Back to the app**, and a menu opens the page list and **GitHub**. **GitHub** opens the project's source code repository in a new browser tab.

On desktop the footer at the bottom of the window states **This is an independent project that is not affiliated with Tampere University.** and links **Source code on GitHub.** to the project's source code repository, which opens in a new browser tab. On a phone the same notice and link sit at the end of the **More** sheet.

The profile control switches between the named profiles and shows how many courses each one has selected and completed, and the language control switches the interface between FI and EN. [Profiles and language](/docs/guides/profiles-and-language.md) covers both.

## Where to go next

- [Searching for courses](/docs/guides/search.md) for the four match methods, the result marks, and the activity option.
- [Comparing two courses](/docs/guides/compare.md) for the two slots, the five meters, and the verdict.
- [Exploring prerequisites](/docs/guides/prerequisites.md) for the prerequisite graph, its toggles, and the minimum route.
- [Discovering courses](/docs/guides/discover.md) for next courses, recommended courses, and the basis.
- [Planning a structure of studies](/docs/guides/structure-of-studies.md) for the official structure, its modules, and your own placements.
- [Sisu import script](/docs/guides/sisu-import.md) for capturing your own plan in Sisu and importing it as a profile.
- [Profiles and language](/docs/guides/profiles-and-language.md) for named profiles and the interface language.
- [Using the app on a phone](/docs/guides/phone.md) for the bottom bar, the **More** sheet, and the option sheets of each tab.

The [documentation home](/docs/README.md) introduces the tabs and the shared course state, and the [Glossary](/docs/reference/glossary.md) defines every term the documentation uses.
