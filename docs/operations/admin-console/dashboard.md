# Dashboard

The Dashboard tab reports the state of the serving site, the host, the database and the embedding runtime, and it warns when a hub file needs a web server restart.

## The five panels

One read fills all five panels, so their markers share one time. **Serving state** spans the width, and **Website** and **Host** sit above **Database** and **Embedding runtime**. The tab shows the state of the selected dataset and the services around it.

![The Dashboard tab with the serving state, website, host, database and embedding runtime panels, each showing the report of one read](/docs/screenshots/admin-console-dashboard.png)

## Serving state

The panel describes the dataset the site serves.

| Row | Meaning |
|---|---|
| **selected dataset** | The id of the dataset the site serves. |
| **kind** | How the dataset entered the chain, **initial** or **returned**. |
| **predecessor** | The dataset that precedes the selected dataset in the chain. |
| **pointer** | The file that names the selected dataset. |
| **schema head** | The database revision recorded by the dataset receipt, which can differ from the live database's own revision. |
| **embedding hub** | The file that holds the embedding hub, and the time it was last written. |
| **outcomes hub** | The file that holds the outcomes hub, and the time it was last written. |
| **web server hubs** | The value **read at process start** states that the web server reads the hub files when its process starts. |

A hub file with no file time shows its path and **unknown** in place of the time. When the site serves its configured database instead of a selected dataset, the dataset rows read **unknown**.

The panel adds **Restart the web server to load the hub files written at {time}.** when a hub file was written after the web server started. The time is the writing time of a newer hub file. On a site that serves the embedding features, the running web server holds the hubs it read at its own start, so a restart is what loads the written files. Restart the web server when the hint appears.

## Website

The panel describes the site's web service.

| Row | Meaning |
|---|---|
| **state** | The state of the service, such as active or inactive. |
| **bind** | The configured address and port the web server binds. |
| **configured processes** | The number of worker processes the settings configure, rather than a measured count. |
| **entry point** | The script the web service runs. |
| **checkout** | The branch and the first nine characters of the revision of the checkout the console reads. |
| **uptime** | How long the web service has run. |
| **started** | When the web service started, in UTC to the whole minute. |

**uptime** and **started** read **unknown** when the service is not active.

## Host

The panel describes the machine that runs the console.

| Row | Meaning |
|---|---|
| **uptime** | How long the host has run since it booted. |
| **CPU usage** | The share of CPU time that was not idle or waiting for I/O over a short sample, from 0% to 100%. |
| **memory** | Used memory of total memory. |
| **data/** | The size of the data directory. |
| **models/** | The size of the models directory. |
| **backups/** | The size of the backups directory. |
| **free space** | Free space of the filesystem that holds the checkout, of its total. |

A directory total reads **unknown** when that directory is absent or is not a real directory of the checkout.

## Database

The panel describes the database service and the database it serves.

| Row | Meaning |
|---|---|
| **state** | The state of the database container, such as running or absent. |
| **image** | The container image. |
| **address** | The configured host and port. |
| **database** | The database name. |
| **schema head** | The migration revision this checkout expects. |
| **migration** | **at head** when the database matches that revision, otherwise the database's own revision. |
| **shared memory** | The container's configured shared-memory size. |
| **size** | The database size. |
| **connections** | The number of connections to the database. |

When the container is not running, **size**, **connections** and **migration** read **unknown**, because no live database read runs.

## Embedding runtime

The panel describes the embedding container and the runtime it serves.

| Row | Meaning |
|---|---|
| **state** | The state of the embedding container, such as running or absent. |
| **image** | The container image. |
| **model** | The configured model name. |
| **artifact** | The configured model file the service loads. |
| **address** | The configured host and port. |
| **context** | The model's context size. |
| **threads** | The configured thread count. |
| **pooling** | The configured pooling method. |
| **normalization** | The configured normalization value. |

## How the tab refreshes

The whole tab follows one automatic read. The read runs when the console opens and then again after the configured interval. Every panel's marker shows **auto** and the time since the last successful read. A switch to another console tab does not start another read, and the return shows the report the read last returned.

An **unknown** value means the report had no value to give, where zero and false are values of their own.

## When the read fails

The five panels share one read, so a failure appears once, above the panels. A panel that has a previous report shows it. A panel with no previous report shows its heading, its **no read** marker and no rows.

The next successful read clears the failure, and the panels then fill from that report.
