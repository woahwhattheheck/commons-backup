"""Proof-of-possession v2 for one-touch outbound-send seam leases.

V1 proves live-provider consistency for public claim values. V2 additionally
requires a private 256-bit capability that is generated inside acquisition and
never published. A lease remains only a mutual-exclusion prerequisite and never
authorizes an external send.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import sys
import urllib.parse
from typing import Any, Callable, Mapping, Sequence

from .atomic_lease import (
    Claim as PublicClaim,
    GitHubTransport,
    LeaseError,
    Transport,
    _canon_json,
    _display_token,
    _machine_token,
    _object_sha,
    _rfc3339,
    _sha256,
    _validate_repo,
    _validate_sha,
    _validate_sha256,
)

SCHEMA = "outbound-send-lease/v2"
RECEIPT_SCHEMA = "outbound-send-lease-receipt/v2"
REF_PREFIX = "refs/tags/outbound-lease-v2/"
CAPABILITY_BYTES = 32
INDETERMINATE = frozenset({0, 408, 500, 502, 503, 504})
CapabilitySink = Callable[[str], None]
CapabilityLeaseError = LeaseError


def _capability(value: Any) -> str:
    return _validate_sha256(value, "claim capability")


def _capability_commitment(capability: str) -> str:
    return hashlib.sha256(bytes.fromhex(_capability(capability))).hexdigest()


def _new_capability() -> str:
    return secrets.token_hex(CAPABILITY_BYTES)


def _seam(claim: PublicClaim) -> dict[str, str]:
    return {
        "schema": SCHEMA,
        "buyer_scope": claim.buyer_scope,
        "offer_scope": claim.offer_scope,
    }


def _seam_sha256(claim: PublicClaim) -> str:
    return _sha256(_seam(claim))


def _ref(claim: PublicClaim) -> str:
    return REF_PREFIX + _seam_sha256(claim)


def _tag_name(claim: PublicClaim, capability_sha256: str) -> str:
    claimant_hash = hashlib.sha256(claim.claimant.encode("ascii")).hexdigest()[:16]
    return (
        f"outbound-claim-v2-{_seam_sha256(claim)[:16]}-"
        f"{claimant_hash}-{capability_sha256[:16]}"
    )


def _metadata(claim: PublicClaim, capability_sha256: str) -> dict[str, str]:
    return {
        "schema": SCHEMA,
        "repo": claim.repo,
        "buyer_scope": claim.buyer_scope,
        "offer_scope": claim.offer_scope,
        "claimant": claim.claimant,
        "claim_id": claim.claim_id,
        "claim_started_at": claim.claim_started_at,
        "anchor_sha": claim.anchor_sha,
        "preflight_sha256": claim.preflight_sha256,
        "claim_capability_sha256": _validate_sha256(
            capability_sha256, "claim_capability_sha256"
        ),
        "seam_sha256": _seam_sha256(claim),
    }


def acquire(
    claim_raw: Mapping[str, Any],
    transport: Transport,
    *,
    retain_capability: CapabilitySink,
) -> dict[str, Any]:
    """Acquire v2 only after privately retaining a generated capability.

    The raw capability is delivered once to ``retain_capability`` before any
    provider I/O. It is never returned in the public receipt or provider data.
    """
    claim = PublicClaim.parse(claim_raw)
    if not callable(retain_capability):
        raise LeaseError("retain_capability: callable required")
    capability = _new_capability()
    capability_sha256 = _capability_commitment(capability)
    try:
        retain_capability(capability)
    except Exception as exc:
        raise LeaseError("capability retention failed before provider I/O") from exc

    owner, repo_name = claim.repo.split("/", 1)
    tag_payload = {
        "tag": _tag_name(claim, capability_sha256),
        "message": _canon_json(_metadata(claim, capability_sha256)).decode("ascii") + "\n",
        "object": claim.anchor_sha,
        "type": "commit",
        "tagger": {
            "name": "outbound-send-lease-v2",
            "email": "lease@tokenjunkielabs.invalid",
            "date": claim.claim_started_at,
        },
    }
    tag_status, tag_body = transport(
        "POST", f"/repos/{owner}/{repo_name}/git/tags", tag_payload
    )
    if tag_status != 201 or not isinstance(tag_body, Mapping):
        raise LeaseError(f"TAG_OBJECT_CREATE_FAILED_{tag_status}")
    tag_sha = _validate_sha(tag_body.get("sha"), "tag response sha")

    ref = _ref(claim)
    ref_status, ref_body = transport(
        "POST", f"/repos/{owner}/{repo_name}/git/refs", {"ref": ref, "sha": tag_sha}
    )
    held = False
    observed_sha: str | None = None
    if ref_status == 201:
        observed_sha = _object_sha(ref_body)
        if observed_sha == tag_sha:
            held = True
            reason = "ACQUIRED_CREATE_201"
            status_for_reason = None
        else:
            status_for_reason = ref_status
    else:
        status_for_reason = ref_status

    if not held:
        if (
            status_for_reason not in INDETERMINATE
            and status_for_reason not in {201, 422}
        ):
            reason = f"ACQUIRE_REJECTED_{status_for_reason}"
        else:
            quoted = urllib.parse.quote(ref.removeprefix("refs/"), safe="/")
            read_status, read_body = transport(
                "GET", f"/repos/{owner}/{repo_name}/git/ref/{quoted}", None
            )
            if read_status == 200:
                observed_sha = _object_sha(read_body)
                if observed_sha == tag_sha:
                    held = True
                    reason = "ACQUIRED_READBACK_SELF"
                elif observed_sha is not None:
                    reason = "HELD_BY_OTHER"
                else:
                    reason = "READBACK_OBJECT_INVALID"
            elif read_status == 404:
                reason = "ACQUIRE_OUTCOME_UNPROVEN"
            else:
                reason = f"READBACK_FAILED_{read_status}"

    receipt: dict[str, Any] = {
        "schema": RECEIPT_SCHEMA,
        "repo": claim.repo,
        "buyer_scope": claim.buyer_scope,
        "offer_scope": claim.offer_scope,
        "seam_sha256": _seam_sha256(claim),
        "lease_ref": ref,
        "claim_id": claim.claim_id,
        "claimant": claim.claimant,
        "claim_started_at": claim.claim_started_at,
        "anchor_sha": claim.anchor_sha,
        "preflight_sha256": claim.preflight_sha256,
        "claim_capability_sha256": capability_sha256,
        "tag_object_sha": tag_sha,
        "observed_ref_sha": observed_sha,
        "lease_held_by_claimant": held,
        "decision": "LEASE_HELD" if held else "HOLD",
        "reason": reason,
        "external_send_authorized": False,
    }
    receipt["receipt_sha256"] = _sha256(receipt)
    return receipt


_RECEIPT_FIELDS = {
    "schema", "repo", "buyer_scope", "offer_scope", "seam_sha256", "lease_ref",
    "claim_id", "claimant", "claim_started_at", "anchor_sha", "preflight_sha256",
    "claim_capability_sha256", "tag_object_sha", "observed_ref_sha",
    "lease_held_by_claimant", "decision", "reason", "external_send_authorized",
    "receipt_sha256",
}


def _claim_from_receipt(raw: Mapping[str, Any]) -> PublicClaim:
    return PublicClaim.parse(
        {
            "repo": raw["repo"],
            "buyer_scope": raw["buyer_scope"],
            "offer_scope": raw["offer_scope"],
            "claimant": raw["claimant"],
            "claim_id": raw["claim_id"],
            "claim_started_at": raw["claim_started_at"],
            "anchor_sha": raw["anchor_sha"],
            "preflight_sha256": raw["preflight_sha256"],
        }
    )


def verify_receipt(raw: Mapping[str, Any]) -> bool:
    if not isinstance(raw, Mapping) or set(raw) != _RECEIPT_FIELDS:
        raise LeaseError("v2 receipt: exact fields required")
    if raw["schema"] != RECEIPT_SCHEMA:
        raise LeaseError("v2 receipt: unsupported schema")
    claim = _claim_from_receipt(raw)
    seam = _validate_sha256(raw["seam_sha256"], "v2 receipt seam_sha256")
    if seam != _seam_sha256(claim) or raw["lease_ref"] != _ref(claim):
        raise LeaseError("v2 receipt: seam/ref mismatch")
    capability_sha = _validate_sha256(
        raw["claim_capability_sha256"], "v2 receipt claim_capability_sha256"
    )
    tag_sha = _validate_sha(raw["tag_object_sha"], "v2 receipt tag_object_sha")
    observed = raw["observed_ref_sha"]
    if observed is not None:
        observed = _validate_sha(observed, "v2 receipt observed_ref_sha")
    held = raw["lease_held_by_claimant"]
    if type(held) is not bool:
        raise LeaseError("v2 receipt: lease_held_by_claimant must be bool")
    if raw["decision"] != ("LEASE_HELD" if held else "HOLD"):
        raise LeaseError("v2 receipt: decision inconsistent with lease state")
    if not isinstance(raw["reason"], str) or not raw["reason"]:
        raise LeaseError("v2 receipt: reason required")
    if raw["external_send_authorized"] is not False:
        raise LeaseError("v2 receipt: lease may never authorize external send")
    if held and observed != tag_sha:
        raise LeaseError("v2 receipt: held lease must prove exact ref object")
    digest = _validate_sha256(raw["receipt_sha256"], "v2 receipt receipt_sha256")
    material = dict(raw)
    material.pop("receipt_sha256")
    if _sha256(material) != digest:
        raise LeaseError("v2 receipt: digest mismatch")
    _ = capability_sha
    return True


_METADATA_FIELDS = {
    "schema", "repo", "buyer_scope", "offer_scope", "claimant", "claim_id",
    "claim_started_at", "anchor_sha", "preflight_sha256",
    "claim_capability_sha256", "seam_sha256",
}


def _strict_object(items):
    out: dict[str, Any] = {}
    for key, value in items:
        if key in out:
            raise LeaseError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def _tag_metadata(tag_body: Any) -> Mapping[str, Any] | None:
    if not isinstance(tag_body, Mapping) or not isinstance(tag_body.get("message"), str):
        return None
    try:
        value = json.loads(
            tag_body["message"],
            object_pairs_hook=_strict_object,
            parse_constant=lambda token: (_ for _ in ()).throw(
                LeaseError(f"non-finite JSON number: {token}")
            ),
        )
    except (TypeError, ValueError, json.JSONDecodeError, LeaseError):
        return None
    return value if isinstance(value, Mapping) and set(value) == _METADATA_FIELDS else None


def verify_possession(
    raw: Mapping[str, Any], *, claim_capability: str, transport: Transport
) -> bool:
    """Require both live v2 provider state and the undisclosed raw capability."""
    verify_receipt(raw)
    capability = _capability(claim_capability)
    if _capability_commitment(capability) != raw["claim_capability_sha256"]:
        return False
    # Live provider state plus the private capability can recover an earlier
    # outcome-unknown/HOLD receipt. This matters because the v2 capability is
    # unique per acquisition; blindly retrying would mint a different tag.
    claim = _claim_from_receipt(raw)
    owner, repo_name = claim.repo.split("/", 1)
    quoted = urllib.parse.quote(_ref(claim).removeprefix("refs/"), safe="/")
    ref_status, ref_body = transport(
        "GET", f"/repos/{owner}/{repo_name}/git/ref/{quoted}", None
    )
    if ref_status != 200:
        return False
    live_tag_sha = _object_sha(ref_body)
    if live_tag_sha is None or live_tag_sha != raw["tag_object_sha"]:
        return False
    tag_status, tag_body = transport(
        "GET", f"/repos/{owner}/{repo_name}/git/tags/{live_tag_sha}", None
    )
    if tag_status != 200 or not isinstance(tag_body, Mapping):
        return False
    try:
        if _validate_sha(tag_body.get("sha"), "v2 tag response sha") != live_tag_sha:
            return False
    except LeaseError:
        return False
    metadata = _tag_metadata(tag_body)
    if metadata is None:
        return False
    try:
        normalized = {
            "schema": metadata["schema"],
            "repo": _validate_repo(metadata["repo"]),
            "buyer_scope": _machine_token(metadata["buyer_scope"], "v2 tag buyer_scope"),
            "offer_scope": _machine_token(metadata["offer_scope"], "v2 tag offer_scope"),
            "claimant": _display_token(metadata["claimant"], "v2 tag claimant"),
            "claim_id": _machine_token(metadata["claim_id"], "v2 tag claim_id"),
            "claim_started_at": _rfc3339(metadata["claim_started_at"], "v2 tag claim_started_at"),
            "anchor_sha": _validate_sha(metadata["anchor_sha"], "v2 tag anchor_sha"),
            "preflight_sha256": _validate_sha256(metadata["preflight_sha256"], "v2 tag preflight_sha256"),
            "claim_capability_sha256": _validate_sha256(metadata["claim_capability_sha256"], "v2 tag claim_capability_sha256"),
            "seam_sha256": _validate_sha256(metadata["seam_sha256"], "v2 tag seam_sha256"),
        }
    except LeaseError:
        return False
    if normalized != _metadata(claim, raw["claim_capability_sha256"]):
        return False
    if tag_body.get("tag") != _tag_name(claim, raw["claim_capability_sha256"]):
        return False
    obj = tag_body.get("object")
    if not isinstance(obj, Mapping) or obj.get("type") != "commit":
        return False
    try:
        if _validate_sha(obj.get("sha"), "v2 tag target sha") != claim.anchor_sha:
            return False
    except LeaseError:
        return False
    tagger = tag_body.get("tagger")
    if not isinstance(tagger, Mapping):
        return False
    if tagger.get("name") != "outbound-send-lease-v2":
        return False
    if tagger.get("email") != "lease@tokenjunkielabs.invalid":
        return False
    try:
        return _rfc3339(tagger.get("date"), "v2 tagger date") == claim.claim_started_at
    except LeaseError:
        return False


def _strict_load(raw: str) -> Mapping[str, Any]:
    try:
        value = json.loads(
            raw,
            object_pairs_hook=_strict_object,
            parse_constant=lambda token: (_ for _ in ()).throw(
                LeaseError(f"non-finite JSON number: {token}")
            ),
        )
    except json.JSONDecodeError as exc:
        raise LeaseError("invalid JSON") from exc
    if not isinstance(value, Mapping):
        raise LeaseError("claim JSON object required")
    return value


def _write_capability_file(path: str, capability: str) -> None:
    _capability(capability)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags, 0o600)
    except OSError as exc:
        raise LeaseError("capability output must be a new file") from exc
    try:
        os.fchmod(fd, 0o600)
        data = (capability + "\n").encode("ascii")
        offset = 0
        while offset < len(data):
            count = os.write(fd, data[offset:])
            if count <= 0:
                raise LeaseError("capability output write failed")
            offset += count
        os.fsync(fd)
    except Exception:
        try:
            os.close(fd)
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass
        raise
    else:
        os.close(fd)

    # Persist the newly created directory entry before any provider mutation.
    # File fsync alone does not make creation crash-durable on POSIX filesystems.
    if hasattr(os, "O_DIRECTORY"):
        parent = os.path.dirname(os.path.abspath(path)) or "."
        try:
            dir_fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except OSError as exc:
            try:
                os.unlink(path)
            except OSError:
                pass
            raise LeaseError("capability directory sync failed") from exc


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Acquire a proof-of-possession v2 outbound-send seam lease"
    )
    parser.add_argument("claim_json", help="path to exact public claim JSON")
    parser.add_argument("--capability-out", required=True, help="new owner-only private capability file")
    parser.add_argument("--token-env", default="GITHUB_TOKEN")
    args = parser.parse_args(argv)
    try:
        with open(args.claim_json, "r", encoding="utf-8") as fh:
            claim_raw = _strict_load(fh.read())
        token = os.environ.get(args.token_env, "")
        receipt = acquire(
            claim_raw,
            GitHubTransport(token),
            retain_capability=lambda secret: _write_capability_file(args.capability_out, secret),
        )
    except (OSError, LeaseError) as exc:
        print(f"HOLD: {exc}", file=sys.stderr)
        return 2
    print(_canon_json(receipt).decode("ascii"))
    return 0 if receipt["lease_held_by_claimant"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
