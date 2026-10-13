# SPDX-License-Identifier: Apache-2.0
"""Public RouteFoundry data API.

The implementation is split by responsibility so operators can inspect and
reuse URL validation separately from persistence and reporting.
"""
from route_validation import (
    EVENT_TYPES, ROUTE_MODES, UTM_KEYS, EventResult, ValidationError, append_utm,
    event_id, referrer_host, require_text, short_url, utc_now,
    validate_destination, validate_public_base_url, validate_slug,
)
from store_base import StoreBase
from store_read import StoreReadMixin
from store_write import StoreWriteMixin


class Store(StoreWriteMixin, StoreReadMixin, StoreBase):
    """Persistent campaign-link workspace."""


__all__ = [
    "EVENT_TYPES", "ROUTE_MODES", "UTM_KEYS", "EventResult", "Store",
    "ValidationError", "append_utm", "event_id", "referrer_host",
    "require_text", "short_url", "utc_now", "validate_destination",
    "validate_public_base_url", "validate_slug",
]
