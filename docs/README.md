# Course explorer documentation

TUNI Course Explorer is a read-only web app for exploring a university course catalogue, and this page introduces its tabs and their shared course state.

## The five tabs

The app opens on one of its tabs, and the top bar switches between them: **Search**, **Compare**, **Prerequisites**, **Discover**, and **Structure of studies**. A site serves the features its operator enables: comparison, recommendations, and semantic matching with the embedding features, and inferred prerequisites with the inference features. The screenshots on these pages show a site that serves every feature.

- **Search** matches a query against a course's official code, its name, or, on a site that serves the embedding features, the meaning of its teaching text. The results group under the search method that matched them, and each result shows its official code and name, its credits, and whether the course is active. **Active only** leaves inactive courses out of the results.
- **Compare**, on a site that serves comparison, places two courses in the slots A and B and reports how they relate. The report holds five percentage meters and one verdict, from **Heavily overlapping** to **Unrelated**, and it states that the comparison is course information analysis rather than official equivalence.
- **Prerequisites** draws the prerequisite graph of one course. The **Recommended** toggle includes recommended prerequisites, and **Inferred**, on a site that serves inference features, includes prerequisites found by analysis. Excluding a course blocks routes through that course, while its prerequisites can contribute through other branches. **Find minimum route** calculates a temporary route with the fewest credits beyond the chosen basis.
- **Discover**, on a site that serves the embedding features, holds two lists drawn from a chosen basis: **Next courses**, whose prerequisites your courses cover, and **Recommended**, courses whose teaching text is similar to your courses. A site that serves no embedding features shows **Next courses** alone and no **Recommended** choice.
- **Structure of studies** follows the official structure of each of its programmes. **Add programme** adds a degree programme or module at the end of the ordered list, and each top-level row holds a **⋯** menu with **Replace programme**, **Reset programme** and **Delete programme**. A selected course that belongs to no programme appears under **Unplaced studies**.

For **Discover**, the basis is your completed courses or every selected course. **All** lists a next course when the basis covers every one of its prerequisites, and **At least one** lists it when any one is covered. A coverage meter appears for a category with course prerequisites, and a category without them shows no meter. The **?** drawer explains the percentages and the marks the site serves.

![The Search tab with the query field, the Active only toggle, and a list of five results. Each result shows its official code and name, the Substring match mark, its credits, and an active label, with the five tabs, Docs, the profile control, and the language control in the top bar.](/docs/screenshots/search-course-list.png)

## Profiles and shared course state

A profile is one named set of the app state: the language, the selected and completed courses, and the settings of each tab. A browser with no saved state starts with one profile named My plan. The open tab belongs to the browser tab rather than to a profile, so switching, importing or restoring a profile leaves the open tab where it is.

The selection and the completion are shared by every tab, so a course selected in one tab is selected in every other. Each course card opens the same menu, with **Add to comparison** on a site that serves comparison, **Open prerequisite graph**, **Add to Unplaced studies**, **Mark completed**, and **Open in Sisu**. Marking a course completed also selects it, and unmarking the completion leaves it selected.

The profile control opens the profile list, which shows the selected and completed counts of each profile and holds the rename and delete controls, the import area, and a bottom row with help, **Copy Sisu import script**, and **Export**. Three kinds of file pass through that area: one profile, the whole saved state, and a capture of a plan from Sisu. The export list downloads a file of either of the first two kinds, and **Choose file** or a drop imports any of the three. A profile file asks for a confirmation that names the profile it holds, a Sisu capture asks for a **Profile name** and names the captured programmes, and saved data comes back after a confirmation that states that it replaces every profile. Every tab of the same browser opens the same saved state, so a change made in one open tab appears in the others. The language control switches the interface between FI and EN, and a course name follows the chosen language when the catalogue holds one for it.

![The profile control open, listing the profiles My plan and Alternative plan with their selected and completed counts and their rename and delete controls, above an import area and a bottom row with a help control, Copy Sisu import script and Export. The FI and EN language control sits beside the profile control.](/docs/screenshots/profile-controls.png)

## Official and inferred information

The app shows course and module information as the university publishes it. Prerequisites that the university lists are official prerequisites. On a site that serves inference features, prerequisites found by analysis of teaching text are shown apart from them while **Inferred** is on, and each one is marked **inferred**.

A comparison states that it is course information analysis rather than official equivalence. A next course that is listed only because of inferred prerequisites carries the mark **inferred**, on a site that serves inference features. A recommended course's similarity meter shows the note **Teaching text includes derived translations** when the text compared on either side comes from a translation.

TUNI Course Explorer is an independent project that is not affiliated with Tampere University, and [Licence](/docs/reference/licence.md) states the terms that apply to the university's curriculum material.

## Where to read more

- [Quickstart](/docs/guides/README.md) walks through a first session, and the guides beside it explain each tab, profiles, the language control, and the [Sisu import script](/docs/guides/sisu-import.md) that captures and imports a plan step by step.
- [Architecture](/docs/architecture/README.md) explains how the browser app, the read-only web server, the prepared data, and the administration command fit together.
- [Backend](/docs/backend/README.md) explains how the official catalogue and its derived text, vectors, and inferred prerequisites are prepared and read.
- [Reference](/docs/reference/README.md) explains how to read the vocabulary of the documentation, and the [Glossary](/docs/reference/glossary.md) defines every term.
