"""Composed SQLite pacemaker store."""

from .store_base import StoreBase
from .store_queue import StoreQueueMixin
from .store_read import StoreReadMixin
from .store_results import StoreResultsMixin


class PacemakerStore(
    StoreQueueMixin,
    StoreResultsMixin,
    StoreReadMixin,
    StoreBase,
):
    """Cooperative queue, claim, result, and reconciliation state."""
