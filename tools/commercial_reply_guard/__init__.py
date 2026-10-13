"""Commercial reply handling guard for deterministic post-inbound triage."""

from .guard import GuardError, evaluate

__all__ = ["GuardError", "evaluate"]
