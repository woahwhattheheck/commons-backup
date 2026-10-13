"""One-shot terminal consumer for externally mutating outbound provider calls.

The module is deliberately provider-agnostic.  It does not grant send authority;
it consumes host-retained authority exactly once and serializes concurrent workers
at a Git ref before an external provider callback can run.
"""
from __future__ import annotations

import hashlib
import json
import re
import secrets
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

RESERVATION_SCHEMA = "outbound-send-consumer-reservation/v1"
OUTCOME_SCHEMA = "outbound-send-consumer-outcome/v1"
RECEIPT_SCHEMA = "outbound-send-consumer-receipt/v1"
INDETERMINATE_HTTP = frozenset({0, 408, 500, 502, 503, 504})
TERMINAL_STATES = frozenset({"SENT", "REJECTED", "OUTCOME_UNKNOWN", "HELD_AUTHORITY"})
_TOKEN_RE = re.compile(r"^[a-z0-9][a-z0-9._:@/+\-]{1,191}$")
_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")
_HEX40_64_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


class ConsumerError(ValueError):
    """Structurally invalid input or provider coordination response."""


class ProviderRejected(RuntimeError):
    """Known provider rejection where the adapter can prove no send completed."""

    def __init__(self, reason_code: str = "provider_rejected") -> None:
        self.reason_code = _token(reason_code, "provider rejection reason")
        super().__init__(self.reason_code)


Transport = Callable[[str, str, Mapping[str, Any] | None], tuple[int, Any]]
AuthorityProbe = Callable[[], str | None]
ProviderCallback = Callable[[str], Any]


def _canon(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError) as exc:
        raise ConsumerError("value is not canonical JSON") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canon(value)).hexdigest()


def _token(value: Any, field: str) -> str:
    if not isinstance(value, str) or value != value.casefold() or not value.isascii():
        raise ConsumerError(f"{field}: lowercase ASCII machine token required")
    if _TOKEN_RE.fullmatch(value) is None:
        raise ConsumerError(f"{field}: malformed machine token")
    return value


def _display(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.isascii() or not (3 <= len(value) <= 192):
        raise ConsumerError(f"{field}: 3..192 ASCII chars required")
    if any(ord(ch) < 0x20 or ch == "\x7f" for ch in value):
        raise ConsumerError(f"{field}: control characters forbidden")
    return value


def _repo(value: Any) -> str:
    if not isinstance(value, str) or _REPO_RE.fullmatch(value) is None:
        raise ConsumerError("repo: owner/name required")
    # GitHub owner/name routing is case-insensitive. Fold before storage and
    # seam hashing so alias spellings share one reservation ref.
    owner, name = value.split("/", 1)
    return f"{owner.casefold()}/{name.casefold()}"


def _hex64(value: Any, field: str) -> str:
    if not isinstance(value, str) or _HEX64_RE.fullmatch(value) is None:
        raise ConsumerError(f"{field}: 64 lowercase hex characters required")
    return value


def _object_id(value: Any, field: str) -> str:
    if not isinstance(value, str) or _HEX40_64_RE.fullmatch(value) is None:
        raise ConsumerError(f"{field}: 40/64 lowercase hex object id required")
    return value


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _object_sha(payload: Any) -> str | None:
    if not isinstance(payload, Mapping):
        return None
    obj = payload.get("object")
    if not isinstance(obj, Mapping):
        return None
    sha = obj.get("sha")
    if not isinstance(sha, str) or _HEX40_64_RE.fullmatch(sha) is None:
        return None
    return sha


@dataclass(frozen=True)
class HostBinding:
    """Values derived independently by the host from the provider request/state."""

    repo: str
    buyer_scope: str
    opportunity_scope: str
    event_kind: str
    event_key: str
    provider_request_sha256: str
    authority_sha256: str
    anchor_sha: str

    @classmethod
    def parse(cls, raw: Mapping[str, Any]) -> "HostBinding":
        expected = {
            "repo",
            "buyer_scope",
            "opportunity_scope",
            "event_kind",
            "event_key",
            "provider_request_sha256",
            "authority_sha256",
            "anchor_sha",
        }
        if not isinstance(raw, Mapping) or set(raw) != expected:
            raise ConsumerError("host binding: exact fields required")
        event_kind = _token(raw["event_kind"], "event_kind")
        if event_kind not in {"initial", "reply", "followup", "provider_event"}:
            raise ConsumerError("event_kind: unsupported generation")
        return cls(
            _repo(raw["repo"]),
            _token(raw["buyer_scope"], "buyer_scope"),
            _token(raw["opportunity_scope"], "opportunity_scope"),
            event_kind,
            _token(raw["event_key"], "event_key"),
            _hex64(raw["provider_request_sha256"], "provider_request_sha256"),
            _hex64(raw["authority_sha256"], "authority_sha256"),
            _object_id(raw["anchor_sha"], "anchor_sha"),
        )

    @property
    def seam(self) -> dict[str, str]:
        # Intentionally excludes route, recipient, draft, price, worker and claim id.
        return {
            "schema": RESERVATION_SCHEMA,
            "repo": self.repo,
            "buyer_scope": self.buyer_scope,
            "opportunity_scope": self.opportunity_scope,
            "event_kind": self.event_kind,
            "event_key": self.event_key,
        }

    @property
    def seam_sha256(self) -> str:
        return _digest(self.seam)

    @property
    def reservation_ref(self) -> str:
        return f"refs/tags/outbound-consume-v1/{self.seam_sha256}"

    @property
    def outcome_ref(self) -> str:
        return f"refs/tags/outbound-consume-outcome-v1/{self.seam_sha256}"

    @property
    def idempotency_key(self) -> str:
        return f"tjlabs-outbound-v1:{self.seam_sha256}"


@dataclass(frozen=True)
class Intent:
    repo: str
    buyer_scope: str
    opportunity_scope: str
    event_kind: str
    event_key: str
    provider_request_sha256: str
    anchor_sha: str
    claimant: str

    @classmethod
    def parse(cls, raw: Mapping[str, Any]) -> "Intent":
        expected = {
            "repo",
            "buyer_scope",
            "opportunity_scope",
            "event_kind",
            "event_key",
            "provider_request_sha256",
            "anchor_sha",
            "claimant",
        }
        if not isinstance(raw, Mapping) or set(raw) != expected:
            raise ConsumerError("intent: exact fields required")
        return cls(
            _repo(raw["repo"]),
            _token(raw["buyer_scope"], "buyer_scope"),
            _token(raw["opportunity_scope"], "opportunity_scope"),
            _token(raw["event_kind"], "event_kind"),
            _token(raw["event_key"], "event_key"),
            _hex64(raw["provider_request_sha256"], "provider_request_sha256"),
            _object_id(raw["anchor_sha"], "anchor_sha"),
            _display(raw["claimant"], "claimant"),
        )

    def matches(self, host: HostBinding) -> bool:
        return (
            self.repo == host.repo
            and self.buyer_scope == host.buyer_scope
            and self.opportunity_scope == host.opportunity_scope
            and self.event_kind == host.event_kind
            and self.event_key == host.event_key
            and self.provider_request_sha256 == host.provider_request_sha256
            and self.anchor_sha == host.anchor_sha
        )


def _post_tag(
    *,
    host: HostBinding,
    transport: Transport,
    tag_name: str,
    metadata: Mapping[str, Any],
    tagger_name: str,
) -> str:
    owner, repo_name = host.repo.split("/", 1)
    payload = {
        "tag": tag_name,
        "message": _canon(metadata).decode("ascii") + "\n",
        "object": host.anchor_sha,
        "type": "commit",
        "tagger": {
            "name": tagger_name,
            "email": "outbound-consumer@tokenjunkielabs.invalid",
            "date": _utcnow(),
        },
    }
    status, body = transport("POST", f"/repos/{owner}/{repo_name}/git/tags", payload)
    if status != 201 or not isinstance(body, Mapping):
        raise ConsumerError(f"TAG_OBJECT_CREATE_FAILED_{status}")
    return _object_id(body.get("sha"), "tag response sha")


def _read_ref(host: HostBinding, ref: str, transport: Transport) -> tuple[int, str | None]:
    owner, repo_name = host.repo.split("/", 1)
    quoted = urllib.parse.quote(ref.removeprefix("refs/"), safe="/")
    status, body = transport("GET", f"/repos/{owner}/{repo_name}/git/ref/{quoted}", None)
    return status, _object_sha(body) if status == 200 else None


def _create_ref(host: HostBinding, ref: str, sha: str, transport: Transport) -> tuple[bool, str]:
    owner, repo_name = host.repo.split("/", 1)
    status, body = transport(
        "POST",
        f"/repos/{owner}/{repo_name}/git/refs",
        {"ref": ref, "sha": sha},
    )
    if status == 201 and _object_sha(body) == sha:
        return True, "CREATE_201"
    if status not in INDETERMINATE_HTTP and status != 422 and status != 201:
        return False, f"CREATE_REJECTED_{status}"
    read_status, observed = _read_ref(host, ref, transport)
    if read_status == 200 and observed == sha:
        return True, "READBACK_SELF"
    if read_status == 200 and observed is not None:
        return False, "HELD_BY_OTHER"
    if read_status == 404:
        return False, "CREATE_OUTCOME_UNPROVEN"
    return False, f"READBACK_FAILED_{read_status}"


def _read_outcome(host: HostBinding, transport: Transport) -> dict[str, Any] | None:
    reservation_status, reservation_tag_sha = _read_ref(host, host.reservation_ref, transport)
    if reservation_status != 200 or reservation_tag_sha is None:
        return None
    status, tag_sha = _read_ref(host, host.outcome_ref, transport)
    if status != 200 or tag_sha is None:
        return None
    owner, repo_name = host.repo.split("/", 1)
    tag_status, tag = transport("GET", f"/repos/{owner}/{repo_name}/git/tags/{tag_sha}", None)
    if tag_status != 200 or not isinstance(tag, Mapping):
        return None
    if tag.get("sha") != tag_sha:
        return None
    message = tag.get("message")
    if not isinstance(message, str):
        return None
    try:
        meta = json.loads(message)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    expected = {
        "schema",
        "seam_sha256",
        "reservation_tag_sha",
        "claimant",
        "invocation_nonce",
        "terminal_state",
        "provider_attempted",
        "external_send_completed",
        "prior_send_observed",
        "reason",
    }
    if not isinstance(meta, dict) or set(meta) != expected:
        return None
    if meta["schema"] != OUTCOME_SCHEMA or meta["seam_sha256"] != host.seam_sha256:
        return None
    if meta["reservation_tag_sha"] != reservation_tag_sha:
        return None
    try:
        _display(meta["claimant"], "outcome claimant")
        nonce = _hex64(meta["invocation_nonce"], "outcome invocation_nonce")
        _token(meta["reason"], "outcome reason")
    except ConsumerError:
        return None
    if tag.get("tag") != f"outbound-consume-outcome-v1-{host.seam_sha256[:16]}-{nonce[:16]}":
        return None
    terminal = meta["terminal_state"]
    if terminal not in TERMINAL_STATES:
        return None
    if type(meta["provider_attempted"]) is not bool or type(meta["external_send_completed"]) is not bool:
        return None
    if meta["prior_send_observed"] is not False:
        return None
    expected_truth = {
        "SENT": (True, True),
        "REJECTED": (True, False),
        "OUTCOME_UNKNOWN": (True, False),
        "HELD_AUTHORITY": (False, False),
    }[terminal]
    if (meta["provider_attempted"], meta["external_send_completed"]) != expected_truth:
        return None
    return meta


def _persist_outcome(
    *,
    host: HostBinding,
    transport: Transport,
    reservation_tag_sha: str,
    claimant: str,
    invocation_nonce: str,
    terminal_state: str,
    provider_attempted: bool,
    external_send_completed: bool,
    reason: str,
) -> bool:
    if terminal_state not in TERMINAL_STATES:
        raise ConsumerError("terminal state invalid")
    metadata = {
        "schema": OUTCOME_SCHEMA,
        "seam_sha256": host.seam_sha256,
        "reservation_tag_sha": reservation_tag_sha,
        "claimant": claimant,
        "invocation_nonce": invocation_nonce,
        "terminal_state": terminal_state,
        "provider_attempted": provider_attempted,
        "external_send_completed": external_send_completed,
        "prior_send_observed": False,
        "reason": _token(reason, "outcome reason"),
    }
    tag_name = f"outbound-consume-outcome-v1-{host.seam_sha256[:16]}-{invocation_nonce[:16]}"
    try:
        tag_sha = _post_tag(
            host=host,
            transport=transport,
            tag_name=tag_name,
            metadata=metadata,
            tagger_name="outbound-send-consumer-outcome",
        )
    except ConsumerError:
        return False
    held, _ = _create_ref(host, host.outcome_ref, tag_sha, transport)
    return held


def _receipt(
    *,
    host: HostBinding,
    claimant: str,
    reservation_tag_sha: str | None,
    decision: str,
    terminal_state: str | None,
    external_send_completed: bool,
    prior_send_observed: bool,
    provider_attempted: bool,
    reason: str,
) -> dict[str, Any]:
    material: dict[str, Any] = {
        "schema": RECEIPT_SCHEMA,
        "seam_sha256": host.seam_sha256,
        "reservation_ref": host.reservation_ref,
        "outcome_ref": host.outcome_ref,
        "claimant": claimant,
        "reservation_tag_sha": reservation_tag_sha,
        "decision": decision,
        "terminal_state": terminal_state,
        "external_send_authorized": False,
        "external_send_completed": external_send_completed,
        "prior_send_observed": prior_send_observed,
        "provider_attempted": provider_attempted,
        "idempotency_key": host.idempotency_key,
        "reason": reason,
    }
    material["receipt_sha256"] = _digest(material)
    return material


def consume_once(
    intent_raw: Mapping[str, Any],
    *,
    host_raw: Mapping[str, Any],
    transport: Transport,
    authority_probe: AuthorityProbe,
    provider_callback: ProviderCallback,
) -> dict[str, Any]:
    """Consume one host-authorized outbound event and call the provider at most once.

    The host binding is independent of the caller-authored intent.  The authority
    probe must re-read live private authority and return its 64-hex generation
    digest; it is executed before reservation and again immediately before the
    provider callback.  Any uncertainty fails closed and never retries the
    provider on this event seam.
    """
    intent = Intent.parse(intent_raw)
    host = HostBinding.parse(host_raw)
    if intent.event_kind not in {"initial", "reply", "followup", "provider_event"}:
        raise ConsumerError("intent event_kind unsupported")
    if not intent.matches(host):
        return _receipt(
            host=host,
            claimant=intent.claimant,
            reservation_tag_sha=None,
            decision="HOLD",
            terminal_state=None,
            external_send_completed=False,
            prior_send_observed=False,
            provider_attempted=False,
            reason="HOST_INTENT_MISMATCH",
        )

    first_authority = authority_probe()
    if first_authority != host.authority_sha256:
        return _receipt(
            host=host,
            claimant=intent.claimant,
            reservation_tag_sha=None,
            decision="HOLD",
            terminal_state=None,
            external_send_completed=False,
            prior_send_observed=False,
            provider_attempted=False,
            reason="AUTHORITY_NOT_CURRENT",
        )

    invocation_nonce = secrets.token_hex(32)
    reservation_meta = {
        "schema": RESERVATION_SCHEMA,
        **host.seam,
        "seam_sha256": host.seam_sha256,
        "claimant": intent.claimant,
        "invocation_nonce": invocation_nonce,
        "anchor_sha": host.anchor_sha,
        "provider_request_sha256": host.provider_request_sha256,
        "authority_sha256": host.authority_sha256,
        "idempotency_key": host.idempotency_key,
    }
    tag_name = f"outbound-consume-v1-{host.seam_sha256[:16]}-{invocation_nonce[:16]}"
    reservation_tag_sha = _post_tag(
        host=host,
        transport=transport,
        tag_name=tag_name,
        metadata=reservation_meta,
        tagger_name="outbound-send-consumer",
    )
    won, reservation_reason = _create_ref(
        host,
        host.reservation_ref,
        reservation_tag_sha,
        transport,
    )
    if not won:
        if reservation_reason == "HELD_BY_OTHER":
            prior = _read_outcome(host, transport)
            if prior is None:
                return _receipt(
                    host=host,
                    claimant=intent.claimant,
                    reservation_tag_sha=reservation_tag_sha,
                    decision="RECONCILE_REQUIRED",
                    terminal_state="OUTCOME_UNKNOWN",
                    external_send_completed=False,
                    prior_send_observed=False,
                    provider_attempted=False,
                    reason="RESERVATION_HELD_OUTCOME_UNPROVEN",
                )
            prior_terminal = prior["terminal_state"]
            if prior_terminal == "OUTCOME_UNKNOWN":
                return _receipt(
                    host=host,
                    claimant=intent.claimant,
                    reservation_tag_sha=reservation_tag_sha,
                    decision="RECONCILE_REQUIRED",
                    terminal_state="OUTCOME_UNKNOWN",
                    external_send_completed=False,
                    prior_send_observed=False,
                    provider_attempted=False,
                    reason="PRIOR_OUTCOME_UNKNOWN",
                )
            prior_sent = prior_terminal == "SENT"
            return _receipt(
                host=host,
                claimant=intent.claimant,
                reservation_tag_sha=reservation_tag_sha,
                decision="SUPPRESSED",
                terminal_state=prior_terminal,
                external_send_completed=False,
                prior_send_observed=prior_sent,
                provider_attempted=False,
                reason="RESERVATION_HELD_BY_OTHER",
            )
        return _receipt(
            host=host,
            claimant=intent.claimant,
            reservation_tag_sha=reservation_tag_sha,
            decision="RECONCILE_REQUIRED",
            terminal_state="OUTCOME_UNKNOWN",
            external_send_completed=False,
            prior_send_observed=False,
            provider_attempted=False,
            reason=reservation_reason,
        )

    second_authority = authority_probe()
    if second_authority != host.authority_sha256:
        persisted = _persist_outcome(
            host=host,
            transport=transport,
            reservation_tag_sha=reservation_tag_sha,
            claimant=intent.claimant,
            invocation_nonce=invocation_nonce,
            terminal_state="HELD_AUTHORITY",
            provider_attempted=False,
            external_send_completed=False,
            reason="authority_changed_after_reservation",
        )
        return _receipt(
            host=host,
            claimant=intent.claimant,
            reservation_tag_sha=reservation_tag_sha,
            decision="HELD_AUTHORITY" if persisted else "RECONCILE_REQUIRED",
            terminal_state="HELD_AUTHORITY" if persisted else "OUTCOME_UNKNOWN",
            external_send_completed=False,
            prior_send_observed=False,
            provider_attempted=False,
            reason="AUTHORITY_CHANGED_AFTER_RESERVATION" if persisted else "OUTCOME_PERSIST_UNCERTAIN",
        )

    terminal = "OUTCOME_UNKNOWN"
    reason = "provider_outcome_unknown"
    provider_attempted = True
    external_send_completed = False
    try:
        callback_result = provider_callback(host.idempotency_key)
    except ProviderRejected as exc:
        terminal = "REJECTED"
        reason = exc.reason_code
        provider_attempted = True
    except Exception:
        # Never stringify provider exceptions: user-defined __str__/__repr__ may
        # be stateful or leak secrets. Process-level BaseException subclasses
        # propagate; the already-created reservation still burns the seam.
        terminal = "OUTCOME_UNKNOWN"
        reason = "provider_exception"
    else:
        if callback_result is None:
            terminal = "SENT"
            reason = "provider_callback_returned_none"
            external_send_completed = True
        else:
            # Never inspect/serialize/repr an arbitrary provider return object.
            terminal = "OUTCOME_UNKNOWN"
            reason = "provider_return_contract_violation"

    persisted = _persist_outcome(
        host=host,
        transport=transport,
        reservation_tag_sha=reservation_tag_sha,
        claimant=intent.claimant,
        invocation_nonce=invocation_nonce,
        terminal_state=terminal,
        provider_attempted=provider_attempted,
        external_send_completed=external_send_completed,
        reason=reason,
    )
    if not persisted:
        return _receipt(
            host=host,
            claimant=intent.claimant,
            reservation_tag_sha=reservation_tag_sha,
            decision="RECONCILE_REQUIRED",
            terminal_state="OUTCOME_UNKNOWN",
            external_send_completed=external_send_completed,
            prior_send_observed=False,
            provider_attempted=provider_attempted,
            reason="OUTCOME_PERSIST_UNCERTAIN",
        )

    decision = terminal if terminal in {"SENT", "REJECTED", "HELD_AUTHORITY"} else "RECONCILE_REQUIRED"
    return _receipt(
        host=host,
        claimant=intent.claimant,
        reservation_tag_sha=reservation_tag_sha,
        decision=decision,
        terminal_state=terminal,
        external_send_completed=external_send_completed,
        prior_send_observed=False,
        provider_attempted=provider_attempted,
        reason=reason.upper(),
    )
