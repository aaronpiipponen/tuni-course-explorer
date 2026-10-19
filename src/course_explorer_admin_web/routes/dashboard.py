"""The read-only Dashboard route of the administration console.

One authenticated GET maps to the one fixed server status command, so the panel reads the server
report from that one command. The route forwards the console's
automatic-read marker to the runner, so a successful scheduled poll leaves no command-log entry.
Every answer is non-cacheable.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response

from course_explorer_admin_web.routes.auth import NO_STORE_HEADERS
from course_explorer_admin_web.routes.read_mode import automatic_read
from course_explorer_admin_web.runner import CommandResult, ServerStatusCommand

router = APIRouter()


@router.get("/api/dashboard")
def dashboard(request: Request, response: Response) -> CommandResult:
    """Run the fixed server status command once and return its transient outcome."""
    response.headers.update(NO_STORE_HEADERS)
    return request.app.state.commands.run(
        ServerStatusCommand(kind="server-status"), automatic=automatic_read(request)
    )
