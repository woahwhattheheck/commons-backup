"""Strict source-to-catalog materializer for procurement response modules.

This module converts owner-reviewed evidence descriptors into a catalog compatible
with procurement_response_module_library.engine. It does not authenticate external
providers and does not authorize contact, submission, certification, pricing,
payment, award, or revenue recognition.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SOURCE_SCHEMA = "procurement-response-modules/materializer-source/v1"
CATALOG_SCHEMA = "procurement-response-modules/library/v1"
DIFF_SCHEMA = "procurement-response-modules/materializer-diff/v1"
RECEIPT_SCHEMA = "procurement-response-modules/materializer-receipt/v1"
TRUTH_BOUNDARY = "INTERNAL_OWNER_REVIEW_ONLY"

FAMILIES = {
    "corporate_capability", "ai_data_governance", "cybersecurity", "accessibility",
    "implementation_delivery", "sla_support", "staffing", "references_past_performance",
    "pricing_assumptions", "subcontractor_partner_matrix", "compliance_crosswalk",
}
OWNER = {"APPROVED", "PENDING", "DENIED"}
EVIDENCE_STATE = {"SUPPORTED", "PARTIAL", "MISSING", "NOT_APPLICABLE"}
CLAIM_KIND = {"CAPABILITY", "POLICY", "CERTIFICATION", "REFERENCE", "SLA", "SECURITY_CONTROL"}
SOURCE_KIND = {
    "APPROVED_INTERNAL_RECEIPT", "APPROVED_POLICY", "APPROVED_CAPABILITY_FACT",
    "ISSUER_VERIFIED_CERTIFICATION", "REFERENCE_PERMISSION_RECEIPT",
    "ACCEPTED_SLA_RECEIPT", "CONTROL_TEST_RECEIPT", "SYNTHETIC_FIXTURE",
}
SENSITIVE_PROOF = {
    "CERTIFICATION": "ISSUER_VERIFIED_CERTIFICATION",
    "REFERENCE": "REFERENCE_PERMISSION_RECEIPT",
    "SLA": "ACCEPTED_SLA_RECEIPT",
    "SECURITY_CONTROL": "CONTROL_TEST_RECEIPT",
}
GENERIC_SOURCE_KINDS = {
    "CAPABILITY": {"APPROVED_INTERNAL_RECEIPT", "APPROVED_CAPABILITY_FACT"},
    "POLICY": {"APPROVED_INTERNAL_RECEIPT", "APPROVED_POLICY"},
}
FAMILY_KINDS = {
    "corporate_capability": {"CAPABILITY"},
    "ai_data_governance": {"CAPABILITY", "POLICY"},
    "cybersecurity": {"POLICY", "SECURITY_CONTROL"},
    "accessibility": {"CAPABILITY", "POLICY"},
    "implementation_delivery": {"CAPABILITY", "POLICY"},
    "sla_support": {"SLA"},
    "staffing": {"CAPABILITY"},
    "references_past_performance": {"REFERENCE"},
    "pricing_assumptions": {"POLICY"},
    "subcontractor_partner_matrix": {"CAPABILITY", "POLICY"},
    "compliance_crosswalk": {"POLICY", "CERTIFICATION"},
}
SENSITIVE_TEXT = re.compile(r"(?i)\b(soc\s*2|hipaa|iso\s*\d+|pci(?:[- ]?dss)?|certif(?:ied|ication)|compliant|compliance|customer\s+reference|past\s+performance|service[- ]level|sla|guarantee(?:d)?|security\s+control)\b")
TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,127}$")
SHA = re.compile(r"^[0-9a-f]{64}$")
TS = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

class Error(ValueError):
    pass


def _pairs(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise Error(f"duplicate JSON key: {k}")
        out[k] = v
    return out


def _bad_number(v):
    raise Error(f"non-integer JSON number forbidden: {v}")


def _scalar_unicode(v: Any, where: str = "input") -> None:
    if isinstance(v, str):
        try:
            v.encode("utf-8", "strict")
        except UnicodeEncodeError as exc:
            raise Error(f"{where}: non-scalar Unicode") from exc
    elif isinstance(v, list):
        for i, x in enumerate(v):
            _scalar_unicode(x, f"{where}[{i}]")
    elif isinstance(v, dict):
        for k, x in v.items():
            _scalar_unicode(k, f"{where}.key")
            _scalar_unicode(x, f"{where}.{k}")


def load(raw: bytes, label: str = "input") -> dict:
    if not isinstance(raw, (bytes, bytearray)):
        raise Error(f"{label}: bytes required")
    raw = bytes(raw)
    if raw.startswith(b"\xef\xbb\xbf"):
        raise Error(f"{label}: BOM forbidden")
    try:
        obj = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                         parse_float=_bad_number, parse_constant=_bad_number)
    except Error:
        raise
    except Exception as exc:
        raise Error(f"{label}: invalid JSON/UTF-8") from exc
    if not isinstance(obj, dict):
        raise Error(f"{label}: object required")
    _scalar_unicode(obj, label)
    return obj


def canon(v: Any) -> bytes:
    _scalar_unicode(v)
    try:
        return (json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")
    except (UnicodeEncodeError, ValueError) as exc:
        raise Error("canonical JSON encoding failed") from exc


def digest(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def exact_keys(v: Any, want: list[str], where: str) -> dict:
    if not isinstance(v, dict) or set(v) != set(want):
        raise Error(f"{where}: keys mismatch")
    return v


def text(v: Any, where: str, *, token: bool = False, limit: int = 4096) -> str:
    if not isinstance(v, str) or not v or len(v) > limit:
        raise Error(f"{where}: invalid string")
    _scalar_unicode(v, where)
    if any(ord(c) < 32 and c not in "\n\t" for c in v):
        raise Error(f"{where}: invalid control character")
    if token and not TOKEN.fullmatch(v):
        raise Error(f"{where}: invalid token")
    return v


def integer(v: Any, where: str, lo: int = 0, hi: int = 10**9) -> int:
    if isinstance(v, bool) or not isinstance(v, int) or not lo <= v <= hi:
        raise Error(f"{where}: integer required")
    return v


def sha(v: Any, where: str) -> str:
    v = text(v, where, limit=64)
    if not SHA.fullmatch(v):
        raise Error(f"{where}: sha256 required")
    return v


def timestamp(v: Any, where: str) -> str:
    v = text(v, where, limit=20)
    try:
        if not TS.fullmatch(v):
            raise ValueError
        datetime.strptime(v, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise Error(f"{where}: RFC3339 UTC second timestamp required") from exc
    return v


def dtime(v: str) -> datetime:
    return datetime.strptime(v, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def tokens(v: Any, where: str, *, min_n: int = 0, max_n: int = 64) -> list[str]:
    if not isinstance(v, list) or not min_n <= len(v) <= max_n:
        raise Error(f"{where}: invalid list")
    out = [text(x, f"{where}[{i}]", token=True, limit=128) for i, x in enumerate(v)]
    if len(out) != len(set(out)):
        raise Error(f"{where}: duplicate item")
    return sorted(out)


def _support_decision(row: dict, generated_at: str) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if row["owner_status"] != "APPROVED":
        reasons.append("OWNER_" + row["owner_status"])
    if row["evidence_state"] != "SUPPORTED":
        reasons.append("EVIDENCE_" + row["evidence_state"])
    if dtime(row["observed_at"]) > dtime(generated_at):
        raise Error(f"records.{row['record_id']}: future evidence")
    if dtime(row["expires_at"]) < dtime(generated_at):
        reasons.append("EXPIRED")
    if dtime(row["valid_from"]) > dtime(generated_at) or dtime(row["valid_until"]) < dtime(generated_at):
        reasons.append("MODULE_OUTSIDE_VALIDITY_WINDOW")
    if row["source_kind"] == "SYNTHETIC_FIXTURE":
        reasons.append("SYNTHETIC_ONLY")
    required = SENSITIVE_PROOF.get(row["claim_kind"])
    if required is not None:
        if row["source_kind"] != required:
            reasons.append("SENSITIVE_PROOF_REQUIRED:" + required)
        reasons.append("SPECIALIZED_AUTHORITY_REQUIRED:" + row["claim_kind"])
    elif SENSITIVE_TEXT.search(row["claim_text"]):
        reasons.append("SENSITIVE_LANGUAGE_REQUIRES_SPECIALIZED_PROOF")
    allowed = GENERIC_SOURCE_KINDS.get(row["claim_kind"])
    if allowed is not None and row["source_kind"] not in allowed and row["source_kind"] != "SYNTHETIC_FIXTURE":
        reasons.append("SOURCE_KIND_NOT_APPROVED_FOR_CLAIM_KIND")
    return ("SUPPORTED" if not reasons else ("MISSING" if row["evidence_state"] == "MISSING" else "PARTIAL"), sorted(set(reasons)))


def normalize_source(v: dict) -> dict:
    exact_keys(v, ["schema", "library_id", "generated_at", "evidence_max_age_seconds", "truth_boundary", "records"], "source")
    if v["schema"] != SOURCE_SCHEMA or v["truth_boundary"] != TRUTH_BOUNDARY:
        raise Error("source: unsupported schema/boundary")
    library_id = text(v["library_id"], "source.library_id", token=True)
    generated_at = timestamp(v["generated_at"], "source.generated_at")
    max_age = integer(v["evidence_max_age_seconds"], "source.evidence_max_age_seconds", 1, 31536000)
    if not isinstance(v["records"], list) or not v["records"]:
        raise Error("source.records: nonempty list required")
    out = []
    for i, raw in enumerate(v["records"]):
        w = f"records[{i}]"
        exact_keys(raw, ["record_id", "evidence_id", "module_id", "claim_id", "family", "title", "claim_text", "claim_kind", "source_kind", "source_ref", "source_sha256", "observed_at", "expires_at", "owner_status", "evidence_state", "revision", "valid_from", "valid_until", "applicability_tags"], w)
        family = text(raw["family"], w + ".family", token=True)
        if family not in FAMILIES:
            raise Error(w + ": unsupported family")
        ck = text(raw["claim_kind"], w + ".claim_kind", token=True)
        sk = text(raw["source_kind"], w + ".source_kind", token=True)
        owner = text(raw["owner_status"], w + ".owner_status", token=True)
        estate = text(raw["evidence_state"], w + ".evidence_state", token=True)
        if ck not in CLAIM_KIND or sk not in SOURCE_KIND or owner not in OWNER or estate not in EVIDENCE_STATE:
            raise Error(w + ": invalid enum")
        if ck not in FAMILY_KINDS[family]:
            raise Error(w + ": claim_kind not allowed for family")
        row = {
            "record_id": text(raw["record_id"], w + ".record_id", token=True),
            "evidence_id": text(raw["evidence_id"], w + ".evidence_id", token=True),
            "module_id": text(raw["module_id"], w + ".module_id", token=True),
            "claim_id": text(raw["claim_id"], w + ".claim_id", token=True),
            "family": family,
            "title": text(raw["title"], w + ".title", limit=256),
            "claim_text": text(raw["claim_text"], w + ".claim_text"),
            "claim_kind": ck,
            "source_kind": sk,
            "source_ref": text(raw["source_ref"], w + ".source_ref", limit=2048),
            "source_sha256": sha(raw["source_sha256"], w + ".source_sha256"),
            "observed_at": timestamp(raw["observed_at"], w + ".observed_at"),
            "expires_at": timestamp(raw["expires_at"], w + ".expires_at"),
            "owner_status": owner,
            "evidence_state": estate,
            "revision": integer(raw["revision"], w + ".revision", 1, 10**6),
            "valid_from": timestamp(raw["valid_from"], w + ".valid_from"),
            "valid_until": timestamp(raw["valid_until"], w + ".valid_until"),
            "applicability_tags": tokens(raw["applicability_tags"], w + ".applicability_tags", min_n=1),
        }
        if dtime(row["observed_at"]) > dtime(row["expires_at"]):
            raise Error(w + ": observed_at after expires_at")
        age = int((dtime(generated_at) - dtime(row["observed_at"])).total_seconds())
        if age > max_age:
            raise Error(w + ": stale evidence outside catalog max age")
        if dtime(row["valid_from"]) > dtime(row["valid_until"]):
            raise Error(w + ": valid_from after valid_until")
        if not dtime(row["valid_from"]) <= dtime(generated_at) <= dtime(row["valid_until"]):
            raise Error(w + ": module outside current validity window")
        row["materialized_status"], row["hold_reasons"] = _support_decision(row, generated_at)
        out.append(row)
    for key in ["record_id", "evidence_id", "module_id", "claim_id"]:
        vals = [r[key] for r in out]
        if len(vals) != len(set(vals)):
            raise Error(f"source.records: duplicate {key}")
    fam_rev = [(r["family"], r["revision"]) for r in out]
    if len(fam_rev) != len(set(fam_rev)):
        raise Error("source.records: duplicate family revision")
    return {"library_id": library_id, "generated_at": generated_at, "evidence_max_age_seconds": max_age, "records": sorted(out, key=lambda r: (r["family"], r["revision"], r["module_id"]))}


def build_catalog(source: dict) -> dict:
    evidence = []
    modules = []
    for r in source["records"]:
        summary = f"{r['claim_kind']} materialized from {r['source_kind']}"
        if r["hold_reasons"]:
            summary += "; HOLD: " + ",".join(r["hold_reasons"])
        evidence.append({
            "evidence_id": r["evidence_id"], "ref": r["source_ref"], "sha256": r["source_sha256"],
            "observed_at": r["observed_at"], "status": r["materialized_status"], "summary": summary,
        })
        modules.append({
            "module_id": r["module_id"], "revision": r["revision"], "family": r["family"], "title": r["title"],
            "tags": r["applicability_tags"],
            "owner_status": "APPROVED" if r["materialized_status"] == "SUPPORTED" else "PENDING",
            "valid_from": r["valid_from"], "valid_until": r["valid_until"],
            "source_ref": r["source_ref"], "source_sha256": r["source_sha256"],
            "claims": [{"claim_id": r["claim_id"], "text": r["claim_text"], "evidence_ids": [r["evidence_id"]]}],
        })
    return {
        "schema": CATALOG_SCHEMA, "library_id": source["library_id"], "generated_at": source["generated_at"],
        "evidence_max_age_seconds": source["evidence_max_age_seconds"], "truth_boundary": TRUTH_BOUNDARY,
        "evidence": sorted(evidence, key=lambda x: x["evidence_id"]),
        "modules": sorted(modules, key=lambda x: (x["family"], x["module_id"], x["revision"])),
    }


def _identity_map(catalog: dict, kind: str) -> dict[str, str]:
    if kind == "evidence":
        return {x["evidence_id"]: digest(canon(x)) for x in catalog.get("evidence", []) if isinstance(x, dict) and isinstance(x.get("evidence_id"), str)}
    return {x["module_id"]: digest(canon(x)) for x in catalog.get("modules", []) if isinstance(x, dict) and isinstance(x.get("module_id"), str)}


def normalize_previous(v: dict | None) -> dict:
    if v is None:
        return {"evidence": [], "modules": []}
    exact_keys(v, ["schema", "library_id", "generated_at", "evidence_max_age_seconds", "truth_boundary", "evidence", "modules"], "previous")
    if v["schema"] != CATALOG_SCHEMA or v["truth_boundary"] != TRUTH_BOUNDARY:
        raise Error("previous: unsupported schema/boundary")
    if not isinstance(v["evidence"], list) or not isinstance(v["modules"], list):
        raise Error("previous: evidence/modules lists required")
    eids=[]; mids=[]
    for i, row in enumerate(v["evidence"]):
        if not isinstance(row, dict): raise Error(f"previous.evidence[{i}]: object required")
        eids.append(text(row.get("evidence_id"), f"previous.evidence[{i}].evidence_id", token=True))
    for i, row in enumerate(v["modules"]):
        if not isinstance(row, dict): raise Error(f"previous.modules[{i}]: object required")
        mids.append(text(row.get("module_id"), f"previous.modules[{i}].module_id", token=True))
    if len(eids) != len(set(eids)) or len(mids) != len(set(mids)):
        raise Error("previous: duplicate identity")
    return v

def build_diff(previous: dict | None, catalog: dict) -> dict:
    prev = normalize_previous(previous)
    out: dict[str, Any] = {"schema": DIFF_SCHEMA, "truth_boundary": TRUTH_BOUNDARY}
    for kind in ["evidence", "modules"]:
        a = _identity_map(prev, kind); b = _identity_map(catalog, kind)
        prefix = "module" if kind == "modules" else "evidence"
        out[f"added_{prefix}_ids"] = sorted(set(b) - set(a))
        out[f"removed_{prefix}_ids"] = sorted(set(a) - set(b))
        out[f"changed_{prefix}_ids"] = sorted(k for k in set(a) & set(b) if a[k] != b[k])
    return out


def compile_materializer(source_raw: bytes, previous_raw: bytes | None = None) -> tuple[bytes, bytes, bytes]:
    source_obj = normalize_source(load(source_raw, "source"))
    catalog = build_catalog(source_obj)
    previous = load(previous_raw, "previous") if previous_raw is not None else None
    diff = build_diff(previous, catalog)
    cb = canon(catalog); db = canon(diff)
    receipt = {
        "schema": RECEIPT_SCHEMA, "truth_boundary": TRUTH_BOUNDARY,
        "source_sha256": digest(source_raw),
        "previous_sha256": None if previous_raw is None else digest(previous_raw),
        "catalog_sha256": digest(cb), "diff_sha256": digest(db),
        "authority": {
            "buyer_contact_authorized": False, "submission_authorized": False,
            "signature_or_certification_authorized": False, "price_commitment_authorized": False,
            "payment_authorized": False, "award_or_revenue_recognized": False,
        },
    }
    return cb, db, canon(receipt)


def verify_materializer(source_raw: bytes, catalog_raw: bytes, diff_raw: bytes, receipt_raw: bytes, previous_raw: bytes | None = None) -> bool:
    expected = compile_materializer(source_raw, previous_raw)
    return expected == (catalog_raw, diff_raw, receipt_raw)


def _read(path: Path, label: str) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise Error(f"{label}: read failed") from exc


def _publish(out: Path, files: dict[str, bytes]) -> None:
    try:
        out.mkdir(mode=0o700, parents=False, exist_ok=False)
    except OSError as exc:
        raise Error("output directory must not already exist") from exc
    for name, data in files.items():
        path = out / name
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as fh:
                fh.write(data); fh.flush(); os.fsync(fh.fileno())
        except OSError as exc:
            raise Error(f"publication failed: {name}") from exc


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    sp = p.add_subparsers(dest="cmd", required=True)
    c = sp.add_parser("compile"); c.add_argument("--source", required=True); c.add_argument("--previous"); c.add_argument("--out-dir", required=True)
    v = sp.add_parser("verify"); v.add_argument("--source", required=True); v.add_argument("--previous"); v.add_argument("--catalog", required=True); v.add_argument("--diff", required=True); v.add_argument("--receipt", required=True)
    try:
        ns = p.parse_args(argv)
        source = _read(Path(ns.source), "source")
        previous = _read(Path(ns.previous), "previous") if ns.previous else None
        if ns.cmd == "compile":
            cb, db, rb = compile_materializer(source, previous)
            _publish(Path(ns.out_dir), {"catalog.json": cb, "diff.json": db, "receipt.json": rb})
            print(json.dumps({"catalog_sha256": digest(cb), "diff_sha256": digest(db), "verified": True}, sort_keys=True))
            return 0
        ok = verify_materializer(source, _read(Path(ns.catalog), "catalog"), _read(Path(ns.diff), "diff"), _read(Path(ns.receipt), "receipt"), previous)
        print(json.dumps({"verified": ok}, sort_keys=True))
        return 0 if ok else 2
    except Error as exc:
        print(f"materializer error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
