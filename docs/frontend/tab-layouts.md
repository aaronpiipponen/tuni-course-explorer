# Tab layouts

The Search, Compare and Discover tabs place their controls and their reports at the desktop, intermediate and phone widths.

## Search

Search runs on an explicit submit. Only a submitted query is sent, and the report follows the text that was submitted rather than the text in the field. **Active only** and the language are part of the request, so a change to either re-runs the submitted query. An empty field submits nothing.

The report arrives in the tier order of the backend, and the tab draws each run of results that share a first match source as one tier under the name of that search method. A result lists every method that matched it. A query with no result shows an empty state.

On a desktop viewport the search field, the result groups and each result row share one aligned column. The search bar holds **Active only** inside it at the right, before the submit button, and the **?** help sits outside the bar. A course name stays on one line in its row, and the shared course menu carries the complete name at any length.

At a phone width the search box sits in the middle of the tab while no report, loading state or error is shown. A search puts the box at the top of the tab and the results scroller under it.

The box is one bordered surface, and that border marks focus while the field has focus. It holds the magnifier, the growing query field and a 35 by 35 px submit button. Below the box, outside its outline, **Active only**, the **?** button and the result count sit on one row, with the count at the right. A border separates that fixed header from the results scroller.

A tap on a result centers it between that header and the action menu and opens the course menu, with temporary space below the list when the card cannot otherwise reach that position. The scroller is the only vertical scroll owner, and it holds the error notices and the results.

At 1200 px and wider a result row holds the comparison slot badge, the code, the name, the match marks, the credits with the activity, and the selected or completed badge on one line, and the name takes the spare width. At a phone width the row sets the code, the comparison slot badge, the selected or completed badge and the activity on the first line, with the activity at the right. The name and its credits share the second line, the name takes the width before the credits and stays on one line with an ellipsis when it is longer, and the match marks close the row. The code and the name begin at one left edge. Adjacent result cards are separated by a small gap. The course menu scrolls within the screen when its content is taller than the viewport.

From 681 to 1199 px a result row sets the code and the comparison badge on the first line, the full title on one line on the second, the credits, the activity and the state on the third, and the match marks on the fourth. The title is cut by an ellipsis where the row is narrower than it, and the course menu carries the complete name.

A report whose query embedding request failed carries no semantic match, and the tab shows a localized notice above the results and draws the lexical matches as usual. The notice belongs to that report alone, so the next submitted search replaces it. A site that serves no semantic matching runs the lexical methods alone, and its tab shows neither the semantic help item nor that notice, because no semantic method ran and no provider was asked for a query vector.

## Compare

A small right-aligned **?** row sits above the slots in the tab and opens the comparison help drawer. It is there with empty or filled slots.

The comparison holds two slots, A and B. A course joins the first empty slot, and a course that already holds a slot is refused. While both slots are full, the app asks which of the two slots takes the course that was picked. Choosing a course that holds the other slot clears that slot. A comparison that the shared read cache already holds is shown again without a server read. [Browser state](/docs/frontend/browser-state.md#async-reads-cancellation-and-request-identity) states the cache key a pair is held under.

Each occupied slot reads its own course summary, so replacing one slot reads only the course that takes it and leaves the other course's card in place. While a changed pair is read, the verdict reads **Comparing courses…**, each meter shows a dash in place of a percentage, and each bar holds its position. The bars move to the values of the returned report. A pair with an empty slot clears the meters.

At a phone width the two slots stack in one column. A filled slot is one bordered surface with a head row above a course band. The head row carries the slot letter A or B in a 28 px square at the left and the **Replace** and **Remove** controls at the right, each at least 36 px tall. The course band holds the code, the full wrapped name at 15 px, the credits and the activity, and the selected or completed badge below them.

At a phone width an empty slot is one dashed surface at least 72 px tall that reads **+ Course A** or **+ Course B**, and the whole surface opens the picker. On a desktop viewport the same surface is at least 162 px tall. The five meters form one bordered surface, and each row puts the label and its description at the left and the percentage at the right on the first line, with the bar across the width on the line below.

The picker fills the tab area from 8 px below the top edge to 8 px above the bottom bar, with an 8 px margin on each side. Its header stays in place. At a width above 680 px the outlined search field holds the magnifier, the text and **Active only** at its right. At 680 px and below the outlined field holds the magnifier and the text, and **Active only** sits below it outside the outline. Each result is one bordered row. On a phone the code and action label share the first line and the name, clamped to two lines, follows, with the credits omitted. On a wider viewport the credits sit on the first line with the code. The whole row picks the course. The result list scrolls in the space below.

## Discover

Discover holds two lists, next courses and recommendations. Its settings are the list, the basis (the completed courses or every selected course), the activity scope, and, for next courses, the prerequisite mode **All** or **Partially covered**. The rendered **Partially covered** label is the `AT_LEAST_ONE` mode and the saved `at_least_one` value. [Discovering courses](/docs/guides/discover.md#coverage-and-activity) states the rule of that mode. Recommendations use **All**. A site that serves no embedding features offers no **Recommended** list at all.

The request carries both course sets, the chosen basis, the activity scope and the mode, and inferred prerequisites take part on a site that serves inference features. An empty chosen basis sends no request and shows a prompt to select or complete courses. A report for a list and request that the browser already holds is shown without a server read, so a change elsewhere in the profile starts no Discover read and the app leaves the result rows in place.

The results keep the backend order, each row carries its prerequisite coverage meters or its similarity meter, and the chosen list, mode, basis and scope are saved. Adding a course to comparison from a result row marks its card with the slot letter and starts no Discover read.

The basis chips name the first four courses, and a chip reading `+{count} more` opens the full list in a bounded picker. The list is framed by a border, keeps one bordered row per course, and scrolls with the shared thin accent scrollbar.

On a desktop viewport a result row fills the aligned column, its course name stays on one line, and its meters keep their own columns. From 681 to 1199 px a result row holds the course title on one line. The card and the meters stack in one column below 851 px, where the code, the name and the meter label share one left edge, and they sit side by side from 851 to 1199 px.

At a phone width a sticky header holds the **Next courses** and **Recommended** buttons, with a settings icon at the right. The icon opens a sheet above the bottom bar with the prerequisite mode, the basis, the activity scope and the **?** help. The sheet closes when the tab content leaves the phone width and returns closed when the width returns, without moving focus to a hidden trigger. The **?** sits at the bottom right, and **Active only** spans the full width of the sheet's two columns.

At a phone width a result row stacks the course card above its meters inside the row's own border. The card uses the same three-row layout as a search result: the code, the comparison slot badge, the selected or completed badge and the activity on the first line, the course name on one line with an ellipsis beside the credits on the second, and the match marks across the row. A next course that depends on inferred prerequisites carries the **inferred** mark beside its code on the first line. A recommendation whose teaching text includes a derived translation says so in the description of its similarity meter.

At a phone width the basis chips show the course code alone, and the expanded basis list wraps each name instead of cutting it. The expanded basis opens in a picker that fills the tab area, and its list fills the space below the total line and scrolls there. Each basis row is a bordered card that opens the course menu, with a small gap between rows. A tapped basis row centers between the list top and the action menu, with temporary space below the list when needed. The whole row, meters included, opens the course menu. On a desktop viewport the menu opens below that row when the viewport has room below it. On a phone it opens as the course sheet from the bottom edge of the window.

On a site that serves no embedding features the tab shows the next-course list, and its controls write the basis, the prerequisite mode, the activity scope and whether the basis is expanded. The tab never writes the saved list value, so a profile that saved **Recommended** shows next courses there.

A coverage meter appears in the **Next courses** list alone, and [Discovering courses](/docs/guides/discover.md#coverage-and-activity) states the categories that carry one and the value it shows.

The **?** drawer explains the open list's settings and its percentages, which are the two coverage meters of a next course and the similarity meter of a recommendation, together with the marks the site serves.

## The reads behind the layouts

The behaviour of each read behind these tabs is described in [Search](/docs/backend/search-and-discovery/search.md), [Comparison](/docs/backend/search-and-discovery/comparison.md), [Next courses](/docs/backend/search-and-discovery/next-courses.md) and [Recommendations](/docs/backend/search-and-discovery/recommendations.md). The stored state and the request lifecycle are described in [Browser state](/docs/frontend/browser-state.md).
