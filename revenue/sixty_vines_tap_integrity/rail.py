#!/usr/bin/env python3
"""Deterministic synthetic Tap-to-Table integrity rail.

This module is deliberately offline.  It does not call a POS, payment provider,
inventory system, guest system, or alcohol-service workflow.  It reconciles an
approved event ledger and fails closed before recording synthetic effects when
lineage or operating-state preconditions are not satisfied.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


class RailError(ValueError):
    """Malformed or contradictory input that makes deterministic replay unsafe."""


def _canon(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canon(value)).hexdigest()


def _require_id(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise RailError(f"{field_name} must be a non-empty trimmed string")
    return value


def _require_int(value: Any, field_name: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise RailError(f"{field_name} must be an integer >= {minimum}")
    return value


def _hold(event: Mapping[str, Any], code: str, detail: str) -> dict[str, Any]:
    return {
        "event_id": event["event_id"],
        "seq": event["seq"],
        "code": code,
        "detail": detail,
    }


@dataclass(frozen=True)
class RailConfig:
    taps: dict[str, dict[str, str]]
    cleaning_max_age: int = 720

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "RailConfig":
        if not isinstance(raw, Mapping):
            raise RailError("config must be an object")
        cleaning_max_age = _require_int(
            raw.get("cleaning_max_age", 720), "cleaning_max_age", minimum=1
        )
        taps_raw = raw.get("taps")
        if not isinstance(taps_raw, Mapping) or not taps_raw:
            raise RailError("config.taps must be a non-empty object")
        taps: dict[str, dict[str, str]] = {}
        seen_lines: set[str] = set()
        for tap_id_raw, tap_raw in taps_raw.items():
            tap_id = _require_id(tap_id_raw, "tap_id")
            if not isinstance(tap_raw, Mapping):
                raise RailError(f"tap {tap_id} must be an object")
            line_id = _require_id(tap_raw.get("line_id"), f"{tap_id}.line_id")
            allowed_sku = _require_id(
                tap_raw.get("allowed_sku"), f"{tap_id}.allowed_sku"
            )
            if line_id in seen_lines:
                raise RailError(f"line_id {line_id} is assigned to multiple taps")
            seen_lines.add(line_id)
            taps[tap_id] = {"line_id": line_id, "allowed_sku": allowed_sku}
        return cls(taps=taps, cleaning_max_age=cleaning_max_age)

    def as_mapping(self) -> dict[str, Any]:
        return {
            "cleaning_max_age": self.cleaning_max_age,
            "taps": {k: dict(v) for k, v in sorted(self.taps.items())},
        }


@dataclass
class RailState:
    kegs: dict[str, dict[str, Any]] = field(default_factory=dict)
    assignments: dict[str, str] = field(default_factory=dict)  # tap -> keg
    line_last_clean: dict[str, int] = field(default_factory=dict)
    line_status: dict[str, str] = field(default_factory=dict)
    effects: dict[str, dict[str, Any]] = field(default_factory=dict)
    pours: dict[str, dict[str, Any]] = field(default_factory=dict)
    pending: dict[str, dict[str, Any]] = field(default_factory=dict)
    resolved_pending: dict[str, str] = field(default_factory=dict)
    inventory_used_ml: int = 0
    inventory_waste_ml: int = 0
    gross_cents: int = 0
    refund_cents: int = 0
    void_cents: int = 0
    holds: list[dict[str, Any]] = field(default_factory=list)
    processed: int = 0

    def snapshot(self) -> dict[str, Any]:
        return {
            "kegs": {k: dict(v) for k, v in sorted(self.kegs.items())},
            "assignments": dict(sorted(self.assignments.items())),
            "line_last_clean": dict(sorted(self.line_last_clean.items())),
            "line_status": dict(sorted(self.line_status.items())),
            "effects": {k: dict(v) for k, v in sorted(self.effects.items())},
            "pours": {k: dict(v) for k, v in sorted(self.pours.items())},
            "pending": {k: dict(v) for k, v in sorted(self.pending.items())},
            "resolved_pending": dict(sorted(self.resolved_pending.items())),
            "inventory_used_ml": self.inventory_used_ml,
            "inventory_waste_ml": self.inventory_waste_ml,
            "gross_cents": self.gross_cents,
            "refund_cents": self.refund_cents,
            "void_cents": self.void_cents,
            "holds": sorted(
                self.holds, key=lambda h: (h["seq"], h["event_id"], h["code"])
            ),
            "processed": self.processed,
        }


def _normalize_events(events: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Deduplicate exact event retries and return a canonical sequence order."""
    by_id: dict[str, dict[str, Any]] = {}
    by_hash: dict[str, str] = {}
    for raw in events:
        if not isinstance(raw, Mapping):
            raise RailError("each event must be an object")
        event = dict(raw)
        event_id = _require_id(event.get("event_id"), "event_id")
        seq = _require_int(event.get("seq"), f"{event_id}.seq", minimum=0)
        kind = _require_id(event.get("type"), f"{event_id}.type")
        event["event_id"] = event_id
        event["seq"] = seq
        event["type"] = kind
        digest = _sha(event)
        if event_id in by_id:
            if by_hash[event_id] != digest:
                raise RailError(f"event_id {event_id} was reused with different bytes")
            continue
        by_id[event_id] = event
        by_hash[event_id] = digest

    ordered = sorted(by_id.values(), key=lambda e: (e["seq"], e["event_id"]))
    seq_owner: dict[int, str] = {}
    for event in ordered:
        prior = seq_owner.get(event["seq"])
        if prior is not None:
            raise RailError(
                f"seq {event['seq']} is shared by {prior} and {event['event_id']}"
            )
        seq_owner[event["seq"]] = event["event_id"]
    return ordered


def _validate_effect_id(state: RailState, event: Mapping[str, Any]) -> str | None:
    effect_id = _require_id(event.get("effect_id"), f"{event['event_id']}.effect_id")
    if effect_id in state.pending:
        state.holds.append(
            _hold(event, "UNKNOWN_EFFECT_BLOCK", f"{effect_id} is unresolved")
        )
        return None
    if effect_id in state.effects:
        state.holds.append(
            _hold(event, "DUPLICATE_EFFECT_ID", f"{effect_id} was already applied")
        )
        return None
    if effect_id in state.resolved_pending:
        state.holds.append(
            _hold(event, "RESOLVED_EFFECT_REUSE", f"{effect_id} is already resolved")
        )
        return None
    return effect_id


def _validate_pour_preconditions(
    state: RailState,
    config: RailConfig,
    event: Mapping[str, Any],
) -> tuple[str, dict[str, Any]] | None:
    tap_id = _require_id(event.get("tap_id"), f"{event['event_id']}.tap_id")
    line_id = _require_id(event.get("line_id"), f"{event['event_id']}.line_id")
    keg_id = _require_id(event.get("keg_id"), f"{event['event_id']}.keg_id")
    lot_id = _require_id(event.get("lot_id"), f"{event['event_id']}.lot_id")
    sku = _require_id(event.get("sku"), f"{event['event_id']}.sku")

    for pending_id, pending in sorted(state.pending.items()):
        pending_spec = pending["spec"]
        resource = None
        if pending_spec["tap_id"] == tap_id:
            resource = f"tap {tap_id}"
        elif pending_spec["line_id"] == line_id:
            resource = f"line {line_id}"
        elif pending_spec["keg_id"] == keg_id:
            resource = f"keg {keg_id}"
        if resource is not None:
            state.holds.append(
                _hold(
                    event,
                    "UNKNOWN_RESOURCE_BLOCK",
                    f"{pending_id} has unresolved {resource}",
                )
            )
            return None

    tap = config.taps.get(tap_id)
    if tap is None:
        state.holds.append(_hold(event, "UNKNOWN_TAP", tap_id))
        return None
    if tap["line_id"] != line_id:
        state.holds.append(
            _hold(event, "WRONG_LINE", f"{tap_id} is approved only for {tap['line_id']}")
        )
        return None
    if tap["allowed_sku"] != sku:
        state.holds.append(
            _hold(
                event,
                "SKU_NOT_APPROVED_FOR_TAP",
                f"{tap_id} expects {tap['allowed_sku']}, got {sku}",
            )
        )
        return None
    if state.line_status.get(line_id, "UNAVAILABLE") != "AVAILABLE":
        state.holds.append(
            _hold(event, "LINE_UNAVAILABLE", f"{line_id} is not AVAILABLE")
        )
        return None

    last_clean = state.line_last_clean.get(line_id)
    if last_clean is None:
        state.holds.append(_hold(event, "CLEANING_UNKNOWN", line_id))
        return None
    age = event["seq"] - last_clean
    if age < 0 or age > config.cleaning_max_age:
        state.holds.append(
            _hold(
                event,
                "CLEANING_OVERDUE",
                f"{line_id} cleaning age {age} > {config.cleaning_max_age}",
            )
        )
        return None

    assigned = state.assignments.get(tap_id)
    if assigned != keg_id:
        state.holds.append(
            _hold(
                event,
                "KEG_NOT_ASSIGNED",
                f"{tap_id} has {assigned or 'no keg'}, event names {keg_id}",
            )
        )
        return None
    keg = state.kegs.get(keg_id)
    if keg is None:
        state.holds.append(_hold(event, "UNKNOWN_KEG", keg_id))
        return None
    if keg["lot_id"] != lot_id:
        state.holds.append(
            _hold(
                event,
                "LOT_MISMATCH",
                f"{keg_id} has lot {keg['lot_id']}, event names {lot_id}",
            )
        )
        return None
    if keg["sku"] != sku:
        state.holds.append(
            _hold(event, "KEG_SKU_MISMATCH", f"{keg_id} has sku {keg['sku']}")
        )
        return None
    return tap_id, keg


def _pour_spec(event: Mapping[str, Any]) -> dict[str, Any]:
    amount_ml = _require_int(event.get("amount_ml"), f"{event['event_id']}.amount_ml", minimum=1)
    price_cents = _require_int(
        event.get("price_cents"), f"{event['event_id']}.price_cents", minimum=0
    )
    return {
        "pour_id": _require_id(event.get("pour_id"), f"{event['event_id']}.pour_id"),
        "tap_id": _require_id(event.get("tap_id"), f"{event['event_id']}.tap_id"),
        "line_id": _require_id(event.get("line_id"), f"{event['event_id']}.line_id"),
        "keg_id": _require_id(event.get("keg_id"), f"{event['event_id']}.keg_id"),
        "lot_id": _require_id(event.get("lot_id"), f"{event['event_id']}.lot_id"),
        "sku": _require_id(event.get("sku"), f"{event['event_id']}.sku"),
        "amount_ml": amount_ml,
        "price_cents": price_cents,
        "check_id": _require_id(event.get("check_id"), f"{event['event_id']}.check_id"),
        "table_id": _require_id(event.get("table_id"), f"{event['event_id']}.table_id"),
    }


def _apply_pour(
    state: RailState,
    event: Mapping[str, Any],
    spec: Mapping[str, Any],
    effect_id: str,
) -> bool:
    keg = state.kegs[spec["keg_id"]]
    if spec["pour_id"] in state.pours:
        state.holds.append(_hold(event, "DUPLICATE_POUR_ID", spec["pour_id"]))
        return False
    if keg["remaining_ml"] < spec["amount_ml"]:
        state.holds.append(
            _hold(
                event,
                "INSUFFICIENT_KEG_VOLUME",
                f"{spec['keg_id']} has {keg['remaining_ml']}ml remaining",
            )
        )
        return False

    keg["remaining_ml"] -= spec["amount_ml"]
    state.inventory_used_ml += spec["amount_ml"]
    state.gross_cents += spec["price_cents"]
    state.effects[effect_id] = {
        "kind": "POUR",
        "source_event_id": event["event_id"],
        "inventory_delta_ml": -spec["amount_ml"],
        "money_delta_cents": spec["price_cents"],
        "pour_id": spec["pour_id"],
    }
    state.pours[spec["pour_id"]] = {
        **dict(spec),
        "effect_id": effect_id,
        "refunded_cents": 0,
        "voided": False,
    }
    return True


def reconcile(
    config_raw: Mapping[str, Any],
    events_raw: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Replay a complete synthetic ledger and return a content-addressed receipt."""
    config = RailConfig.from_mapping(config_raw)
    events = _normalize_events(events_raw)
    state = RailState()

    for event in events:
        state.processed += 1
        kind = event["type"]

        if kind == "RECEIVE_KEG":
            keg_id = _require_id(event.get("keg_id"), f"{event['event_id']}.keg_id")
            lot_id = _require_id(event.get("lot_id"), f"{event['event_id']}.lot_id")
            sku = _require_id(event.get("sku"), f"{event['event_id']}.sku")
            initial_ml = _require_int(
                event.get("initial_ml"), f"{event['event_id']}.initial_ml", minimum=1
            )
            existing = state.kegs.get(keg_id)
            candidate = {
                "lot_id": lot_id,
                "sku": sku,
                "initial_ml": initial_ml,
                "remaining_ml": initial_ml,
            }
            if existing is not None:
                state.holds.append(_hold(event, "DUPLICATE_KEG", keg_id))
                continue
            state.kegs[keg_id] = candidate
            continue

        if kind == "CLEAN_LINE":
            line_id = _require_id(event.get("line_id"), f"{event['event_id']}.line_id")
            if line_id not in {v["line_id"] for v in config.taps.values()}:
                state.holds.append(_hold(event, "UNKNOWN_LINE", line_id))
                continue
            prior = state.line_last_clean.get(line_id, -1)
            if event["seq"] < prior:
                raise RailError("canonical sequence moved cleaning backwards")
            state.line_last_clean[line_id] = event["seq"]
            continue

        if kind == "SET_LINE_STATUS":
            line_id = _require_id(event.get("line_id"), f"{event['event_id']}.line_id")
            status = _require_id(event.get("status"), f"{event['event_id']}.status")
            if line_id not in {v["line_id"] for v in config.taps.values()}:
                state.holds.append(_hold(event, "UNKNOWN_LINE", line_id))
                continue
            if status not in {"AVAILABLE", "HOLD", "CLEANING"}:
                raise RailError(f"invalid line status {status}")
            state.line_status[line_id] = status
            continue

        if kind == "ASSIGN_KEG":
            tap_id = _require_id(event.get("tap_id"), f"{event['event_id']}.tap_id")
            line_id = _require_id(event.get("line_id"), f"{event['event_id']}.line_id")
            keg_id = _require_id(event.get("keg_id"), f"{event['event_id']}.keg_id")
            tap = config.taps.get(tap_id)
            keg = state.kegs.get(keg_id)
            if tap is None:
                state.holds.append(_hold(event, "UNKNOWN_TAP", tap_id))
                continue
            if tap["line_id"] != line_id:
                state.holds.append(_hold(event, "WRONG_LINE", line_id))
                continue
            if keg is None:
                state.holds.append(_hold(event, "UNKNOWN_KEG", keg_id))
                continue
            if keg["sku"] != tap["allowed_sku"]:
                state.holds.append(
                    _hold(
                        event,
                        "SKU_NOT_APPROVED_FOR_TAP",
                        f"{keg['sku']} != {tap['allowed_sku']}",
                    )
                )
                continue
            state.assignments[tap_id] = keg_id
            continue

        if kind in {"POUR", "POUR_UNKNOWN"}:
            effect_id = _validate_effect_id(state, event)
            if effect_id is None:
                continue
            spec = _pour_spec(event)
            validated = _validate_pour_preconditions(state, config, event)
            if validated is None:
                continue
            _, keg = validated
            if keg["remaining_ml"] < spec["amount_ml"]:
                state.holds.append(
                    _hold(
                        event,
                        "INSUFFICIENT_KEG_VOLUME",
                        f"{spec['keg_id']} has {keg['remaining_ml']}ml remaining",
                    )
                )
                continue
            if spec["pour_id"] in state.pours:
                state.holds.append(_hold(event, "DUPLICATE_POUR_ID", spec["pour_id"]))
                continue
            if any(
                pending["spec"]["pour_id"] == spec["pour_id"]
                for pending in state.pending.values()
            ):
                state.holds.append(
                    _hold(event, "PENDING_POUR_ID", spec["pour_id"])
                )
                continue
            if kind == "POUR_UNKNOWN":
                state.pending[effect_id] = {
                    "source_event_id": event["event_id"],
                    "source_seq": event["seq"],
                    "spec": spec,
                }
            else:
                _apply_pour(state, event, spec, effect_id)
            continue

        if kind == "RESOLVE_POUR":
            effect_id = _require_id(
                event.get("effect_id"), f"{event['event_id']}.effect_id"
            )
            resolution = _require_id(
                event.get("resolution"), f"{event['event_id']}.resolution"
            )
            if resolution not in {"APPLIED", "NOT_APPLIED"}:
                raise RailError("resolution must be APPLIED or NOT_APPLIED")
            if effect_id in state.resolved_pending:
                state.holds.append(
                    _hold(event, "UNKNOWN_ALREADY_RESOLVED", effect_id)
                )
                continue
            pending = state.pending.get(effect_id)
            if pending is None:
                state.holds.append(_hold(event, "UNKNOWN_PENDING_EFFECT", effect_id))
                continue
            if resolution == "APPLIED":
                source_event = {
                    "event_id": pending["source_event_id"],
                    "seq": pending["source_seq"],
                }
                if not _apply_pour(state, source_event, pending["spec"], effect_id):
                    state.holds.append(
                        _hold(event, "RESOLUTION_APPLY_FAILED", effect_id)
                    )
                    continue
            state.pending.pop(effect_id)
            state.resolved_pending[effect_id] = resolution
            continue

        if kind == "WASTE":
            effect_id = _validate_effect_id(state, event)
            if effect_id is None:
                continue
            spec_event = dict(event)
            spec_event.setdefault("price_cents", 0)
            spec_event.setdefault("pour_id", f"waste:{event['event_id']}")
            spec_event.setdefault("check_id", "WASTE")
            spec_event.setdefault("table_id", "WASTE")
            spec = _pour_spec(spec_event)
            validated = _validate_pour_preconditions(state, config, spec_event)
            if validated is None:
                continue
            keg = state.kegs[spec["keg_id"]]
            if keg["remaining_ml"] < spec["amount_ml"]:
                state.holds.append(
                    _hold(event, "INSUFFICIENT_KEG_VOLUME", spec["keg_id"])
                )
                continue
            keg["remaining_ml"] -= spec["amount_ml"]
            state.inventory_waste_ml += spec["amount_ml"]
            state.effects[effect_id] = {
                "kind": "WASTE",
                "source_event_id": event["event_id"],
                "inventory_delta_ml": -spec["amount_ml"],
                "money_delta_cents": 0,
            }
            continue

        if kind in {"REFUND", "VOID"}:
            effect_id = _validate_effect_id(state, event)
            if effect_id is None:
                continue
            pour_id = _require_id(event.get("pour_id"), f"{event['event_id']}.pour_id")
            pour = state.pours.get(pour_id)
            if pour is None:
                state.holds.append(_hold(event, "UNKNOWN_POUR", pour_id))
                continue
            if kind == "VOID":
                if pour["voided"] or pour["refunded_cents"]:
                    state.holds.append(
                        _hold(event, "VOID_CONFLICT", f"{pour_id} already reversed")
                    )
                    continue
                amount_cents = pour["price_cents"]
                pour["voided"] = True
                state.void_cents += amount_cents
            else:
                amount_cents = _require_int(
                    event.get("amount_cents"),
                    f"{event['event_id']}.amount_cents",
                    minimum=1,
                )
                if pour["voided"]:
                    state.holds.append(_hold(event, "REFUND_AFTER_VOID", pour_id))
                    continue
                remaining = pour["price_cents"] - pour["refunded_cents"]
                if amount_cents > remaining:
                    state.holds.append(
                        _hold(
                            event,
                            "REFUND_EXCEEDS_REMAINING",
                            f"{amount_cents} > {remaining}",
                        )
                    )
                    continue
                pour["refunded_cents"] += amount_cents
                state.refund_cents += amount_cents
            state.effects[effect_id] = {
                "kind": kind,
                "source_event_id": event["event_id"],
                "inventory_delta_ml": 0,
                "money_delta_cents": -amount_cents,
                "pour_id": pour_id,
            }
            continue

        raise RailError(f"unknown event type {kind}")

    snapshot = state.snapshot()
    unresolved = sorted(state.pending)
    tap_coverage = {
        tap_id: sum(1 for p in state.pours.values() if p["tap_id"] == tap_id)
        for tap_id in sorted(config.taps)
    }
    summary = {
        "unique_events": len(events),
        "processed_events": state.processed,
        "applied_effects": len(state.effects),
        "holds": len(state.holds),
        "unresolved_unknown_effects": len(unresolved),
        "tap_count": len(config.taps),
        "taps_with_pours": sum(1 for count in tap_coverage.values() if count > 0),
        "inventory_used_ml": state.inventory_used_ml,
        "inventory_waste_ml": state.inventory_waste_ml,
        "gross_cents": state.gross_cents,
        "refund_cents": state.refund_cents,
        "void_cents": state.void_cents,
        "net_cents": state.gross_cents - state.refund_cents - state.void_cents,
        "remaining_ml": sum(k["remaining_ml"] for k in state.kegs.values()),
    }
    receipt: dict[str, Any] = {
        "schema": "sixty-vines-tap-integrity-receipt/v1",
        "config_sha256": _sha(config.as_mapping()),
        "events_sha256": _sha(events),
        "state_sha256": _sha(snapshot),
        "summary": summary,
        "tap_coverage": tap_coverage,
        "holds": snapshot["holds"],
        "unresolved_effect_ids": unresolved,
    }
    receipt["receipt_sha256"] = receipt_digest(receipt)
    return receipt


def receipt_digest(receipt: Mapping[str, Any]) -> str:
    unsigned = dict(receipt)
    unsigned.pop("receipt_sha256", None)
    return _sha(unsigned)


def _is_nonnegative_int(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, int) and value >= 0


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(char in "0123456789abcdef" for char in value)
    )


def verify_receipt(receipt: Mapping[str, Any]) -> bool:
    if not isinstance(receipt, Mapping):
        return False

    required_fields = {
        "schema",
        "config_sha256",
        "events_sha256",
        "state_sha256",
        "summary",
        "tap_coverage",
        "holds",
        "unresolved_effect_ids",
        "receipt_sha256",
    }
    if set(receipt) != required_fields:
        return False
    if receipt["schema"] != "sixty-vines-tap-integrity-receipt/v1":
        return False
    if not all(
        _is_sha256(receipt[field])
        for field in (
            "config_sha256",
            "events_sha256",
            "state_sha256",
            "receipt_sha256",
        )
    ):
        return False

    summary = receipt["summary"]
    summary_fields = {
        "unique_events",
        "processed_events",
        "applied_effects",
        "holds",
        "unresolved_unknown_effects",
        "tap_count",
        "taps_with_pours",
        "inventory_used_ml",
        "inventory_waste_ml",
        "gross_cents",
        "refund_cents",
        "void_cents",
        "net_cents",
        "remaining_ml",
    }
    if not isinstance(summary, Mapping) or set(summary) != summary_fields:
        return False
    if not all(_is_nonnegative_int(summary[field]) for field in summary_fields):
        return False
    if summary["tap_count"] < 1:
        return False
    if summary["processed_events"] != summary["unique_events"]:
        return False
    if summary["applied_effects"] > summary["processed_events"]:
        return False
    if summary["taps_with_pours"] > summary["tap_count"]:
        return False
    if summary["net_cents"] != (
        summary["gross_cents"] - summary["refund_cents"] - summary["void_cents"]
    ):
        return False

    coverage = receipt["tap_coverage"]
    if not isinstance(coverage, Mapping) or len(coverage) != summary["tap_count"]:
        return False
    for tap_id, count in coverage.items():
        if (
            not isinstance(tap_id, str)
            or not tap_id
            or tap_id.strip() != tap_id
            or not _is_nonnegative_int(count)
        ):
            return False
    if sum(1 for count in coverage.values() if count > 0) != summary["taps_with_pours"]:
        return False

    holds = receipt["holds"]
    if not isinstance(holds, list) or len(holds) != summary["holds"]:
        return False
    hold_fields = {"event_id", "seq", "code", "detail"}
    for hold in holds:
        if not isinstance(hold, Mapping) or set(hold) != hold_fields:
            return False
        if not _is_nonnegative_int(hold["seq"]):
            return False
        for field in ("event_id", "code", "detail"):
            value = hold[field]
            if not isinstance(value, str) or not value or value.strip() != value:
                return False

    unresolved = receipt["unresolved_effect_ids"]
    if not isinstance(unresolved, list):
        return False
    if len(unresolved) != summary["unresolved_unknown_effects"]:
        return False
    if unresolved != sorted(unresolved) or len(unresolved) != len(set(unresolved)):
        return False
    if any(
        not isinstance(effect_id, str)
        or not effect_id
        or effect_id.strip() != effect_id
        for effect_id in unresolved
    ):
        return False

    return receipt["receipt_sha256"] == receipt_digest(receipt)


def make_config(tap_count: int = 60, *, cleaning_max_age: int = 720) -> dict[str, Any]:
    tap_count = _require_int(tap_count, "tap_count", minimum=1)
    return {
        "cleaning_max_age": cleaning_max_age,
        "taps": {
            f"TAP-{i:02d}": {
                "line_id": f"LINE-{i:02d}",
                "allowed_sku": f"WINE-{i:02d}",
            }
            for i in range(1, tap_count + 1)
        },
    }


def generate_acceptance_events(
    event_count: int = 20_000,
    tap_count: int = 60,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Generate an exact-size, deterministic all-tap synthetic acceptance ledger."""
    event_count = _require_int(event_count, "event_count", minimum=1)
    tap_count = _require_int(tap_count, "tap_count", minimum=1)
    minimum = tap_count * 4
    if event_count < minimum:
        raise RailError(
            f"event_count must be >= {minimum} to initialize {tap_count} taps"
        )
    config = make_config(tap_count, cleaning_max_age=900)
    events: list[dict[str, Any]] = []
    seq = 0

    for i in range(1, tap_count + 1):
        tap = f"TAP-{i:02d}"
        line = f"LINE-{i:02d}"
        sku = f"WINE-{i:02d}"
        keg = f"KEG-{i:02d}"
        lot = f"LOT-{i:02d}"
        events.append(
            {
                "event_id": f"E-{seq:06d}",
                "seq": seq,
                "type": "RECEIVE_KEG",
                "keg_id": keg,
                "lot_id": lot,
                "sku": sku,
                "initial_ml": 100_000,
            }
        )
        seq += 1
        events.append(
            {
                "event_id": f"E-{seq:06d}",
                "seq": seq,
                "type": "CLEAN_LINE",
                "line_id": line,
            }
        )
        seq += 1
        events.append(
            {
                "event_id": f"E-{seq:06d}",
                "seq": seq,
                "type": "SET_LINE_STATUS",
                "line_id": line,
                "status": "AVAILABLE",
            }
        )
        seq += 1
        events.append(
            {
                "event_id": f"E-{seq:06d}",
                "seq": seq,
                "type": "ASSIGN_KEG",
                "tap_id": tap,
                "line_id": line,
                "keg_id": keg,
            }
        )
        seq += 1

    pour_counter = 0
    last_pour_by_tap: dict[str, str] = {}
    last_clean_seq: dict[str, int] = {
        f"LINE-{i:02d}": i * 4 - 3 for i in range(1, tap_count + 1)
    }

    while seq < event_count:
        i = (pour_counter % tap_count) + 1
        tap = f"TAP-{i:02d}"
        line = f"LINE-{i:02d}"
        sku = f"WINE-{i:02d}"
        keg = f"KEG-{i:02d}"
        lot = f"LOT-{i:02d}"

        if seq - last_clean_seq[line] > 800:
            events.append(
                {
                    "event_id": f"E-{seq:06d}",
                    "seq": seq,
                    "type": "CLEAN_LINE",
                    "line_id": line,
                }
            )
            last_clean_seq[line] = seq
            seq += 1
            if seq >= event_count:
                break

        # Exercise refund lineage periodically without making the fixture depend
        # on provider effects.  The referenced pour is always on the same tap.
        if pour_counter and pour_counter % 173 == 0 and tap in last_pour_by_tap:
            events.append(
                {
                    "event_id": f"E-{seq:06d}",
                    "seq": seq,
                    "type": "REFUND",
                    "effect_id": f"FX-{seq:06d}",
                    "pour_id": last_pour_by_tap[tap],
                    "amount_cents": 100,
                }
            )
            seq += 1
            pour_counter += 1
            continue

        if pour_counter and pour_counter % 127 == 0:
            events.append(
                {
                    "event_id": f"E-{seq:06d}",
                    "seq": seq,
                    "type": "WASTE",
                    "effect_id": f"FX-{seq:06d}",
                    "tap_id": tap,
                    "line_id": line,
                    "keg_id": keg,
                    "lot_id": lot,
                    "sku": sku,
                    "amount_ml": 5,
                }
            )
            seq += 1
            pour_counter += 1
            continue

        pour_id = f"POUR-{pour_counter:06d}"
        if pour_counter and pour_counter % 211 == 0 and seq + 1 < event_count:
            # Timeout-after-commit shape: preserve UNKNOWN until an explicit
            # reconciliation event says the intended effect was applied.
            effect_id = f"FX-{seq:06d}"
            events.append(
                {
                    "event_id": f"E-{seq:06d}",
                    "seq": seq,
                    "type": "POUR_UNKNOWN",
                    "effect_id": effect_id,
                    "pour_id": pour_id,
                    "tap_id": tap,
                    "line_id": line,
                    "keg_id": keg,
                    "lot_id": lot,
                    "sku": sku,
                    "amount_ml": 5,
                    "price_cents": 300,
                    "check_id": f"CHECK-{pour_counter // 4:06d}",
                    "table_id": f"TABLE-{(pour_counter % 80) + 1:03d}",
                }
            )
            seq += 1
            events.append(
                {
                    "event_id": f"E-{seq:06d}",
                    "seq": seq,
                    "type": "RESOLVE_POUR",
                    "effect_id": effect_id,
                    "resolution": "APPLIED",
                }
            )
            last_pour_by_tap[tap] = pour_id
            seq += 1
            pour_counter += 1
            continue

        events.append(
            {
                "event_id": f"E-{seq:06d}",
                "seq": seq,
                "type": "POUR",
                "effect_id": f"FX-{seq:06d}",
                "pour_id": pour_id,
                "tap_id": tap,
                "line_id": line,
                "keg_id": keg,
                "lot_id": lot,
                "sku": sku,
                "amount_ml": 5,
                "price_cents": 300,
                "check_id": f"CHECK-{pour_counter // 4:06d}",
                "table_id": f"TABLE-{(pour_counter % 80) + 1:03d}",
            }
        )
        last_pour_by_tap[tap] = pour_id
        seq += 1
        pour_counter += 1

    if len(events) != event_count:
        raise AssertionError(f"generator produced {len(events)} != {event_count}")
    return config, events


def _load_fixture(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise RailError("fixture must be an object")
    config = raw.get("config")
    events = raw.get("events")
    if not isinstance(config, Mapping) or not isinstance(events, list):
        raise RailError("fixture requires object config and array events")
    return dict(config), events


def _main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    acceptance = sub.add_parser("acceptance", help="run deterministic synthetic acceptance")
    acceptance.add_argument("--events", type=int, default=20_000)
    acceptance.add_argument("--taps", type=int, default=60)
    acceptance.add_argument("--receipt", type=Path)
    acceptance.add_argument("--require-pass", action="store_true")

    fixture = sub.add_parser("fixture", help="reconcile a JSON fixture")
    fixture.add_argument("path", type=Path)
    fixture.add_argument("--receipt", type=Path)
    fixture.add_argument("--require-pass", action="store_true")

    verify = sub.add_parser("verify-receipt", help="verify an offline receipt hash")
    verify.add_argument("path", type=Path)

    args = parser.parse_args(argv)

    if args.command == "verify-receipt":
        receipt = json.loads(args.path.read_text(encoding="utf-8"))
        ok = verify_receipt(receipt)
        print(json.dumps({"valid": ok}, sort_keys=True))
        return 0 if ok else 2

    if args.command == "acceptance":
        config, events = generate_acceptance_events(args.events, args.taps)
    else:
        config, events = _load_fixture(args.path)

    receipt = reconcile(config, events)
    payload = json.dumps(receipt, sort_keys=True, indent=2) + "\n"
    if args.receipt:
        args.receipt.write_text(payload, encoding="utf-8")
    print(payload, end="")

    passed = (
        receipt["summary"]["holds"] == 0
        and receipt["summary"]["unresolved_unknown_effects"] == 0
        and receipt["summary"]["taps_with_pours"] == receipt["summary"]["tap_count"]
    )
    if args.require_pass and not passed:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
