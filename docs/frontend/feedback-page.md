# Feedback page

The feedback page renders the configured feedback definition at the feedback route beside the app and returns to the app without becoming a tab.

## The page and the app

The app serves three page paths: the app at `/`, the documentation at `/docs`, and the feedback page at `/feedback`. **Feedback** in the top bar and in the phone **More** sheet opens the feedback page. Each page keeps one history entry, so **Return to app** and the browser's back action restore the app and the tab that was open.

A direct reload of `/feedback` reads the form again. The page uses the language of the current profile and changes nothing in it. It sets the document title to its localized heading and restores the previous title when it leaves. The page scrolls in its own full-height pane rather than in the document or the course carousel. The form lives in the page's own state, so leaving the page drops the answers that were not sent.

## The feedback definition and its fields

The page reads `GET /api/feedback/definition` once when it opens. The report carries the feedback definition, the destination repository, the visibility `public` or `private`, and the largest accepted request body in bytes. The feedback definition is the file `config/feedback-form.json`, copied at setup from the tracked `examples/config/feedback-form.json`: an ordered list of fields, the placeholder of an unanswered select, and the field mapping of the GitHub issue.

Each field has one kind and one bilingual label. A text field is one row, a textarea expands and scrolls, and a select starts at the configured placeholder, which is not one of its opened choices. A select answer is saved as the configured option value.

The feedback definition also decides what a required field holds. A required text or select field blocks submission until its answer is not blank, and a required image field until it holds one image. A text or textarea answer above its configured `maxLength` is refused with its own error.

## Images and their limits

An image field declares its accepted MIME types, its file count and its byte size per file. The example accepts `image/png` and `image/jpeg`, up to three files of 5242880 bytes each. Choosing or dropping images appends them to that field's list. A selection that would exceed the count or the size, or that holds another type, is refused whole, so the earlier list stays and the field shows its own localized error.

Each chosen image is one row that leaves the list through its own **Remove** control. Added and removed rows animate their height, and the page grows or shrinks with them so the submit control stays inside the form.

The whole submission body has one bound, `FEEDBACK_MAX_REQUEST_BYTES` in `config/feedback.toml`, set to 25165824 bytes in the example. A body above it is refused before the request is sent, with the message that asks to remove images or shorten the answers.

## The publication default

A select option may declare `publicIssueByDefault`. The page derives the toggle from the conjunction of every selected option that declares the value. An absent property contributes nothing, an unanswered select contributes nothing, and an empty conjunction is true.

The toggle starts at that derived value. A change to the toggle fixes the explicit choice for the rest of the form, so another answer change, a refused submission or a cancelled confirmation leaves it as the sender set it. The choice the submission carries is always explicit.

## The confirmation

Every submission opens a confirmation. For a publication it states the destination repository and its visibility, the mapped fields and the image field the issue would include, and that the other answers stay private. For a private save it states that no issue is created and only the feedback application store receives the submission.

The confirmation carries **Cancel** and **Submit and create issue** for a publication, or **Submit feedback** for a private save. Cancelling, Escape and a press outside the dialog send nothing. A confirmed submission sends the body once and replaces the form with a short submitting state, so the form does not return.

## Acknowledgment states

An accepted submission answers with one state, `private` or `pending`. A `private` submission reads **Saved as private feedback**, and a `pending` one reads **GitHub publication pending**. The saved page shows no issue link in either state, and the form is gone.

A saved pending publication carries no issue link, because the issue does not exist when the submission is saved. [Feedback publication](/docs/backend/feedback-publication.md) states the sender's single attempt and the states it records.

## Refused submissions and read failures

A refused submission keeps the form and states its cause. A 429 response reports that too many submissions arrived instead of the generic failure. A submission that fails in another way shows the generic failure and keeps the answers.

A feedback definition read that fails shows the page's own failure with the instruction to reload. The failure names no stored identity.

## Motion

The outgoing view fades out, the block animates to the incoming view's height on the shared curve, and the incoming view fades and rises as one, title included. A scrolled page first eases to the top. With the operating system's reduced-motion preference every final state applies at once.

The modules behind the page, the field control and the publication derivation are described in [Feedback page code](/docs/frontend/feedback-page-code.md).
