"""Deterministic pacemaker error types."""


class PacemakerError(RuntimeError):
    """Base class for deterministic refusals."""


class IntentConflict(PacemakerError):
    """A stable key was reused for different semantics."""


class StoreInvariantError(PacemakerError):
    """Persistent state no longer satisfies the recorded contract."""


class NoDispatchableMutation(PacemakerError):
    """No queued mutation is eligible at the current time."""

    def __init__(self, *args, retry_at=None, retry_after_seconds=None):
        super().__init__(*args)
        self.retry_at = retry_at
        self.retry_after_seconds = retry_after_seconds


class AmbiguousOutcome(PacemakerError):
    """A prior provider effect requires external readback."""
