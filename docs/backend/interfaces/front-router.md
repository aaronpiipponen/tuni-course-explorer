# Front router

The front router listens on the configured loopback port, admits each request, forwards it to one worker process and writes its request record.

## The process tree

The supervisor creates the public listener and one ephemeral loopback listener per worker process, forks the workers and starts the front router on the public listener. [Web supervisor](/docs/backend/interfaces/web-supervisor.md) describes that startup, the readiness barrier and the replacement of an exited child. This page describes the boundaries the front router applies to each request it receives.

`RouterApplication` in `src/course_explorer_web/router/app.py` is a pure ASGI application over a fixed set of loopback worker addresses. It recognises only the two fixed feedback paths itself. Every other HTTP request is read under the body bound, admitted, and forwarded once to one worker process through one `httpx` client. The router has one forwarding path with no retry and no fallback, so a worker connection failure raises and answers a server error. [Web routes](/docs/backend/interfaces/web-routes.md) describes the application the worker processes serve, and [Serving state](/docs/backend/interfaces/serving-state.md) describes what a request reads.

The router resolves the serving dataset once in its `startup` and holds it for the life of the process, and it builds its admission state and feedback allowance there. `create_router` builds the one router over the given worker addresses.

## The request usage record

`UsageMiddleware` in `src/course_explorer_web/router/usage.py` is a pure ASGI middleware that the front router wraps around its forwarding handler. A non-HTTP scope passes through on its own path. For an HTTP scope it captures the current UTC hour, rounded down by the shared owner `course_explorer.usage.rounded_usage_hour`, and the monotonic start time at entry, wraps `send` so it reads the status of the `http.response.start` message while passing every message through to the client, and appends exactly one record in a `finally` block after the forwarding handler returns or raises.

With `ADMISSION_ENABLED` true, the front router also holds its admission counters, activity timestamps and [graph cost cache](/docs/reference/glossary.md#administration) in its process memory, as [Admission control](/docs/backend/interfaces/admission-control.md) describes. Only the router reads that state, nothing persists it or shares it between processes, and no usage report or administration surface reads it. An admitted feedback submission writes its answers and attachment metadata to the feedback application store and its image files beneath the configured attachment root, through its owning service, and that store is neither authoritative catalogue data nor browser state.

The append adds one line to the checkout's `data/usage/requests`, which is neither authoritative catalogue data nor user data, and no aggregation or pruning runs inside a request. Each line is one compact JSON object with exactly four fields:

| Field | Meaning |
|---|---|
| `hour` | The request-start UTC hour rounded down, as an aware ISO timestamp |
| `route` | The fixed route label described below |
| `status` | The status the response started with, or 500 when the request failed before a response started |
| `duration_seconds` | Elapsed monotonic serving seconds until the inner application returned or raised, including ordinary response sends |

Every HTTP outcome of every address is recorded once: a successful feature, shell or asset read, a disabled-feature 403, a validation 422, an admission 429, a method 405, a 404 for an unknown path, and an unhandled failure that produces the server's 500. The record holds no method, identity, payload, exception, request URL, query or header.

The route label comes from the request path rather than from the worker process's routing metadata. Exactly `/`, `/docs` and `/feedback` report themselves, a path equal to one of the nine catalogue API paths or the two fixed feedback API paths reports that path, and a path equal to `/assets` or beginning `/assets/` reports `/assets`. Any other path reports `unmatched`. A requested asset name, an unknown path and a query string are therefore never retained.

The append runs in a thread pool thread, so a usage report holding the file's lock cannot block the event loop. An append failure propagates, including when it happens after the response was transmitted. The middleware reads no settings and resolves the usage file when a request is handled, so construction and import create no file.

## Feedback intake boundary

`src/course_explorer_web/feedback_intake.py` owns the two fixed feedback paths and the router's feedback-specific state. `require_feedback_site` requires exactly one Host equal to the configured origin's netloc and exactly one Origin equal to the configured origin string. A missing, repeated, `null` or foreign value raises `RequestRefused(403)`. `FeedbackIntake` holds one deque of `(monotonic timestamp, identity)` entries, prunes entries at or older than `now - 3600` seconds, refuses 429 when either the browser or site count reaches its configured ceiling, and appends once when both admit. A refusal carries the greater ceiling of the two waits, and the check and the append run in one turn.

`src/course_explorer_web/router/feedback.py` owns the submission gate that runs before a feedback body reaches a worker. `read_submission` calls `require_feedback_site`, then `require_content_type`, which refuses anything but one `application/json` media type with 415, then `require_declared_length`, which refuses a malformed or repeated declared length with 400 and a length over `FEEDBACK_MAX_REQUEST_BYTES` with 413. Those three checks answer before any identity exists. It then establishes the cookie identity, charges the allowance through `FeedbackIntake.admit`, reads the body under the same byte bound, and returns the cookie, the body and the cookie-wrapped response channel of an admitted submission. `feedback_refusal` builds every refusal with the fixed body `{"detail": "Feedback request refused"}`, `Cache-Control: no-store` and, for a 429, its `Retry-After`.

`RequestRefused` and `read_body` live in `src/course_explorer_web/request_body.py`. The bounded reader raises 413 on the first chunk that crosses the bound, before appending it or reading another, and raises 400 on a disconnect inside a bounded read. The router calls `read_body` with `WEB_REQUEST_BODY_MAX_BYTES` for every other request and answers an over-bound body or a disconnect with `{"detail": "Request body refused"}` and that status. [Web routes](/docs/backend/interfaces/web-routes.md#the-input-bounds) states those bounds.

`RouterApplication.startup` resolves `FeedbackIntakeSettings` once and builds the allowance independently of `ADMISSION_ENABLED`. `_handle_http` recognises only `GET /api/feedback/definition` and `POST /api/feedback`. Both use `identify` and `cookie_send` with `ADMISSION_COOKIE_MAX_AGE_SECONDS`, so the feedback paths share the catalogue reads' anonymous cookie. The feedback definition read takes no allowance and forwards with an ordinary non-heavy `_Admission`. The submission is gated by `read_submission` and then forwarded through the one `_forward`. Other routes call `read_body` with the body bound and then `_admit`.

Only the front router admits a feedback write, so a worker process applies no site, size or hourly policy, and its loopback listener is not exposed. A refusal sets `Cache-Control: no-store`, and a 429 adds `Retry-After`. The allowance is transient process memory: a replacement router starts empty, and no counter or identity reaches disk.

## Admission decisions

`RouterApplication` calls `classify` for each catalogue POST, takes a ticket from `AdmissionState`, forwards the request and releases the ticket when the response body ends. [Admission control](/docs/backend/interfaces/admission-control.md) owns the classes, the cost curves, the light and heavy limits, the load regimes, the cookie, the queue caps and the refusal answers.

`src/course_explorer_web/admission/classify.py` owns the class and the cost of one request. `classify` returns a `Classification` of an `AdmissionClass` and a cost, `basis_size` counts the distinct nonblank identifier strings of the chosen basis list, and `recommendation_cost` and `next_courses_cost` evaluate the configured curve. The graph class reads the cost the router measured for the same request field.

`src/course_explorer_web/admission/graph_cost.py` owns the graph cost cache. `graph_cost_field` builds the field `<target>|<recommended>|<inferred>|<active>` from the request's `target_code` string as sent, so an official code and the canonical identity of the same course make two fields. `GraphCostCache` holds one cost per field under the serving dataset identity its router resolved, and a record under another identity clears the map.

`RouterApplication._forward` measures a graph build from immediately before `client.send` to the end of the response body, so the elapsed time includes the worker process's compression. `POST /api/prerequisites` in `src/course_explorer_web/routes/prerequisites.py` sets `MEASURE_GRAPH_HEADER` on a response only when `request.target_code` is in `_root_identifiers(report)`, which returns `report.solver.root_group_id` plus the exact `code` of every `solver.courses` entry whose `group_id` is that root. `_forward` stores a marked response in the [graph cost cache](/docs/reference/glossary.md#administration) under the serving dataset identity and the request field, and `_response_headers` strips the marker from the client's headers.

The marker gate covers the root's canonical identity and the exact official codes of the root course alone. A request that sends another spelling, including a lowercase official code, has its graph resolved and answered but records no cost, so a read of that field is light. Each spelling keys its own field, so a canonical identity and an official code hold one recorded cost each. The browser stores the course's `group_id` as `rootCourseId` (`web/src/features/prerequisites/RootBox.tsx` and `web/src/shared/course/CourseMenu.tsx`) and sends it as `target_code` (`web/src/features/prerequisites/usePrerequisiteInputs.ts`), so its builds satisfy the gate. `GraphCostCache.get` returns `None` for an identity other than the stored one, and `record` clears the map when the identity changes, so the cache holds one cost per target string and flag combination of one dataset.

`WorkerPool.choose` in `src/course_explorer_web/router/workers.py` excludes a worker process that carries a heavy request from a heavy placement and picks the lowest in-flight count with the lowest index on a tie, and `occupy` holds the count for the duration of the forward. The router's `httpx.AsyncClient` sets `max_keepalive_connections=0`, so one forwarded request opens a fresh loopback connection, and a connection failure raises instead of retrying or rerouting.

To add a class, change `AdmissionClass` and `classify`. To change a limit or its arithmetic, change the key in `config/admission.toml` and its field on `AdmissionSettings`, as [Admission policy arithmetic](/docs/backend/interfaces/admission-policy.md#the-policy-arithmetic) states.

## Tests

| Test file | Covers |
|---|---|
| `tests/web/test_usage.py` | One recorded line per request through the router and one real worker process across a catalogue read, a validation failure, a disabled-feature refusal, an unknown path, a method mismatch, the shells, a served asset, a missing asset, an unhandled failure, a limited refusal, the feedback definition read and a site-refused feedback submission, with the route label, the hour rounding, the field shape and no sentinel from the request. |
| `tests/feedback/test_feedback_http.py` | The exact-site refusal of missing, foreign, null, duplicate and forwarded Host or Origin values, the media-type and declared-length refusals, the declared and streamed body bound before forwarding, and the browser and site hourly allowances with admission on and off. |
| `tests/web/test_admission.py` | The class of every catalogue route, one pinned point of each cost curve, the basis and scope choice, one middle-regime value of each scaled limit with the saturation light concurrency and the heavy slot cap, the score's interpolation, saturation entry and release over controlled host samples and light admissions, the heavy activity window over one ticket lifecycle, the dataset-scoped graph cost cache in process memory, the heavy queue's wait at saturation and its refusal at the cap, and one router run of a free read, two limited cookies, a malformed cookie, a heavy budget refusal, admission off without a cookie and the activity its admitted reads leave. |
| `tests/web/test_router.py` | Three concurrent heavy requests on three distinct worker processes, a held worker process skipped by the next light request with the lowest index on a tie, an unreadable host counter that logs one error, clears the CPU baseline, the score and the latch, counts the admitted activity on the next good sample and stores no pre-outage CPU, and an oversized body that answers 413 before any worker process is called. |
