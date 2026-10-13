"""Atomic GitHub-ref lease primitive for one-touch outbound send seams.

A lease is a precondition only. Acquiring it never authorizes an external send;
callers must separately satisfy their outbound dedupe/content/owner authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Sequence

SCHEMA = "outbound-send-lease/v1"
RECEIPT_SCHEMA = "outbound-send-lease-receipt/v1"
INDETERMINATE = frozenset({0, 408, 500, 502, 503, 504})
_TOKEN_RE = re.compile(r"^[a-z0-9][a-z0-9._:@/+\-]{2,191}$")
_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")
_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}(?:[0-9a-fA-F]{24})?$")


class LeaseError(ValueError):
    pass


def _canon_json(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")
    except (TypeError, ValueError) as exc:
        raise LeaseError("value is not canonical-JSON serializable") from exc


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canon_json(value)).hexdigest()


def _machine_token(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise LeaseError(f"{field}: must be string")
    lowered = value.casefold()
    if value != lowered or not value.isascii() or _TOKEN_RE.fullmatch(value) is None:
        raise LeaseError(f"{field}: must be lowercase ASCII machine token")
    return value


def _display_token(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.isascii() or not (3 <= len(value) <= 192):
        raise LeaseError(f"{field}: must be 3..192 ASCII chars")
    if any(ord(ch) < 0x20 or ch == "\x7f" for ch in value):
        raise LeaseError(f"{field}: control characters forbidden")
    return value


def _rfc3339(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise LeaseError(f"{field}: RFC3339 timestamp required")
    raw = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise LeaseError(f"{field}: invalid RFC3339 timestamp") from exc
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise LeaseError(f"{field}: timezone required")
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _validate_repo(repo: Any) -> str:
    if not isinstance(repo, str) or _REPO_RE.fullmatch(repo) is None:
        raise LeaseError("repo: expected owner/name")
    return repo


def _validate_sha(value: Any, field: str) -> str:
    if not isinstance(value, str) or _SHA_RE.fullmatch(value) is None:
        raise LeaseError(f"{field}: expected 40/64 hex object id")
    return value.lower()


def _validate_sha256(value: Any, field: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise LeaseError(f"{field}: expected 64 lowercase hex characters")
    if value != value.lower() or any(ch not in "0123456789abcdef" for ch in value):
        raise LeaseError(f"{field}: expected 64 lowercase hex characters")
    return value


@dataclass(frozen=True)
class Claim:
    repo: str
    buyer_scope: str
    offer_scope: str
    claimant: str
    claim_id: str
    claim_started_at: str
    anchor_sha: str
    preflight_sha256: str

    @classmethod
    def parse(cls, raw: Mapping[str, Any]) -> "Claim":
        expected = {"repo", "buyer_scope", "offer_scope", "claimant", "claim_id", "claim_started_at", "anchor_sha", "preflight_sha256"}
        if not isinstance(raw, Mapping) or set(raw) != expected:
            raise LeaseError("claim: exact fields required")
        return cls(
            _validate_repo(raw["repo"]),
            _machine_token(raw["buyer_scope"], "buyer_scope"),
            _machine_token(raw["offer_scope"], "offer_scope"),
            _display_token(raw["claimant"], "claimant"),
            _machine_token(raw["claim_id"], "claim_id"),
            _rfc3339(raw["claim_started_at"], "claim_started_at"),
            _validate_sha(raw["anchor_sha"], "anchor_sha"),
            _validate_sha256(raw["preflight_sha256"], "preflight_sha256"),
        )

    @property
    def seam(self) -> dict[str, str]:
        return {"schema": SCHEMA, "buyer_scope": self.buyer_scope, "offer_scope": self.offer_scope}

    @property
    def seam_sha256(self) -> str:
        return _sha256(self.seam)

    @property
    def ref(self) -> str:
        return f"refs/tags/outbound-lease-v1/{self.seam_sha256}"

    @property
    def tag_name(self) -> str:
        claimant_hash = hashlib.sha256(self.claimant.encode("ascii")).hexdigest()[:16]
        return f"outbound-claim-v1-{self.seam_sha256[:16]}-{claimant_hash}"

    @property
    def metadata(self) -> dict[str, str]:
        return {
            "schema": SCHEMA,
            "repo": self.repo,
            "buyer_scope": self.buyer_scope,
            "offer_scope": self.offer_scope,
            "claimant": self.claimant,
            "claim_id": self.claim_id,
            "claim_started_at": self.claim_started_at,
            "anchor_sha": self.anchor_sha,
            "preflight_sha256": self.preflight_sha256,
            "seam_sha256": self.seam_sha256,
        }


Transport = Callable[[str, str, Mapping[str, Any] | None], tuple[int, Any]]


def _object_sha(payload: Any) -> str | None:
    if not isinstance(payload, Mapping):
        return None
    obj = payload.get("object")
    sha = obj.get("sha") if isinstance(obj, Mapping) else None
    return sha.lower() if isinstance(sha, str) and _SHA_RE.fullmatch(sha) else None


def acquire(claim_raw: Mapping[str, Any], transport: Transport) -> dict[str, Any]:
    """Attempt one atomic seam lease and return a content-addressed receipt.

    Creating the annotated tag object is content-addressed/non-authoritative. The
    deterministic ref creation is the atomic authority event. A 422 or an
    indeterminate ref-create response is reconciled by exactly one GET. Only a
    ref that points to this claim's exact tag object proves lease ownership.
    """
    claim = Claim.parse(claim_raw)
    owner, repo_name = claim.repo.split("/", 1)
    tag_payload = {
        "tag": claim.tag_name,
        "message": _canon_json(claim.metadata).decode("ascii") + "\n",
        "object": claim.anchor_sha,
        "type": "commit",
        "tagger": {
            "name": "outbound-send-lease",
            "email": "lease@tokenjunkielabs.invalid",
            "date": claim.claim_started_at,
        },
    }
    tag_status, tag_body = transport("POST", f"/repos/{owner}/{repo_name}/git/tags", tag_payload)
    if tag_status != 201 or not isinstance(tag_body, Mapping):
        raise LeaseError(f"TAG_OBJECT_CREATE_FAILED_{tag_status}")
    tag_sha = _validate_sha(tag_body.get("sha"), "tag response sha")

    ref_payload = {"ref": claim.ref, "sha": tag_sha}
    ref_status, ref_body = transport("POST", f"/repos/{owner}/{repo_name}/git/refs", ref_payload)
    reason: str
    lease_held = False
    observed_sha: str | None = None
    if ref_status == 201:
        observed_sha = _object_sha(ref_body)
        if observed_sha != tag_sha:
            ref_status_for_reason = ref_status
        else:
            lease_held = True
            reason = "ACQUIRED_CREATE_201"
            ref_status_for_reason = None
    else:
        ref_status_for_reason = ref_status

    if not lease_held:
        if ref_status_for_reason not in INDETERMINATE and ref_status_for_reason != 422 and ref_status_for_reason != 201:
            reason = f"ACQUIRE_REJECTED_{ref_status_for_reason}"
        else:
            quoted = urllib.parse.quote(claim.ref.removeprefix("refs/"), safe="/")
            read_status, read_body = transport("GET", f"/repos/{owner}/{repo_name}/git/ref/{quoted}", None)
            if read_status == 200:
                observed_sha = _object_sha(read_body)
                if observed_sha == tag_sha:
                    lease_held = True
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
        "seam_sha256": claim.seam_sha256,
        "lease_ref": claim.ref,
        "claim_id": claim.claim_id,
        "claimant": claim.claimant,
        "claim_started_at": claim.claim_started_at,
        "preflight_sha256": claim.preflight_sha256,
        "tag_object_sha": tag_sha,
        "observed_ref_sha": observed_sha,
        "lease_held_by_claimant": lease_held,
        "decision": "LEASE_HELD" if lease_held else "HOLD",
        "reason": reason,
        "external_send_authorized": False,
    }
    material = dict(receipt)
    receipt["receipt_sha256"] = _sha256(material)
    return receipt


def verify_receipt(raw: Mapping[str, Any]) -> bool:
    expected = {
        "schema", "seam_sha256", "lease_ref", "claim_id", "claimant",
        "claim_started_at", "preflight_sha256", "tag_object_sha",
        "observed_ref_sha", "lease_held_by_claimant", "decision", "reason",
        "external_send_authorized", "receipt_sha256",
    }
    if not isinstance(raw, Mapping) or set(raw) != expected:
        raise LeaseError("receipt: exact fields required")
    if raw["schema"] != RECEIPT_SCHEMA:
        raise LeaseError("receipt: unsupported schema")
    seam = _validate_sha(raw["seam_sha256"], "receipt seam_sha256")
    if raw["lease_ref"] != f"refs/tags/outbound-lease-v1/{seam}":
        raise LeaseError("receipt: lease_ref/seam mismatch")
    _machine_token(raw["claim_id"], "receipt claim_id")
    _display_token(raw["claimant"], "receipt claimant")
    _rfc3339(raw["claim_started_at"], "receipt claim_started_at")
    _validate_sha256(raw["preflight_sha256"], "receipt preflight_sha256")
    tag_sha = _validate_sha(raw["tag_object_sha"], "receipt tag_object_sha")
    observed = raw["observed_ref_sha"]
    if observed is not None:
        observed = _validate_sha(observed, "receipt observed_ref_sha")
    held = raw["lease_held_by_claimant"]
    if type(held) is not bool:
        raise LeaseError("receipt: lease_held_by_claimant must be bool")
    if raw["decision"] != ("LEASE_HELD" if held else "HOLD"):
        raise LeaseError("receipt: decision inconsistent with lease state")
    if not isinstance(raw["reason"], str) or not raw["reason"]:
        raise LeaseError("receipt: reason required")
    if raw["external_send_authorized"] is not False:
        raise LeaseError("receipt: lease may never authorize external send")
    if held and observed != tag_sha:
        raise LeaseError("receipt: held lease must prove exact ref object")
    digest = _validate_sha(raw["receipt_sha256"], "receipt_sha256")
    material = dict(raw)
    del material["receipt_sha256"]
    if _sha256(material) != digest:
        raise LeaseError("receipt: digest mismatch")
    return True


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class GitHubTransport:
    def __init__(self, token: str, *, api_url: str = "https://api.github.com", timeout: float = 15.0):
        if not token:
            raise LeaseError("GitHub token required")
        if api_url != "https://api.github.com":
            raise LeaseError("api_url must be https://api.github.com")
        self._token = token
        self._base = api_url
        self._timeout = timeout
        context = ssl.create_default_context()
        self._opener = urllib.request.build_opener(_NoRedirect(), urllib.request.HTTPSHandler(context=context))

    def __call__(self, method: str, path: str, body: Mapping[str, Any] | None) -> tuple[int, Any]:
        if not path.startswith("/"):
            raise LeaseError("GitHub path must be absolute")
        data = _canon_json(body) if body is not None else None
        request = urllib.request.Request(
            self._base + path,
            data=data,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
                "User-Agent": "tjlabs-outbound-send-lease/1",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with self._opener.open(request, timeout=self._timeout) as response:
                raw = response.read()
                return int(response.status), json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            try:
                payload = json.loads(raw) if raw else None
            except json.JSONDecodeError:
                payload = None
            return int(exc.code), payload
        except (urllib.error.URLError, TimeoutError, OSError):
            return 0, None


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Acquire an atomic outbound-send seam lease")
    parser.add_argument("claim_json", help="path to exact claim JSON")
    parser.add_argument("--token-env", default="GITHUB_TOKEN")
    args = parser.parse_args(argv)
    try:
        with open(args.claim_json, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
        token = os.environ.get(args.token_env, "")
        receipt = acquire(raw, GitHubTransport(token))
    except (OSError, json.JSONDecodeError, LeaseError) as exc:
        print(f"HOLD: {exc}", file=sys.stderr)
        return 2
    print(_canon_json(receipt).decode("ascii"))
    return 0 if receipt["lease_held_by_claimant"] else 3


if __name__ == "__main__":
    raise SystemExit(main())