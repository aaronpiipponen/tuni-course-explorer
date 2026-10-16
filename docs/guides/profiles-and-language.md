# Profiles and language

A profile is one named set of the app state, and the profile control and the language control manage the profiles of this browser.

## What a profile holds

A profile holds the language, the open tab, the [shared course sets](/docs/guides/README.md#shared-course-state), and the state of each tab.

| Part | What the profile holds |
|---|---|
| App language | Finnish or English. |
| Open tab | The tab that the app shows when the profile opens. |
| Selected courses | Every course in the selection. |
| Completed courses | Every course marked completed. |
| Search | The query and the **Active only** setting. |
| Compare | The two comparison slots. |
| Prerequisites | The open course, the search field, the **Recommended**, **Inferred** and **Active only** settings, the [route basis](/docs/guides/prerequisites.md#graph-options), the excluded courses, and the completed and excluded marks on module and requirement nodes. |
| Discover | The chosen list, the mode, the basis, and the **Active only** setting. |
| Structure of studies | The [structure root](/docs/guides/structure-of-studies.md#choosing-the-root), the choices, and the places of the courses and modules. |

A browser with no saved state starts with one profile named My plan. Each profile holds its own copy, so the courses and the settings of one profile do not appear in another.

The profiles belong to this browser. They are held in the local storage of the browser, so another browser or another device does not have them.

## The profile control

The control in the top bar carries the name of the open profile. Select it to open **Profiles**, which lists every profile of this browser.

Each row shows the profile name and its counts, written as selected first and completed second, such as "4 selected · 2 completed". The open profile is marked.

![The Profiles list open below the top bar, with two profiles and their selected and completed counts, a rename control and a delete control on each row, and the New profile form with its Name field and Save button.](/docs/screenshots/profile-controls.png)

## Creating a profile

1. Under **New profile**, type a name in the field that reads **Name**.
2. Select **Save**.

The profile that is created becomes the open one and starts as a copy of the profile that was open, so its courses and its settings carry over. **Save** is available once the field holds a name.

> [!TIP]
> A second profile starts as a copy of the open one and then changes on its own, so two profiles can hold two different plans of the same degree.

## Switching, renaming and deleting

Select a profile row to switch to that profile. The app opens it with its own language, tab, courses and settings.

The pencil control on a row renames that profile, and it is labelled with the profile name. The **Rename profile** dialog opens a field that carries the name. Change the name and select **Save**.

The trash control on a row deletes that profile, and it is labelled with the profile name. The confirmation reads **Delete profile “My plan”?**, with the name of the profile in place of My plan, and it offers **Cancel** and **Delete**. Deleting the profile that is open makes the first of the profiles left in the list the open one, and the confirmation states this. The delete control appears on each row while two or more profiles are stored, and the deletion of the last remaining profile is refused.

> [!WARNING]
> A deleted profile and everything that it holds leave this browser together. The courses and the settings of another profile are not affected.

## Profile names

The name of a profile is trimmed of the spaces around it before it is stored.

An empty name is refused, and the message is **Profile name cannot be empty**. The **Save** button of the profile form is not available while the field is empty.

A name that another profile already holds is refused, and the message is **A profile with that name already exists**. The names are compared as written, so two names that differ only in capitalisation are two different names. A refusal message closes on its own after five seconds.

## The language control

The **FI** and **EN** control in the top bar sets the app language of the open profile. The pressed side is the language in use, and the control reports it.

![The Profiles panel open below the profile control, with My plan and its 4 selected and 2 completed courses and the New profile form, and the FI and EN language control in the top bar with EN pressed.](/docs/screenshots/profile-language.png)

The language belongs to the profile, so switching profile switches the language with the rest of that profile.

The app language changes:

- every interface word of the app, including the labels of the tabs and the controls
- the name of a course or a module, where the catalogue holds a name in that language

Where the catalogue holds no name in the chosen language, the app shows the name in the other language, and then the course or the module code.

## When the saved profiles cannot be read

The app reads the stored state when it starts. If the stored value cannot be read, the app shows a notice in place of the interface, with the summary in English and in Finnish, and the stored value is left as it is.

The notice names what could not be read: stored state that is not a valid envelope, a version of the stored state that the app does not support, a state that names no open profile, a profile that is not valid, or the saved state of one tab that is not valid.

Clearing the stored data for this site starts the browser fresh on the next load, with one profile named My plan.

The saved shape of a profile and the store that writes it are described in [Browser app](/docs/frontend/browser-app.md#saved-state-and-transient-reports).
