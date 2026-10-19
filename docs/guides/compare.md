# Comparing two courses

The Compare tab holds two courses in the slots A and B and reports how much of their teaching text the two have in common.

## The two slots

Two courses fill the slots A and B.

1. Open the **Compare** tab. Each empty slot reads **+ Course A** or **+ Course B**.
2. Select the empty slot. The course picker opens over the tab and names the slot it fills.
3. Type part of a course name or code into the picker's filter field. The picker lists every course whose code or shown name contains the text.
4. Select **+ add** on a course. The course takes the slot.

A course also joins from any tab: choose **Add to comparison** in its [course menu](/docs/guides/README.md#shared-course-state), and it takes the first empty slot. A course that already holds a slot shows **Already in comparison** in place of that action.

To see what one of the two courses expects before it is taken, open its [prerequisite graph](/docs/guides/prerequisites.md).

![The course picker open below the two slots, with slot A filled and slot B empty, a filter field holding a code fragment, the Active only option, Close, and course rows that each end in + add. One row carries the completed badge and another the slot A badge.](/docs/screenshots/compare-course-picker.png)

The picker carries its own **Active only** option and a **Close** button, and it closes when you choose a course, when you select outside it, and when you press Escape. While the picker is open the rest of the tab fades back.

## When both slots are full

Adding a course from a course menu while both slots are full opens the dialog **Replace which course?**, which lists the two courses that hold the slots with a **Replace** button on each, above a **Cancel** button at the left of the dialog. The course behind the button you select leaves the comparison, and the course you chose takes its slot.

![The Replace which course? dialog, naming the course to add and listing the two courses in the slots, each with a Replace button, above Cancel.](/docs/screenshots/compare-replace-dialog.png)

Choosing a course in the picker needs no question, because the picker was opened from one slot, so that slot is the one that changes.

The two slots never hold the same course, so choosing the course that holds the other slot clears that other slot.

## Changing or clearing a slot

Each filled slot carries **Replace** and **Remove**. **Replace** opens the picker for that slot, and the course you choose takes the place of the one that is there. **Remove** empties the slot. With fewer than two courses in the slots the tab reads **Select two courses to compare** in the place of a verdict.

## The five meters

A comparison reports five percentages. Each one carries an amount on a bar and a sublabel that names what the meter puts side by side.

| Meter | What it measures |
|---|---|
| **Overall relatedness** | The whole teaching text of the two courses together, the name, the content, and the learning outcomes. |
| **Content similarity** | The content text of the two courses. |
| **Learning-outcome similarity** | The learning outcomes of the two courses. |
| **Overlap** from the slot A course into the slot B course | The share of the first course's content and learning-outcome text that has a close match in the second course. |
| **Overlap** from the slot B course into the slot A course | The share of the second course's content and learning-outcome text that has a close match in the first course. |

Each of the two overlap meters names both course codes and the direction it measures. The sublabels read **whole course**, **content vs content**, **outcomes vs outcomes**, **how much of A has a match in B**, and **how much of B has a match in A**.

A meter with no value to show reads **not available**, which happens when the two courses share no language, or when one side carries no text in the field that the meter reads. A reading of 0 % is a result, and **not available** alone marks a meter without a value.

![Two courses in the slots A and B, each with Replace and Remove, the verdict Loosely related beside the analysis notice, and the five meters with their names, sublabels, bars, and percentages](/docs/screenshots/compare-meters.png)

## The verdict

One label summarizes the whole comparison.

| Verdict | What it means |
|---|---|
| **Heavily overlapping** | A large share of one course's teaching text has a close match in the other course. |
| **Partly overlapping** | A smaller but substantial share of one course's teaching text has a close match in the other course. |
| **Same area, different content** | The two courses are close as a whole, and they share little teaching text. |
| **Loosely related** | The two courses are somewhat close as a whole. |
| **Unrelated** | Neither overlap is substantial, and the two courses are not close as a whole. |

The verdict follows the stronger of the two overlap meters first. A large enough overlap in either direction gives **Heavily overlapping** or **Partly overlapping** on its own. Otherwise the **Overall relatedness** figure decides between **Same area, different content**, **Loosely related**, and **Unrelated**.

Before both slots hold a course the tab reads **Select two courses to compare**, and while the analysis runs it reads **Comparing courses…**, and each meter shows a dash until the report arrives. A pair the app cannot analyze reads **not available** in place of a verdict.

> [!IMPORTANT]
> The five meters and the verdict are analysis of the teaching text, labeled apart from the official data that the university publishes.

Beside the verdict the tab states **Course information analysis, not official equivalence.**, and it adds **Includes derived text.** when the teaching text behind the analysis includes a translation on either side.

## What the slots remember

The two slots belong to the [profile](/docs/guides/profiles-and-language.md), so they hold their courses across a move between tabs and after a reload, and each profile holds its own pair. The picker's filter text and its **Active only** option are kept the same way. The analysis itself is read for the pair in the slots, so it appears when both slots hold a course.

## When a site serves no comparison

Comparison measures stored teaching-text vectors, so it belongs to a site that serves the embedding features. On a site that does not serve them the **Compare** tab is absent from the top bar and from the tab ring, a course menu lists no **Add to comparison**, and a course card carries no slot letter. The slots your profile saved are its own values, so the pair is there on a site that serves the tab again, and a stored **Compare** tab opens **Search** while the site serves no comparison.

How each meter and the verdict are worked out is described in [Comparison](/docs/backend/search-and-discovery/comparison.md).
