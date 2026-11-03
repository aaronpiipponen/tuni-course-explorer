# Admission policy arithmetic

Admission control prices each heavy read and turns one load position into the light rate, the light concurrency, the heavy budget, the queue cap and the heavy slot count.

## The cost curves

`recommendation_cost` and `next_courses_cost` in `src/course_explorer_web/admission/classify.py` evaluate one two-segment line per scope: `origin_cost + slope * (basis - origin_basis)` up to the knee basis, then `tail_cost + tail_slope * (basis - knee_basis)`. `basis` is the basis size of the read. The two scopes of one curve share that curve's origin basis, `ADMISSION_RECOMMENDATION_ORIGIN_BASIS` or `ADMISSION_NEXT_COURSES_ORIGIN_BASIS`, and each scope has its own knee basis, origin cost, slope, tail cost and tail slope. The four knee keys are `ADMISSION_RECOMMENDATION_ACTIVE_KNEE_BASIS`, `ADMISSION_RECOMMENDATION_INACTIVE_KNEE_BASIS`, `ADMISSION_NEXT_COURSES_ACTIVE_KNEE_BASIS` and `ADMISSION_NEXT_COURSES_INACTIVE_KNEE_BASIS`.

`basis_size` returns the number of distinct nonblank identifiers of the chosen basis list, and `active_only_from_body` selects the scope.

A search that includes inactive courses carries the fixed `ADMISSION_SEARCH_INACTIVE_COST_CORE_SECONDS` charge instead of a curve. A prerequisite graph carries the elapsed seconds the front router measured for the same request field, which `GraphCostCache` in `src/course_explorer_web/admission/graph_cost.py` retains per serving dataset identity.

The example value of each curve key is the one [Subsystem keys](/docs/backend/configuration.md#subsystem-keys) lists, and the measured costs behind the curves are recorded in [Serving request cost and admission curves](/docs/experiments/runtime-storage-and-serving/serving-request-cost-and-admission.md).

## The policy arithmetic

`src/course_explorer_web/admission/policy.py` owns the arithmetic, and `AdmissionState` in `src/course_explorer_web/admission/state.py` holds the counters, activity timestamps and tickets in process memory. `p` is the load position of the current regime.

`regime` maps `p` to headroom at 0, saturated at 1 and middle between. `light_load_factor` is `1 - (1 - ADMISSION_LIGHT_LOAD_FLOOR) * p`, `light_rate_per_millisecond` divides the scaled rate by 60000, and `light_concurrency` is `max(1, int(ADMISSION_LIGHT_CONCURRENCY * factor))`. `heavy_budget` interpolates the two budget values by `p`, `heavy_queue_limit` picks the regime's cap, and `heavy_slots` is `max(1, min(ceil(ADMISSION_HEAVY_SLOTS - (ADMISSION_HEAVY_SLOTS - 1) * p), WEB_WORKERS - 1))`. `light_balance` refills a light bucket at its rate and caps it at the burst, and `heavy_balance` refills a heavy bucket at `budget / (ADMISSION_WINDOW_SECONDS * 1000)` per millisecond and caps it at the budget.

`sample` adds one host busy interval, drops intervals older than the window, divides the window's core-seconds by the window length and the host's core count, refreshes the light and heavy activity and stores the score and the load position. `_apply_score` computes the score's position between the headroom and saturation lines and latches saturation at the saturation line until the score falls below the release line. `_refresh_activity` counts a light admission and a heavy start inside the window and adds a running heavy read whose start has left it. `_identity` starts a cookie's light bucket at `ADMISSION_LIGHT_BURST` and its heavy bucket at the larger of the two budget values.

`admit_light` raises `AdmissionRefused` when the cookie's concurrency is used or its balance is below one token. `admit_heavy` charges `min(cost, budget)`, refunds the charge when `_acquire_slot` refuses at the queue cap, and registers the start after it takes a slot. `_acquire_slot` waits on one `asyncio.Condition` in first-in-first-out order, holds a queued ticket in place when the cap drops, and admits the head of the queue when a slot is free. `release_heavy` drops the ticket and wakes every waiter, and `release_light` drops the ticket and the identity once it is stale and idle. `expire` drops every identity that is idle for `ADMISSION_IDENTITY_TTL_SECONDS` and holds no ticket. `reset_meter` clears the CPU baseline, the stored CPU intervals, the score, the saturation latch, the derived activity counts and the load position, while it leaves every admission timestamp and cookie bucket as it is, so the next good sample counts the activity already admitted.

## Support modules and tests

`src/course_explorer_web/admission/identity.py` holds `COOKIE_NAME`, `identify`, `set_cookie_value` and `cookie_send`. `busy_cpu_seconds` in `src/course_explorer_web/admission/host_cpu.py` reads the first eight numeric fields of `/proc/stat`, subtracts idle and iowait, and converts the ticks with `SC_CLK_TCK`, and `core_count` raises when the host reports none. The front router's `_too_much_traffic` builds the one refusal as a `JSONResponse` with `{"detail": "Too much traffic"}`, status 429 and `Retry-After`.

`tests/web/test_admission.py` proves every route's admission class, the fixed cost of a search that includes inactive courses and the recorded cost of a measured heavy graph, one pinned point of each cost curve, the basis size and scope choice, and one middle-regime value of each scaled limit. [Front router](/docs/backend/interfaces/front-router.md#tests) lists it with the router's own tests.
