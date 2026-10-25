# Administration console

The administration console is a separate signed-in browser application that runs the same fixed administration commands as the operator menu and shows their reports.

The console uses a narrow desktop layout. A phone renders that layout scaled to the screen, with the same tabs, panels and controls.

## Signing in

Open the console's address. The sign-in screen appears before any panel, with the site name, the **Administration** heading, the **Username** and **Password** fields and the **Sign in** button.

![The sign-in card with the TUNI Course Explorer mark, the Administration heading, the empty Username and Password fields and the Sign in button](/docs/screenshots/admin-console-sign-in.png)

Enter the site's username and password, then select **Sign in**. A wrong username or password shows **Invalid username or password.** and clears the password field. A network or server failure shows **The sign-in attempt failed.**, and a console that cannot read its session at start shows **The administration console is unavailable.**

Three consecutive failed sign-ins lock the site. The third failure leaves a blank page, and the site then refuses every request, including a request that carries the correct credential. The lock is cleared only by hand. [Console access and records](/docs/operations/admin-console/access-and-records.md#failed-attempts-and-the-lock) states how the lock is cleared. A successful sign-in resets the consecutive failure count.

Opening many fresh sign-in sessions within a short time can temporarily delay another fresh sign-in. The console shows **The sign-in attempt failed.** or **The administration console is unavailable.** A page holding a live session can sign in, and a console that is already signed in continues to work. Wait briefly, then reload the page and sign in again.

## The header

The signed-in header carries the site name, the **Admin** label and the five tabs: **Dashboard**, **Data preparation**, **Inference**, **Logs** and **Settings**. The right side holds **GitHub**, **Docs**, **App** and **Sign out**.

![The console header with the site name, the Admin label, the five tabs and the GitHub, Docs, App and Sign out controls](/docs/screenshots/admin-console-header.png)

- **GitHub** opens the project's repository in another browser tab.
- **Docs** opens the documentation home of the course-exploration site.
- **App** opens the course-exploration site.
- **Sign out** ends the session on the server and returns to the sign-in screen.

Every tab holds its panels mounted for the signed-in session, so a switch between tabs shows the reports and markers of that tab without starting it again. The open tab belongs to the browser tab, so a reload returns to the same tab.

## How panels refresh

An automatic panel reads once when the signed-in console opens and then reads again after the configured interval, measured from the end of the previous read. The example settings set the interval to one minute. A panel's marker shows a dot, **auto** and the time since its last successful read, in seconds, minutes, hours or days. Before the first success the marker shows **no read**, and a first read in progress shows **Reading…**.

The console reads while its browser tab is visible. A hidden browser tab cancels a scheduled read and aborts a read in flight without showing a failure. The return to the tab reads once immediately and then resumes the interval. A switch between console tabs does not pause or restart a read.

A few panels read only on request, because their read reaches the worker. The worker log reads and the worker preflight are examples. Such a panel's marker says **manual** and gives the time of the requested read.

## Confirmations

Some actions ask for confirmation before they run. Each dialog names the action it runs. The backup and dataset deletions name the file or dataset they remove, and a worker setup names the branch. For a stage, **Stop** opens **Stop Ingestion** with **Stop the Ingestion stage.**, and the **Stop Translation** and **Stop Embedding** dialogs name their stage the same way. **Cancel**, Escape and a click outside the dialog close it and run nothing. **Confirm** runs the action.

Actions that do not ask for confirmation run immediately when selected. A stage's **Start**, **Pause** and **Resume** are examples.

The administration rebuild signs every operator out. Its confirmation states that, and a successful build returns the console to the sign-in screen with **The admin panel is restarting. Sign in again.** The console's server process restarts after the build, and every session ends with it.

## Failures

Each panel shows the failure of its own read or command inside the panel, with a short message. A failed read leaves the last successful report and its marker in place, and the next successful read clears the failure. A failed command shows its failure in the same panel. The Dashboard's single read reports its failure above its five panels.

A request refused because the session has ended returns the console to the sign-in screen. While the failed-attempt lock exists, every request leaves the blank page.

## The tabs

Each tab owns one part of the administration work.

- **[Dashboard](/docs/operations/admin-console/dashboard.md)** reports the serving state, the website, the host, the database and the embedding runtime.
- **[Data preparation](/docs/operations/admin-console/data-preparation.md)** holds the ingestion, translation and embedding stages, their controls and the three reports over the selected dataset.
- **[Inference](/docs/operations/admin-console/inference.md)** holds the inference run, its publication diagnostics, coverage, generation identities and retained failures, the target decisions and the dataset cleanup.
- **[Logs](/docs/operations/admin-console/logs.md)** holds the command log, the session and runtime logs and the request usage report.
- **[Settings](/docs/operations/admin-console/settings.md)** holds the configuration editor, the feature switches, the backups, the two rebuilds, the dataset actions and the worker setup and preflight.

The same commands are available from the [Operator menu](/docs/operations/operator-menu.md), and [Stage lifecycle](/docs/operations/stage-lifecycle.md) describes the states behind the stage actions.
