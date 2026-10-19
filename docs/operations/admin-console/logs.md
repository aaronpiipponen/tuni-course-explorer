# Logs

The Logs tab shows the administration command log, the stage session and runtime logs, and the request usage report.

![The Logs tab with the command log, the session logs panel reporting no recorded session, the embedding runtime log and the usage report](/docs/screenshots/admin-console-logs.png)

The command log spans the tab above the session, runtime and usage panels.

## Command log

The **Command log** panel lists the commands the administration backend ran, newest first. The log reads automatically, and the marker shows the time since the last successful read.

| Column | Meaning |
|---|---|
| **Time** | The command's start time, in UTC to the whole minute. |
| **Command** | The fixed command label, followed by one short failure line when the command failed. |
| **Exit** | The command's exit code. |
| **Duration** | The elapsed time, to two decimals of a second. |
| **Result** | **ok**, **failed**, **login**, **failed login** or **lock**. |

A successful read that the console issues automatically records no entry. A failed automatic read records one, and every explicit read, action and sign-in event records one. A sign-in, a failed sign-in and the creation of the lock appear in the same table as the commands.

An entry holds no captured command output beyond the one failure line and no argument, target identity, dataset identity, file name or branch name. The log holds its most recent entries up to its configured limit.

## Session logs

The **Session logs** panel reads the logs of one stage session.

The session picker lists the sessions the console discovered across the four stages, newest first, and names each one by its stage and session identity. The console selects the first listed session and a server source when the listing arrives.

The source picker offers the two server streams and, for a translation or inference session, the keepalive file and the worker runner log. The server streams and the keepalive file read automatically. The worker runner log reads only when **Read** is selected, and the panel's marker then says **manual**.

1. Choose the session and the source.
2. Enter a positive whole line count and select **Apply**.
3. For the worker runner log, select **Read**.

The line count starts at 200. Selecting **Apply** with any other value shows **Enter a positive whole line count.**

The panel shows the last lines of the chosen log. A log that has not been read shows **No log has been read.** A log the stage never wrote shows **The log is unavailable.** An empty log shows **The log holds no lines.** Any other log shows its lines. Selecting another session or source clears the previous text. A worker log read reaches the worker only when **Read** is selected.

When no session is recorded, the panel shows **No session is recorded.** and lists no picker.

## Runtime logs

The **Runtime logs** panel reads the embedding service's own log and the runtime log of a listed worker session.

The picker offers **Embedding runtime log** and each listed translation or inference session. The embedding log reads automatically. A worker session's runtime log reads only when **Read** is selected, and the marker then says **manual**. The read contacts the worker for that log alone.

The line count and its **Apply** control work as they do in **Session logs**. The panel shows the same states for a log that has not been read, a log that is unavailable, an empty log and a log that holds lines.

## Usage

The **Usage** panel summarizes the requests the course-exploration site answered in one window of hours. The window is 24 hours at first and reads automatically, and its marker shows the time since the last successful read.

1. Enter a positive whole number of hours and select **Apply**.
2. Read the **Window**, **Requests** and **Mean** rows.
3. Read one row per route in the table.

The panel accepts a positive whole number of hours. Selecting **Apply** with any other value shows **Enter a positive whole hour count.**

The **Window** row shows the start and the end of the window in UTC. The window covers the current hour and the whole hours before it, up to the entered number of hours, and it ends at the end of the current hour. **Requests** gives the total number of requests, and **Mean** gives the mean duration to two decimals of a second.

| Column | Meaning |
|---|---|
| **Route** | The fixed route label. |
| **Requests** | The number of requests on that route. |
| **Mean** | The mean duration on that route, to two decimals of a second. |

![The Usage panel with the 24-hour window, the request total, the mean duration and one row for each recorded route](/docs/screenshots/admin-console-logs-usage.png)

A window with no recorded request shows zero requests, **unknown** for the mean, no route row and the message **The window holds no recorded request.**

Each report removes the request records older than the configured retention. A window longer than that retention is refused, and the panel shows the failure.

The usage report counts requests to the course-exploration site, not the console's own commands. [Console access and records](/docs/operations/admin-console/access-and-records.md) describes the command log, the request records and the usage report.

## How the panels refresh

Each panel reads on its own. An automatic marker shows **auto** and the time since the last successful read, and a panel that waits for the operator shows **manual**. A switch to another console tab leaves the panels mounted, so the return shows the report and marker the panel last held.

## When a read fails

A failed read leaves the last successful report and its marker in place, and the next successful read clears the failure. A panel with no successful read shows the failure and no rows. The [Administration console](/docs/operations/admin-console/README.md) describes the sign-in, the header, the confirmation dialog and the read markers.
