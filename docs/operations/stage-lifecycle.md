# Stage lifecycle

Every stage exposes the same five actions, and this page describes the durable states, boundaries, and failures behind them.

## The five actions

One algorithm serves all four stages, so ingestion, embedding, translation, and inference accept the same five actions with the same meaning.

| Action | What it does |
|---|---|
| start | Continues a session the stage retained, or begins a fresh one, then launches one detached worker. |
| pause | Publishes a pause request, waits for the owned worker to exit, and unloads the resources the session started. |
| resume | Re-arms the session the stage retained and launches its worker again. |
| status | Reads the recorded state and the owned process and reports the lifecycle state. It writes nothing and starts no service. |
| stop | Publishes a stop request, waits for the owned worker to exit, finalizes the completed work through its owning writer, releases the resources, and returns the stage to idle. |

The commands behind the actions are listed in the [Operator menu](/docs/operations/operator-menu.md#the-stage-tools).

## The durable states

One record holds the current state of a stage, and one immutable receipt per session holds the identity and the options of that session. The receipt is written when the session is created and never changes.

| State | Meaning |
|---|---|
| idle | The stage holds a session and its progress, and its status carries no session identity. |
| starting | A start reserved the stage and recorded the invoking command as the owner. |
| running | The detached worker reports that it is working. |
| paused | A pause took effect at a durable boundary, and the session is retained for a resume. |
| stopped | A stop took effect at a durable boundary, and the stop action then finalizes the session. |
| completed | The work of the session finished. |
| failed | The run ended with an error, and the stage holds the content-free failure record. |

A status read adds one projected state, interrupted, in place of starting or running when the recorded owned process is not alive. No command writes it, and the projection writes nothing. A start resumes the retained session when its work identity matches this device and refuses it when the identity differs, and the retained work is left in place.

![One stage moves from idle through starting to running, and the run then ends at a durable boundary as completed, failed, paused, or stopped. A stop finalizes any of those states to idle, and a status read projects the interrupted state while a starting or running stage has no live owned process.](/docs/diagrams/stage-lifecycle.svg)

## Starting a session

A start on a stage with no state creates a fresh session. The stage chooses its options, records a work identity from those options and its validated configuration, records the revision of the running checkout, and publishes starting. An ingestion start adopts the one partial capture the stage retained, and it fails when more than one candidate exists.

A start on a stage with a state continues that session when the retained identity matches this device, and it re-reads the retained capture manifest before it continues. Which of the two happens follows from the retained state.

| The retained state | What a start does |
|---|---|
| A live owned worker | Reports the current status and launches nothing |
| completed | Reports the current status |
| idle after the work finished | Creates a fresh session |
| idle on a stage that finalizes its work at a stop | Creates a fresh session |
| Anything else that matches this device | Re-arms the retained session |
| Anything else that does not match this device | Refuses, and leaves the retained state in place |

A resume follows the same compatibility rule as a start and is refused with a safe error when the stage retained no session.

## Pause and stop

A pause publishes a pause request and waits for the owned worker to exit, and the run then ends at its next durable boundary. The stage runs its release hook, which for a remote stage hands the unloaded pause to the worker session and releases the owned worker resources, and the command then releases the services the session started. The session, its receipt, its progress, and its stored work are all retained. A pause never overwrites a pending stop.

A stop publishes a stop request, waits for the owned worker to exit, and then finalizes the session. Finalization writes the completed work through the owning writer, releases the services the session started, deletes the local runner logs of the session, and publishes idle. The stop records whether the work had finished, so an idle state after a completed run holds the work as complete and an idle state after a partial run holds pending work. Either way, the stage holds the session receipt and the progress it recorded.

Ownership decides what a pause or a stop releases. The state records only the resources this session created or started, so the release never touches a service the session did not start. A local stage requests the database service, and the embedding stage also requests the embedding service, so only the embedding service is a session-owned temporary service that the stage stops and deletes.

> [!WARNING]
> An ingestion stop that reaches idle deletes every raw capture run under `RAW_DATA_ROOT` in `config/curriculum.toml` except the one the stage retains for an incomplete capture. After a completed capture, no raw capture run is retained. A failed stop deletes nothing.

> [!IMPORTANT]
> A stop with partial coverage is a valid end of a run. The stage returns to idle with the pending rows marked, and the next start takes that work up.

A stop that fails at one of its steps records a content-free stop failure and fails loudly. The record names the step that was executing, the exception class, and an available integer status, and the owned resources and the retained evidence are left in place. A following stop retries from the real state and clears the record when it completes.

## The boundaries of a run

Pause and stop act only at the durable boundaries of a stage, so a run ends on a committed unit of work.

| Stage | Where a pause or a stop takes effect |
|---|---|
| Ingestion | After a committed batch of `CAPTURE_CHECKPOINT_RESPONSE_COUNT` responses and before the next source request, between two stored responses during verification, and between a completed capture and normalization |
| Embedding | After the vectors of one batch are stored |
| Translation | Between two translated cells, after the retained output was republished |
| Inference | After a completed unit of work in the processing cycle |

Normalization is one transaction. It reads the completed capture, validates it, and writes the whole batch, and no control request interrupts it. [Ingestion](/docs/backend/catalogue/ingestion.md#pause-stop-and-the-normalization-transaction) describes that transaction.

## Active time and coverage

A stage measures active time only while it is running and its recorded start time is known, so the idle time between two runs does not inflate the measured rate or the projected remaining time.

Coverage counts the stored rows of the selected dataset, so it says what has been written and not what the run is doing. The two facts are independent. A stage returns to idle after a completed run with complete coverage, and it also returns to idle after a partial run with pending rows. The [Full-catalogue inference run](/docs/experiments/inference/full-catalogue-inference-run.md) report records a run that stopped part-way and resumed to a complete cycle. The coverage reports are described in the [Operator menu](/docs/operations/operator-menu.md#coverage-and-summaries).

## The worker at a stop

A remote stage finalizes on the worker before the dataset changes. The worker session imports the output the stage retained into the worker's own copy of the dataset, and inference publishes the accepted proposals and equivalence groups there. The finished copy then returns as one whole, is checked against the snapshot taken when the session started, and is restored and selected as the selected dataset. The returned worker database is dropped once the server receipt exists, and the dataset rotation retains the selected dataset and the one before it.

A stop of a remote stage therefore has an order: the run ends, the worker session is stopped and finalized, the copy returns, and only then do the owned resources and the local scratch go. [Worker sessions](/docs/operations/worker-sessions.md) describes the session and its return, [Datasets](/docs/operations/datasets.md) describes the selection and the rotation, and [Translation](/docs/backend/text-and-vectors/translation.md#the-output-it-publishes) describes the import that writes the retained output.

## The periodic reboot

The worker restarts after a configured amount of model run time, set by `WORKER_GPU_REBOOT_INTERVAL_MINUTES` in `config/worker.toml`. The interval is a worker-side setting, and the example sets 120 minutes.

The clock accumulates only while a local model is loaded on the worker, and it samples at a completed unit of work and at every recorded failed generation attempt, so a run with repeated failed attempts reaches the restart as well. The worker then reports a paused status with the restart due, the administration command releases its owned worker resources, restarts the worker once, and resumes the same session with its pending work. A pause that arrives first issues no restart. [Inference scheduling and disposition](/docs/backend/inference/inference-scheduling.md#the-periodic-reboot) describes the timing rule for the inference stage.

## Failures and recovery

A failed run publishes the failed state with one content-free record. The record holds the step that was executing, the exception class name, and an available integer status, and nothing else. No message, no input value, and no path from the failure is stored.

| Step | The phase the stage was in |
|---|---|
| session | Reading the retained session receipt |
| intent | Publishing the control request |
| await_exit | Waiting for the owned worker to exit |
| transport | Opening the connection to the worker |
| capture | Taking the input snapshot and creating the worker session |
| bring_up | Preparing the owned resources on the worker |
| launch | Launching the worker run and acknowledging it |
| status | Reading the worker status |
| release | Releasing the owned worker resources |
| reboot | Restarting the worker and proving it came back |
| finalize | Running the finalize hook of the stage |
| worker_finalize | Stopping and finalizing the worker session |
| return | Returning and retaining the worker dataset |
| worker_cleanup | Dropping the returned worker database |
| local_cleanup | Deleting the local scratch of the session |
| services | Releasing the services the session started |
| idle | Publishing the idle state |

A failed local run holds its progress and its ownership. The stop action then finalizes the session to idle with incomplete work, and the next start continues the pending work. A failed remote run holds the ownership record, so a following stop verifies the retained state, returns whatever the worker holds, cleans it, and clears the diagnostics.

> [!NOTE]
> A stage reports its failure in every status read. The failure record and the stop failure record are cleared only by a completed stop, and a pause preserves both.
