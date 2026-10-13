"""Commercial Decision Relay: evidence-bound commercial decision routing."""

from .core import (
    AuthorityBoundaryError,
    DecisionRelayError,
    canonical_digest,
    receipt_self_digest_matches,
    verify_current_receipt,
    verify_receipt,
)
from .current import CurrentRelayEngine as RelayEngine
from .current import reconcile_current, reconcile_historical

# The package-level/default surface is current-state reconciliation and therefore
# requires an out-of-band trusted evaluation instant. Historical snapshot replay
# remains available only under an explicit historical name.
reconcile = reconcile_current

__all__ = [
    "AuthorityBoundaryError",
    "DecisionRelayError",
    "RelayEngine",
    "canonical_digest",
    "receipt_self_digest_matches",
    "reconcile",
    "reconcile_current",
    "reconcile_historical",
    "verify_current_receipt",
    "verify_receipt",
]
