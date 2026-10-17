# Profiles and language

A profile is one named set of the app state, and the profile control and the language control manage the profiles of this browser.

## What a profile holds

A profile holds the language, the [shared course sets](/docs/guides/README.md#shared-course-state), and the state of each tab. The open tab belongs to the browser tab instead, so a profile never moves the tab you are looking at.

| Part | What the profile holds |
|---|---|
| App language | Finnish or English. |
| Selected courses | Every course in the selection. |
| Completed courses | Every course marked completed. |
| Search | The query and the **Active only** setting. |
| Compare | The two comparison slots. |
| Prerequisites | The open course, the search field, the **Recommended**, **Inferred** and **Active only** settings, the [route basis](/docs/guides/prerequisites.md#graph-options), the excluded courses, and the completed and excluded marks on module and requirement nodes. |
| Discover | The chosen list, the mode, the basis, and the **Active only** setting. |
| Structure of studies | The ordered [programmes](/docs/guides/structure-of-studies.md#adding-a-programme), the choices, the places of the courses and modules, and a captured Sisu plan that the tab has not placed yet. |

A browser with no saved state starts with one profile named My plan. Each profile holds its own copy, so the courses and the settings of one profile do not appear in another.

The profiles belong to this browser. They are held in the local storage of the browser, so another browser or another device does not have them.

## The profile control

The control in the top bar carries the name of the open profile. Select it to open **Profiles**, which lists every profile of this browser. The panel holds the profile list, the **New profile** form, the **Import** area, and a bottom row with a **?** help control, **Copy Sisu import script**, and **Export**.

Every tab of the same browser opens the same saved state, so a change made in one open tab appears in the other open tabs, and a profile switch reaches them as well.

Each row shows the profile name and its counts, written as selected first and completed second, such as "4 selected · 2 completed". The open profile is marked.

![The Profiles list open below the top bar, with two profiles and their selected and completed counts, a rename control and a delete control on each row, above an import area and a bottom row with a question-mark help control, Copy Sisu import script and Export.](/docs/screenshots/profile-controls.png)

## Creating a profile

1. Under **New profile**, type a name in the field that reads **Name**.
2. Select **Save**.

The profile that is created becomes the open one and starts as a copy of the profile that was open, so its courses and its settings carry over. **Save** is available once the field holds a name.

> [!TIP]
> A second profile starts as a copy of the open one and then changes on its own, so two profiles can hold two different plans of the same degree.

## Switching, renaming and deleting

Select a profile row to switch to that profile. The app opens it with its own language, courses and settings, and the tab you are looking at stays where it is.

The pencil control on a row renames that profile, and it is labelled with the profile name. The **Rename profile** dialog opens a field that carries the name. Change the name and select **Save**.

The trash control on a row deletes that profile, and it is labelled with the profile name. The confirmation reads **Delete profile “My plan”?**, with the name of the profile in place of My plan, and it offers **Cancel** and **Delete**. Deleting the profile that is open makes the first of the profiles left in the list the open one, and the confirmation states this. The delete control appears on each row while two or more profiles are stored, and the deletion of the last remaining profile is refused.

> [!WARNING]
> A deleted profile and everything that it holds leave this browser together. The courses and the settings of another profile are not affected.

## Profile names

The name of a profile is trimmed of the spaces around it before it is stored.

An empty name is refused, and the message is **Profile name cannot be empty**. The **Save** button of the profile form is not available while the field is empty.

A name that another profile already holds is refused, and the message is **A profile with that name already exists**. The names are compared as written, so two names that differ only in capitalisation are two different names. Creating or renaming a profile shows the message in a red box that grows into its place and shrinks away again, and it closes on its own after five seconds. With reduced motion set in the operating system the box appears and disappears at once.

## Exporting a profile or the saved data

1. Select the profile control to open **Profiles**.
2. Select **Export**. A list opens under the bottom row of the panel.
3. Select a profile to download it as one file, or select **All saved data** to download every profile with every setting of this browser.

![The Export list open at the bottom of the Profiles panel, naming My plan and Alternative plan above All saved data.](/docs/screenshots/profile-export-menu.png)

Exporting a profile leaves the profiles as they are, and it does not open the exported profile. The list is open for several downloads in a row.

The **?** control at the left of the bottom row opens a drawer that explains export, import and Sisu plan import in three sections.

A profile downloads as `course-explorer-profile-<profile name>.json`. Every character that a file name cannot hold is replaced by `_`, and the spaces, the letters outside the plain Latin alphabet and the other characters of the name are kept. The whole saved data downloads as `course-explorer-saved-data.json`.

## Importing a file

1. Select the profile control to open **Profiles**.
2. Select **Choose file** in the **Import** area and pick one file, or drop one file onto the area.

The control reads **Choose file** and **or drop a .json file**, and it reads the three kinds of file: a profile, the whole saved data, or a capture of a Sisu plan. The file's own `type` decides which one it is, and the **?** help drawer of the bottom row explains the three kinds.

A file that holds a profile opens the dialog **Import profile “My plan”?**, with the name of the imported profile in place of My plan. Select **Import** to create a profile from the file and open it, or **Cancel**, Escape or a click outside the dialog to leave the profiles as they are. The created profile carries the name and everything the file holds, and it is a separate profile from the one that is open.

![The Import profile “Alternative plan”? dialog, stating that a profile with that name is created and made current, above Cancel and Import.](/docs/screenshots/profile-import-confirm.png)

An imported profile whose name another profile already holds is refused when **Import** is selected, and the message is **A profile with that name already exists**. The dialog is left open and nothing is written. A profile file whose name carries spaces at either end is refused with a message before anything is written.

A file that holds the whole saved data opens the dialog **Replace all saved data?**, which states that every profile in this browser is replaced by the imported saved data. Select **Replace** to replace the saved data and reload the app, or **Cancel** to leave the saved data as it is.

A file that holds a Sisu plan capture opens the dialog **Import Sisu plan**. It names the captured programmes in the order Sisu shows them, and it names every item whose identity the capture could not resolve. Type a name in **Profile name** and select **Import** to create the profile, or **Cancel**, Escape or a click outside the dialog to leave the profiles as they are. **Import** is available once the name holds something. [Sisu import script](/docs/guides/sisu-import.md) covers the capture and what the import places.

A file of another kind, or a file whose content is not valid, is refused with a message and changes nothing.

## Copying the Sisu import script

**Copy Sisu import script** in the bottom row of the profile panel copies the console script that captures a Sisu plan to the clipboard, and the panel reports **Sisu import script copied** in a green box that closes on its own after five seconds, the same lifetime as a **Save** or **Rename** failure message. A copy that the browser refuses reports **Could not copy Sisu import script**. The script itself, and the steps that use it, are in [Sisu import script](/docs/guides/sisu-import.md).

## The language control

The **FI** and **EN** control in the top bar sets the app language of the open profile. The pressed side is the language in use, and the control reports it.

![The Profiles panel lists My plan with four selected and two completed courses and Alternative plan with two selected and one completed course. Alternative plan is current, FI is pressed in the language control, and the top bar and the panel read in Finnish.](/docs/screenshots/profile-language.png)

The language belongs to the profile, so switching profile switches the language with the rest of that profile.

The app language changes:

- every interface word of the app, including the labels of the tabs and the controls
- the name of a course or a module, where the catalogue holds a name in that language

Where the catalogue holds no name in the chosen language, the app shows the name in the other language, and then the course or the module code.

## When the saved profiles cannot be read

The app reads the stored state when it starts. If the stored value cannot be read, the app shows a notice in place of the interface, and the stored value is left as it is. That screen is in English, because no profile language can be read there. Stored state of another version is not converted, so it reads as unreadable and is kept until it is reset.

The notice names what could not be read: stored state that is not a valid envelope, a version of the stored state that the app does not support, a state that names no open profile, a profile that is not valid, or the saved state of one tab that is not valid.

Under the notice are two controls.

![The recovery screen shown when the saved profiles cannot be read, with the notice Saved browser state is invalid above the Export saved data and Reset saved data controls.](/docs/screenshots/storage-recovery.png)

**Export saved data** downloads the stored text exactly as it is as `course-explorer-saved-data.json`. The file can be repaired by hand and put back through the **Import** area.

**Reset saved data** asks for a confirmation titled **Reset saved data** that states that every profile saved in this browser is deleted and the app then starts with a profile named My plan. Select **Reset** to delete every profile and start again, or **Cancel** to leave the saved data as it is. Every profile is deleted, and the app starts with one profile named My plan.

Clearing the stored data for this site starts the browser fresh on the next load, with one profile named My plan.

The saved shape of a profile and the store that writes it are described in [Browser app](/docs/frontend/browser-app.md#saved-state-and-transient-reports).
