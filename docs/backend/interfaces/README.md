# Interfaces

The interfaces chapter covers the HTTP read surface, the report command line, the administrative command, and the launcher that starts the web server.

## The HTTP read surface

The web server answers ten fixed read commands under `/api/` and serves the browser application, whose `/docs` address opens the documentation wiki. Each command answers a POST request with a closed JSON body, delegates once to one package command, and returns its report. The browser sends its state as request inputs, and no route writes data, starts a stage, or reaches the worker. [Web API](/docs/backend/interfaces/web-api.md) lists the routes and the failure outcomes, and [Web server](/docs/backend/interfaces/web-server.md) describes the application and its launcher.

## The command line

The feature read scripts answer the same package commands as the HTTP routes and print one JSON report each. The administrative command runs the operator menu and the machine commands that enroll a dataset, prepare the worker, run the stages, and report coverage. The example data loader fills the invented dataset, and a shell script starts the web server. [Command line](/docs/backend/interfaces/command-line.md) describes the scripts and their inputs, and [Command adapters](/docs/backend/interfaces/command-adapters.md) describes the delegation.

## Command ownership and the browser boundary

Every surface accepts one input shape and calls one owner once, so a rule lives in a package command. Nine of the ten HTTP reads answer a command that also has a script adapter. The user state belongs to the browser and reaches the server only as the inputs of one request. [System boundaries](/docs/architecture/boundaries.md) and [Configuration](/docs/backend/configuration.md) describe the settings each surface reads.
