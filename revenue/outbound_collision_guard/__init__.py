"""Outbound collision/replay guard public surface."""
from .core import (
    AUTHORITY, MUSE_REGISTRY_SCHEMA, MUSE_TRUST_KEY_ENV, SCHEMA, STATES,
    GuardError, acquire, ambiguous_hold, begin_send, canonical_intent,
    intent_fingerprint, observe_send, release_unsent, verify,
)
__all__ = [
    "AUTHORITY", "MUSE_REGISTRY_SCHEMA", "MUSE_TRUST_KEY_ENV", "SCHEMA", "STATES",
    "GuardError", "acquire", "ambiguous_hold", "begin_send", "canonical_intent",
    "intent_fingerprint", "observe_send", "release_unsent", "verify",
]
