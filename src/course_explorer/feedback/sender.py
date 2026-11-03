"""Dispatch one bounded feedback publication attempt from the operator's scheduled unit.

One invocation composes the sender destination, credential and timeout, opens the feedback store,
and asks its owning service to publish at most one opted-in pending submission. Success output names
only the selected identity, current state and link. Failure output names a safe exception class or
the missing setting aliases, never a value, answer, path or the credential.
"""

from __future__ import annotations

import sys
from pathlib import Path

from pydantic import ValidationError

from course_explorer.config import load_feedback_sender_settings
from course_explorer.feedback.publication import PublicationResult, create_github_issue
from course_explorer.feedback.service import FeedbackPublicationReport, feedback_context


def dispatch_once() -> FeedbackPublicationReport:
    """Publish at most one pending submission through the configured destination."""
    settings = load_feedback_sender_settings()

    def publisher(
        title: str, body: str, attachments: tuple[tuple[str, Path], ...]
    ) -> PublicationResult:
        return create_github_issue(
            settings=settings, title=title, body=body, attachments=attachments
        )

    with feedback_context() as service:
        return service.publish_next(publish=publisher)


def _missing_aliases(error: ValidationError) -> str:
    """Return the refused setting aliases alone, without any input or context."""
    aliases = sorted({str(part) for item in error.errors() for part in item.get("loc", ())})
    return ", ".join(aliases)


def main() -> int:
    """Run one dispatch and report its identity, state and link, or a content-safe failure."""
    try:
        report = dispatch_once()
    except ValidationError as error:
        print(
            f"feedback sender configuration is invalid: {_missing_aliases(error)}",
            file=sys.stderr,
        )
        return 1
    except Exception as error:
        print(f"feedback sender failed: {type(error).__name__}", file=sys.stderr)
        return 1
    if report.feedback_id is None:
        print("no pending feedback")
        return 0
    link = report.issue_url if report.issue_url is not None else "-"
    print(f"{report.feedback_id} {report.publication_state} {link}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
