"""The front router package: one loopback listener in front of the plain worker processes."""

# Seconds the supervisor waits for a terminated child before it kills the child.
TERMINATE_SECONDS = 10.0

# Seconds the router bounds its own graceful shutdown, so a terminated router exits inside the
# supervisor's terminate wait.
ROUTER_SHUTDOWN_SECONDS = TERMINATE_SECONDS / 2
