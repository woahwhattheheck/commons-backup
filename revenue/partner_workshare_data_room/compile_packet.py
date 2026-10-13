#!/usr/bin/env python3
"""Deterministic, evidence-bound partner/workshare owner-review packet compiler.

This module is intentionally stdlib-only and side-effect bounded: it reads one JSON input,
writes packet.md + receipt.json beneath an explicit output directory, and never performs
network, messaging, pricing, payment, submission, or provider mutations.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
import tempfile
from datetime import datetime, timezone
from typing import Any, Iterable

SCHEMA_VERSION = "partner-workshare-data-room/v1"
TRUTH_CEILING = "PROPOSED_NOT_ACCEPTED"
ALLOWED_RELATIONSHIP_STATES = {"PROSPECT", "DISCUSSION", TRUTH_CEILING}
ALLOWED_EVIDENCE_STATUS = {"VERIFIED", "PROVIDED_UNVERIFIED", "MISSING", "CONFLICTING"}
SENSITIVE_CLAIM_CATEGORIES = {
    "CAPABILITY", "CERTIFICATION", "PAST_PERFORMANCE", "SECURITY",
    "PRICING_BASIS", "PARTNER_RELATIONSHIP",
}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
PLACEHOLDER_STATE = "PLACEHOLDER_OWNER_REVIEW"
ACCEPTANCE_STATE = "NOT_REQUESTED_OR_ACCEPTED"


class InputError(ValueError):
    """Raised for malformed or authority-violating input."""


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _parse_dt(value: str, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise InputError(f"{field}: expected non-empty ISO-8601 timestamp")
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise InputError(f"{field}: invalid ISO-8601 timestamp") from exc
    if dt.tzinfo is None:
        raise InputError(f"{field}: timezone offset required")
    return dt.astimezone(timezone.utc)


def _required_str(obj: dict[str, Any], key: str, where: str) -> str:
    value = obj.get(key)
    if not isinstance(value, str) or not value.strip():
        raise InputError(f"{where}.{key}: required non-empty string")
    return value.strip()


def _required_id(obj: dict[str, Any], key: str, where: str) -> str:
    value = _required_str(obj, key, where)
    if not ID_RE.fullmatch(value):
        raise InputError(f"{where}.{key}: invalid identifier")
    return value


def _list(obj: dict[str, Any], key: str, where: str, *, required: bool = True) -> list[Any]:
    value = obj.get(key)
    if value is None and not required:
        return []
    if not isinstance(value, list):
        raise InputError(f"{where}.{key}: expected list")
    return value


def _dict(obj: dict[str, Any], key: str, where: str) -> dict[str, Any]:
    value = obj.get(key)
    if not isinstance(value, dict):
        raise InputError(f"{where}.{key}: expected object")
    return value


def _sha(value: Any, field: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise InputError(f"{field}: expected lowercase SHA-256 hex")
    return value


def _safe_source(value: str, field: str) -> str:
    """Allow HTTPS evidence URLs or bounded repository-relative evidence paths."""
    if value.startswith("https://"):
        if any(ch.isspace() for ch in value) or "@" in value.split("/", 3)[2]:
            raise InputError(f"{field}: unsafe HTTPS URL")
        return value
    p = PurePosixPath(value)
    if p.is_absolute() or not value or "\\" in value or any(part in {"", ".", ".."} for part in p.parts):
        raise InputError(f"{field}: expected HTTPS URL or safe repository-relative path")
    return value


def _unique(items: Iterable[str], where: str) -> None:
    seen: set[str] = set()
    for item in items:
        if item in seen:
            raise InputError(f"{where}: duplicate id {item!r}")
        seen.add(item)


def _strings(values: list[Any], where: str, *, min_items: int = 0) -> list[str]:
    if len(values) < min_items:
        raise InputError(f"{where}: expected at least {min_items} item(s)")
    out: list[str] = []
    for i, value in enumerate(values):
        if not isinstance(value, str) or not value.strip():
            raise InputError(f"{where}[{i}]: expected non-empty string")
        out.append(value.strip())
    return out


def validate_and_normalize(raw: Any) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Return canonical normalized input plus HOLD reasons.

    Malformed/authority-violating data raises InputError. Evidence insufficiency compiles
    deterministically to HOLD so an owner can inspect the packet without truth escalation.
    """
    if not isinstance(raw, dict):
        raise InputError("root: expected object")
    if raw.get("schema") != SCHEMA_VERSION:
        raise InputError(f"schema: expected {SCHEMA_VERSION!r}")
    if raw.get("truth_ceiling") != TRUTH_CEILING:
        raise InputError(f"truth_ceiling: must be {TRUTH_CEILING}")

    doc = copy.deepcopy(raw)
    as_of = _parse_dt(_required_str(doc, "as_of", "root"), "as_of")
    as_of_s = as_of.isoformat().replace("+00:00", "Z")
    doc["as_of"] = as_of_s

    opportunity = _dict(doc, "opportunity", "root")
    _required_id(opportunity, "id", "opportunity")
    for key in ("title", "buyer", "scope_summary"):
        opportunity[key] = _required_str(opportunity, key, "opportunity")
    opportunity["source"] = _safe_source(
        _required_str(opportunity, "source", "opportunity"), "opportunity.source"
    )
    opportunity["source_sha256"] = _sha(opportunity.get("source_sha256"), "opportunity.source_sha256")
    opportunity["observed_at"] = _parse_dt(
        _required_str(opportunity, "observed_at", "opportunity"), "opportunity.observed_at"
    ).isoformat().replace("+00:00", "Z")
    if "due_at" in opportunity and opportunity["due_at"] is not None:
        opportunity["due_at"] = _parse_dt(opportunity["due_at"], "opportunity.due_at").isoformat().replace("+00:00", "Z")

    parties = _list(doc, "parties", "root")
    if len(parties) < 2:
        raise InputError("parties: expected at least prime + prospective partner")
    party_ids: list[str] = []
    prime_count = 0
    for i, party in enumerate(parties):
        if not isinstance(party, dict):
            raise InputError(f"parties[{i}]: expected object")
        pid = _required_id(party, "id", f"parties[{i}]")
        party_ids.append(pid)
        party["name"] = _required_str(party, "name", f"parties[{i}]")
        role = _required_str(party, "role", f"parties[{i}]").upper()
        if role not in {"PRIME", "PROSPECTIVE_PARTNER"}:
            raise InputError(f"parties[{i}].role: expected PRIME or PROSPECTIVE_PARTNER")
        party["role"] = role
        prime_count += role == "PRIME"
        rel = _required_str(party, "relationship_state", f"parties[{i}]").upper()
        if rel not in ALLOWED_RELATIONSHIP_STATES:
            raise InputError(f"parties[{i}].relationship_state: exceeds truth ceiling")
        if role == "PROSPECTIVE_PARTNER" and rel not in {"PROSPECT", "DISCUSSION", TRUTH_CEILING}:
            raise InputError(f"parties[{i}].relationship_state: invalid prospective state")
        party["relationship_state"] = rel
    _unique(party_ids, "parties")
    if prime_count != 1:
        raise InputError("parties: exactly one PRIME required")
    party_set = set(party_ids)

    receipts = _list(doc, "evidence_receipts", "root")
    receipt_ids: list[str] = []
    receipt_by_id: dict[str, dict[str, Any]] = {}
    for i, receipt in enumerate(receipts):
        if not isinstance(receipt, dict):
            raise InputError(f"evidence_receipts[{i}]: expected object")
        rid = _required_id(receipt, "id", f"evidence_receipts[{i}]")
        receipt_ids.append(rid)
        subject = _required_id(receipt, "subject_party_id", f"evidence_receipts[{i}]")
        if subject not in party_set:
            raise InputError(f"evidence_receipts[{i}].subject_party_id: unknown party")
        receipt["kind"] = _required_str(receipt, "kind", f"evidence_receipts[{i}]").upper()
        status = _required_str(receipt, "status", f"evidence_receipts[{i}]").upper()
        if status not in ALLOWED_EVIDENCE_STATUS:
            raise InputError(f"evidence_receipts[{i}].status: invalid")
        receipt["status"] = status
        receipt["source"] = _safe_source(
            _required_str(receipt, "source", f"evidence_receipts[{i}]"),
            f"evidence_receipts[{i}].source",
        )
        receipt["source_sha256"] = _sha(
            receipt.get("source_sha256"), f"evidence_receipts[{i}].source_sha256"
        )
        receipt["observed_at"] = _parse_dt(
            _required_str(receipt, "observed_at", f"evidence_receipts[{i}]"),
            f"evidence_receipts[{i}].observed_at",
        ).isoformat().replace("+00:00", "Z")
        if receipt.get("valid_through") is not None:
            receipt["valid_through"] = _parse_dt(
                receipt["valid_through"], f"evidence_receipts[{i}].valid_through"
            ).isoformat().replace("+00:00", "Z")
        receipt["summary"] = _required_str(receipt, "summary", f"evidence_receipts[{i}]")
        receipt_by_id[rid] = receipt
    _unique(receipt_ids, "evidence_receipts")

    holds: list[dict[str, str]] = []

    def evidence_ok(eid: str, subject: str | None = None, kind: str | None = None) -> tuple[bool, str]:
        rec = receipt_by_id.get(eid)
        if rec is None:
            return False, "missing receipt"
        if rec["status"] != "VERIFIED":
            return False, f"receipt status {rec['status']}"
        if subject is not None and rec["subject_party_id"] != subject:
            return False, "receipt subject mismatch"
        if kind is not None and rec["kind"] != kind:
            return False, f"receipt kind {rec['kind']} does not match {kind}"
        if rec.get("valid_through") and _parse_dt(rec["valid_through"], "valid_through") < as_of:
            return False, "receipt expired before as_of"
        return True, ""

    claims = _list(doc, "claims", "root")
    claim_ids: list[str] = []
    for i, claim in enumerate(claims):
        if not isinstance(claim, dict):
            raise InputError(f"claims[{i}]: expected object")
        cid = _required_id(claim, "id", f"claims[{i}]")
        claim_ids.append(cid)
        subject = _required_id(claim, "subject_party_id", f"claims[{i}]")
        if subject not in party_set:
            raise InputError(f"claims[{i}].subject_party_id: unknown party")
        category = _required_str(claim, "category", f"claims[{i}]").upper()
        claim["category"] = category
        claim["text"] = _required_str(claim, "text", f"claims[{i}]")
        eids = _strings(_list(claim, "evidence_ids", f"claims[{i}]"), f"claims[{i}].evidence_ids")
        claim["evidence_ids"] = sorted(eids)
        if category == "PARTNER_RELATIONSHIP":
            raise InputError(
                f"claims[{i}]: partner-relationship assertions are prohibited; relationship_state is authoritative"
            )
        if category in SENSITIVE_CLAIM_CATEGORIES:
            valid = [evidence_ok(eid, subject) for eid in eids]
            if not valid or not any(ok for ok, _ in valid):
                holds.append({"code": "UNSUPPORTED_CLAIM", "ref": cid, "detail": "; ".join(reason for ok, reason in valid if not ok) or "no evidence"})
    _unique(claim_ids, "claims")

    slices = _list(doc, "capability_slices", "root")
    slice_ids: list[str] = []
    for i, item in enumerate(slices):
        if not isinstance(item, dict):
            raise InputError(f"capability_slices[{i}]: expected object")
        sid = _required_id(item, "id", f"capability_slices[{i}]")
        slice_ids.append(sid)
        item["label"] = _required_str(item, "label", f"capability_slices[{i}]")
        owner = _required_id(item, "owner_party_id", f"capability_slices[{i}]")
        if owner not in party_set:
            raise InputError(f"capability_slices[{i}].owner_party_id: unknown party")
        eids = _strings(_list(item, "evidence_ids", f"capability_slices[{i}]"), f"capability_slices[{i}].evidence_ids")
        item["evidence_ids"] = sorted(eids)
        if not any(evidence_ok(eid, owner)[0] for eid in eids):
            holds.append({"code": "CAPABILITY_EVIDENCE_HOLD", "ref": sid, "detail": "no current VERIFIED owner evidence"})
    _unique(slice_ids, "capability_slices")

    workshare = _list(doc, "workshare", "root")
    work_ids: list[str] = []
    for i, ws in enumerate(workshare):
        if not isinstance(ws, dict):
            raise InputError(f"workshare[{i}]: expected object")
        wid = _required_id(ws, "id", f"workshare[{i}]")
        work_ids.append(wid)
        ws["workstream"] = _required_str(ws, "workstream", f"workshare[{i}]")
        lead = _required_id(ws, "lead_party_id", f"workshare[{i}]")
        if lead not in party_set:
            raise InputError(f"workshare[{i}].lead_party_id: unknown party")
        allocations = _list(ws, "allocations", f"workshare[{i}]")
        seen_alloc: list[str] = []
        total = 0
        lead_seen = False
        for j, alloc in enumerate(allocations):
            if not isinstance(alloc, dict):
                raise InputError(f"workshare[{i}].allocations[{j}]: expected object")
            pid = _required_id(alloc, "party_id", f"workshare[{i}].allocations[{j}]")
            if pid not in party_set:
                raise InputError(f"workshare[{i}].allocations[{j}].party_id: unknown party")
            bps = alloc.get("basis_points")
            if not isinstance(bps, int) or isinstance(bps, bool) or bps < 0 or bps > 10000:
                raise InputError(f"workshare[{i}].allocations[{j}].basis_points: expected 0..10000 integer")
            seen_alloc.append(pid)
            total += bps
            lead_seen |= pid == lead and bps > 0
        _unique(seen_alloc, f"workshare[{i}].allocations")
        if total != 10000:
            raise InputError(f"workshare[{i}].allocations: basis_points must sum to 10000")
        if not lead_seen:
            raise InputError(f"workshare[{i}]: lead must have positive allocation")
        ws["responsibilities"] = sorted(_strings(
            _list(ws, "responsibilities", f"workshare[{i}]"),
            f"workshare[{i}].responsibilities", min_items=1
        ))
        eids = _strings(_list(ws, "evidence_ids", f"workshare[{i}]", required=False), f"workshare[{i}].evidence_ids")
        ws["evidence_ids"] = sorted(eids)
        ws["allocations"] = sorted(allocations, key=lambda x: x["party_id"])
    _unique(work_ids, "workshare")

    sec = _list(doc, "security_access_requirements", "root")
    sec_ids: list[str] = []
    for i, req in enumerate(sec):
        if not isinstance(req, dict):
            raise InputError(f"security_access_requirements[{i}]: expected object")
        sid = _required_id(req, "id", f"security_access_requirements[{i}]")
        sec_ids.append(sid)
        req["requirement"] = _required_str(req, "requirement", f"security_access_requirements[{i}]")
        subject = _required_id(req, "subject_party_id", f"security_access_requirements[{i}]")
        if subject not in party_set:
            raise InputError(f"security_access_requirements[{i}].subject_party_id: unknown party")
        required = req.get("required")
        if not isinstance(required, bool):
            raise InputError(f"security_access_requirements[{i}].required: expected boolean")
        eids = _strings(_list(req, "evidence_ids", f"security_access_requirements[{i}]", required=False), f"security_access_requirements[{i}].evidence_ids")
        req["evidence_ids"] = sorted(eids)
        if required and not any(evidence_ok(eid, subject, "SECURITY")[0] for eid in eids):
            holds.append({"code": "SECURITY_ACCESS_HOLD", "ref": sid, "detail": "required security/access assertion lacks current VERIFIED SECURITY evidence"})
    _unique(sec_ids, "security_access_requirements")

    proofs = _list(doc, "delivery_proof_refs", "root")
    proof_ids: list[str] = []
    for i, proof in enumerate(proofs):
        if not isinstance(proof, dict):
            raise InputError(f"delivery_proof_refs[{i}]: expected object")
        pid = _required_id(proof, "id", f"delivery_proof_refs[{i}]")
        proof_ids.append(pid)
        proof["label"] = _required_str(proof, "label", f"delivery_proof_refs[{i}]")
        proof["path"] = _safe_source(_required_str(proof, "path", f"delivery_proof_refs[{i}]"), f"delivery_proof_refs[{i}].path")
        proof["sha256"] = _sha(proof.get("sha256"), f"delivery_proof_refs[{i}].sha256")
    _unique(proof_ids, "delivery_proof_refs")

    pricing = _list(doc, "pricing_basis", "root")
    pricing_ids: list[str] = []
    for i, line in enumerate(pricing):
        if not isinstance(line, dict):
            raise InputError(f"pricing_basis[{i}]: expected object")
        lid = _required_id(line, "id", f"pricing_basis[{i}]")
        pricing_ids.append(lid)
        line["description"] = _required_str(line, "description", f"pricing_basis[{i}]")
        line["basis"] = _required_str(line, "basis", f"pricing_basis[{i}]")
        if line.get("commitment_state") != PLACEHOLDER_STATE:
            raise InputError(f"pricing_basis[{i}].commitment_state: must be {PLACEHOLDER_STATE}")
        for forbidden in ("amount", "currency", "total", "rate"):
            if forbidden in line and line[forbidden] not in (None, ""):
                raise InputError(f"pricing_basis[{i}].{forbidden}: numeric/committed pricing prohibited")
    _unique(pricing_ids, "pricing_basis")

    acceptance = _dict(doc, "acceptance", "root")
    if acceptance.get("state") != ACCEPTANCE_STATE:
        raise InputError(f"acceptance.state: must be {ACCEPTANCE_STATE}")
    questions = _strings(_list(acceptance, "questions", "acceptance"), "acceptance.questions", min_items=1)
    acceptance["questions"] = sorted(questions)

    doc["exclusions"] = sorted(_strings(_list(doc, "exclusions", "root"), "exclusions", min_items=1))
    doc["assumptions"] = sorted(_strings(_list(doc, "assumptions", "root"), "assumptions", min_items=1))

    # Canonical ordering makes semantically equivalent input permutations produce one packet.
    doc["parties"] = sorted(parties, key=lambda x: x["id"])
    doc["evidence_receipts"] = sorted(receipts, key=lambda x: x["id"])
    doc["claims"] = sorted(claims, key=lambda x: x["id"])
    doc["capability_slices"] = sorted(slices, key=lambda x: x["id"])
    doc["workshare"] = sorted(workshare, key=lambda x: x["id"])
    doc["security_access_requirements"] = sorted(sec, key=lambda x: x["id"])
    doc["delivery_proof_refs"] = sorted(proofs, key=lambda x: x["id"])
    doc["pricing_basis"] = sorted(pricing, key=lambda x: x["id"])
    holds = sorted(holds, key=lambda x: (x["code"], x["ref"], x["detail"]))
    return doc, holds


def _md(text: Any) -> str:
    return str(text).replace("\r", " ").replace("\n", " ").replace("|", "\\|").strip()


def render_packet(doc: dict[str, Any], holds: list[dict[str, str]]) -> str:
    status = "HOLD" if holds else "OWNER_REVIEW_READY"
    opp = doc["opportunity"]
    lines = [
        "# Partner / Workshare Conversion Packet",
        "",
        f"- **Status:** `{status}`",
        f"- **Truth ceiling:** `{TRUTH_CEILING}`",
        f"- **As of:** `{doc['as_of']}`",
        f"- **Opportunity:** `{_md(opp['id'])}` — {_md(opp['title'])}",
        f"- **Buyer:** {_md(opp['buyer'])}",
        f"- **Source:** `{_md(opp['source'])}`",
        f"- **Source SHA-256:** `{opp['source_sha256']}`",
        "",
        "> Internal owner-review artifact only. This packet is not partner acceptance, a bid,",
        "> a submission, a price quote, an award, a payment event, or evidence of revenue.",
        "",
        "## Scope",
        "",
        _md(opp["scope_summary"]),
        "",
        "## Parties",
        "",
        "| Party | Role | Relationship state |",
        "|---|---|---|",
    ]
    for party in doc["parties"]:
        lines.append(f"| {_md(party['name'])} (`{party['id']}`) | `{party['role']}` | `{party['relationship_state']}` |")

    lines += ["", "## Capability slices", ""]
    for item in doc["capability_slices"]:
        ev = ", ".join(f"`{e}`" for e in item["evidence_ids"]) or "_none_"
        lines.append(f"- **{_md(item['label'])}** (`{item['id']}`, owner `{item['owner_party_id']}`): evidence {ev}")

    lines += ["", "## Proposed workshare", ""]
    for ws in doc["workshare"]:
        allocations = ", ".join(f"`{a['party_id']}` {a['basis_points']/100:.2f}%" for a in ws["allocations"])
        lines.append(f"### {_md(ws['workstream'])} (`{ws['id']}`)")
        lines.append(f"- Lead: `{ws['lead_party_id']}`")
        lines.append(f"- Proposed allocation: {allocations}")
        lines.append("- Responsibilities:")
        for r in ws["responsibilities"]:
            lines.append(f"  - {_md(r)}")
        lines.append("")

    lines += ["## Exclusions", ""]
    lines.extend(f"- {_md(v)}" for v in doc["exclusions"])
    lines += ["", "## Assumptions", ""]
    lines.extend(f"- {_md(v)}" for v in doc["assumptions"])

    lines += ["", "## Security / access requirements", ""]
    for req in doc["security_access_requirements"]:
        ev = ", ".join(f"`{e}`" for e in req["evidence_ids"]) or "_none_"
        lines.append(f"- `{req['id']}` {_md(req['requirement'])} — subject `{req['subject_party_id']}`, required `{str(req['required']).lower()}`, evidence {ev}")

    lines += ["", "## Delivery proof references", ""]
    for proof in doc["delivery_proof_refs"]:
        lines.append(f"- `{proof['id']}` {_md(proof['label'])}: `{_md(proof['path'])}` (`sha256:{proof['sha256']}`)")

    lines += ["", "## Pricing-basis placeholders", ""]
    for item in doc["pricing_basis"]:
        lines.append(f"- `{item['id']}` {_md(item['description'])}: {_md(item['basis'])} — `{PLACEHOLDER_STATE}`")
    lines += ["", "No numeric amount, rate, total, currency commitment, or acceptance authority is carried by this packet."]

    lines += ["", "## Evidence receipts", ""]
    for rec in doc["evidence_receipts"]:
        validity = f", valid through `{rec['valid_through']}`" if rec.get("valid_through") else ""
        lines.append(f"- `{rec['id']}` `{rec['kind']}` / `{rec['status']}` — subject `{rec['subject_party_id']}`, observed `{rec['observed_at']}`{validity}; source `{_md(rec['source'])}`; `{_md(rec['summary'])}`")

    lines += ["", "## Claims", ""]
    for claim in doc["claims"]:
        ev = ", ".join(f"`{e}`" for e in claim["evidence_ids"]) or "_none_"
        lines.append(f"- `{claim['id']}` `{claim['category']}` subject `{claim['subject_party_id']}`: {_md(claim['text'])} (evidence: {ev})")

    lines += ["", "## Acceptance questions", ""]
    lines.extend(f"- {_md(q)}" for q in doc["acceptance"]["questions"])

    lines += ["", "## Holds", ""]
    if holds:
        for hold in holds:
            lines.append(f"- `{hold['code']}` / `{hold['ref']}` — {_md(hold['detail'])}")
    else:
        lines.append("- None. Packet may proceed to human owner review; this does **not** elevate the truth ceiling.")

    lines += [
        "",
        "## Authority boundary",
        "",
        f"`{TRUTH_CEILING}` is the maximum representable relationship state. External contact,",
        "partner acceptance, bid/submission, pricing commitment, award, payment, and revenue claims",
        "require separate authoritative evidence and explicit owner-controlled workflows.",
        "",
    ]
    return "\n".join(lines)


def compile_document(raw: Any) -> tuple[dict[str, Any], str, dict[str, Any]]:
    doc, holds = validate_and_normalize(raw)
    packet = render_packet(doc, holds)
    packet_bytes = packet.encode("utf-8")
    canonical_input = canonical_json(doc)
    receipt = {
        "schema": SCHEMA_VERSION,
        "truth_ceiling": TRUTH_CEILING,
        "status": "HOLD" if holds else "OWNER_REVIEW_READY",
        "hold_count": len(holds),
        "holds": holds,
        "input_sha256": sha256_bytes(canonical_input),
        "packet_sha256": sha256_bytes(packet_bytes),
        "opportunity_id": doc["opportunity"]["id"],
        "as_of": doc["as_of"],
    }
    return doc, packet, receipt


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    finally:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass


def compile_to_dir(input_path: Path, out_dir: Path, fail_on_hold: bool = False) -> int:
    raw = json.loads(input_path.read_text(encoding="utf-8"))
    doc, packet, receipt = compile_document(raw)
    out_dir.mkdir(parents=True, exist_ok=True)
    _atomic_write(out_dir / "canonical_input.json", canonical_json(doc))
    _atomic_write(out_dir / "packet.md", packet.encode("utf-8"))
    _atomic_write(out_dir / "receipt.json", canonical_json(receipt))
    if fail_on_hold and receipt["status"] == "HOLD":
        return 2
    return 0


def verify_artifacts(input_path: Path, packet_path: Path, receipt_path: Path) -> int:
    raw = json.loads(input_path.read_text(encoding="utf-8"))
    doc, expected_packet, expected_receipt = compile_document(raw)
    actual_packet = packet_path.read_bytes()
    actual_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    problems: list[str] = []
    if actual_packet != expected_packet.encode("utf-8"):
        problems.append("packet bytes differ from deterministic compile")
    if actual_receipt != expected_receipt:
        problems.append("receipt differs from deterministic compile")
    if actual_receipt.get("input_sha256") != sha256_bytes(canonical_json(doc)):
        problems.append("input SHA mismatch")
    if actual_receipt.get("packet_sha256") != sha256_bytes(actual_packet):
        problems.append("packet SHA mismatch")
    if problems:
        for problem in problems:
            print(f"VERIFY_FAIL: {problem}", file=sys.stderr)
        return 1
    print(
        f"VERIFY_OK opportunity={expected_receipt['opportunity_id']} "
        f"status={expected_receipt['status']} packet_sha256={expected_receipt['packet_sha256']}"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    c = sub.add_parser("compile", help="compile JSON input into deterministic review artifacts")
    c.add_argument("--input", required=True, type=Path)
    c.add_argument("--out-dir", required=True, type=Path)
    c.add_argument("--fail-on-hold", action="store_true")
    v = sub.add_parser("verify", help="recompile and verify an existing packet + receipt")
    v.add_argument("--input", required=True, type=Path)
    v.add_argument("--packet", required=True, type=Path)
    v.add_argument("--receipt", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "compile":
            return compile_to_dir(args.input, args.out_dir, args.fail_on_hold)
        return verify_artifacts(args.input, args.packet, args.receipt)
    except (InputError, json.JSONDecodeError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
