#!/usr/bin/env python3
"""Deterministic source-bound buyer/prime redline -> owner-review delta compiler.

This is an internal decision-support tool. It never signs, accepts, sends, submits,
quotes, invoices, pays, mutates providers, or supplies legal advice.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from datetime import datetime, timezone
from typing import Any

SCHEMA = "buyer-redline-scope-delta/v1"
TRUTH_STATE = "PROPOSED_NOT_ACCEPTED"
DECISIONS = (
    "ACCEPTABLE_AS_WRITTEN",
    "OWNER_REVIEW",
    "REQUOTE_REQUIRED",
    "LEGAL_REVIEW_REQUIRED",
    "HOLD_CONTRADICTION",
)
CATEGORIES = (
    "SCOPE",
    "DELIVERABLES",
    "ACCEPTANCE",
    "PRICE_PAYMENT",
    "SCHEDULE",
    "DATA_SECURITY",
    "IP",
    "LIABILITY_WARRANTY",
    "TERMINATION",
    "DEPENDENCIES",
    "ASSUMPTIONS",
)
LEGAL_CATEGORIES = {"IP", "LIABILITY_WARRANTY", "TERMINATION"}
COMMERCIAL_CATEGORIES = {"SCOPE", "DELIVERABLES", "PRICE_PAYMENT", "SCHEDULE"}
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")

class InputError(ValueError):
    pass

def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def _pairs_no_duplicates(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise InputError(f"duplicate JSON key: {k}")
        out[k] = v
    return out

def _reject_constant(value: str):
    raise InputError(f"non-finite JSON number prohibited: {value}")

def load_json_strict(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    # Unicode normalization is NOT applied: byte/semantic differences remain visible.
    try:
        return json.loads(
            text,
            object_pairs_hook=_pairs_no_duplicates,
            parse_constant=_reject_constant,
        )
    except json.JSONDecodeError as exc:
        raise InputError(f"invalid JSON: {exc}") from exc

def _req_str(obj: dict[str, Any], key: str, where: str) -> str:
    val = obj.get(key)
    if not isinstance(val, str) or not val.strip():
        raise InputError(f"{where}.{key}: required non-empty string")
    return val.strip()

def _req_id(obj: dict[str, Any], key: str, where: str) -> str:
    val = _req_str(obj, key, where)
    if not ID_RE.fullmatch(val):
        raise InputError(f"{where}.{key}: invalid identifier")
    return val

def _sha(value: Any, where: str) -> str:
    if not isinstance(value, str) or not SHA_RE.fullmatch(value):
        raise InputError(f"{where}: expected lowercase SHA-256")
    return value

def _dt(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InputError(f"{where}: timestamp required")
    raw = value.strip()
    candidate = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise InputError(f"{where}: invalid ISO-8601") from exc
    if parsed.tzinfo is None:
        raise InputError(f"{where}: timezone required")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

def _safe_source(value: str, where: str) -> str:
    if value.startswith("https://"):
        authority = value.split("/", 3)[2]
        if "@" in authority or any(c.isspace() for c in value):
            raise InputError(f"{where}: unsafe HTTPS URL")
        return value
    if value.startswith("/") or "\\" in value:
        raise InputError(f"{where}: unsafe repository-relative source")
    parts = value.split("/")
    if not value or any(p in {"", ".", ".."} for p in parts):
        raise InputError(f"{where}: unsafe repository-relative source")
    return value

def _int(value: Any, where: str, *, minimum: int = 0) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise InputError(f"{where}: integer >= {minimum} required")
    return value

def _bool(value: Any, where: str) -> bool:
    if not isinstance(value, bool):
        raise InputError(f"{where}: boolean required")
    return value

def _norm_terms(value: Any, where: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise InputError(f"{where}: object required")
    out = {}
    for key in sorted(value):
        val = value[key]
        if not isinstance(key, str) or not key:
            raise InputError(f"{where}: non-empty string keys required")
        if isinstance(val, bool) or val is None or isinstance(val, str):
            out[key] = val
        elif isinstance(val, int) and not isinstance(val, bool):
            out[key] = val
        else:
            raise InputError(f"{where}.{key}: only string/integer/boolean/null scalar terms allowed")
    return out

def normalize_document(raw: Any, where: str) -> tuple[dict[str, Any], list[dict[str, str]]]:
    if not isinstance(raw, dict):
        raise InputError(f"{where}: object required")
    doc = {
        "document_id": _req_id(raw, "document_id", where),
        "generation": _req_id(raw, "generation", where),
        "source": _safe_source(_req_str(raw, "source", where), f"{where}.source"),
        "source_sha256": _sha(raw.get("source_sha256"), f"{where}.source_sha256"),
        "observed_at": _dt(raw.get("observed_at"), f"{where}.observed_at"),
        "truth_state": _req_str(raw, "truth_state", where),
        "currency": _req_str(raw, "currency", where).upper(),
        "price_total_minor": _int(raw.get("price_total_minor"), f"{where}.price_total_minor"),
        "payment_days": _int(raw.get("payment_days"), f"{where}.payment_days"),
    }
    if doc["truth_state"] != TRUTH_STATE:
        raise InputError(f"{where}.truth_state: must be {TRUTH_STATE}")
    if not re.fullmatch(r"[A-Z]{3}", doc["currency"]):
        raise InputError(f"{where}.currency: ISO-like three-letter code required")
    if where == "counter":
        doc["baseline_generation"] = _req_id(raw, "baseline_generation", where)

    clauses = raw.get("clauses")
    if not isinstance(clauses, list):
        raise InputError(f"{where}.clauses: list required")
    normalized = []
    seen_ids = set()
    logical: dict[str, list[str]] = {}
    for i, clause in enumerate(clauses):
        loc = f"{where}.clauses[{i}]"
        if not isinstance(clause, dict):
            raise InputError(f"{loc}: object required")
        cid = _req_id(clause, "id", loc)
        if cid in seen_ids:
            raise InputError(f"{where}.clauses: duplicate id {cid}")
        seen_ids.add(cid)
        key = _req_id(clause, "logical_key", loc)
        category = _req_str(clause, "category", loc).upper()
        if category not in CATEGORIES:
            raise InputError(f"{loc}.category: unknown category")
        text = _req_str(clause, "text", loc)
        # Preserve Unicode exactly. NFKC-equivalent but byte-distinct text must remain a diff.
        item = {
            "id": cid,
            "logical_key": key,
            "category": category,
            "text": text,
            "terms": _norm_terms(clause.get("terms", {}), f"{loc}.terms"),
            "buyer_visible": _bool(clause.get("buyer_visible", True), f"{loc}.buyer_visible"),
        }
        normalized.append(item)
        logical.setdefault(key, []).append(cid)

    holds = []
    for key, ids in logical.items():
        if len(ids) > 1:
            holds.append({
                "code": "CONFLICTING_LOGICAL_KEY",
                "ref": key,
                "detail": f"{where} contains multiple active clauses for logical key {key}: {','.join(sorted(ids))}",
            })
    doc["clauses"] = sorted(normalized, key=lambda c: (c["logical_key"], c["id"]))
    return doc, holds

def _clause_map(doc: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out = {}
    for clause in doc["clauses"]:
        if clause["logical_key"] not in out:
            out[clause["logical_key"]] = clause
    return out

def _change_kind(before: dict[str, Any] | None, after: dict[str, Any] | None) -> str:
    if before is None:
        return "ADDED"
    if after is None:
        return "DELETED"
    comparable_before = {k: before[k] for k in ("category", "text", "terms", "buyer_visible")}
    comparable_after = {k: after[k] for k in ("category", "text", "terms", "buyer_visible")}
    return "UNCHANGED" if comparable_before == comparable_after else "MODIFIED"

def _impact_for_change(
    key: str,
    kind: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> tuple[str, str]:
    category = (after or before)["category"]
    if kind == "UNCHANGED":
        return "NONE", "No semantic change."
    if before is not None and after is not None and before["category"] != after["category"]:
        return "HOLD", "Clause category changed across the same logical key; classification is contradictory."
    if category in LEGAL_CATEGORIES:
        return "LEGAL", f"{category} language changed; route to qualified legal review without treating this tool as legal advice."
    if category == "PRICE_PAYMENT":
        if before is None or after is None:
            return "REQUOTE", "Price/payment clause added or removed; commercial basis changed."
        b, a = before["terms"], after["terms"]
        if b.get("currency") != a.get("currency"):
            return "REQUOTE", "Clause-level currency changed."
        if b.get("amount_minor") != a.get("amount_minor"):
            return "REQUOTE", "Clause-level amount changed."
        if isinstance(b.get("payment_days"), int) and isinstance(a.get("payment_days"), int) and a["payment_days"] > b["payment_days"]:
            return "REQUOTE", "Payment timing widened."
        return "OWNER", "Price/payment wording changed and needs explicit commercial owner review."
    if category in {"SCOPE", "DELIVERABLES"}:
        if kind in {"ADDED", "DELETED"}:
            return "REQUOTE", f"{category} obligation set changed; do not silently absorb it into the prior price."
        if before["text"] != after["text"] or before["terms"] != after["terms"]:
            return "REQUOTE", f"{category} wording or structured terms changed; commercial effort may have changed."
    if category == "SCHEDULE":
        return "REQUOTE", "Schedule changed; owner must re-evaluate delivery/economics before reusing the prior offer."
    if category == "ACCEPTANCE":
        if kind == "DELETED":
            return "OWNER", "Acceptance criterion was deleted; owner review is required before relying on delivery completion semantics."
        return "OWNER", "Acceptance semantics changed."
    if category == "DATA_SECURITY":
        return "OWNER", "Data/security responsibility changed; owner review and evidence refresh may be required."
    if category in {"DEPENDENCIES", "ASSUMPTIONS"}:
        return "OWNER", f"{category} changed; verify responsibility and scope effects."
    return "OWNER", "Material clause changed and requires owner review."

def compile_case(raw: Any) -> tuple[dict[str, Any], str, dict[str, Any]]:
    if not isinstance(raw, dict):
        raise InputError("root: object required")
    if raw.get("schema") != SCHEMA:
        raise InputError(f"schema: expected {SCHEMA}")
    as_of = _dt(raw.get("as_of"), "as_of")
    baseline, baseline_holds = normalize_document(raw.get("baseline"), "baseline")
    counter, counter_holds = normalize_document(raw.get("counter"), "counter")
    holds = baseline_holds + counter_holds

    if counter["baseline_generation"] != baseline["generation"]:
        holds.append({
            "code": "STALE_BASELINE_GENERATION",
            "ref": counter["baseline_generation"],
            "detail": f"counter targets {counter['baseline_generation']} but retained baseline is {baseline['generation']}",
        })

    if baseline["currency"] != counter["currency"]:
        # Currency change is not a parser contradiction; it is a requote trigger.
        currency_changed = True
    else:
        currency_changed = False

    # Explicit commercial-header contradictions inside the counter are HOLDs.
    counter_price_clauses = [c for c in counter["clauses"] if c["category"] == "PRICE_PAYMENT"]
    clause_currencies = {
        c["terms"].get("currency")
        for c in counter_price_clauses
        if isinstance(c["terms"].get("currency"), str)
    }
    if len(clause_currencies) > 1:
        holds.append({
            "code": "CONFLICTING_CURRENCIES",
            "ref": "counter",
            "detail": "counter contains multiple active clause-level currencies",
        })
    if clause_currencies and counter["currency"] not in clause_currencies:
        holds.append({
            "code": "HEADER_CLAUSE_CURRENCY_CONFLICT",
            "ref": "counter",
            "detail": "counter document currency conflicts with its price/payment clause currency",
        })

    bmap, cmap = _clause_map(baseline), _clause_map(counter)
    issues = []
    impacts = []
    for key in sorted(set(bmap) | set(cmap)):
        before, after = bmap.get(key), cmap.get(key)
        kind = _change_kind(before, after)
        impact, rationale = _impact_for_change(key, kind, before, after)
        if impact == "HOLD":
            holds.append({"code": "CATEGORY_CONTRADICTION", "ref": key, "detail": rationale})
        if kind != "UNCHANGED":
            issues.append({
                "logical_key": key,
                "change": kind,
                "category": (after or before)["category"],
                "impact": impact,
                "baseline_clause_id": before["id"] if before else None,
                "counter_clause_id": after["id"] if after else None,
                "rationale": rationale,
            })
            impacts.append(impact)

    header_issues = []
    if currency_changed:
        header_issues.append({
            "field": "currency",
            "baseline": baseline["currency"],
            "counter": counter["currency"],
            "impact": "REQUOTE",
            "rationale": "Document currency changed; never roll prior economics into a new currency silently.",
        })
        impacts.append("REQUOTE")
    if baseline["price_total_minor"] != counter["price_total_minor"]:
        header_issues.append({
            "field": "price_total_minor",
            "baseline": baseline["price_total_minor"],
            "counter": counter["price_total_minor"],
            "impact": "REQUOTE",
            "rationale": "Proposed total price changed.",
        })
        impacts.append("REQUOTE")
    if baseline["payment_days"] != counter["payment_days"]:
        impact = "REQUOTE" if counter["payment_days"] > baseline["payment_days"] else "OWNER"
        header_issues.append({
            "field": "payment_days",
            "baseline": baseline["payment_days"],
            "counter": counter["payment_days"],
            "impact": impact,
            "rationale": "Payment timing changed; explicit commercial review is required.",
        })
        impacts.append(impact)

    holds = sorted(holds, key=lambda h: (h["code"], h["ref"], h["detail"]))
    if holds:
        decision = "HOLD_CONTRADICTION"
    elif "LEGAL" in impacts:
        decision = "LEGAL_REVIEW_REQUIRED"
    elif "REQUOTE" in impacts:
        decision = "REQUOTE_REQUIRED"
    elif "OWNER" in impacts:
        decision = "OWNER_REVIEW"
    else:
        decision = "ACCEPTABLE_AS_WRITTEN"

    normalized = {
        "schema": SCHEMA,
        "as_of": as_of,
        "truth_state": TRUTH_STATE,
        "baseline": baseline,
        "counter": counter,
        "decision": decision,
        "header_issues": header_issues,
        "issues": issues,
        "holds": holds,
    }
    packet = render_packet(normalized)
    receipt = {
        "schema": SCHEMA,
        "truth_state": TRUTH_STATE,
        "decision": decision,
        "as_of": as_of,
        "baseline_document_id": baseline["document_id"],
        "baseline_generation": baseline["generation"],
        "baseline_source_sha256": baseline["source_sha256"],
        "counter_document_id": counter["document_id"],
        "counter_generation": counter["generation"],
        "counter_source_sha256": counter["source_sha256"],
        "normalized_sha256": sha256_bytes(canonical_json(normalized)),
        "packet_sha256": sha256_bytes(packet.encode("utf-8")),
        "issue_count": len(issues) + len(header_issues),
        "hold_count": len(holds),
    }
    return normalized, packet, receipt

def _esc(value: Any) -> str:
    return str(value).replace("\r", " ").replace("\n", " ").replace("|", "\\|")

def render_packet(result: dict[str, Any]) -> str:
    b, c = result["baseline"], result["counter"]
    lines = [
        "# Buyer / Prime Redline Owner Review Packet",
        "",
        f"- **Decision:** `{result['decision']}`",
        f"- **Truth state:** `{TRUTH_STATE}`",
        f"- **As of:** `{result['as_of']}`",
        f"- **Baseline:** `{b['document_id']}` generation `{b['generation']}` / `{b['source_sha256']}`",
        f"- **Counter:** `{c['document_id']}` generation `{c['generation']}` / `{c['source_sha256']}`",
        "",
        "> Internal decision-support only. This packet is not a signature, acceptance, legal opinion,",
        "> submission, invoice, payment instruction, award, or revenue event.",
        "",
        "## Commercial header delta",
        "",
        "| Field | Baseline | Counter | Impact | Rationale |",
        "|---|---:|---:|---|---|",
    ]
    if result["header_issues"]:
        for i in result["header_issues"]:
            lines.append(f"| `{i['field']}` | `{_esc(i['baseline'])}` | `{_esc(i['counter'])}` | `{i['impact']}` | {_esc(i['rationale'])} |")
    else:
        lines.append("| — | — | — | `NONE` | No commercial-header delta. |")

    lines += [
        "",
        "## Clause changes",
        "",
        "| Logical key | Change | Category | Impact | Baseline | Counter | Rationale |",
        "|---|---|---|---|---|---|---|",
    ]
    if result["issues"]:
        for i in result["issues"]:
            lines.append(
                f"| `{i['logical_key']}` | `{i['change']}` | `{i['category']}` | `{i['impact']}` | "
                f"`{i['baseline_clause_id'] or '—'}` | `{i['counter_clause_id'] or '—'}` | {_esc(i['rationale'])} |"
            )
    else:
        lines.append("| — | `UNCHANGED` | — | `NONE` | — | — | No semantic clause changes. |")

    lines += ["", "## Holds", ""]
    if result["holds"]:
        for h in result["holds"]:
            lines.append(f"- `{h['code']}` / `{h['ref']}` — {_esc(h['detail'])}")
    else:
        lines.append("- None.")

    lines += [
        "",
        "## Owner action boundary",
        "",
        "- `ACCEPTABLE_AS_WRITTEN` means this compiler detected no semantic delta; it does not accept or sign anything.",
        "- `OWNER_REVIEW` requires explicit commercial/operational owner judgment.",
        "- `REQUOTE_REQUIRED` means prior economics must not be silently reused against the changed scope/timing/payment basis.",
        "- `LEGAL_REVIEW_REQUIRED` routes changed IP/liability/warranty/termination language for qualified human legal review; this tool gives no legal advice.",
        "- `HOLD_CONTRADICTION` means source/generation/category/currency conflicts prevent a trustworthy decision.",
        "",
        "No external contact, signature, contract acceptance, buyer submission, payment/provider mutation, or revenue recognition is authorized.",
        "",
    ]
    return "\n".join(lines)

def _atomic_write(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass

def compile_to_dir(input_path: Path, out_dir: Path, *, fail_on_hold: bool = False) -> int:
    raw = load_json_strict(input_path)
    result, packet, receipt = compile_case(raw)
    out_dir.mkdir(parents=True, exist_ok=True)
    _atomic_write(out_dir / "normalized.json", canonical_json(result))
    _atomic_write(out_dir / "packet.md", packet.encode("utf-8"))
    _atomic_write(out_dir / "receipt.json", canonical_json(receipt))
    if fail_on_hold and receipt["decision"] == "HOLD_CONTRADICTION":
        return 2
    return 0

def verify(input_path: Path, packet_path: Path, receipt_path: Path) -> int:
    raw = load_json_strict(input_path)
    _, packet, receipt = compile_case(raw)
    actual_packet = packet_path.read_bytes()
    actual_receipt = load_json_strict(receipt_path)
    problems = []
    if actual_packet != packet.encode("utf-8"):
        problems.append("packet differs from deterministic compile")
    if actual_receipt != receipt:
        problems.append("receipt differs from deterministic compile")
    if actual_receipt.get("packet_sha256") != sha256_bytes(actual_packet):
        problems.append("packet digest mismatch")
    if problems:
        for p in problems:
            print(f"VERIFY_FAIL: {p}", file=sys.stderr)
        return 1
    print(f"VERIFY_OK decision={receipt['decision']} packet_sha256={receipt['packet_sha256']}")
    return 0

def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("compile")
    c.add_argument("--input", required=True, type=Path)
    c.add_argument("--out-dir", required=True, type=Path)
    c.add_argument("--fail-on-hold", action="store_true")
    v = sub.add_parser("verify")
    v.add_argument("--input", required=True, type=Path)
    v.add_argument("--packet", required=True, type=Path)
    v.add_argument("--receipt", required=True, type=Path)
    return p

def main(argv=None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.cmd == "compile":
            return compile_to_dir(args.input, args.out_dir, fail_on_hold=args.fail_on_hold)
        return verify(args.input, args.packet, args.receipt)
    except (InputError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
