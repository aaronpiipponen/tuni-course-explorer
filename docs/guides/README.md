# Quickstart

TUNI Course Explorer is a read-only web app for exploring a university course catalogue, and a first session touches each of its five tabs.

## What the app is for

The app shows one university course catalogue as the university publishes it. Five tabs read that catalogue in different ways: **Search** finds a course by code, name, or topic, **Compare** measures two courses against each other, **Prerequisites** draws what a course expects before it is taken, **Discover** suggests courses that follow from a chosen basis, and **Structure of studies** follows the official structure of each of its ordered programmes. Information that analysis produced, such as a verdict on two courses or a prerequisite found in teaching text, is labeled apart from the [official data](/docs/README.md#official-and-inferred-information).

## A first session

1. **Search for a course.** Type a code fragment, a name, or a topic into the field on the **Search** tab and press Enter. The results name every method that matched each course. [Searching for courses](/docs/guides/search.md) explains the four methods and how to read a result.

2. **Mark a course completed.** Activating a course card opens its [course menu](/docs/reference/glossary.md#browser-app), which holds the same actions in every tab. Choose **Mark completed**. Marking a course completed also selects it, so the course counts as covered in the other four tabs.

3. **Compare two courses.** Choose **Add to comparison** from the course menu of one course, then of a second course. The two take the slots A and B on the **Compare** tab, which reports five percentages and one verdict. [Comparing two courses](/docs/guides/compare.md) explains the meters and the verdict.

4. **Open a prerequisite graph.** Choose **Open prerequisite graph** from any course menu. The **Prerequisites** tab opens with that course at the top and follows the requirements the catalogue lists before it. [Exploring prerequisites](/docs/guides/prerequisites.md) covers the graph and the route with the fewest new credits.

5. **Look at what comes next.** Open the **Discover** tab to see the courses that your completed or selected courses reach, and the courses whose teaching text resembles them. [Discovering courses](/docs/guides/discover.md) explains the two lists and the basis they share.

6. **Start a structure of studies.** Open the **Structure of studies** tab and select **Add programme** to append a degree programme or module to the end of the ordered programme list, before **Unplaced studies**. [Planning a structure of studies](/docs/guides/structure-of-studies.md) covers the official structure and your own places in it.

## Shared course state

The selection and the completion belong to the profile and are read by all five tabs, so a course selected on **Search** is selected on **Compare**, **Prerequisites**, **Discover**, and **Structure of studies** as well.

![The course menu open on a search result, listing Add to comparison, Open prerequisite graph, Add to Unplaced studies, Mark completed, and Open in Sisu](/docs/screenshots/course-actions-menu.png)

Every course card opens that same menu: **Add to comparison**, **Open prerequisite graph**, **Add to Unplaced studies**, **Mark completed**, and **Open in Sisu**. Marking a course completed also selects it, and clearing the completion leaves the course selected. Marking a course completed records the completion in the profile and changes nothing in the catalogue, so the completion serves the app's own calculations. **Open in Sisu** is the one action that leaves the app, and it opens the official page of the course. **Add to Unplaced studies** selects a course and places it under [**Unplaced studies**](/docs/guides/structure-of-studies.md#unplaced-studies) in the structure of studies, whether or not the programme list holds a programme.

## The top bar and the tab controls

![The five tab buttons, Docs, the profile control, and the FI and EN language control in the top bar, above the Search tab's query field and result list](/docs/screenshots/app-shell.png)

The top bar holds a button for each of the five tabs, **Docs**, the profile control, and the language control. **Docs** opens the documentation wiki inside the app, where a search field, **GitHub** and **Back to the app** sit in its header. **GitHub** opens the project's source code repository in a new browser tab. The profile control switches between the named profiles and shows how many courses each one has selected and completed, and the language control switches the interface between FI and EN. [Profiles and language](/docs/guides/profiles-and-language.md) covers both controls.

An arrow at each side of the tab area moves one tab back or forward, and the left and right arrow keys do the same. The five tabs form a ring, so the last tab leads back to the first, and a move takes the shorter way round. An arrow key is ignored while the focus sits in a text field and while a menu or a dialog is open.

The footer at the bottom of the window states **This is an independent project that is not affiliated with Tampere University.** and links **Source code on GitHub.** to the project's source code repository, which opens in a new browser tab.

## Where to go next

- [Searching for courses](/docs/guides/search.md) for the four match methods, the result marks, and the activity option.
- [Comparing two courses](/docs/guides/compare.md) for the two slots, the five meters, and the verdict.
- [Exploring prerequisites](/docs/guides/prerequisites.md) for the prerequisite graph, its toggles, and the minimum route.
- [Discovering courses](/docs/guides/discover.md) for next courses, recommended courses, and the basis.
- [Planning a structure of studies](/docs/guides/structure-of-studies.md) for the official structure, its modules, and your own placements.
- [Sisu import script](/docs/guides/sisu-import.md) for capturing your own plan in Sisu and importing it as a profile.
- [Profiles and language](/docs/guides/profiles-and-language.md) for named profiles and the interface language.

The [documentation home](/docs/README.md) introduces the five tabs and the shared course state, and the [Glossary](/docs/reference/glossary.md) defines every term the documentation uses.
