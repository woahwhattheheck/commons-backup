#!/usr/bin/env python3
"""Strict schema and validation primitives for partner workshare packets."""
from __future__ import annotations

import hashlib, json, math, re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

SCHEMA = "tjlabs-partner-workshare-data-room/v1"
COMPILER = "partner-workshare-data-room/1.0.0"
COMMERCIAL_STATE = "PROPOSED_NOT_ACCEPTED"
PRIMARY = {"BUYER_OFFICIAL", "PARTNER_OFFICIAL", "OWNER_VERIFIED", "SIGNED_RECORD"}
AUTHORITIES = PRIMARY | {"PUBLIC_FIRST_PARTY", "SECONDARY", "SYNTHETIC"}
RISKY = {"QUALIFICATION", "CERTIFICATION", "REFERENCE", "SECURITY", "PRICING", "LEGAL", "STAFFING"}
CLAIM_KINDS = RISKY | {"CAPABILITY", "DELIVERY", "SCOPE", "ASSUMPTION"}
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
AUTHORITY_CEILING = {k: False for k in (
    "external_send_authorized", "partner_acceptance_proven", "buyer_acceptance_proven",
    "bid_submission_authorized", "contract_authorized", "pricing_commitment_authorized",
    "invoice_authorized", "payment_proven", "cash_proven", "revenue_recognition_authorized",
)}

TOP = {"schema_version", "evaluation_at_utc", "opportunity", "parties", "evidence", "claims", "capability_slices", "workshare", "exclusions", "assumptions", "security_access", "pricing_basis", "acceptance_questions"}
FIELDS = {
    "opportunity": {"id", "title", "buyer", "source_generation", "source_sha256", "deadline_utc"},
    "party": {"id", "display_name", "role", "evidence_refs"},
    "evidence": {"id", "kind", "subject", "source_uri", "sha256", "observed_at_utc", "expires_at_utc", "authority", "summary"},
    "claim": {"id", "subject", "kind", "statement", "state", "evidence_refs"},
    "capability": {"id", "title", "owner_party_id", "claim_ids", "evidence_refs", "deliverables", "acceptance_criteria"},
    "workshare": {"id", "capability_id", "owner_party_id", "status", "dependencies"},
    "assumption": {"id", "text", "required_for_ready", "evidence_refs"},
    "security": {"id", "requirement", "state", "evidence_refs"},
    "pricing": {"status", "currency", "amount_minor", "basis", "evidence_refs"},
    "question": {"id", "question", "owner"},
}

class PacketError(ValueError): pass

@dataclass(frozen=True)
class CompiledBundle:
    packet_json: str
    packet_markdown: str
    receipt_json: str
    decision: str
    blockers: tuple[str, ...]

def _dupes(pairs):
    out = {}
    for k, v in pairs:
        if k in out: raise PacketError(f"duplicate JSON key: {k}")
        out[k] = v
    return out

def _constant(v): raise PacketError(f"non-finite JSON number: {v}")

def load_strict_json(text: str) -> Any:
    try: value = json.loads(text, object_pairs_hook=_dupes, parse_constant=_constant)
    except PacketError: raise
    except json.JSONDecodeError as exc: raise PacketError(f"invalid JSON: {exc.msg}") from exc
    def walk(v):
        if type(v) is float and not math.isfinite(v): raise PacketError("non-finite number")
        if type(v) is dict:
            for x in v.values(): walk(x)
        elif type(v) is list:
            for x in v: walk(x)
    walk(value); return value

def _obj(v, label, fields, optional=frozenset()):
    if type(v) is not dict: raise PacketError(f"{label} must be an object")
    unknown, missing = set(v)-fields, fields-set(v)-set(optional)
    if unknown: raise PacketError(f"{label} has unknown fields: {sorted(unknown)!r}")
    if missing: raise PacketError(f"{label} missing fields: {sorted(missing)!r}")
    return v

def _arr(v, label):
    if type(v) is not list: raise PacketError(f"{label} must be an array")
    return v

def _str(v, label, n=2000):
    if type(v) is not str or not v or v != v.strip(): raise PacketError(f"{label} must be nonempty and trim-stable string")
    if len(v) > n or any(ord(c)<32 and c not in "\t\n" for c in v): raise PacketError(f"{label} is unsafe/oversize")
    return v

def _id(v, label):
    v = _str(v, label, 128)
    if not ID_RE.fullmatch(v): raise PacketError(f"{label} has invalid identifier syntax")
    return v

def _sha(v, label):
    v = _str(v, label, 64)
    if not SHA_RE.fullmatch(v): raise PacketError(f"{label} must be lowercase SHA-256")
    return v

def _ts(v, label):
    s = _str(v, label, 64); s = s[:-1]+"+00:00" if s.endswith("Z") else s
    try: d = datetime.fromisoformat(s)
    except ValueError as exc: raise PacketError(f"{label} must be ISO-8601 with timezone") from exc
    if d.tzinfo is None or d.utcoffset() is None: raise PacketError(f"{label} must include timezone")
    return d.astimezone(timezone.utc)

def _url(v, label):
    s = _str(v, label, 2048); p = urlparse(s)
    if p.scheme != "https" or not p.hostname or "@" in p.netloc: raise PacketError(f"{label} must be an https URL without userinfo")
    if any(x in s for x in ("\\", "\x00", "../", "/..")): raise PacketError(f"{label} contains unsafe path material")
    return s

def _enum(v, label, allowed):
    s = _str(v, label, 64)
    if s not in allowed: raise PacketError(f"{label} must be one of {sorted(allowed)!r}")
    return s

def _ids(v, label):
    xs = sorted(_id(x, f"{label}[]") for x in _arr(v, label))
    if len(xs) != len(set(xs)): raise PacketError(f"{label} contains duplicates")
    return xs

def _texts(v, label, minimum=0):
    xs = sorted(_str(x, f"{label}[]", 1000) for x in _arr(v, label))
    if len(xs) < minimum or len(xs) != len(set(xs)): raise PacketError(f"{label} has invalid cardinality/duplicates")
    return xs

def _index(xs, label):
    out = {}
    for x in xs:
        if x["id"] in out: raise PacketError(f"duplicate {label} id: {x['id']}")
        out[x["id"]] = x
    return out

def _refs(refs, known, label):
    miss = sorted(set(refs)-set(known))
    if miss: raise PacketError(f"{label} references unknown ids: {miss!r}")

def _canonical(v): return json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False)+"\n"
def _digest(v): return hashlib.sha256(v.encode()).hexdigest()

