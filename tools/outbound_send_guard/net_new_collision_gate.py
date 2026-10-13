#!/usr/bin/env python3
"""Compose buyer-scope dedupe evidence with live v3 lease possession.

This is a collision gate, not a sender.  It proves that one exact ALLOW_NEW
buyer/offer preflight is the preflight bound into one exact provider-backed v3
lease and that the current caller still possesses that lease capability against
fresh provider readback.  Other outbound policy gates remain independent.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Mapping

SCHEMA = "outbound-net-new-collision-gate/v1"
BUYER_RECEIPT_SCHEMA = "outbound-send-buyer-scope-receipt/v2"
LEASE_RECEIPT_SCHEMA = "outbound-send-lease-receipt/v3"
DECISIONS = {"COLLISION_CLEAR", "HOLD"}
_HEX = frozenset("0123456789abcdef")


class CollisionGateError(ValueError):
    pass


def _canon_bytes(value: Any) -> bytes:
    try:
        return (
            json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise CollisionGateError("value is not canonical-JSON serializable") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canon_bytes(value)).hexdigest()


def _lease_scope_token(prefix: str, value: str) -> str:
    """Return a lowercase machine token stable across independent workers."""
    if prefix not in {"email", "offer"}:
        raise CollisionGateError("unsupported lease-scope prefix")
    text = _text(value, f"{prefix} scope source", max_len=512)
    return f"{prefix}-" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _hex64(value: Any, label: str) -> str:
    if type(value) is not str or len(value) != 64 or value != value.lower() or any(ch not in _HEX for ch in value):
        raise CollisionGateError(f"{label}: expected 64 lowercase hex characters")
    return value


def _text(value: Any, label: str, *, max_len: int = 256) -> str:
    if type(value) is not str or not value or len(value) > max_len:
        raise CollisionGateError(f"{label}: nonempty bounded string required")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise CollisionGateError(f"{label}: control characters forbidden")
    return value


def _obj(value: Any, label: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise CollisionGateError(f"{label}: object required")
    return value


def _exact(obj: Mapping[str, Any], fields: set[str], label: str) -> None:
    if set(obj) != fields:
        missing = sorted(fields - set(obj))
        extra = sorted(set(obj) - fields)
        raise CollisionGateError(f"{label}: exact fields required; missing={missing}; extra={extra}")


def _strict_pairs(pairs):
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise CollisionGateError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def parse_json_bytes(raw: bytes, label: str) -> dict[str, Any]:
    if type(raw) is not bytes:
        raise CollisionGateError(f"{label}: bytes required")
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise CollisionGateError(f"{label}: UTF-8 JSON required") from exc
    try:
        value = json.loads(
            text,
            object_pairs_hook=_strict_pairs,
            parse_constant=lambda token: (_ for _ in ()).throw(
                CollisionGateError(f"{label}: non-finite number {token}")
            ),
        )
    except CollisionGateError:
        raise
    except json.JSONDecodeError as exc:
        raise CollisionGateError(f"{label}: invalid JSON: {exc.msg}") from exc
    return _obj(value, label)


def _validate_buyer_receipt(raw: Mapping[str, Any]) -> tuple[str, str, str, str]:
    receipt = _obj(raw, "buyer receipt")
    _exact(receipt, {"payload", "receipt_sha256"}, "buyer receipt")
    payload = _obj(receipt["payload"], "buyer receipt.payload")
    expected_payload_fields = {
        "schema_version", "buyer_scope", "source", "core_receipt_sha256", "core",
        "decision", "authority", "side_effects_authorized",
    }
    _exact(payload, expected_payload_fields, "buyer receipt.payload")
    if payload["schema_version"] != BUYER_RECEIPT_SCHEMA:
        raise CollisionGateError("buyer receipt: unsupported schema")
    receipt_sha = _hex64(receipt["receipt_sha256"], "buyer receipt.receipt_sha256")
    if _digest(payload) != receipt_sha:
        raise CollisionGateError("buyer receipt: digest mismatch")
    if payload["side_effects_authorized"] is not False:
        raise CollisionGateError("buyer receipt: side effects must remain unauthorized")

    buyer = _obj(payload["buyer_scope"], "buyer receipt.payload.buyer_scope")
    _exact(buyer, {"scope_id", "members"}, "buyer receipt.payload.buyer_scope")
    scope_id = _text(buyer["scope_id"], "buyer scope id", max_len=200)
    members = buyer["members"]
    if type(members) is not list or not members:
        raise CollisionGateError("buyer receipt: nonempty members required")
    member_emails: set[str] = set()
    for index, raw_member in enumerate(members):
        member = _obj(raw_member, f"buyer receipt member[{index}]")
        _exact(member, {"email", "mailbox_complete", "mailbox_query_id", "slack_complete", "slack_query_id"}, f"buyer receipt member[{index}]")
        email = _text(member["email"], f"buyer receipt member[{index}].email", max_len=320)
        if email in member_emails:
            raise CollisionGateError("buyer receipt: duplicate member email")
        member_emails.add(email)
        if type(member["mailbox_complete"]) is not bool or type(member["slack_complete"]) is not bool:
            raise CollisionGateError("buyer receipt: member completeness flags must be boolean")
        _text(member["mailbox_query_id"], f"buyer receipt member[{index}].mailbox_query_id", max_len=200)
        _text(member["slack_query_id"], f"buyer receipt member[{index}].slack_query_id", max_len=200)

    core = _obj(payload["core"], "buyer receipt.payload.core")
    core_sha = _hex64(payload["core_receipt_sha256"], "buyer receipt.core_receipt_sha256")
    if _digest(core) != core_sha:
        raise CollisionGateError("buyer receipt: embedded core digest mismatch")
    core_intent = _obj(core.get("intent"), "buyer receipt.payload.core.intent")
    recipient = _text(core_intent.get("recipient"), "core intent recipient", max_len=320)
    offer_id = _text(core_intent.get("offer_id"), "core intent offer_id", max_len=200)
    if core_intent.get("route_kind") != "email":
        raise CollisionGateError("buyer receipt: core route must be email")
    if recipient not in member_emails:
        raise CollisionGateError("buyer receipt: core recipient is not a declared buyer-scope member")
    if core.get("side_effects_authorized") is not False:
        raise CollisionGateError("buyer receipt: embedded core may not authorize side effects")
    if core.get("decision") != payload["decision"] or core.get("authority") != payload["authority"]:
        raise CollisionGateError("buyer receipt: projected decision/authority mismatch")
    return receipt_sha, scope_id, recipient, offer_id


def _default_receipt_verifier(raw: Mapping[str, Any]) -> bool:
    from .connector_capability_lease import verify_receipt
    return bool(verify_receipt(raw))


def _default_possession_verifier(
    raw: Mapping[str, Any], *, claim_capability: str,
    live_branch_sha: str | None, live_parent_sha: str | None,
    live_metadata_json: str | None,
) -> bool:
    from .connector_capability_lease import verify_possession
    return bool(
        verify_possession(
            raw,
            claim_capability=claim_capability,
            live_branch_sha=live_branch_sha,
            live_parent_sha=live_parent_sha,
            live_metadata_json=live_metadata_json,
        )
    )


def evaluate(
    buyer_receipt: Mapping[str, Any],
    lease_receipt: Mapping[str, Any],
    *,
    claim_capability: str,
    live_branch_sha: str | None,
    live_parent_sha: str | None,
    live_metadata_json: str | None,
    receipt_verifier: Callable[[Mapping[str, Any]], bool] | None = None,
    possession_verifier: Callable[..., bool] | None = None,
) -> dict[str, Any]:
    """Return a content-addressed collision decision for one net-new outreach seam.

    Malformed/tampered public artifacts raise ``CollisionGateError``.  Valid but
    non-authoritative/other-owned evidence returns ``HOLD``.  The raw capability
    is never copied into the result.
    """
    buyer_sha, buyer_scope_id, recipient, offer_id = _validate_buyer_receipt(buyer_receipt)
    expected_lease_buyer_scope = _lease_scope_token("email", recipient)
    expected_lease_offer_scope = _lease_scope_token("offer", offer_id)
    capability = _hex64(claim_capability, "claim capability")
    lease = _obj(lease_receipt, "lease receipt")
    if lease.get("schema") != LEASE_RECEIPT_SCHEMA:
        raise CollisionGateError("lease receipt: unsupported schema")
    verify_receipt = receipt_verifier or _default_receipt_verifier
    try:
        if verify_receipt(lease) is not True:
            raise CollisionGateError("lease receipt: verifier rejected receipt")
    except CollisionGateError:
        raise
    except Exception as exc:
        raise CollisionGateError(f"lease receipt: invalid: {exc}") from exc

    lease_buyer = _text(lease.get("buyer_scope"), "lease buyer_scope", max_len=200)
    lease_offer = _text(lease.get("offer_scope"), "lease offer_scope", max_len=200)
    lease_preflight = _hex64(lease.get("preflight_sha256"), "lease preflight_sha256")
    if lease.get("external_send_authorized") is not False:
        raise CollisionGateError("lease receipt may never authorize external send")
    held = lease.get("lease_held_by_claimant")
    if type(held) is not bool:
        raise CollisionGateError("lease receipt.lease_held_by_claimant must be boolean")

    reasons: list[str] = []
    buyer_payload = buyer_receipt["payload"]
    if buyer_payload["decision"] != "ALLOW_NEW":
        reasons.append("BUYER_PREFLIGHT_NOT_ALLOW_NEW")
    if buyer_payload["authority"] != "complete":
        reasons.append("BUYER_PREFLIGHT_AUTHORITY_NOT_COMPLETE")
    if lease_buyer != expected_lease_buyer_scope:
        reasons.append("RECIPIENT_LEASE_SCOPE_BINDING_MISMATCH")
    if lease_offer != expected_lease_offer_scope:
        reasons.append("OFFER_LEASE_SCOPE_BINDING_MISMATCH")
    if lease_preflight != buyer_sha:
        reasons.append("PREFLIGHT_DIGEST_BINDING_MISMATCH")
    if lease.get("decision") != "LEASE_HELD" or held is not True:
        reasons.append("LEASE_NOT_HELD")

    possession_ok = False
    if not reasons:
        verify_possession = possession_verifier or _default_possession_verifier
        try:
            possession_ok = verify_possession(
                lease,
                claim_capability=capability,
                live_branch_sha=live_branch_sha,
                live_parent_sha=live_parent_sha,
                live_metadata_json=live_metadata_json,
            ) is True
        except Exception:
            possession_ok = False
        if not possession_ok:
            reasons.append("LIVE_LEASE_POSSESSION_NOT_PROVEN")

    clear = not reasons
    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "decision": "COLLISION_CLEAR" if clear else "HOLD",
        "collision_gate_passed": clear,
        "buyer_scope_id": buyer_scope_id,
        "lease_buyer_scope": expected_lease_buyer_scope,
        "lease_offer_scope": expected_lease_offer_scope,
        "buyer_preflight_receipt_sha256": buyer_sha,
        "lease_receipt_sha256": _hex64(lease.get("receipt_sha256"), "lease receipt_sha256"),
        "lease_seam_sha256": _hex64(lease.get("seam_sha256"), "lease seam_sha256"),
        "lease_claimant": _text(lease.get("claimant"), "lease claimant", max_len=192),
        "lease_claim_id": _text(lease.get("claim_id"), "lease claim_id", max_len=192),
        "live_possession_proven": possession_ok,
        "reasons": reasons,
        "external_send_authorized": False,
    }
    return {"payload": payload, "receipt_sha256": _digest(payload)}


def _regular_file_bytes(path: Path, label: str) -> bytes:
    try:
        st = path.lstat()
    except OSError as exc:
        raise CollisionGateError(f"{label}: cannot stat {path}: {exc}") from exc
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
        raise CollisionGateError(f"{label}: ordinary regular file required")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise CollisionGateError(f"{label}: cannot read {path}: {exc}") from exc


def _private_capability(path: Path) -> str:
    raw = _regular_file_bytes(path, "capability file")
    if os.name != "nt":
        mode = path.stat().st_mode
        if mode & 0o077:
            raise CollisionGateError("capability file must not be group/world accessible")
    try:
        text = raw.decode("ascii").strip()
    except UnicodeDecodeError as exc:
        raise CollisionGateError("capability file must contain ASCII hex") from exc
    return _hex64(text, "capability file")


def _same_path(a: Path, b: Path) -> bool:
    try:
        return a.resolve(strict=False) == b.resolve(strict=False) or (a.exists() and b.exists() and os.path.samefile(a, b))
    except OSError as exc:
        raise CollisionGateError(f"cannot compare path identity: {exc}") from exc


def _atomic_write(path: Path, raw: bytes) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=f".{path.name}.stage-", dir=str(path.parent))
    except OSError as exc:
        raise CollisionGateError(f"cannot stage output {path}: {exc}") from exc
    temp = Path(name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
        if os.name != "nt":
            dfd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(dfd)
            finally:
                os.close(dfd)
    except OSError as exc:
        try:
            temp.unlink(missing_ok=True)
        finally:
            raise CollisionGateError(f"cannot publish output {path}: {exc}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compose net-new outbound dedupe evidence with live v3 lease possession")
    parser.add_argument("--buyer-receipt", required=True, type=Path)
    parser.add_argument("--lease-receipt", required=True, type=Path)
    parser.add_argument("--capability-file", required=True, type=Path)
    parser.add_argument("--live-branch-sha", required=True)
    parser.add_argument("--live-parent-sha", required=True)
    parser.add_argument("--live-metadata", required=True, type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    try:
        inputs = [args.buyer_receipt, args.lease_receipt, args.capability_file, args.live_metadata]
        for i, first in enumerate(inputs):
            for second in inputs[i + 1:]:
                if _same_path(first, second):
                    raise CollisionGateError("all input files must be distinct")
        if args.out is not None and any(_same_path(args.out, src) for src in inputs):
            raise CollisionGateError("output must not alias any input")
        buyer = parse_json_bytes(_regular_file_bytes(args.buyer_receipt, "buyer receipt"), "buyer receipt")
        lease = parse_json_bytes(_regular_file_bytes(args.lease_receipt, "lease receipt"), "lease receipt")
        capability = _private_capability(args.capability_file)
        live_metadata_raw = _regular_file_bytes(args.live_metadata, "live metadata")
        try:
            live_metadata = live_metadata_raw.decode("ascii", errors="strict")
        except UnicodeDecodeError as exc:
            raise CollisionGateError("live metadata must be ASCII") from exc
        result = evaluate(
            buyer,
            lease,
            claim_capability=capability,
            live_branch_sha=args.live_branch_sha,
            live_parent_sha=args.live_parent_sha,
            live_metadata_json=live_metadata,
        )
        encoded = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8") + b"\n"
        if args.out is None:
            sys.stdout.buffer.write(encoded)
        else:
            _atomic_write(args.out, encoded)
        return 0 if result["payload"]["decision"] == "COLLISION_CLEAR" else 4
    except CollisionGateError as exc:
        print(f"outbound-net-new-collision-gate: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
