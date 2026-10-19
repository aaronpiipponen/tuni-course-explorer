# Settings

The Settings tab edits the site's settings files and runs the maintenance actions for the dataset, the backups, the rebuilds and the worker.

## Panel order

The **Configuration** editor spans the tab first, then **Dataset** and **Backups**, **Rebuild** and **Worker provisioning**, and **Feature switches** last.

![The Settings tab with the configuration file list, the dataset panel, the backup list, the rebuild steps, the worker provisioning form and the feature switches](/docs/screenshots/admin-console-settings.png)

## Configuration editor

The **Configuration** panel edits the values of one settings file at a time. It opens with no file selected and shows **Select a file to edit its keys.** The list names the subsystem files and the environment file. A subsystem file holds portable settings, and the environment file holds the values that change per machine.

1. Select a file in the list.
2. Edit the value in the text field beside its key.
3. Select the save control, which names the open file (**Save config/web.toml** for the web settings file).

Every key of the open file appears with its value. A string value edits its own contents, and a number, on/off value, list or table edits JSON text. The save control is disabled while the file has no changed value.

Before the first write, the panel checks every changed value. A change to a number, on/off value, list or table that is not valid JSON stops the save before any key is written, and the notice names the key.

The save writes the changed keys one at a time in the order the file lists them. If one key is refused, the keys before it are saved and the rest are unsaved. The panel shows the failure and states how many of the changed keys are saved. Selecting the save control again retries the unsaved keys. When every changed key is saved, the panel states **All changed keys are saved.**

The affected process reads a saved change when it restarts. The open file reads again automatically while it has no changed value, so its values follow the file.

> [!WARNING]
> Selecting another file clears the unsaved edits of the open file.

![The configuration editor with the web settings file open, its keys in text fields, the save control at the top right and the file list on the left](/docs/screenshots/admin-console-settings-configuration.png)

The [Configuration](/docs/backend/configuration.md) page describes how the settings files compose and how a saved value reaches a process.

## Dataset

The **Dataset** panel shows the pointer, the selected dataset and its schema facts.

| Row | Meaning |
|---|---|
| **pointer** | The pointer file that names the selected dataset. |
| **selected dataset** | The identity of the dataset the site serves. |
| **kind** | How the dataset entered the chain, **initial** or **returned**. |
| **database** | The database name. |
| **receipt records** | The schema head recorded by the dataset's receipt. |
| **database head** | The schema head the database reports. |
| **at head** | **yes** when the database matches this checkout's migration head, **no** when it differs, and **unknown** when no database head is reported. |

The selected dataset, the kind and the database appear when the site reports the selected dataset enabled. When the site reports it disabled, the panel shows **The selected dataset is not enabled on this site.** in place of those rows.

![The Dataset panel with the pointer, the selected dataset, its kind, database, receipt and database heads, and the Enroll or select dataset and Migrate selected dataset controls](/docs/screenshots/admin-console-settings-dataset.png)

The panel shows the selected dataset and its schema facts above the two actions.

**Enroll or select dataset** asks for confirmation first. It migrates the configured database to the migration head of the checkout, verifies it, writes the receipt and selects it. When a dataset is already selected, the action returns that selection and changes nothing. A successful enrollment shows a receipt note naming the dataset identity, its kind and its database, and shows the recorded head and the number of verified tables.

**Migrate selected dataset** asks for confirmation first. It applies the migration head to the selected dataset and shows the live head and the number of verified tables.

> [!IMPORTANT]
> The migration refuses while any stage is not idle or while the database service is not running.

[Datasets](/docs/operations/datasets.md) describes the dataset chain, the receipt and the migration.

## Backups

The **Backups** panel lists one row per backup file, with its name, its modification time in UTC to the whole minute and its size. A successful read that finds no file shows **No backup file is listed.**

**Delete** opens the **Delete backup** dialog, which names the exact file. **Cancel**, Escape and a click outside the dialog close it and change nothing. **Confirm** removes the file and reloads the listing. A failed deletion leaves the row and shows the failure in the panel.

## Rebuild

The **Rebuild** panel lists the four steps of an app rebuild in order:

1. **Build the site frontend**
2. **Recreate the database and embedding containers**
3. **Restart the site's web server**
4. **Verify the web server's loopback bind**

**Rebuild app** asks for confirmation first. It runs the four steps and shows the steps it ran and the bind it verified.

![The Rebuild app confirmation dialog with the rebuild question, Cancel and Confirm over the Settings tab](/docs/screenshots/admin-console-settings-rebuild-dialog.png)

**Rebuild admin panel** asks for confirmation first, and the dialog states that it signs all operators out. It builds the console, and the administration backend then restarts. The console returns to the sign-in screen with **The admin panel is restarting. Sign in again.**

While either action runs, the panel shows **Running…** and disables both actions. A failed rebuild shows its failure in the panel. A completed administration rebuild ends every administration session, and a failed administration build queues no restart and leaves the console signed in.

## Worker provisioning

The **Worker provisioning** panel sets up or updates the worker.

1. Enter the **origin branch**.
2. Leave **code only** off for a full setup, or switch it on to update the code and its locked dependencies alone.
3. Select **Worker setup or update**.

The origin branch input starts empty. **Worker setup or update** is disabled until a branch is entered, and the panel shows **Enter an origin branch before the setup.** The confirmation names the branch, and **Cancel**, Escape and a click outside the dialog close it and change nothing.

A full setup also performs the worker bootstrap and prepares its resources. The report shows the code branch, the code revision, whether the server origin differs, whether the resources are ready and, when they are not, the missing resources. With **code only** on, the setup reports the code facts and shows resource readiness as **unknown**.

**Preflight** only reads the worker's prepared code and resources. It sends nothing on its own, shows a preflight report from the worker when selected, and holds that report separate from a setup report. The panel's marker says **manual**.

[Worker sessions](/docs/operations/worker-sessions.md) describes the worker session that the stages run.

## Feature switches

The **Feature switches** panel holds the two switches that decide which features the site serves. **Inference features** covers the inferred toggle, inferred tags and Discover. **Embedding features** covers recommendations, the semantic tier and the vector meters.

Each switch writes its setting when selected. A successful write shows the written position and adds a notice above the panels that names the setting and its state and states that a rebuild or restart applies it to serving. A refused write shows the position the file holds and the failure. A value the file does not report as on or off shows **unknown** in place of the switch.

> [!IMPORTANT]
> A saved switch changes serving only after the site's web server is rebuilt or restarted.

## When a read fails

Each panel shows the failure of its own read. A failed read leaves the last successful report and its marker in place, and the next successful read clears the failure. A panel that has no successful read shows the failure. A failed save, deletion, rebuild, enrollment, migration or worker action shows its failure in its own panel.

The [Administration console](/docs/operations/admin-console/README.md) describes the sign-in, the header, the confirmation dialog and the read markers.
