"""Administrative sibling package.

This package owns the operator-facing, process-level mechanics that live outside
the product ``course_explorer`` domain: detached worker lifecycle and transport, worker
state, provisioning, the shared GPU-reboot checkpoint owner, and the request-scoped timer used by
detached worker main threads. Imports are one-way ``course_explorer_admin`` -> ``course_explorer``.
Product services never import this package.
"""
