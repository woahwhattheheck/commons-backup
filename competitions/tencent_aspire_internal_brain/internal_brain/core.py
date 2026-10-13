from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

BUNDLE_SCHEMA = "internal-brain-bundle/v1"
DOCUMENT_SCHEMA = "internal-brain-document/v1"
QUERY_SCHEMA = "internal-brain-query/v1"
AUDIT_SCHEMA = "internal-brain-audit/v1"
RECEIPT_SCHEMA = "internal-brain-receipt/v1"

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,127}$")
_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_'-]{1,63}")
_INSTRUCTION_MARKERS = (
    "ignore previous",
    "ignore all previous",
    "system prompt",
    "developer message",
    "override policy",
    "bypass authorization",
    "reveal secrets",
    "exfiltrate",
)
_MAX_CONTENT_CHARS = 200_000
_MAX_QUERY_CHARS = 2_000
_MAX_RESULTS = 20


class BrainError(Exception):
    pass


class SchemaError(BrainError):
    pass


class AuthorizationError(BrainError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class AuditError(BrainError):
    pass


def _pairs_no_duplicates(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise SchemaError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def strict_loads(text: str) -> Any:
    def finite_float(value: str) -> float:
        parsed = float(value)
        if not math.isfinite(parsed):
            raise SchemaError(f"non-finite JSON number: {value}")
        return parsed

    try:
        return json.loads(
            text,
            object_pairs_hook=_pairs_no_duplicates,
            parse_float=finite_float,
            parse_constant=lambda value: (_ for _ in ()).throw(
                SchemaError(f"non-finite JSON number: {value}")
            ),
        )
    except BrainError:
        raise
    except (json.JSONDecodeError, TypeError, ValueError, RecursionError) as exc:
        raise SchemaError(f"invalid JSON: {exc}") from exc


def canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise SchemaError(f"not canonicalizable JSON: {exc}") from exc


def sha256_hex(value: bytes | str) -> str:
    try:
        data = value.encode("utf-8") if isinstance(value, str) else value
    except UnicodeError as exc:
        raise SchemaError("text must be valid UTF-8 without unpaired surrogates") from exc
    return hashlib.sha256(data).hexdigest()


def _digest(value: Any) -> str:
    return sha256_hex(canonical_json(value))


def _object(value: Any, where: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SchemaError(f"{where} must be an object")
    return value


def _exact_keys(value: Mapping[str, Any], allowed: set[str], required: set[str], where: str) -> None:
    missing = sorted(required - set(value))
    extra = sorted(set(value) - allowed)
    if missing:
        raise SchemaError(f"{where} missing keys: {', '.join(missing)}")
    if extra:
        raise SchemaError(f"{where} unsupported keys: {', '.join(extra)}")


def _identifier(value: Any, where: str) -> str:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise SchemaError(f"{where} must match {_ID_RE.pattern}")
    return value


def _bounded_text(value: Any, where: str, *, maximum: int, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise SchemaError(f"{where} must be a string")
    if not allow_empty and not value.strip():
        raise SchemaError(f"{where} must not be empty")
    if len(value) > maximum or "\x00" in value:
        raise SchemaError(f"{where} exceeds its safe text boundary")
    try:
        value.encode("utf-8")
    except UnicodeError as exc:
        raise SchemaError(f"{where} must be valid UTF-8 without unpaired surrogates") from exc
    return value


def _string_list(value: Any, where: str, *, maximum: int = 128, ids: bool = True) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > maximum:
        raise SchemaError(f"{where} must be a list of at most {maximum} strings")
    out: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(value):
        item = _identifier(item, f"{where}[{index}]") if ids else _bounded_text(
            item, f"{where}[{index}]", maximum=256
        )
        if item in seen:
            raise SchemaError(f"{where} contains duplicate value: {item}")
        seen.add(item)
        out.append(item)
    return tuple(out)


def _integer(value: Any, where: str, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise SchemaError(f"{where} must be an integer in [{minimum}, {maximum}]")
    return value


@dataclass(frozen=True)
class Role:
    role_id: str
    permissions: frozenset[str]
    clearance: int


@dataclass(frozen=True)
class User:
    user_id: str
    role_ids: tuple[str, ...]


@dataclass(frozen=True)
class Document:
    tenant_id: str
    document_id: str
    title: str
    content: str
    source_uri: str
    version: str
    classification: int
    allowed_roles: tuple[str, ...]
    labels: tuple[str, ...]
    content_sha256: str

    def public_record(self) -> dict[str, Any]:
        return {
            "schema": DOCUMENT_SCHEMA,
            "tenant_id": self.tenant_id,
            "document_id": self.document_id,
            "title": self.title,
            "content": self.content,
            "source_uri": self.source_uri,
            "version": self.version,
            "classification": self.classification,
            "allowed_roles": list(self.allowed_roles),
            "labels": list(self.labels),
            "content_sha256": self.content_sha256,
        }


def normalize_document(value: Mapping[str, Any], *, tenant_id: str | None = None) -> Document:
    value = _object(value, "document")
    allowed = {
        "schema", "tenant_id", "document_id", "title", "content", "source_uri",
        "version", "classification", "allowed_roles", "labels", "content_sha256",
    }
    required = allowed - {"content_sha256"}
    _exact_keys(value, allowed, required, "document")
    if value.get("schema") != DOCUMENT_SCHEMA:
        raise SchemaError(f"document.schema must be {DOCUMENT_SCHEMA!r}")
    doc_tenant = _identifier(value.get("tenant_id"), "document.tenant_id")
    if tenant_id is not None and doc_tenant != tenant_id:
        raise SchemaError("document tenant does not match bundle tenant")
    document_id = _identifier(value.get("document_id"), "document.document_id")
    title = _bounded_text(value.get("title"), "document.title", maximum=512)
    content = _bounded_text(value.get("content"), "document.content", maximum=_MAX_CONTENT_CHARS)
    source_uri = _bounded_text(value.get("source_uri"), "document.source_uri", maximum=2048)
    version = _identifier(value.get("version"), "document.version")
    classification = _integer(value.get("classification"), "document.classification", minimum=0, maximum=9)
    allowed_roles = _string_list(value.get("allowed_roles"), "document.allowed_roles")
    if not allowed_roles:
        raise SchemaError("document.allowed_roles must not be empty")
    labels = _string_list(value.get("labels"), "document.labels", ids=False)
    computed = sha256_hex(content)
    supplied = value.get("content_sha256")
    if supplied is not None:
        if not isinstance(supplied, str) or not re.fullmatch(r"[0-9a-f]{64}", supplied):
            raise SchemaError("document.content_sha256 must be 64 lowercase hex characters")
        if supplied != computed:
            raise SchemaError("document.content_sha256 mismatch")
    return Document(
        tenant_id=doc_tenant,
        document_id=document_id,
        title=title,
        content=content,
        source_uri=source_uri,
        version=version,
        classification=classification,
        allowed_roles=allowed_roles,
        labels=labels,
        content_sha256=computed,
    )


def normalize_query(value: Mapping[str, Any]) -> dict[str, Any]:
    value = _object(value, "query")
    allowed = {"schema", "tenant_id", "actor_user_id", "question", "max_results", "document_ids"}
    required = {"schema", "tenant_id", "actor_user_id", "question", "max_results"}
    _exact_keys(value, allowed, required, "query")
    if value.get("schema") != QUERY_SCHEMA:
        raise SchemaError(f"query.schema must be {QUERY_SCHEMA!r}")
    question = _bounded_text(value.get("question"), "query.question", maximum=_MAX_QUERY_CHARS)
    max_results = _integer(value.get("max_results"), "query.max_results", minimum=1, maximum=_MAX_RESULTS)
    document_ids = value.get("document_ids", [])
    return {
        "schema": QUERY_SCHEMA,
        "tenant_id": _identifier(value.get("tenant_id"), "query.tenant_id"),
        "actor_user_id": _identifier(value.get("actor_user_id"), "query.actor_user_id"),
        "question": question,
        "max_results": max_results,
        "document_ids": list(_string_list(document_ids, "query.document_ids")),
    }


def normalize_bundle(value: Mapping[str, Any]) -> dict[str, Any]:
    value = _object(value, "bundle")
    allowed = {"schema", "tenant_id", "roles", "users", "documents"}
    _exact_keys(value, allowed, allowed, "bundle")
    if value.get("schema") != BUNDLE_SCHEMA:
        raise SchemaError(f"bundle.schema must be {BUNDLE_SCHEMA!r}")
    tenant_id = _identifier(value.get("tenant_id"), "bundle.tenant_id")

    raw_roles = value.get("roles")
    if not isinstance(raw_roles, list) or not raw_roles or len(raw_roles) > 128:
        raise SchemaError("bundle.roles must contain 1..128 role objects")
    roles: dict[str, Role] = {}
    for index, raw in enumerate(raw_roles):
        raw = _object(raw, f"roles[{index}]")
        _exact_keys(raw, {"role_id", "permissions", "clearance"}, {"role_id", "permissions", "clearance"}, f"roles[{index}]")
        role_id = _identifier(raw.get("role_id"), f"roles[{index}].role_id")
        if role_id in roles:
            raise SchemaError(f"duplicate role_id: {role_id}")
        permissions = frozenset(_string_list(raw.get("permissions"), f"roles[{index}].permissions"))
        unknown = sorted(permissions - {"query", "ingest", "audit:read"})
        if unknown:
            raise SchemaError(f"role {role_id} has unsupported permissions: {', '.join(unknown)}")
        roles[role_id] = Role(
            role_id=role_id,
            permissions=permissions,
            clearance=_integer(raw.get("clearance"), f"roles[{index}].clearance", minimum=0, maximum=9),
        )

    raw_users = value.get("users")
    if not isinstance(raw_users, list) or not raw_users or len(raw_users) > 10_000:
        raise SchemaError("bundle.users must contain 1..10000 user objects")
    users: dict[str, User] = {}
    for index, raw in enumerate(raw_users):
        raw = _object(raw, f"users[{index}]")
        _exact_keys(raw, {"user_id", "role_ids"}, {"user_id", "role_ids"}, f"users[{index}]")
        user_id = _identifier(raw.get("user_id"), f"users[{index}].user_id")
        if user_id in users:
            raise SchemaError(f"duplicate user_id: {user_id}")
        role_ids = _string_list(raw.get("role_ids"), f"users[{index}].role_ids")
        if not role_ids:
            raise SchemaError(f"user {user_id} must have at least one role")
        unknown = sorted(set(role_ids) - set(roles))
        if unknown:
            raise SchemaError(f"user {user_id} references unknown roles: {', '.join(unknown)}")
        users[user_id] = User(user_id=user_id, role_ids=role_ids)

    raw_docs = value.get("documents")
    if not isinstance(raw_docs, list) or len(raw_docs) > 50_000:
        raise SchemaError("bundle.documents must be a list of at most 50000 documents")
    documents: dict[str, Document] = {}
    for index, raw in enumerate(raw_docs):
        doc = normalize_document(_object(raw, f"documents[{index}]"), tenant_id=tenant_id)
        if doc.document_id in documents:
            raise SchemaError(f"duplicate document_id: {doc.document_id}")
        unknown = sorted(set(doc.allowed_roles) - set(roles))
        if unknown:
            raise SchemaError(f"document {doc.document_id} references unknown roles: {', '.join(unknown)}")
        documents[doc.document_id] = doc

    return {
        "schema": BUNDLE_SCHEMA,
        "tenant_id": tenant_id,
        "roles": roles,
        "users": users,
        "documents": documents,
    }


def _tokenize(text: str) -> tuple[str, ...]:
    return tuple(token.lower() for token in _TOKEN_RE.findall(text))


def _instruction_markers(content: str) -> tuple[str, ...]:
    lowered = content.lower()
    return tuple(marker for marker in _INSTRUCTION_MARKERS if marker in lowered)


def _snippet(content: str, query_tokens: set[str], maximum: int = 320) -> str:
    flat = " ".join(content.split())
    if len(flat) <= maximum:
        return flat
    lowered = flat.lower()
    positions = [lowered.find(token) for token in query_tokens if lowered.find(token) >= 0]
    start = max(0, min(positions) - maximum // 4) if positions else 0
    end = min(len(flat), start + maximum)
    prefix = "…" if start else ""
    suffix = "…" if end < len(flat) else ""
    return prefix + flat[start:end] + suffix


def _score(doc: Document, query_tokens: set[str]) -> int:
    title_tokens = set(_tokenize(doc.title))
    content_tokens = set(_tokenize(doc.content))
    label_tokens = set(token for label in doc.labels for token in _tokenize(label))
    return 5 * len(query_tokens & title_tokens) + 2 * len(query_tokens & label_tokens) + len(query_tokens & content_tokens)


def _event_without_digest(
    *,
    sequence: int,
    previous_digest: str,
    tenant_id: str,
    actor_user_id: str,
    event_type: str,
    decision_code: str,
    subject_id: str | None,
    payload_digest: str,
) -> dict[str, Any]:
    return {
        "schema": AUDIT_SCHEMA,
        "sequence": sequence,
        "previous_digest": previous_digest,
        "tenant_id": tenant_id,
        "actor_user_id": actor_user_id,
        "event_type": event_type,
        "decision_code": decision_code,
        "subject_id": subject_id,
        "payload_digest": payload_digest,
    }


def verify_audit(
    events: Sequence[Mapping[str, Any]],
    *,
    expected_head_digest: str | None = None,
    expected_event_count: int | None = None,
) -> dict[str, Any]:
    if not isinstance(events, (list, tuple)):
        raise AuditError("audit must contain an ordered list of events")
    decisions = {
        "QUERY": {
            "AUTHORIZED_MATCH", "AUTHORIZED_AMBIGUOUS_MATCH", "NO_AUTHORIZED_MATCH",
            "UNKNOWN_USER", "PERMISSION_DENIED",
        },
        "DOCUMENT_INGEST": {
            "INGESTED", "IDEMPOTENT_REPLAY", "UNKNOWN_USER", "PERMISSION_DENIED",
            "CLEARANCE_DENIED", "ROLE_SCOPE_DENIED", "DOCUMENT_ID_CONFLICT",
        },
        "AUDIT_READ": {"UNKNOWN_USER", "PERMISSION_DENIED"},
    }
    previous = "0" * 64
    tenant_id = None
    expected_sequence = 0
    for index, raw in enumerate(events):
        event = _object(raw, f"audit[{index}]")
        allowed = {
            "schema", "sequence", "previous_digest", "tenant_id", "actor_user_id",
            "event_type", "decision_code", "subject_id", "payload_digest", "event_digest",
        }
        _exact_keys(event, allowed, allowed, f"audit[{index}]")
        if event.get("schema") != AUDIT_SCHEMA:
            raise AuditError(f"audit[{index}] schema mismatch")
        if type(event.get("sequence")) is not int or event["sequence"] != expected_sequence:
            raise AuditError(f"audit[{index}] sequence mismatch")
        if event.get("previous_digest") != previous:
            raise AuditError(f"audit[{index}] previous digest mismatch")
        try:
            event_tenant = _identifier(event.get("tenant_id"), f"audit[{index}].tenant_id")
            _identifier(event.get("actor_user_id"), f"audit[{index}].actor_user_id")
            if event.get("subject_id") is not None:
                _identifier(event["subject_id"], f"audit[{index}].subject_id")
        except SchemaError as exc:
            raise AuditError(str(exc)) from exc
        if tenant_id is None:
            tenant_id = event_tenant
        elif event_tenant != tenant_id:
            raise AuditError(f"audit[{index}] tenant mismatch")
        event_type = event.get("event_type")
        decision_code = event.get("decision_code")
        if (
            not isinstance(event_type, str)
            or event_type not in decisions
            or not isinstance(decision_code, str)
            or decision_code not in decisions[event_type]
        ):
            raise AuditError(f"audit[{index}] event/decision mismatch")
        if event_type != "DOCUMENT_INGEST" and event["subject_id"] is not None:
            raise AuditError(f"audit[{index}] unexpected subject")
        if decision_code in {"INGESTED", "IDEMPOTENT_REPLAY"} and event["subject_id"] is None:
            raise AuditError(f"audit[{index}] ingestion subject missing")
        payload_digest = event.get("payload_digest")
        event_digest = event.get("event_digest")
        if not isinstance(payload_digest, str) or not re.fullmatch(r"[0-9a-f]{64}", payload_digest):
            raise AuditError(f"audit[{index}] payload digest malformed")
        if not isinstance(event_digest, str) or not re.fullmatch(r"[0-9a-f]{64}", event_digest):
            raise AuditError(f"audit[{index}] event digest malformed")
        unsigned = {key: value for key, value in event.items() if key != "event_digest"}
        computed = _digest(unsigned)
        if computed != event_digest:
            raise AuditError(f"audit[{index}] event digest mismatch")
        previous = computed
        expected_sequence += 1
    if expected_head_digest is not None:
        if not isinstance(expected_head_digest, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_head_digest):
            raise AuditError("expected audit head must be 64 lowercase hex characters")
        if previous != expected_head_digest:
            raise AuditError("audit head does not match the retained checkpoint")
    if expected_event_count is not None:
        if type(expected_event_count) is not int or expected_event_count < 0:
            raise AuditError("expected audit event count must be a nonnegative integer")
        if len(events) != expected_event_count:
            raise AuditError("audit event count does not match the retained checkpoint")
    return {
        "schema": "internal-brain-audit-verification/v1",
        "valid": True,
        "event_count": len(events),
        "head_digest": previous,
    }


class InternalBrain:
    """Deterministic, non-generative reference engine with authorization before retrieval."""

    def __init__(self, bundle: Mapping[str, Any]) -> None:
        normalized = normalize_bundle(bundle)
        self.tenant_id: str = normalized["tenant_id"]
        self.roles: dict[str, Role] = dict(normalized["roles"])
        self.users: dict[str, User] = dict(normalized["users"])
        self.documents: dict[str, Document] = dict(normalized["documents"])
        self._audit: list[dict[str, Any]] = []

    @classmethod
    def from_json(cls, text: str) -> "InternalBrain":
        return cls(_object(strict_loads(text), "bundle"))

    def _actor(self, tenant_id: str, actor_user_id: str, permission: str) -> tuple[User, set[str], int]:
        _identifier(tenant_id, "tenant_id")
        _identifier(actor_user_id, "actor_user_id")
        if tenant_id != self.tenant_id:
            raise AuthorizationError("TENANT_MISMATCH", "request tenant does not match engine tenant")
        user = self.users.get(actor_user_id)
        if user is None:
            raise AuthorizationError("UNKNOWN_USER", "actor is not a member of this tenant")
        role_ids = set(user.role_ids)
        role_records = [self.roles[role_id] for role_id in user.role_ids]
        if not any(permission in role.permissions for role in role_records):
            raise AuthorizationError("PERMISSION_DENIED", f"actor lacks {permission!r} permission")
        clearance = max(role.clearance for role in role_records)
        return user, role_ids, clearance

    def _append_audit(
        self,
        *,
        actor_user_id: str,
        event_type: str,
        decision_code: str,
        subject_id: str | None,
        payload: Any,
    ) -> dict[str, Any]:
        previous = self._audit[-1]["event_digest"] if self._audit else "0" * 64
        unsigned = _event_without_digest(
            sequence=len(self._audit),
            previous_digest=previous,
            tenant_id=self.tenant_id,
            actor_user_id=actor_user_id,
            event_type=event_type,
            decision_code=decision_code,
            subject_id=subject_id,
            payload_digest=_digest(payload),
        )
        event = {**unsigned, "event_digest": _digest(unsigned)}
        self._audit.append(event)
        return dict(event)

    def audit_events(self, *, tenant_id: str, actor_user_id: str) -> list[dict[str, Any]]:
        try:
            self._actor(tenant_id, actor_user_id, "audit:read")
        except AuthorizationError as exc:
            self._record_denial(
                tenant_id=tenant_id,
                actor_user_id=actor_user_id,
                event_type="AUDIT_READ",
                decision_code=exc.code,
            )
            raise
        return [dict(event) for event in self._audit]

    def _record_denial(
        self,
        *,
        tenant_id: str,
        actor_user_id: str,
        event_type: str,
        decision_code: str,
        subject_id: str | None = None,
        query_sha256: str | None = None,
    ) -> None:
        # A request for another tenant must not mutate this tenant's audit stream.
        if tenant_id != self.tenant_id:
            return
        payload = {
            "tenant_id": tenant_id,
            "actor_user_id": actor_user_id,
            "decision_code": decision_code,
            "subject_id": subject_id,
        }
        if query_sha256 is not None:
            payload["query_sha256"] = query_sha256
        self._append_audit(
            actor_user_id=actor_user_id,
            event_type=event_type,
            decision_code=decision_code,
            subject_id=subject_id,
            payload=payload,
        )

    def ingest(self, *, tenant_id: str, actor_user_id: str, document: Mapping[str, Any]) -> dict[str, Any]:
        try:
            return self._ingest(tenant_id=tenant_id, actor_user_id=actor_user_id, document=document)
        except AuthorizationError as exc:
            subject = document.get("document_id") if isinstance(document, Mapping) else None
            if not isinstance(subject, str) or not _ID_RE.fullmatch(subject):
                subject = None
            self._record_denial(
                tenant_id=tenant_id,
                actor_user_id=actor_user_id,
                event_type="DOCUMENT_INGEST",
                decision_code=exc.code,
                subject_id=subject,
            )
            raise

    def _ingest(self, *, tenant_id: str, actor_user_id: str, document: Mapping[str, Any]) -> dict[str, Any]:
        _, actor_roles, clearance = self._actor(tenant_id, actor_user_id, "ingest")
        doc = normalize_document(document, tenant_id=self.tenant_id)
        unknown = sorted(set(doc.allowed_roles) - set(self.roles))
        if unknown:
            raise SchemaError(f"document references unknown roles: {', '.join(unknown)}")
        if doc.classification > clearance:
            raise AuthorizationError("CLEARANCE_DENIED", "actor clearance is below document classification")
        if not actor_roles.intersection(doc.allowed_roles):
            raise AuthorizationError(
                "ROLE_SCOPE_DENIED",
                "actor cannot create a document outside every one of their role scopes",
            )
        existing = self.documents.get(doc.document_id)
        if existing is not None and existing != doc:
            raise AuthorizationError(
                "DOCUMENT_ID_CONFLICT",
                "document_id already exists with different content or metadata; use a new document_id",
            )
        if existing is None:
            self.documents[doc.document_id] = doc
        document_record = doc.public_record()
        event = self._append_audit(
            actor_user_id=actor_user_id,
            event_type="DOCUMENT_INGEST",
            decision_code="INGESTED" if existing is None else "IDEMPOTENT_REPLAY",
            subject_id=doc.document_id,
            payload=document_record,
        )
        receipt = {
            "schema": RECEIPT_SCHEMA,
            "operation": "ingest",
            "decision_code": event["decision_code"],
            "tenant_id": self.tenant_id,
            "actor_user_id": actor_user_id,
            "document_id": doc.document_id,
            "content_sha256": doc.content_sha256,
            "document_sha256": _digest(document_record),
            "audit_event_digest": event["event_digest"],
        }
        return {**receipt, "receipt_sha256": _digest(receipt)}

    def query(self, request: Mapping[str, Any]) -> dict[str, Any]:
        query = normalize_query(request)
        actor_id = query["actor_user_id"]
        try:
            _, actor_roles, clearance = self._actor(query["tenant_id"], actor_id, "query")
        except AuthorizationError as exc:
            self._record_denial(
                tenant_id=query["tenant_id"],
                actor_user_id=actor_id,
                event_type="QUERY",
                decision_code=exc.code,
                query_sha256=_digest(query),
            )
            raise

        requested_ids = set(query["document_ids"])
        query_tokens = set(_tokenize(query["question"]))
        candidates: list[tuple[int, Document]] = []
        denied_by_scope = 0
        considered = 0
        for document_id in sorted(self.documents):
            doc = self.documents[document_id]
            if requested_ids and doc.document_id not in requested_ids:
                continue
            considered += 1
            if doc.classification > clearance or not actor_roles.intersection(doc.allowed_roles):
                denied_by_scope += 1
                continue
            score = _score(doc, query_tokens)
            if score > 0:
                candidates.append((score, doc))

        candidates.sort(key=lambda item: (-item[0], item[1].document_id, item[1].content_sha256))
        selected = candidates[: query["max_results"]]
        if not selected:
            decision_code = "NO_AUTHORIZED_MATCH"
        elif len(candidates) > 1 and candidates[0][0] == candidates[1][0]:
            decision_code = "AUTHORIZED_AMBIGUOUS_MATCH"
        else:
            decision_code = "AUTHORIZED_MATCH"

        results: list[dict[str, Any]] = []
        for score, doc in selected:
            markers = _instruction_markers(doc.content)
            results.append(
                {
                    "document_id": doc.document_id,
                    "version": doc.version,
                    "score": score,
                    "title": doc.title,
                    "snippet": _snippet(doc.content, query_tokens),
                    "citation": {
                        "source_uri": doc.source_uri,
                        "content_sha256": doc.content_sha256,
                        "document_sha256": _digest(doc.public_record()),
                    },
                    "untrusted_instruction_markers": list(markers),
                }
            )

        evidence = {
            "query_sha256": _digest(query),
            "decision_code": decision_code,
            "considered_document_count": considered,
            "scope_denied_count": denied_by_scope,
            "result_ids": [item["document_id"] for item in results],
            "result_content_sha256": [item["citation"]["content_sha256"] for item in results],
            "result_document_sha256": [item["citation"]["document_sha256"] for item in results],
        }
        event = self._append_audit(
            actor_user_id=actor_id,
            event_type="QUERY",
            decision_code=decision_code,
            subject_id=None,
            payload=evidence,
        )
        response = {
            "schema": RECEIPT_SCHEMA,
            "operation": "query",
            "decision_code": decision_code,
            "tenant_id": self.tenant_id,
            "actor_user_id": actor_id,
            "query_sha256": evidence["query_sha256"],
            "authorization": {
                "evaluated_before_retrieval": True,
                "scope_denied_count": denied_by_scope,
                "requested_document_ids": sorted(requested_ids),
            },
            "results": results,
            "audit_event_digest": event["event_digest"],
            "security_boundary": {
                "document_text_is_data_not_instruction": True,
                "retrieval_cannot_widen_actor_roles": True,
                "cross_tenant_requests_fail_closed": True,
            },
        }
        stable_receipt = {key: value for key, value in response.items() if key != "audit_event_digest"}
        response["result_receipt_sha256"] = _digest(stable_receipt)
        return response

    def export_bundle(self) -> dict[str, Any]:
        return {
            "schema": BUNDLE_SCHEMA,
            "tenant_id": self.tenant_id,
            "roles": [
                {
                    "role_id": role.role_id,
                    "permissions": sorted(role.permissions),
                    "clearance": role.clearance,
                }
                for role in sorted(self.roles.values(), key=lambda role: role.role_id)
            ],
            "users": [
                {"user_id": user.user_id, "role_ids": list(user.role_ids)}
                for user in sorted(self.users.values(), key=lambda user: user.user_id)
            ],
            "documents": [self.documents[key].public_record() for key in sorted(self.documents)],
        }
