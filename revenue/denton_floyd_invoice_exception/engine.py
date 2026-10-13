#!/usr/bin/env python3
"""Deterministic read-only invoice/PO/vendor exception control.

This module intentionally has no provider or accounting-system write capability. It
accepts a bounded evidence packet, validates exact types and source bindings, and
emits deterministic READY/HOLD decisions plus tamper-evident projections.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

SCHEMA_VERSION = "denton-floyd-invoice-exception/v1"
RESULT_VERSION = "denton-floyd-invoice-exception-result/v1"
ALLOWED_CURRENCIES = {"USD"}
MAX_EVIDENCE_AGE_DAYS = 45
MAX_TEXT = 240


class EvidenceError(ValueError):
    """Fail-closed input or verification error."""


def _pairs_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise EvidenceError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def loads_strict(text: str) -> Any:
    try:
        return json.loads(
            text,
            object_pairs_hook=_pairs_no_duplicates,
            parse_constant=lambda token: (_ for _ in ()).throw(
                EvidenceError(f"non-finite JSON number: {token}")
            ),
        )
    except EvidenceError:
        raise
    except json.JSONDecodeError as exc:
        raise EvidenceError(f"invalid JSON: {exc.msg}") from exc


def canonical_bytes(value: Any) -> bytes:
    _validate_json_value(value, "$")
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _validate_json_value(value: Any, path: str) -> None:
    if value is None or type(value) is bool or type(value) is str or type(value) is int:
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise EvidenceError(f"{path}: non-finite float")
        return
    if type(value) is list:
        for i, item in enumerate(value):
            _validate_json_value(item, f"{path}[{i}]")
        return
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise EvidenceError(f"{path}: non-string object key")
            _validate_json_value(item, f"{path}.{key}")
        return
    raise EvidenceError(f"{path}: unsupported value type {type(value).__name__}")


def _expect_dict(value: Any, path: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise EvidenceError(f"{path}: expected object")
    return value


def _expect_list(value: Any, path: str) -> list[Any]:
    if type(value) is not list:
        raise EvidenceError(f"{path}: expected array")
    return value


def _expect_str(value: Any, path: str, *, max_len: int = MAX_TEXT) -> str:
    if type(value) is not str:
        raise EvidenceError(f"{path}: expected string")
    if not value or value.strip() != value:
        raise EvidenceError(f"{path}: empty or surrounding whitespace")
    if len(value) > max_len:
        raise EvidenceError(f"{path}: too long")
    if any(ord(ch) < 32 for ch in value):
        raise EvidenceError(f"{path}: control character")
    return value


def _expect_keys(obj: Mapping[str, Any], required: set[str], optional: set[str], path: str) -> None:
    keys = set(obj)
    missing = sorted(required - keys)
    unknown = sorted(keys - required - optional)
    if missing:
        raise EvidenceError(f"{path}: missing fields {missing}")
    if unknown:
        raise EvidenceError(f"{path}: unknown fields {unknown}")


def _parse_date(value: Any, path: str) -> date:
    s = _expect_str(value, path, max_len=10)
    try:
        parsed = date.fromisoformat(s)
    except ValueError as exc:
        raise EvidenceError(f"{path}: expected YYYY-MM-DD") from exc
    if parsed.isoformat() != s:
        raise EvidenceError(f"{path}: non-canonical date")
    return parsed


def _parse_instant(value: Any, path: str) -> datetime:
    s = _expect_str(value, path, max_len=32)
    if not s.endswith("Z"):
        raise EvidenceError(f"{path}: instant must end in Z")
    try:
        parsed = datetime.fromisoformat(s[:-1] + "+00:00")
    except ValueError as exc:
        raise EvidenceError(f"{path}: invalid UTC instant") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise EvidenceError(f"{path}: instant must be UTC")
    canonical = parsed.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    if canonical != s:
        raise EvidenceError(f"{path}: instant must use canonical seconds precision")
    return parsed


def _money(value: Any, path: str) -> Decimal:
    s = _expect_str(value, path, max_len=32)
    try:
        d = Decimal(s)
    except InvalidOperation as exc:
        raise EvidenceError(f"{path}: invalid decimal") from exc
    if not d.is_finite() or d < 0:
        raise EvidenceError(f"{path}: amount must be finite and nonnegative")
    if d.as_tuple().exponent != -2:
        raise EvidenceError(f"{path}: amount must have exactly two decimal places")
    if d > Decimal("999999999999.99"):
        raise EvidenceError(f"{path}: amount too large")
    return d


def _parse_sha256(value: Any, path: str) -> str:
    s = _expect_str(value, path, max_len=64)
    if len(s) != 64 or any(ch not in "0123456789abcdef" for ch in s):
        raise EvidenceError(f"{path}: expected lowercase sha256")
    return s


@dataclass(frozen=True)
class Decision:
    invoice_id: str
    state: str
    reasons: tuple[str, ...]
    invoice_digest: str
    po_digest: str | None
    vendor_digest: str | None

    def as_json(self) -> dict[str, Any]:
        return {
            "invoice_id": self.invoice_id,
            "state": self.state,
            "reasons": list(self.reasons),
            "invoice_digest": self.invoice_digest,
            "po_digest": self.po_digest,
            "vendor_digest": self.vendor_digest,
        }


def _index_unique(rows: Sequence[dict[str, Any]], key: str, path: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for i, row in enumerate(rows):
        value = _expect_str(row.get(key), f"{path}[{i}].{key}")
        if value in out:
            raise EvidenceError(f"{path}: duplicate {key} {value}")
        out[value] = row
    return out


def _validate_vendor(raw: Any, i: int) -> dict[str, Any]:
    path = f"$.vendors[{i}]"
    obj = _expect_dict(raw, path)
    _expect_keys(obj, {"vendor_id", "name", "status", "currency", "snapshot_sha256"}, set(), path)
    _expect_str(obj["vendor_id"], f"{path}.vendor_id", max_len=80)
    _expect_str(obj["name"], f"{path}.name", max_len=160)
    if obj["status"] not in {"ACTIVE", "INACTIVE"}:
        raise EvidenceError(f"{path}.status: expected ACTIVE or INACTIVE")
    if obj["currency"] not in ALLOWED_CURRENCIES:
        raise EvidenceError(f"{path}.currency: unsupported currency")
    _parse_sha256(obj["snapshot_sha256"], f"{path}.snapshot_sha256")
    return dict(obj)


def _validate_po(raw: Any, i: int) -> dict[str, Any]:
    path = f"$.purchase_orders[{i}]"
    obj = _expect_dict(raw, path)
    _expect_keys(
        obj,
        {"po_id", "vendor_id", "currency", "total", "issued_date", "status", "snapshot_sha256"},
        set(),
        path,
    )
    _expect_str(obj["po_id"], f"{path}.po_id", max_len=80)
    _expect_str(obj["vendor_id"], f"{path}.vendor_id", max_len=80)
    if obj["currency"] not in ALLOWED_CURRENCIES:
        raise EvidenceError(f"{path}.currency: unsupported currency")
    _money(obj["total"], f"{path}.total")
    _parse_date(obj["issued_date"], f"{path}.issued_date")
    if obj["status"] not in {"OPEN", "CLOSED", "VOID"}:
        raise EvidenceError(f"{path}.status: invalid PO status")
    _parse_sha256(obj["snapshot_sha256"], f"{path}.snapshot_sha256")
    return dict(obj)


def _validate_invoice(raw: Any, i: int) -> dict[str, Any]:
    path = f"$.invoices[{i}]"
    obj = _expect_dict(raw, path)
    _expect_keys(
        obj,
        {
            "invoice_id", "vendor_id", "po_id", "currency", "amount", "invoice_date",
            "due_date", "source_ref", "snapshot_sha256"
        },
        set(),
        path,
    )
    _expect_str(obj["invoice_id"], f"{path}.invoice_id", max_len=80)
    _expect_str(obj["vendor_id"], f"{path}.vendor_id", max_len=80)
    _expect_str(obj["po_id"], f"{path}.po_id", max_len=80)
    if obj["currency"] not in ALLOWED_CURRENCIES:
        raise EvidenceError(f"{path}.currency: unsupported currency")
    _money(obj["amount"], f"{path}.amount")
    _parse_date(obj["invoice_date"], f"{path}.invoice_date")
    _parse_date(obj["due_date"], f"{path}.due_date")
    _expect_str(obj["source_ref"], f"{path}.source_ref", max_len=160)
    _parse_sha256(obj["snapshot_sha256"], f"{path}.snapshot_sha256")
    return dict(obj)


def compile_packet(packet: Any, *, as_of: str) -> dict[str, Any]:
    root = _expect_dict(packet, "$")
    _expect_keys(
        root,
        {"schema_version", "captured_at", "vendors", "purchase_orders", "invoices"},
        {"packet_id"},
        "$",
    )
    if root["schema_version"] != SCHEMA_VERSION:
        raise EvidenceError("$.schema_version: unsupported schema")
    captured = _parse_instant(root["captured_at"], "$.captured_at")
    now = _parse_instant(as_of, "$as_of")
    if captured > now:
        raise EvidenceError("$.captured_at: future evidence")
    if (now - captured).total_seconds() > MAX_EVIDENCE_AGE_DAYS * 86400:
        raise EvidenceError("$.captured_at: stale evidence")
    if "packet_id" in root:
        _expect_str(root["packet_id"], "$.packet_id", max_len=100)

    vendors = [_validate_vendor(v, i) for i, v in enumerate(_expect_list(root["vendors"], "$.vendors"))]
    pos = [_validate_po(v, i) for i, v in enumerate(_expect_list(root["purchase_orders"], "$.purchase_orders"))]
    invoices = [_validate_invoice(v, i) for i, v in enumerate(_expect_list(root["invoices"], "$.invoices"))]

    vendor_ix = _index_unique(vendors, "vendor_id", "$.vendors")
    po_ix = _index_unique(pos, "po_id", "$.purchase_orders")
    inv_ix = _index_unique(invoices, "invoice_id", "$.invoices")

    # Repeated vendor/source/amount/date is duplicate evidence even if invoice_id differs.
    semantic_groups: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for inv in invoices:
        semantic_key = (inv["vendor_id"], inv["source_ref"], inv["amount"], inv["invoice_date"])
        semantic_groups.setdefault(semantic_key, []).append(inv)
    semantic_dupes = {
        inv["invoice_id"]
        for group in semantic_groups.values()
        if len(group) > 1
        for inv in group
    }

    # First apply every existing row-level gate.  Cumulative PO utilization is a
    # second-stage constraint over rows that would otherwise be READY: a row already
    # held for bad/missing/duplicate evidence is not treated as authorized spend.
    evaluated: dict[str, tuple[dict[str, Any], dict[str, Any] | None, dict[str, Any] | None, list[str]]] = {}
    for invoice_id in sorted(inv_ix):
        inv = inv_ix[invoice_id]
        reasons: list[str] = []
        vendor = vendor_ix.get(inv["vendor_id"])
        po = po_ix.get(inv["po_id"])

        if invoice_id in semantic_dupes:
            reasons.append("DUPLICATE_INVOICE_EVIDENCE")
        if vendor is None:
            reasons.append("VENDOR_MISSING")
        else:
            if vendor["status"] != "ACTIVE":
                reasons.append("VENDOR_INACTIVE")
            if vendor["currency"] != inv["currency"]:
                reasons.append("VENDOR_CURRENCY_MISMATCH")
        if po is None:
            reasons.append("PO_MISSING")
        else:
            if po["vendor_id"] != inv["vendor_id"]:
                reasons.append("PO_VENDOR_MISMATCH")
            if po["currency"] != inv["currency"]:
                reasons.append("PO_CURRENCY_MISMATCH")
            if po["status"] != "OPEN":
                reasons.append("PO_NOT_OPEN")
            if _money(inv["amount"], "invoice.amount") > _money(po["total"], "po.total"):
                reasons.append("INVOICE_EXCEEDS_PO")
            if _parse_date(inv["invoice_date"], "invoice.invoice_date") < _parse_date(po["issued_date"], "po.issued_date"):
                reasons.append("INVOICE_PREDATES_PO")
        if _parse_date(inv["due_date"], "invoice.due_date") < _parse_date(inv["invoice_date"], "invoice.invoice_date"):
            reasons.append("DUE_DATE_PRECEDES_INVOICE")

        evaluated[invoice_id] = (inv, vendor, po, sorted(set(reasons)))

    candidate_exposure_by_po: dict[str, Decimal] = {}
    for inv, _vendor, po, reasons in evaluated.values():
        if reasons or po is None:
            continue
        po_id = inv["po_id"]
        candidate_exposure_by_po[po_id] = (
            candidate_exposure_by_po.get(po_id, Decimal("0.00"))
            + _money(inv["amount"], "invoice.amount")
        )

    cumulative_overrun_pos = {
        po_id
        for po_id, exposure in candidate_exposure_by_po.items()
        if exposure > _money(po_ix[po_id]["total"], "po.total")
    }

    decisions: list[Decision] = []
    for invoice_id in sorted(inv_ix):
        inv, vendor, po, base_reasons = evaluated[invoice_id]
        reasons = list(base_reasons)
        if not reasons and inv["po_id"] in cumulative_overrun_pos:
            reasons.append("PO_CUMULATIVE_AMOUNT_EXCEEDED")

        decisions.append(
            Decision(
                invoice_id=invoice_id,
                state="READY" if not reasons else "HOLD",
                reasons=tuple(sorted(set(reasons))),
                invoice_digest=digest(inv),
                po_digest=digest(po) if po is not None else None,
                vendor_digest=digest(vendor) if vendor is not None else None,
            )
        )

    packet_projection = {
        "schema_version": root["schema_version"],
        "captured_at": root["captured_at"],
        "packet_id": root.get("packet_id"),
        "vendors": vendors,
        "purchase_orders": pos,
        "invoices": invoices,
    }
    decision_json = [d.as_json() for d in decisions]
    counts = {
        "total": len(decisions),
        "ready": sum(d.state == "READY" for d in decisions),
        "hold": sum(d.state == "HOLD" for d in decisions),
    }
    manifest_core = {
        "result_version": RESULT_VERSION,
        "as_of": as_of,
        "packet_sha256": digest(packet_projection),
        "decisions_sha256": digest(decision_json),
        "counts": counts,
        "authority": {
            "read_only": True,
            "approve_invoice": False,
            "post_to_ledger": False,
            "release_payment": False,
            "change_vendor": False,
        },
    }
    manifest = dict(manifest_core)
    manifest["manifest_sha256"] = digest(manifest_core)
    return {
        "manifest": manifest,
        "decisions": decision_json,
        "queue": [d for d in decision_json if d["state"] == "HOLD"],
    }


def verify_result(packet: Any, result: Any, *, as_of: str) -> bool:
    expected = compile_packet(packet, as_of=as_of)
    if canonical_bytes(expected) != canonical_bytes(result):
        raise EvidenceError("result mismatch: packet/as_of do not reproduce supplied result")
    manifest = _expect_dict(result.get("manifest") if type(result) is dict else None, "$.manifest")
    supplied = manifest.get("manifest_sha256")
    _parse_sha256(supplied, "$.manifest.manifest_sha256")
    core = {k: v for k, v in manifest.items() if k != "manifest_sha256"}
    if digest(core) != supplied:
        raise EvidenceError("manifest digest mismatch")
    return True


def decisions_csv(result: Mapping[str, Any]) -> str:
    out = io.StringIO(newline="")
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(["invoice_id", "state", "reasons", "invoice_digest", "po_digest", "vendor_digest"])
    for row in result["decisions"]:
        writer.writerow([
            row["invoice_id"], row["state"], ";".join(row["reasons"]), row["invoice_digest"],
            row["po_digest"] or "", row["vendor_digest"] or ""
        ])
    return out.getvalue()


def summary_markdown(result: Mapping[str, Any]) -> str:
    m = result["manifest"]
    lines = [
        "# Invoice Exception Control Receipt",
        "",
        f"- Result version: `{m['result_version']}`",
        f"- As of: `{m['as_of']}`",
        f"- Packet SHA-256: `{m['packet_sha256']}`",
        f"- Decisions SHA-256: `{m['decisions_sha256']}`",
        f"- READY: **{m['counts']['ready']}**",
        f"- HOLD: **{m['counts']['hold']}**",
        "",
        "| Invoice | State | Reasons |",
        "|---|---|---|",
    ]
    for row in result["decisions"]:
        reasons = ", ".join(row["reasons"]) if row["reasons"] else "—"
        lines.append(f"| `{row['invoice_id']}` | **{row['state']}** | {reasons} |")
    lines.extend([
        "",
        "> Read-only evidence classification only. This receipt cannot approve an invoice, post to a ledger, modify vendor records, or release payment.",
        "",
    ])
    return "\n".join(lines)


def _read_json(path: str) -> Any:
    return loads_strict(Path(path).read_text(encoding="utf-8"))


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def cli(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("compile")
    c.add_argument("packet")
    c.add_argument("--as-of", required=True)
    c.add_argument("--out-dir", required=True)
    v = sub.add_parser("verify")
    v.add_argument("packet")
    v.add_argument("result")
    v.add_argument("--as-of", required=True)
    args = p.parse_args(argv)

    try:
        packet = _read_json(args.packet)
        if args.cmd == "compile":
            result = compile_packet(packet, as_of=args.as_of)
            out = Path(args.out_dir)
            _write(out / "result.json", json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
            _write(out / "decisions.csv", decisions_csv(result))
            _write(out / "receipt.md", summary_markdown(result))
            print(json.dumps(result["manifest"], sort_keys=True, separators=(",", ":")))
            return 0
        result = _read_json(args.result)
        verify_result(packet, result, as_of=args.as_of)
        print("VERIFIED")
        return 0
    except (EvidenceError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli())
