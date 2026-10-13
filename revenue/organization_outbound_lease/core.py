from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Optional, Protocol, Tuple

from .local_reference import _LOCAL_REFERENCE_CHECKER
from .strict import parse_json_strict

READY_STATE = "READY_FOR_SINGLE_WRITER_REVIEW"
LEASE_SCHEMA = "commons.organization-outbound-lease/v2"
ATTESTATION_SCHEMA = "commons.organization-pressure-attestation/v2"
OUTCOME_SCHEMA = "commons.organization-outbound-outcome/v2"
ACQUIRE_SCHEMA = "commons.organization-outbound-acquire/v2"
FINALIZE_SCHEMA = "commons.organization-outbound-finalize/v2"
TERMINAL_STATES = frozenset({"SENT", "OUTCOME_UNKNOWN", "REJECTED", "HELD_AUTHORITY", "UNSENT_RELEASED"})
BLOCKING_TERMINALS = frozenset({"SENT", "OUTCOME_UNKNOWN", "REJECTED", "HELD_AUTHORITY"})
MAX_PREFLIGHT_AGE_SECONDS = 300
MAX_OUTCOME_AGE_SECONDS = 600
MAX_FUTURE_SKEW_SECONDS = 5
HEX64 = re.compile(r"^[0-9a-f]{64}$")
HEX_ANY = re.compile(r"^[0-9a-f]+$")
OPAQUE = re.compile(r"^[A-Za-z0-9._:-]{1,160}$")
RSA_SHA256_DIGESTINFO_PREFIX = bytes.fromhex("3031300d060960864801650304020105000420")
PRESSURE_DOMAIN = b"commons-pressure-v2\x00"
HOLDER_DOMAIN = b"holder-capability-v1\x00"


class LeaseStore(Protocol):
    def get_active(self, org_fingerprint: str) -> Optional[Tuple[bytes, str]]: ...
    def get_outcome(self, org_fingerprint: str, lease_id: str) -> Optional[Tuple[bytes, str]]: ...
    def create_active(self, org_fingerprint: str, content: bytes) -> str: ...
    def create_outcome(self, org_fingerprint: str, lease_id: str, content: bytes) -> str: ...
    def delete_active(self, org_fingerprint: str, expected_generation: str) -> None: ...


@dataclass(frozen=True)
class RsaPublicKey:
    key_id: str
    modulus: int
    exponent: int = 65537

    def __post_init__(self) -> None:
        _opaque(self.key_id, "RSA key id")
        if type(self.modulus) is not int or self.modulus <= 0 or self.modulus.bit_length() < 2048:
            raise ValueError("RSA modulus must be at least 2048 bits")
        if self.modulus % 2 == 0:
            raise ValueError("RSA modulus must be odd")
        if type(self.exponent) is not int or self.exponent < 3 or self.exponent % 2 == 0 or self.exponent >= self.modulus:
            raise ValueError("RSA public exponent must be an odd integer >= 3 and smaller than modulus")

    @classmethod
    def from_hex(cls, *, key_id: str, modulus_hex: str, exponent: int = 65537) -> "RsaPublicKey":
        if not isinstance(modulus_hex, str) or not modulus_hex or not HEX_ANY.fullmatch(modulus_hex):
            raise ValueError("RSA modulus must be lower-case hex")
        return cls(key_id=key_id, modulus=int(modulus_hex, 16), exponent=exponent)


@dataclass(frozen=True)
class AcquireResult:
    state: str
    lease: dict
    active_generation: Optional[str]
    replay: bool
    terminal_outcome: Optional[str] = None


@dataclass(frozen=True)
class FinalizeResult:
    state: str
    outcome: dict
    outcome_generation: str
    active_released: bool
    replay: bool


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _require_secret(key: bytes, label: str) -> bytes:
    if not isinstance(key, (bytes, bytearray)) or len(key) < 32:
        raise ValueError("%s must be at least 32 bytes" % label)
    return bytes(key)


def fingerprint_organization(canonical_identity: bytes, key: bytes) -> str:
    key = _require_secret(key, "organization fingerprint key")
    if not isinstance(canonical_identity, (bytes, bytearray)):
        raise TypeError("canonical organization identity must be bytes")
    raw = bytes(canonical_identity)
    if not (1 <= len(raw) <= 4096):
        raise ValueError("canonical organization identity must be 1..4096 bytes")
    return hmac.new(key, b"org-v1\x00" + raw, hashlib.sha256).hexdigest()


def holder_capability_commitment(capability: bytes) -> str:
    if not isinstance(capability, (bytes, bytearray)) or len(capability) != 32:
        raise ValueError("holder capability must be exactly 32 bytes")
    return sha256_hex(HOLDER_DOMAIN + bytes(capability))


def normalize_organization_fingerprint(value: Any) -> str:
    return _hex64(value, "organizationFingerprint")


def _utc(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("%s must be canonical UTC seconds" % label)
    try:
        dt = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise ValueError("%s must be canonical UTC seconds" % label) from exc
    rendered = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    if rendered != value:
        raise ValueError("%s must be canonical UTC seconds" % label)
    return value


def _dt(value: str, label: str) -> datetime:
    _utc(value, label)
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _process_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _require_fresh(event_time: str, *, now: datetime, max_age_seconds: int, label: str) -> None:
    dt = _dt(event_time, label)
    if dt > now + timedelta(seconds=MAX_FUTURE_SKEW_SECONDS):
        raise ValueError("%s is from the future" % label)
    age = (now - dt).total_seconds()
    if age > max_age_seconds:
        raise ValueError("%s is stale" % label)


def _hex64(value: Any, label: str) -> str:
    if not isinstance(value, str) or not HEX64.fullmatch(value):
        raise ValueError("%s must be lower-case sha256 hex" % label)
    return value


def _hex_exact(value: Any, nbytes: int, label: str) -> str:
    if not isinstance(value, str) or len(value) != nbytes * 2 or not HEX_ANY.fullmatch(value):
        raise ValueError("%s must be exactly %d bytes of lower-case hex" % (label, nbytes))
    return value


def _opaque(value: Any, label: str) -> str:
    if not isinstance(value, str) or not OPAQUE.fullmatch(value):
        raise ValueError("%s must be a bounded opaque token" % label)
    return value


def _exact_keys(obj: Any, expected: set, label: str) -> Mapping[str, Any]:
    if type(obj) is not dict:
        raise ValueError("%s must be an object" % label)
    got = set(obj)
    if got != expected:
        missing = sorted(expected - got)
        extra = sorted(got - expected)
        raise ValueError("%s keys mismatch missing=%r extra=%r" % (label, missing, extra))
    return obj


def _raise(message: str):
    raise ValueError(message)


def pressure_attestation_body(payload: Mapping[str, Any]) -> dict:
    expected = {
        "schema", "organizationFingerprint", "pressureReceiptSha256",
        "authorityCommitment", "ledgerCommitment", "verifiedState", "verifiedAt",
    }
    obj = _exact_keys(payload, expected, "pressure attestation body")
    if obj["schema"] != ATTESTATION_SCHEMA:
        raise ValueError("unsupported pressure attestation schema")
    return {
        "schema": ATTESTATION_SCHEMA,
        "organizationFingerprint": _hex64(obj["organizationFingerprint"], "organizationFingerprint"),
        "pressureReceiptSha256": _hex64(obj["pressureReceiptSha256"], "pressureReceiptSha256"),
        "authorityCommitment": _hex64(obj["authorityCommitment"], "authorityCommitment"),
        "ledgerCommitment": _hex64(obj["ledgerCommitment"], "ledgerCommitment"),
        "verifiedState": obj["verifiedState"] if obj["verifiedState"] == READY_STATE else _raise("upstream state is not positive"),
        "verifiedAt": _utc(obj["verifiedAt"], "verifiedAt"),
    }


def _rsa_pkcs1_v15_sha256_verify(public_key: RsaPublicKey, message: bytes, signature_hex: str) -> None:
    k = (public_key.modulus.bit_length() + 7) // 8
    signature_hex = _hex_exact(signature_hex, k, "pressure RSA signature")
    sig = int(signature_hex, 16)
    if sig >= public_key.modulus:
        raise ValueError("pressure RSA signature out of range")
    em = pow(sig, public_key.exponent, public_key.modulus).to_bytes(k, "big")
    digest_info = RSA_SHA256_DIGESTINFO_PREFIX + hashlib.sha256(message).digest()
    pad_len = k - len(digest_info) - 3
    if pad_len < 8:
        raise ValueError("RSA modulus too small for SHA-256 signature")
    expected = b"\x00\x01" + (b"\xff" * pad_len) + b"\x00" + digest_info
    if not hmac.compare_digest(em, expected):
        raise ValueError("invalid pressure RSA signature")


def verify_pressure_attestation(attestation: Any, verifier: RsaPublicKey, *, organization_fingerprint: str) -> dict:
    obj = _exact_keys(attestation, {"body", "algorithm", "keyId", "signatureHex"}, "pressure attestation")
    if obj["algorithm"] != "RS256-PKCS1-v1_5":
        raise ValueError("unsupported pressure signature algorithm")
    if _opaque(obj["keyId"], "pressure keyId") != verifier.key_id:
        raise ValueError("pressure signature key id mismatch")
    body = pressure_attestation_body(obj["body"])
    message = PRESSURE_DOMAIN + canonical_json(body)
    _rsa_pkcs1_v15_sha256_verify(verifier, message, obj["signatureHex"])
    if body["organizationFingerprint"] != _hex64(organization_fingerprint, "organization_fingerprint"):
        raise ValueError("pressure attestation organization transplant")
    return body


def normalize_request(request: Any) -> dict:
    expected = {
        "schema", "claimId", "organizationFingerprint", "prospectFingerprint",
        "routeCommitment", "opportunityCommitment", "holderCapabilityCommitment",
        "requestedAt", "pressureAttestation",
    }
    obj = _exact_keys(request, expected, "acquire request")
    if obj["schema"] != ACQUIRE_SCHEMA:
        raise ValueError("unsupported acquire schema")
    return {
        "schema": obj["schema"],
        "claimId": _opaque(obj["claimId"], "claimId"),
        "organizationFingerprint": _hex64(obj["organizationFingerprint"], "organizationFingerprint"),
        "prospectFingerprint": _hex64(obj["prospectFingerprint"], "prospectFingerprint"),
        "routeCommitment": _hex64(obj["routeCommitment"], "routeCommitment"),
        "opportunityCommitment": _hex64(obj["opportunityCommitment"], "opportunityCommitment"),
        "holderCapabilityCommitment": _hex64(obj["holderCapabilityCommitment"], "holderCapabilityCommitment"),
        "requestedAt": _utc(obj["requestedAt"], "requestedAt"),
        "pressureAttestation": obj["pressureAttestation"],
    }


def _lease_document(request: dict, pressure: dict, nonce_key: bytes) -> dict:
    nonce_key = _require_secret(nonce_key, "lease nonce key")
    intent = {
        "claimId": request["claimId"],
        "organizationFingerprint": request["organizationFingerprint"],
        "prospectFingerprint": request["prospectFingerprint"],
        "routeCommitment": request["routeCommitment"],
        "opportunityCommitment": request["opportunityCommitment"],
        "holderCapabilityCommitment": request["holderCapabilityCommitment"],
        "requestedAt": request["requestedAt"],
        "pressureReceiptSha256": pressure["pressureReceiptSha256"],
        "authorityCommitment": pressure["authorityCommitment"],
        "ledgerCommitment": pressure["ledgerCommitment"],
        "pressureVerifiedAt": pressure["verifiedAt"],
    }
    intent_sha = sha256_hex(canonical_json(intent))
    nonce = hmac.new(nonce_key, b"lease-nonce-v2\x00" + canonical_json(intent), hashlib.sha256).hexdigest()
    lease_id = sha256_hex(b"lease-id-v2\x00" + bytes.fromhex(intent_sha) + bytes.fromhex(nonce))
    body = {
        "schema": LEASE_SCHEMA,
        "leaseId": lease_id,
        "intentSha256": intent_sha,
        "leaseNonce": nonce,
        **intent,
        "externalSendAuthorized": False,
    }
    body["leaseSha256"] = sha256_hex(canonical_json(body))
    return body


def verify_lease_document(value: Any) -> dict:
    expected = {
        "schema", "leaseId", "intentSha256", "leaseNonce", "claimId",
        "organizationFingerprint", "prospectFingerprint", "routeCommitment",
        "opportunityCommitment", "holderCapabilityCommitment", "requestedAt",
        "pressureReceiptSha256", "authorityCommitment", "ledgerCommitment",
        "pressureVerifiedAt", "externalSendAuthorized", "leaseSha256",
    }
    obj = dict(_exact_keys(value, expected, "lease"))
    if obj["schema"] != LEASE_SCHEMA:
        raise ValueError("unsupported lease schema")
    for key in (
        "leaseId", "intentSha256", "leaseNonce", "organizationFingerprint",
        "prospectFingerprint", "routeCommitment", "opportunityCommitment",
        "holderCapabilityCommitment", "pressureReceiptSha256", "authorityCommitment",
        "ledgerCommitment", "leaseSha256",
    ):
        _hex64(obj[key], key)
    _opaque(obj["claimId"], "claimId")
    _utc(obj["requestedAt"], "requestedAt")
    _utc(obj["pressureVerifiedAt"], "pressureVerifiedAt")
    if obj["externalSendAuthorized"] is not False:
        raise ValueError("lease can never authorize external send")
    claimed = obj.pop("leaseSha256")
    actual = sha256_hex(canonical_json(obj))
    obj["leaseSha256"] = claimed
    if not hmac.compare_digest(claimed, actual):
        raise ValueError("lease digest mismatch")
    return obj


def _retained_outcome_for_candidate(store: LeaseStore, lease: dict) -> Optional[Tuple[dict, str]]:
    existing = store.get_outcome(lease["organizationFingerprint"], lease["leaseId"])
    if existing is None:
        return None
    raw, generation = existing
    outcome = verify_outcome_document(parse_json_strict(raw.decode("utf-8")))
    if outcome["leaseSha256"] != lease["leaseSha256"] or outcome["leaseNonce"] != lease["leaseNonce"]:
        raise ValueError("retained outcome conflicts with candidate lease identity")
    return outcome, generation


def acquire_lease(
    store: LeaseStore,
    request: Any,
    *,
    pressure_verifier: Optional[RsaPublicKey] = None,
    lease_nonce_key: bytes,
) -> AcquireResult:
    """Acquire under the pinned production verifier or explicit local test seam.

    Caller-selected verifier material is accepted only for the frozen local/reference
    FileLeaseStore implementation.  Production and unknown stores are rejected before
    request parsing or store I/O.  This boundary lives in ``core`` itself, so reloading
    this module cannot restore the old raw caller-verifier function.
    """
    if pressure_verifier is None:
        from .trust import load_pressure_verifier
        verifier = load_pressure_verifier()
    else:
        if not _LOCAL_REFERENCE_CHECKER(store):
            raise ValueError("caller-supplied pressure verifier is forbidden for production stores")
        verifier = pressure_verifier

    req = normalize_request(request)
    pressure = verify_pressure_attestation(req["pressureAttestation"], verifier, organization_fingerprint=req["organizationFingerprint"])
    if _dt(pressure["verifiedAt"], "pressure verifiedAt") > _dt(req["requestedAt"], "requestedAt"):
        raise ValueError("pressure verification cannot postdate acquire request")
    if (_dt(req["requestedAt"], "requestedAt") - _dt(pressure["verifiedAt"], "pressure verifiedAt")).total_seconds() > MAX_PREFLIGHT_AGE_SECONDS:
        raise ValueError("pressure verification is stale relative to acquire request")
    lease = _lease_document(req, pressure, lease_nonce_key)
    content = canonical_json(lease)

    # A retained terminal is stronger than an active byte match. This blocks exact
    # replay after SENT/UNKNOWN/etc and prevents A->release->A ABA re-creation.
    retained = _retained_outcome_for_candidate(store, lease)
    if retained is not None:
        outcome, _ = retained
        return AcquireResult(
            "LEASE_FINALIZED_%s" % outcome["outcome"],
            lease,
            None,
            True,
            terminal_outcome=outcome["outcome"],
        )

    # Exact already-held replay may recover after freshness because it creates no new
    # authority. A conflicting holder is disclosed only as a public lease document.
    existing = store.get_active(req["organizationFingerprint"])
    if existing is not None:
        raw, generation = existing
        existing_lease = verify_lease_document(parse_json_strict(raw.decode("utf-8")))
        if existing_lease["leaseSha256"] == lease["leaseSha256"]:
            return AcquireResult("LEASE_ACQUIRED", existing_lease, generation, True)
        return AcquireResult("ORGANIZATION_ALREADY_LEASED", existing_lease, generation, False)

    now = _process_now()
    _require_fresh(req["requestedAt"], now=now, max_age_seconds=MAX_PREFLIGHT_AGE_SECONDS, label="requestedAt")
    _require_fresh(pressure["verifiedAt"], now=now, max_age_seconds=MAX_PREFLIGHT_AGE_SECONDS, label="pressure verifiedAt")

    try:
        generation = store.create_active(req["organizationFingerprint"], content)
        return AcquireResult("LEASE_ACQUIRED", lease, generation, False)
    except Exception as exc:
        # Reconcile outcome first: another actor may have acquired+finalized between
        # our create attempt and authoritative readback.
        retained = _retained_outcome_for_candidate(store, lease)
        if retained is not None:
            outcome, _ = retained
            return AcquireResult(
                "LEASE_FINALIZED_%s" % outcome["outcome"],
                lease,
                None,
                True,
                terminal_outcome=outcome["outcome"],
            )
        existing = store.get_active(req["organizationFingerprint"])
        if existing is None:
            raise RuntimeError("acquire outcome uncertain; reconciliation required") from exc
        raw, generation = existing
        existing_lease = verify_lease_document(parse_json_strict(raw.decode("utf-8")))
        if existing_lease["leaseSha256"] == lease["leaseSha256"]:
            return AcquireResult("LEASE_ACQUIRED", existing_lease, generation, True)
        return AcquireResult("ORGANIZATION_ALREADY_LEASED", existing_lease, generation, False)


def normalize_finalize_request(value: Any) -> dict:
    expected = {
        "schema", "organizationFingerprint", "leaseId", "leaseNonce", "claimId",
        "outcomeId", "outcome", "observedAt", "evidenceCommitment", "holderCapability",
    }
    obj = _exact_keys(value, expected, "finalize request")
    if obj["schema"] != FINALIZE_SCHEMA:
        raise ValueError("unsupported finalize schema")
    if obj["outcome"] not in TERMINAL_STATES:
        raise ValueError("unsupported terminal outcome")
    return {
        "schema": obj["schema"],
        "organizationFingerprint": _hex64(obj["organizationFingerprint"], "organizationFingerprint"),
        "leaseId": _hex64(obj["leaseId"], "leaseId"),
        "leaseNonce": _hex64(obj["leaseNonce"], "leaseNonce"),
        "claimId": _opaque(obj["claimId"], "claimId"),
        "outcomeId": _opaque(obj["outcomeId"], "outcomeId"),
        "outcome": obj["outcome"],
        "observedAt": _utc(obj["observedAt"], "observedAt"),
        "evidenceCommitment": _hex64(obj["evidenceCommitment"], "evidenceCommitment"),
        "holderCapability": _hex_exact(obj["holderCapability"], 32, "holderCapability"),
    }


def _assert_holder_capability(req: dict, commitment: str) -> None:
    actual = holder_capability_commitment(bytes.fromhex(req["holderCapability"]))
    if not hmac.compare_digest(actual, commitment):
        raise ValueError("holder capability does not authorize this lease")


def _outcome_doc(req: dict, lease: dict) -> dict:
    if req["organizationFingerprint"] != lease["organizationFingerprint"]:
        raise ValueError("cross-organization finalization")
    if req["leaseId"] != lease["leaseId"] or req["leaseNonce"] != lease["leaseNonce"] or req["claimId"] != lease["claimId"]:
        raise ValueError("finalization does not bind exact lease generation")
    _assert_holder_capability(req, lease["holderCapabilityCommitment"])
    if _dt(req["observedAt"], "observedAt") < _dt(lease["requestedAt"], "requestedAt"):
        raise ValueError("outcome predates acquire request")
    body = {
        "schema": OUTCOME_SCHEMA,
        "organizationFingerprint": req["organizationFingerprint"],
        "leaseId": req["leaseId"],
        "leaseNonce": req["leaseNonce"],
        "leaseSha256": lease["leaseSha256"],
        "holderCapabilityCommitment": lease["holderCapabilityCommitment"],
        "claimId": req["claimId"],
        "outcomeId": req["outcomeId"],
        "outcome": req["outcome"],
        "observedAt": req["observedAt"],
        "evidenceCommitment": req["evidenceCommitment"],
        "externalSendAuthorized": False,
        "cashOrRevenueClaimed": False,
    }
    body["outcomeSha256"] = sha256_hex(canonical_json(body))
    return body


def verify_outcome_document(value: Any) -> dict:
    expected = {
        "schema", "organizationFingerprint", "leaseId", "leaseNonce", "leaseSha256",
        "holderCapabilityCommitment", "claimId", "outcomeId", "outcome", "observedAt",
        "evidenceCommitment", "externalSendAuthorized", "cashOrRevenueClaimed", "outcomeSha256",
    }
    obj = dict(_exact_keys(value, expected, "outcome"))
    if obj["schema"] != OUTCOME_SCHEMA:
        raise ValueError("unsupported outcome schema")
    for key in (
        "organizationFingerprint", "leaseId", "leaseNonce", "leaseSha256",
        "holderCapabilityCommitment", "evidenceCommitment", "outcomeSha256",
    ):
        _hex64(obj[key], key)
    _opaque(obj["claimId"], "claimId")
    _opaque(obj["outcomeId"], "outcomeId")
    if obj["outcome"] not in TERMINAL_STATES:
        raise ValueError("unsupported terminal outcome")
    _utc(obj["observedAt"], "observedAt")
    if obj["externalSendAuthorized"] is not False or obj["cashOrRevenueClaimed"] is not False:
        raise ValueError("outcome exceeds authority ceiling")
    claimed = obj.pop("outcomeSha256")
    actual = sha256_hex(canonical_json(obj))
    obj["outcomeSha256"] = claimed
    if not hmac.compare_digest(claimed, actual):
        raise ValueError("outcome digest mismatch")
    return obj


def _outcome_matches_request(outcome: dict, req: dict) -> bool:
    return all((
        outcome["organizationFingerprint"] == req["organizationFingerprint"],
        outcome["leaseId"] == req["leaseId"],
        outcome["leaseNonce"] == req["leaseNonce"],
        outcome["claimId"] == req["claimId"],
        outcome["outcomeId"] == req["outcomeId"],
        outcome["outcome"] == req["outcome"],
        outcome["observedAt"] == req["observedAt"],
        outcome["evidenceCommitment"] == req["evidenceCommitment"],
    ))


def _release_unsent_if_needed(store: LeaseStore, req: dict, outcome: dict) -> bool:
    """Release only the exact finalized lease generation; never a successor."""
    _assert_holder_capability(req, outcome["holderCapabilityCommitment"])
    active = store.get_active(req["organizationFingerprint"])
    if active is None:
        return True
    raw, active_generation = active
    lease = verify_lease_document(parse_json_strict(raw.decode("utf-8")))
    if lease["leaseSha256"] != outcome["leaseSha256"]:
        # A distinct active generation proves the finalized lease was already released.
        return True
    _assert_holder_capability(req, lease["holderCapabilityCommitment"])
    try:
        store.delete_active(req["organizationFingerprint"], active_generation)
        return True
    except Exception as exc:
        current = store.get_active(req["organizationFingerprint"])
        if current is None:
            return True
        current_raw, _ = current
        current_lease = verify_lease_document(parse_json_strict(current_raw.decode("utf-8")))
        if current_lease["leaseSha256"] != outcome["leaseSha256"]:
            return True
        raise RuntimeError("lease release uncertain; reconciliation required") from exc


def finalize_lease(store: LeaseStore, request: Any) -> FinalizeResult:
    req = normalize_finalize_request(request)

    existing = store.get_outcome(req["organizationFingerprint"], req["leaseId"])
    if existing is not None:
        prior_raw, outcome_generation = existing
        outcome = verify_outcome_document(parse_json_strict(prior_raw.decode("utf-8")))
        _assert_holder_capability(req, outcome["holderCapabilityCommitment"])
        if not _outcome_matches_request(outcome, req):
            raise ValueError("conflicting outcome already exists")
        released = False
        if req["outcome"] == "UNSENT_RELEASED":
            released = _release_unsent_if_needed(store, req, outcome)
        return FinalizeResult(req["outcome"], outcome, outcome_generation, released, True)

    _require_fresh(req["observedAt"], now=_process_now(), max_age_seconds=MAX_OUTCOME_AGE_SECONDS, label="observedAt")
    active = store.get_active(req["organizationFingerprint"])
    if active is None:
        raise ValueError("no active organization lease; reconcile before finalization")
    raw, _active_generation = active
    lease = verify_lease_document(parse_json_strict(raw.decode("utf-8")))
    outcome = _outcome_doc(req, lease)
    content = canonical_json(outcome)
    try:
        outcome_generation = store.create_outcome(req["organizationFingerprint"], req["leaseId"], content)
        replay = False
    except Exception as exc:
        existing = store.get_outcome(req["organizationFingerprint"], req["leaseId"])
        if existing is None:
            raise RuntimeError("outcome persistence uncertain; reconciliation required") from exc
        prior_raw, outcome_generation = existing
        prior = verify_outcome_document(parse_json_strict(prior_raw.decode("utf-8")))
        _assert_holder_capability(req, prior["holderCapabilityCommitment"])
        if not _outcome_matches_request(prior, req) or not hmac.compare_digest(prior_raw, content):
            raise ValueError("conflicting outcome already exists") from exc
        outcome = prior
        replay = True

    released = False
    if req["outcome"] == "UNSENT_RELEASED":
        released = _release_unsent_if_needed(store, req, outcome)
    return FinalizeResult(req["outcome"], outcome, outcome_generation, released, replay)
