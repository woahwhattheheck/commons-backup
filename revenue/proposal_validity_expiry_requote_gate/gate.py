from __future__ import annotations

"""Public hardened facade for the canonical proposal-validity gate.

The reviewed 9dee implementation remains structurally preserved in
``_proposal_validity_core.py``, with one later source-literal authority
hardening at the packet-emission seam. This facade closes the clock and
supersession STOPs without otherwise rewriting that large validated core:

* current public APIs capture their trusted clock generation at import time, so
  rebinding ``gate._utc_now`` cannot select or freeze historical time; and
* supersession source-currentness checks run only after exact-offer relevance
  and post-issuance chronology are established. Unrelated or pre-issue history
  remains syntactically validated but cannot veto current truth.
"""

import datetime as _facade_dt
from typing import Any


def _facade_utc_now(
    _now=_facade_dt.datetime.now,
    _utc=_facade_dt.timezone.utc,
) -> _facade_dt.datetime:
    """Facade-owned process clock; independent of mutable private-core bindings."""
    return _now(_utc).replace(microsecond=0)


if __package__:
    from . import _proposal_validity_core as _core
else:
    import _proposal_validity_core as _core

# Preserve the canonical module surface for callers/tests. Public current APIs
# are replaced below; the core's evaluator globals are patched only at the two
# STOP seams.
for _name in dir(_core):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_core, _name)

_original_validate_current = _core._validate_current


def _validate_current_hardened(current: Any) -> dict[str, Any]:
    """Validate all event syntax, but defer v2 current-source binding.

    The predecessor validator applied generation/digest/observation-currentness
    to every historical row before knowing whether the row applied to this offer
    or postdated issuance. Validate the current snapshot itself through the
    canonical validator with an empty event list, then validate every original
    event's schema and duplicate identity here. Relevance-sensitive authority is
    enforced by ``_active_superseders_hardened`` below.
    """
    if not isinstance(current, dict):
        return _original_validate_current(current)
    events = current.get("superseding_events")
    if not isinstance(events, list) or len(events) > _core._MAX_COLLECTION:
        return _original_validate_current(current)

    shell = dict(current)
    shell["superseding_events"] = []
    _original_validate_current(shell)

    version = current.get("schema_version")
    seen: set[str] = set()
    for idx, event in enumerate(events):
        _core._validate_event(event, idx, version)
        event_id = event["event_id"]
        if event_id in seen:
            raise _core.GateError("duplicate superseding event_id")
        seen.add(event_id)
    return current


def _active_superseders_hardened(
    issued: dict[str, Any], current: dict[str, Any]
) -> list[dict[str, Any]]:
    """Return only relevant post-issue superseders, then bind their authority."""
    issued_at = _core._parse_time(issued["issued_on"], "issued_offer.issued_on")
    current_observed = None
    if current.get("schema_version") == 2:
        current_observed = _core._parse_time(
            current["source_observed_at"], "current_offer.source_observed_at"
        )

    active: list[dict[str, Any]] = []
    for event in current["superseding_events"]:
        # Historical rows for other offers are valid ledger history, not current
        # authority for this offer.
        if event["applies_to_offer_id"] != issued["offer_id"]:
            continue
        observed = _core._parse_time(event["observed_at"], "event.observed_at")
        # Rows at/before issuance cannot supersede the issued offer, even when
        # they correctly reference an older historical source generation.
        if observed <= issued_at:
            continue

        if current.get("schema_version") == 2:
            if event["source_generation"] != current["source_generation"]:
                raise _core.GateError(
                    "superseding event source generation is not current"
                )
            if event["source_digest_sha256"] != current["source_digest_sha256"]:
                raise _core.GateError("superseding event source digest is not current")
            if observed > current_observed:
                raise _core.GateError(
                    "superseding event postdates current source observation"
                )
        active.append(event)
    return sorted(active, key=lambda event: (event["observed_at"], event["event_id"]))


# The canonical evaluator resolves these helpers through its own module globals;
# replace exactly those two seams before constructing the public API generation.
_core._validate_current = _validate_current_hardened
_core._active_superseders = _active_superseders_hardened
_validate_current = _validate_current_hardened
_active_superseders = _active_superseders_hardened


def _build_current_api(
    _clock=_facade_utc_now,
    _evaluate=_core._evaluate_at,
    _parse=_core._parse_time,
    _canonicalize=_core._canonical,
    _project=_core._semantic_projection,
    _error=_core.GateError,
):
    """Construct one current API generation with a closure-owned clock."""

    def evaluate_offer(issued_offer: Any, current_offer: Any) -> dict[str, Any]:
        return _evaluate(
            issued_offer,
            current_offer,
            _clock(),
            _clock_basis="PROCESS_UTC",
        )

    def verify_packet(issued_offer: Any, current_offer: Any, packet: Any) -> bool:
        if not isinstance(packet, dict):
            return False
        try:
            if (
                packet.get("schema_version") != 2
                or packet.get("clock_basis") != "PROCESS_UTC"
            ):
                return False
            evaluated_at = _parse(packet.get("evaluated_at"), "packet.evaluated_at")
            expected = _evaluate(
                issued_offer,
                current_offer,
                evaluated_at,
                _clock_basis="PROCESS_UTC",
            )
            if _canonicalize(expected) != _canonicalize(packet):
                return False
            live = _evaluate(
                issued_offer,
                current_offer,
                _clock(),
                _clock_basis="PROCESS_UTC",
            )
            if _project(live) != _project(packet):
                return False
        except (
            _error,
            ValueError,
            TypeError,
            UnicodeError,
            OverflowError,
            RecursionError,
        ):
            return False
        return True

    return evaluate_offer, verify_packet


evaluate_offer, verify_packet = _build_current_api()

# Deterministic predecessor tests can build a separate generation without
# retargeting the supported public generation. This is not a public clock input.
_build_current_api_for_test = _build_current_api
del _build_current_api

# Ensure the preserved CLI calls the same hardened public generation.
_core.evaluate_offer = evaluate_offer
_core.verify_packet = verify_packet
main = _core.main


if __name__ == "__main__":
    raise SystemExit(main())
