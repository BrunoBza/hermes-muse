"""Low-level correlation for a committed semantic mutation; no service imports."""

from contextvars import ContextVar

CURRENT_REQUEST = ContextVar("muse_mutation_request", default=None)
