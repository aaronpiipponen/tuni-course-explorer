# Feedback publication states

Every feedback submission carries one publication state that records whether and how its sender attempt created a GitHub issue.

## The two starting states

A submission that chooses publication starts in **GitHub publication pending**, and one that chooses no publication starts in **Private**. No state returns to pending by itself.

The sender selects only the oldest opted-in pending submission. It commits that row as **Publication outcome unconfirmed** before the external call, so a process that stops after the claim leaves the row in that state. It then makes one attempt to create one GitHub issue.

![Two publication choices at submission lead to Private or GitHub publication pending. The sender claims the oldest pending submission as Publication outcome unconfirmed before one issue-create attempt that ends as Issue created, Issue created with incomplete attachments, or Publication failed before issue creation, and an unconfirmed outcome leaves the row unconfirmed. Operator deletion removes a submission from any state.](/docs/diagrams/feedback-publication-states.svg)

The claim comes before the call, so the stored state always admits the worst case: a row claimed for an attempt may have created an issue even when the process never saw the result.

## The outcomes of one attempt

One attempt ends in one of four ways: the issue is created, the issue is created with an incomplete image upload, no issue is created because a local input or the GitHub CLI failed, or the claimed attempt leaves an unconfirmed outcome.

The stored state, its recorded link and its recorded failure for each outcome are stated in [Feedback publication](/docs/backend/feedback-publication.md#recorded-outcomes). The tag and the fixed description an operator reads for each one are stated in the [Feedback tab](/docs/operations/admin-console/feedback.md#the-entry).

A claimed row receives no second attempt. The sender does not retry it, search GitHub for a matching issue or create a second issue. An operator inspects the destination repository after an unconfirmed outcome.

Deletion applies to a submission in any state. A deletion either wins before a publication attempt or waits for an attempt already under way, and a sender schedules no work because a record was deleted.

## Where the attempt runs

The sender runs from its own service and timer, one activation after boot and one after each completed activation. [Feedback publication](/docs/backend/feedback-publication.md) states the issue mapping, the command boundary and the recorded failure values, and the [Feedback tab](/docs/operations/admin-console/feedback.md) states the labels an operator reads.
