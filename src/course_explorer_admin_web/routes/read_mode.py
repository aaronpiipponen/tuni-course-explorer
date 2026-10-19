"""The automatic-read request marker of the administration console.

The console's automatic reads tag themselves with one fixed header, and the read routes translate
that marker into the fixed-command runner's own automatic flag so a successful poll leaves no entry
in the sole command log. The marker is request metadata alone: it changes no argument list, no
admission decision and no CSRF requirement, so a tagged request is admitted and executed exactly
like an untagged one.
"""

from __future__ import annotations

from fastapi import Request

# The one request header the console sets on an automatic read.
AUTOMATIC_READ_HEADER = "X-Admin-Automatic-Read"

# The one header value that marks an automatic read.
AUTOMATIC_READ_VALUE = "1"


def automatic_read(request: Request) -> bool:
    """Report whether one request carries the console's automatic-read marker.

    The marker is exactly one occurrence of the named header with the value ``1``. An absent header,
    another value and a repeated header all report false, so an explicit read, an action and a
    manual client use the runner's default recording of their outcome.
    """
    return request.headers.getlist(AUTOMATIC_READ_HEADER) == [AUTOMATIC_READ_VALUE]
