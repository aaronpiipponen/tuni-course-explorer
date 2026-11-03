# Feedback publication

The sender makes one feedback publication attempt per activation and records the created issue link or a safe failure.

## The sender operation

`FeedbackService.publish_next` in `src/course_explorer/feedback/service.py` owns the feedback publication attempt. It selects only the oldest opted-in `pending` row, orders the candidates by `created_at` and `id`, locks one row with `FOR UPDATE SKIP LOCKED`, and limits the selection to one record.

`src/course_explorer/feedback/sender.py` composes the sender settings and the feedback application store, then calls `publish_next` once with a publisher bound to the configured destination. `scripts/run_feedback_sender.sh` runs the module, and `examples/deploy/systemd/tuni-course-explorer-feedback-sender.service.in` with its timer schedules one activation after boot and after each completed activation. The timer starts the paired service, and only the timer is enabled.

## The claim and the single attempt

The attempt has three steps.

1. The operation claims the selected row by setting `publication_state` to `uncertain` and commits that state before any external call. A process killed after the claim therefore leaves an `uncertain` row, and the row can never return to `pending` by itself.
2. A second transaction locks the selected row again and holds the lock through one external attempt and the result update. A deletion takes the same row lock, so it either wins before the attempt or waits for an attempt already under way. A deletion that takes the row first leaves nothing to send.
3. The operation renders the issue, calls the supplied publisher once, saves the returned state, link and safe failure, and commits.

A `pending` row is the only row the operation selects. A `private`, `uncertain`, `failed`, `partial` or `published` row is never selected automatically, and the operation never retries an attempted record, searches GitHub for a matching issue, or creates a second issue. An operator inspects the destination repository after an unconfirmed outcome and handles any remote copy by hand.

## The issue mapping

`render_publication` in `src/course_explorer/feedback/publication.py` reads only `githubIssue` of the current feedback definition. The title is `[<type option label.en uppercased>] <mapped title answer>`. The body carries each mapped body field in mapping order under its English label as a Markdown heading. Text answers are preserved as submitted, and a select answer becomes its current English option label. A null optional body answer is omitted.

Only the mapped attachment field contributes files, and each contributed file is a local image. A missing required mapped answer, a select answer with no current option, a missing required attachment and an unreadable designated file all fail before the external call, and the row is recorded as `failed` with `publication_input_invalid`. Role, every other unmapped field, record metadata and another attachment field never enter the title or body, and no local path enters the title or body. The designated attachment files do appear, under their submitted filenames, in the CLI `--attach` arguments that upload them.

## The GitHub CLI boundary

`create_github_issue` invokes `gh issue create --repo <owner>/<repository> --title <title> --body-file -` through an argument list, with the body on standard input and one `--attach <path>` per designated image. Each image is copied into the attempt's owned temporary directory under its submitted filename, with a numeric suffix for a repeated name, so the issue shows readable attachment names. The child receives only the inherited `HOME`, `PATH` and `LANG` names, `GH_TOKEN` from the sender's secret, `GH_PROMPT_DISABLED=1` and an owned empty `GH_CONFIG_DIR`. The command removes the temporary directory after the call, and the command runs under `FEEDBACK_GITHUB_TIMEOUT_SECONDS`.

The command's standard output is interpreted only as one canonical `https://github.com/<owner>/<repository>/issues/<positive integer>` link with surrounding whitespace allowed. Any other host, repository or decorated output is unconfirmed. Standard output and standard error are held in memory, classified and discarded, and the sender never prints the argument list, the body or the environment.

## Recorded outcomes

| State | Meaning | Link | Safe failure |
|---|---|---|---|
| `private` | The submission chose no publication. | None | None |
| `pending` | An opted-in submission awaits its attempt. | None | None |
| `published` | The command exited zero and printed the canonical link. | Created issue | None |
| `partial` | The command exited nonzero and printed the canonical link. | Created issue | `attachment_upload_incomplete` |
| `failed` | The local input was invalid or the command could not start. | None | `publication_input_invalid` or `github_unavailable` |
| `uncertain` | The attempt reached the command and its outcome is unknown. | None | `github_outcome_unconfirmed` |

A timeout, a nonzero exit without a canonical link, a zero exit without a canonical link and an interruption after the command started all leave `uncertain`. A missing executable leaves `failed` with `github_unavailable`. The public submission acknowledgment reports `private` or `pending` and is derived from the committed publication choice, so an anonymous response neither exposes another state nor fails when a sender advances the row.

## Local and remote deletion

`FeedbackService.delete` locks the submission row before it removes the stored attachment metadata and files. The local deletion removes the feedback record and its local images and never deletes a GitHub issue or GitHub-hosted image. The console states that distinction in its deletion confirmation, and a sender schedules no work because a record was deleted.

## Tests

`tests/feedback/test_feedback_publication.py` proves the mapped title, body and both designated images, under their filenames, through the real renderer and CLI adapter, the unmapped field exclusion, the saved partial outcome with no second creation, and the no-retry contract over a timeout, an unconfirmed failure and a precommitted `uncertain` row.

`tests/feedback/test_feedback_service.py` proves the migration from the initial schema, the submission round trip, the opted-out case that is never sent, the named deletion and the schema isolation. The publication test replaces only `subprocess.run` and runs against a disposable `_test` feedback application store and temporary attachment files.
