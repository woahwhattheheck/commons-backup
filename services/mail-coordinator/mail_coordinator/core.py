from __future__ import annotations

from .base import BaseCoordinator
from .attempt import AttemptMixin
from .claim import ClaimMixin
from .reconcile import ReconcileMixin
from .inbound import InboundMixin
from .models import (
    ACTIVE_STATES, Claim, ConflictError, CoordinationError, Envelope,
    NotFoundError, QueueRequest, QueueResult, ValidationError, body_digest,
    canonical_hash, normalize_address, normalize_key, normalize_subject,
    stable_identifier, utc_now,
)
from .query import QueryMixin
from .queue import QueueMixin


class MailCoordinator(QueryMixin, ReconcileMixin, AttemptMixin, ClaimMixin, QueueMixin, InboundMixin, BaseCoordinator):
    """Durable, transactionally serialized outbound-mail coordinator."""


__all__ = [
    "ACTIVE_STATES", "Claim", "ConflictError", "CoordinationError",
    "Envelope", "MailCoordinator", "NotFoundError", "QueueRequest",
    "QueueResult", "ValidationError", "body_digest", "canonical_hash",
    "normalize_address", "normalize_key", "normalize_subject",
    "stable_identifier", "utc_now",
]
