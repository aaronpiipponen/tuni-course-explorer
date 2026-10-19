# Interfaces

The interfaces chapter covers the HTTP read surface, the command line, the administration backend, and both launchers.

## The HTTP read surface

The web server answers 10 fixed dataset read commands plus one feature read under `/api/` and serves the browser application, whose `/docs` address opens the documentation wiki. Each dataset command answers a POST request with a closed JSON body, delegates once to one package command, and returns its report, and the feature read reports the site's two serving switches. The browser sends its state as request inputs, and no route writes data, starts a stage, or reaches the worker. [Web API](/docs/backend/interfaces/web-api.md) lists the routes and the failure outcomes, and [Web server](/docs/backend/interfaces/web-server.md) describes the application and its launcher.

## The command line

The feature read scripts call package commands and print one JSON report each. The administration command runs the operator menu and the machine commands that enroll a dataset, prepare the worker, run the stages, and report coverage. The example data loader fills the invented dataset, and shell scripts start the web server and the administration backend. [Command line](/docs/backend/interfaces/command-line.md) describes the scripts and their inputs, and [Command adapters](/docs/backend/interfaces/command-adapters.md) describes the delegation.

## Command ownership and the browser boundary

A dataset read surface accepts one input shape and calls one owner once, so a rule lives in a package command. Nine of the 10 dataset HTTP reads answer a command that also has a script adapter, and the feature read runs no command. The administration rebuild runs one build and then queues one restart. The user state belongs to the browser and reaches the server only as the inputs of one request. [System boundaries](/docs/architecture/boundaries.md) and [Configuration](/docs/backend/configuration.md) describe the settings each surface reads.

## The administration backend

The administration backend is a third surface with its own package, its own configuration, its own process and its own React application build. It serves the three authentication routes, admits a request before any handler runs, and runs the fixed administration commands over the services the operator menu already reaches.

Its authentication, its sessions, its administration lock and its command log belong to it alone, and the course-exploration web package holds no administration route, file or import. A read-only request for the built console shell or a built asset needs no session, and `GET /auth/session` reuses the session of its cookie or creates an anonymous one within a [server-wide creation limit](/docs/operations/admin-console/access-and-records.md#the-anonymous-session-creation-limit), which answers `429` while the limit is spent. `POST /auth/login` needs a live session of any kind, whose CSRF token the request carries. Every other address and every action needs an authenticated live session.

[Administration backend](/docs/backend/interfaces/admin-backend.md) describes the routes, the admission order, the session and lock state, and the fixed runner. [Administration console code](/docs/frontend/admin-console.md) describes the separate console build.
