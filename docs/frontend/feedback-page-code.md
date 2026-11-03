# Feedback page code

The feedback page renders one configured form from a same-origin report, keeps its answers in the page and sends one submission with an explicit publication choice.

## The page and its views

`web/src/features/feedback/FeedbackPage.tsx` exports `FeedbackPage({ returnToApp })`. It reads the language from the open profile and stores nothing in the profile. The component holds the form report, a load-failure flag, the answers, the chosen files, the manual publication choice, the field errors, a form error, the confirmation, a submitting flag and the acknowledgment.

One effect reads the form through `readFeedbackForm(signal)` with an `AbortController` that aborts when the page leaves. A failed read sets the failure flag, and the page then shows the reload instruction in place of the form.

The rendered view is one value: `saved` while an acknowledgment is held, `submitting` while the request runs, and `form` otherwise. The page wraps the three views in `AnimatedHeight` and `AnimatePresence` with `mode="wait"`, keys the `motion.main` by that view, and runs the exchange over 0.26 seconds with the shared easing. A layout effect scrolls the page pane to the top on each view change, at once under reduced motion.

`validate(definition)` fills one error per field: a required text or select field whose answer is blank, a required attachment field with no file, and a text or textarea answer longer than `maxLength`. A select answer is exempt from the length check.

`buildRequest(definition, publicIssue)` collects the answers and reads each chosen file as standard base64 without the data URL prefix. The body holds `answers`, the attachment carriers with `field_id`, `filename` and `content_base64`, and `public_issue`. `startSubmit` compares the encoded body against `report.max_request_bytes` before the request, sets the size message when it is larger, and otherwise calls `submitFeedback`. One `inFlight` ref keeps a second submission from starting, a 429 answer shows the too-many message, and any other failure keeps the answers and shows the generic message.

`designatedLabels(definition, language)` reads the configured `githubIssue` mapping, removes repeated field ids, and returns the joined labels of the type field, the title field and the body fields plus the label of the attachment field. The toggle label, the explanation and the confirmation copy read those labels.

## One field control

`web/src/features/feedback/FeedbackField.tsx` exports `FeedbackField` and the `ChosenFile` type. The component renders exactly one of four controls from the field kind and takes the field, the language, the select placeholder, the answer, the files, the three callbacks, the error and a disabled flag.

- A text field is one `input` and a textarea is one scrolling `textarea`. Each answer is `null` when the control is empty, and a filled answer reaches `onAnswer`.
- A select is one Radix dropdown with `modal={false}` over a radio group. The trigger shows the configured placeholder while the answer is `null` and the chosen option's label otherwise.
- An attachment field is a `role="group"` block with a drop label, a hidden file input that accepts the declared MIME types, and one animating row per chosen file. A drop appends the files it carries, and each row's **Remove** control calls `onRemoveFile` with the row's identity.

Every control carries `aria-invalid` and `aria-describedby` while its field error is set, and the error paragraph has `role="alert"`. The file rows animate their height over 0.18 seconds and take their final state at once under reduced motion.

## The derived publication choice

`derivedPublicationChoice(definition, answers)` in `web/src/features/feedback/publication.ts` starts at `true` and reads every select field whose answer names one of its options. An option with a boolean `publicIssueByDefault` joins the conjunction, an absent property contributes nothing, and an unanswered select contributes nothing, so an empty conjunction is true.

`FeedbackPage` renders `manualChoice ?? derivedPublicationChoice(definition, answers)`. A change to the toggle writes `manualChoice`, and only a remount clears it, so a following answer change, a refused submission or a cancelled confirmation leaves the sender's choice as it stands. The request always carries the resulting boolean as `public_issue`.

## The typed client

`web/src/api/feedback.ts` holds the report types and the two same-origin calls. `FeedbackFormReport` carries the `definition`, the `repository`, the `visibility` of `public` or `private`, and `max_request_bytes`. `FeedbackDefinition` holds the ordered `fields`, the `selectPlaceholder` and the `githubIssue` mapping. `FeedbackFieldDefinition` is the union of a text or textarea field with `maxLength`, a select field with its `options`, and an attachment field with `acceptedMimeTypes`, `maxFiles` and `maxBytesPerFile`.

`readFeedbackForm(signal)` reads `GET /api/feedback/definition`, and `submitFeedback(body, signal)` posts `FeedbackSubmissionRequest` to `POST /api/feedback` and returns `FeedbackAcknowledgment`, whose `publication_state` is `private` or `pending`.

## Layout and motion

`web/src/features/feedback/feedback.css` owns the page. `.feedback-page` is the full-height scrolling pane, `.feedback-shell` the centred column, and `.feedback-form`, `.feedback-field`, `.feedback-drop`, `.feedback-files` and `.feedback-publication` the form surfaces. The page takes the shared thin accent scrollbar, and the select menu and the textarea reuse it.

## Where a change belongs

- A field kind belongs in `FeedbackFieldDefinition` in `web/src/api/feedback.ts`, in the `FeedbackField` branch that renders it, and in `validate` and `buildRequest` in `FeedbackPage.tsx`.
- A change to how a default becomes the toggle belongs in `derivedPublicationChoice` in `web/src/features/feedback/publication.ts`, not in the page.
- The form content, the select options, the image limits and the issue mapping belong in `config/feedback-form.json`, which the page reads through the report.
- The whole submission bound is `FEEDBACK_MAX_REQUEST_BYTES` in `config/feedback.toml`, and the page reads it from `max_request_bytes` rather than from the file.
- A change to the confirmation or the acknowledgment copy belongs in `FeedbackPage.tsx` beside the view it belongs to.

## Tests

| File | Covers |
|---|---|
| `web/src/features/feedback/FeedbackPage.test.ts` | The derived toggle following a selected option that declares a false default, and an explicit toggle change that holds through a following selection whose own default is true or false |
