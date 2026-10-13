"""Hardened public facade for the paid-discovery offer compiler.

The immutable implementation core lives in :mod:`._core`.  This facade tightens
cross-record chronology, commercial coherence, route rejection, literal Markdown
rendering, and bundle-manifest receipts without expanding the authority ceiling.
"""
from __future__ import annotations

import copy
import hashlib
import os
import re
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Mapping

from . import _core

# Public constants and compatibility helpers used by the focused acceptance suite.
PACKET_VERSION = _core.PACKET_VERSION
ROOTS_VERSION = _core.ROOTS_VERSION
INPUT_VERSION = _core.INPUT_VERSION
MAX_SAFE_INTEGER = _core.MAX_SAFE_INTEGER
MAX_INBOUND_AGE = _core.MAX_INBOUND_AGE
MAX_ROOTS_AGE = _core.MAX_ROOTS_AGE
MAX_INPUT_BYTES = _core.MAX_INPUT_BYTES
READY = _core.READY
HOLD = _core.HOLD
HISTORICAL = _core.HISTORICAL
OfferError = _core.OfferError
canonical_json = _core.canonical_json
_sha256_value = _core._sha256_value
_sha256_text = _core._sha256_text
_validate_roots = _core._validate_roots
_timestamp = _core._timestamp
_fmt = _core._fmt
loads_strict = _core.loads_strict
read_strict_json_file = _core.read_strict_json_file

_DIRECT_ROUTE = re.compile(r"(?i)(?:mailto:|tel:)")
_MARKDOWN_PUNCT = frozenset(chr(92) + "`*_{}[]()#+-.!|<>")


def _markdown_text(text: str) -> str:
    """Render already-validated public text as literal Markdown content."""
    return "".join(chr(92) + ch if ch in _MARKDOWN_PUNCT else ch for ch in text)


def _validate_candidate(candidate: Any) -> Dict[str, Any]:
    value = _core._validate_candidate(candidate)
    offer = value["proposed_offer"]
    public_text = list(offer["buyer_inputs"]) + list(offer["exclusions"])
    for item in offer["scope_items"]:
        public_text.extend((item["deliverable"], item["acceptance_evidence"]))
    if any(_DIRECT_ROUTE.search(text) for text in public_text):
        raise OfferError("input.proposed_offer: direct mailto/tel route-shaped text rejected")
    return value


def _authority_reasons(candidate: Dict[str, Any], roots: Dict[str, Any], at: datetime):
    reasons, valid_until = _core._authority_reasons(candidate, roots, at)
    reasons = list(reasons)
    opp = candidate["opportunity"]
    inbound = candidate["positive_inbound"]
    custody = candidate["custody"]
    caps = candidate["capabilities"]
    policy = candidate["commercial_policy"]
    offer = candidate["proposed_offer"]

    roots_at = _timestamp(roots["captured_at"], "roots.captured_at")
    opp_captured = _timestamp(opp["captured_at"], "input.opportunity.captured_at")
    opp_until = _timestamp(opp["valid_until"], "input.opportunity.valid_until")
    inbound_captured = _timestamp(inbound["captured_at"], "input.positive_inbound.captured_at")
    cust_acquired = _timestamp(custody["acquired_at"], "input.custody.acquired_at")
    cust_until = _timestamp(custody["expires_at"], "input.custody.expires_at")
    policy_eff = _timestamp(policy["effective_at"], "input.commercial_policy.effective_at")
    policy_until = _timestamp(policy["expires_at"], "input.commercial_policy.expires_at")

    if opp_until <= opp_captured:
        reasons.append("OPPORTUNITY_CHRONOLOGY_INVALID")
    if cust_until <= cust_acquired:
        reasons.append("CUSTODY_CHRONOLOGY_INVALID")
    if policy_until <= policy_eff:
        reasons.append("COMMERCIAL_POLICY_CHRONOLOGY_INVALID")
    if offer["upfront_minor"] > offer["price_minor"]:
        reasons.append("UPFRONT_EXCEEDS_TOTAL_PRICE")

    rooted_evidence_times = [opp_captured, inbound_captured, cust_acquired]
    rooted_evidence_times.extend(
        _timestamp(cap["verified_at"], "capability.verified_at") for cap in caps
    )
    if roots_at < max(rooted_evidence_times):
        reasons.append("AUTHORITY_ROOT_CHRONOLOGY_INVALID")
    return sorted(set(reasons)), valid_until


def _base_packet(candidate: Dict[str, Any], roots: Dict[str, Any], at: datetime, mode: str) -> Dict[str, Any]:
    packet = _core._base_packet(candidate, roots, at, mode)
    reasons, _ = _authority_reasons(candidate, roots, at)
    packet["reasons"] = reasons
    if mode == "CURRENT":
        packet["decision"] = READY if not reasons else HOLD
    elif mode == HISTORICAL:
        packet["historical_assessment"] = READY if not reasons else HOLD
    else:
        raise OfferError("internal: unsupported mode")
    packet.pop("receipt_sha256", None)
    packet["receipt_sha256"] = _sha256_value(packet)
    return packet


def compile_current(candidate: Any, roots: Any) -> Dict[str, Any]:
    c = _validate_candidate(candidate)
    r = _validate_roots(roots)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    return _base_packet(c, r, now, "CURRENT")


def audit_at(candidate: Any, roots: Any, at: str) -> Dict[str, Any]:
    c = _validate_candidate(candidate)
    r = _validate_roots(roots)
    when = _timestamp(at, "at")
    return _base_packet(c, r, when, HISTORICAL)


def _verify_receipt(packet: Mapping[str, Any]) -> None:
    _core._verify_receipt(packet)


def verify_historical(candidate: Any, roots: Any, packet: Any) -> bool:
    p = dict(_core._expect_mapping(packet, "packet"))
    _verify_receipt(p)
    if p.get("mode") != HISTORICAL or p.get("decision") != HISTORICAL:
        raise OfferError("packet: not historical integrity mode")
    rebuilt = audit_at(candidate, roots, p.get("evaluated_at"))
    return canonical_json(rebuilt) == canonical_json(p)


def verify_current(candidate: Any, roots: Any, packet: Any) -> bool:
    c = _validate_candidate(candidate)
    r = _validate_roots(roots)
    p = dict(_core._expect_mapping(packet, "packet"))
    _verify_receipt(p)
    if p.get("mode") != "CURRENT" or p.get("decision") not in {READY, HOLD}:
        raise OfferError("packet: not a current packet")
    original_at = _timestamp(p.get("evaluated_at"), "packet.evaluated_at")
    rebuilt = _base_packet(c, r, original_at, "CURRENT")
    if canonical_json(rebuilt) != canonical_json(p):
        return False
    if p["decision"] == READY:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        if now > original_at + timedelta(minutes=15):
            return False
        fresh = _base_packet(c, r, now, "CURRENT")
        return fresh["decision"] == READY and now < _timestamp(p["valid_until"], "packet.valid_until")
    return True


def markdown(packet: Mapping[str, Any]) -> str:
    _verify_receipt(packet)
    safe = copy.deepcopy(dict(packet))
    for item in safe["scope_items"]:
        item["deliverable"] = _markdown_text(item["deliverable"])
        if item["acceptance_evidence"]:
            item["acceptance_evidence"] = _markdown_text(item["acceptance_evidence"])
    safe["buyer_inputs"] = [_markdown_text(x) for x in safe["buyer_inputs"]]
    safe["exclusions"] = [_markdown_text(x) for x in safe["exclusions"]]
    original_receipt = packet["receipt_sha256"]
    safe.pop("receipt_sha256", None)
    safe["receipt_sha256"] = _sha256_value(safe)
    rendered = _core.markdown(safe)
    return rendered.replace(safe["receipt_sha256"], original_receipt)


def write_bundle(path: str, packet: Mapping[str, Any]) -> Dict[str, str]:
    _verify_receipt(packet)
    target = Path(path)
    parent = target.parent
    try:
        pst = os.lstat(parent)
    except OSError as exc:
        raise OfferError(f"output parent unavailable: {exc}") from exc
    if not stat.S_ISDIR(pst.st_mode) or stat.S_ISLNK(pst.st_mode):
        raise OfferError("output parent must be an ordinary directory")
    try:
        os.mkdir(target, 0o700)
    except FileExistsError as exc:
        raise OfferError("output bundle already exists") from exc
    except OSError as exc:
        raise OfferError(f"cannot create output bundle: {exc}") from exc

    packet_text = canonical_json(packet) + "\n"
    markdown_text = markdown(packet)
    manifest = {
        "packet.json": _sha256_text(packet_text),
        "offer.md": _sha256_text(markdown_text),
        "receipt.sha256": _sha256_text(packet["receipt_sha256"] + "\n"),
    }
    manifest_text = canonical_json(manifest) + "\n"
    try:
        for name, content in (
            ("packet.json", packet_text),
            ("offer.md", markdown_text),
            ("receipt.sha256", packet["receipt_sha256"] + "\n"),
            ("manifest.json", manifest_text),
        ):
            with open(target / name, "x", encoding="utf-8", newline="\n") as fh:
                fh.write(content)
                fh.flush()
                os.fsync(fh.fileno())
        dfd = os.open(target, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    except Exception as exc:
        raise OfferError(f"bundle publication failed; preserved for inspection: {exc}") from exc
    return {
        "bundle": str(target),
        "packet_receipt": packet["receipt_sha256"],
        "manifest_sha256": _sha256_text(manifest_text),
    }


__all__ = [
    "OfferError", "READY", "HOLD", "HISTORICAL", "compile_current", "audit_at",
    "verify_current", "verify_historical", "markdown", "loads_strict",
    "read_strict_json_file", "write_bundle", "canonical_json",
]
