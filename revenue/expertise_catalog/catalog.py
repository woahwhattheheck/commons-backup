from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

SCHEMA = "commons.expertise-catalog/v1"
MAX_SAFE_INTEGER = 9_007_199_254_740_991
DELIVERABLE_TYPES = {
    "ADVISORY_HOUR",
    "WRITTEN_ASSESSMENT",
    "DESIGN_REVIEW",
    "EMBEDDED_ENGAGEMENT",
}
EVIDENCE_KINDS = {
    "CAPABILITY_DEMO",
    "DELIVERY_RECEIPT",
    "ASSESSMENT_SAMPLE",
    "VERIFICATION_REPORT",
    "SOURCE_ARTIFACT",
}
OFFER_FIELDS = {
    "offer_id",
    "version",
    "title",
    "summary",
    "deliverable_type",
    "currency",
    "price_cents",
    "valid_from",
    "valid_until",
    "delivery_window_days",
    "source",
    "evidence",
    "scope",
}
SOURCE_FIELDS = {"repository", "commit", "path", "sha256"}
EVIDENCE_FIELDS = {"evidence_id", "kind", "repository", "commit", "path", "sha256"}
SCOPE_FIELDS = {"included", "excluded"}
HEX40_RE = re.compile(r"^[0-9a-f]{40}$")
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
ID_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
EMAIL_RE = re.compile(r"(?i)(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![A-Za-z0-9._%+-])")
SECRET_PATTERNS = (
    re.compile(r"(?i)\bsk-(?:proj-)?[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bAIza[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"(?i)\b(?:password|passwd|api[_-]?key|access[_-]?token)\s*[:=]\s*[^\s]{8,}"),
)


class CatalogError(ValueError):
    """Fail-closed validation error for catalog compilation."""


@dataclass(frozen=True)
class CompiledCatalog:
    manifest: dict[str, Any]
    markdown: str


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_json(value: Any) -> str:
    return _sha256_bytes(_canonical_bytes(value))


def _require_dict(value: Any, label: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise CatalogError(f"{label}: expected object")
    return value


def _require_exact_fields(obj: Mapping[str, Any], allowed: set[str], label: str) -> None:
    unknown = sorted(set(obj) - allowed)
    missing = sorted(allowed - set(obj))
    if unknown:
        raise CatalogError(f"{label}: unknown fields: {', '.join(unknown)}")
    if missing:
        raise CatalogError(f"{label}: missing fields: {', '.join(missing)}")


def _require_str(value: Any, label: str, *, min_len: int = 1, max_len: int = 400) -> str:
    if type(value) is not str:
        raise CatalogError(f"{label}: expected string")
    if value != unicodedata.normalize("NFC", value):
        raise CatalogError(f"{label}: string must be NFC-normalized")
    if value != value.strip():
        raise CatalogError(f"{label}: leading/trailing whitespace forbidden")
    if "\x00" in value or "\r" in value:
        raise CatalogError(f"{label}: forbidden control character")
    if len(value) < min_len or len(value) > max_len:
        raise CatalogError(f"{label}: length out of bounds")
    return value


def _reject_sensitive_text(value: str, label: str) -> None:
    if EMAIL_RE.search(value):
        raise CatalogError(f"{label}: email/PII-shaped text forbidden")
    for pattern in SECRET_PATTERNS:
        if pattern.search(value):
            raise CatalogError(f"{label}: secret-shaped text forbidden")


def _require_public_text(value: Any, label: str, *, min_len: int = 1, max_len: int = 400) -> str:
    text = _require_str(value, label, min_len=min_len, max_len=max_len)
    _reject_sensitive_text(text, label)
    return text


def _parse_timestamp(value: Any, label: str) -> datetime:
    text = _require_str(value, label, min_len=1, max_len=40)
    if not TIMESTAMP_RE.fullmatch(text):
        raise CatalogError(f"{label}: expected canonical UTC timestamp YYYY-MM-DDTHH:MM:SSZ")
    try:
        parsed = datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise CatalogError(f"{label}: invalid timestamp") from exc
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != text:
        raise CatalogError(f"{label}: noncanonical timestamp")
    return parsed


def _validate_repo_ref(obj: Any, label: str, allowed_fields: set[str]) -> dict[str, str]:
    record = _require_dict(obj, label)
    _require_exact_fields(record, allowed_fields, label)
    repository = _require_str(record["repository"], f"{label}.repository", max_len=160)
    if not REPO_RE.fullmatch(repository):
        raise CatalogError(f"{label}.repository: expected owner/repo")
    commit = _require_str(record["commit"], f"{label}.commit", min_len=1, max_len=80)
    if not HEX40_RE.fullmatch(commit):
        raise CatalogError(f"{label}.commit: expected lowercase 40-hex commit")
    path = _require_str(record["path"], f"{label}.path", max_len=300)
    if path.startswith(("/", "\\")) or "\\" in path:
        raise CatalogError(f"{label}.path: must be repository-relative POSIX path")
    parts = path.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise CatalogError(f"{label}.path: empty/dot/traversal segment forbidden")
    digest = _require_str(record["sha256"], f"{label}.sha256", min_len=64, max_len=64)
    if not HEX64_RE.fullmatch(digest):
        raise CatalogError(f"{label}.sha256: expected lowercase 64-hex digest")
    return {"repository": repository, "commit": commit, "path": path, "sha256": digest}


def _validate_scope(value: Any, label: str) -> dict[str, list[str]]:
    scope = _require_dict(value, label)
    _require_exact_fields(scope, SCOPE_FIELDS, label)
    out: dict[str, list[str]] = {}
    for key in ("included", "excluded"):
        raw = scope[key]
        if type(raw) is not list or not raw:
            raise CatalogError(f"{label}.{key}: expected non-empty list")
        items = [_require_public_text(v, f"{label}.{key}[{i}]", max_len=240) for i, v in enumerate(raw)]
        if len(items) != len(set(items)):
            raise CatalogError(f"{label}.{key}: duplicate entries forbidden")
        out[key] = sorted(items)
    if set(out["included"]) & set(out["excluded"]):
        raise CatalogError(f"{label}: included/excluded overlap")
    return out


def _validate_evidence(value: Any, label: str) -> list[dict[str, str]]:
    if type(value) is not list or not value:
        raise CatalogError(f"{label}: expected non-empty list")
    normalized: list[dict[str, str]] = []
    by_id: dict[str, str] = {}
    for index, raw in enumerate(value):
        evidence_label = f"{label}[{index}]"
        obj = _require_dict(raw, evidence_label)
        _require_exact_fields(obj, EVIDENCE_FIELDS, evidence_label)
        evidence_id = _require_str(obj["evidence_id"], f"{evidence_label}.evidence_id", max_len=64)
        if not ID_RE.fullmatch(evidence_id):
            raise CatalogError(f"{evidence_label}.evidence_id: invalid stable id")
        kind = _require_str(obj["kind"], f"{evidence_label}.kind", max_len=40)
        if kind not in EVIDENCE_KINDS:
            raise CatalogError(f"{evidence_label}.kind: unsupported evidence kind")
        repo_ref = _validate_repo_ref(
            {k: obj[k] for k in SOURCE_FIELDS}, evidence_label, SOURCE_FIELDS
        )
        item = {"evidence_id": evidence_id, "kind": kind, **repo_ref}
        digest = _sha256_json(item)
        previous = by_id.get(evidence_id)
        if previous is not None and previous != digest:
            raise CatalogError(f"{label}: conflicting duplicate evidence_id {evidence_id}")
        if previous is None:
            by_id[evidence_id] = digest
            normalized.append(item)
    normalized.sort(key=lambda item: item["evidence_id"])
    return normalized


def _validate_offer(raw: Any, *, as_of: datetime) -> dict[str, Any]:
    obj = _require_dict(raw, "offer")
    _require_exact_fields(obj, OFFER_FIELDS, "offer")

    offer_id = _require_str(obj["offer_id"], "offer.offer_id", max_len=64)
    if not ID_RE.fullmatch(offer_id):
        raise CatalogError("offer.offer_id: invalid stable id")
    version = _require_str(obj["version"], "offer.version", max_len=32)
    if not VERSION_RE.fullmatch(version):
        raise CatalogError("offer.version: expected numeric semver x.y.z")
    title = _require_public_text(obj["title"], "offer.title", max_len=120)
    summary = _require_public_text(obj["summary"], "offer.summary", max_len=600)
    deliverable_type = _require_str(obj["deliverable_type"], "offer.deliverable_type", max_len=40)
    if deliverable_type not in DELIVERABLE_TYPES:
        raise CatalogError("offer.deliverable_type: unsupported deliverable type")
    currency = _require_str(obj["currency"], "offer.currency", min_len=3, max_len=3)
    if not CURRENCY_RE.fullmatch(currency):
        raise CatalogError("offer.currency: expected uppercase three-letter currency")
    price_cents = obj["price_cents"]
    if type(price_cents) is not int or not (1 <= price_cents <= MAX_SAFE_INTEGER):
        raise CatalogError("offer.price_cents: expected positive JSON-safe integer cents")
    delivery_window_days = obj["delivery_window_days"]
    if type(delivery_window_days) is not int or not (1 <= delivery_window_days <= 365):
        raise CatalogError("offer.delivery_window_days: expected integer 1..365")

    valid_from_text = _require_str(obj["valid_from"], "offer.valid_from", min_len=1, max_len=40)
    valid_until_text = _require_str(obj["valid_until"], "offer.valid_until", min_len=1, max_len=40)
    valid_from = _parse_timestamp(valid_from_text, "offer.valid_from")
    valid_until = _parse_timestamp(valid_until_text, "offer.valid_until")
    if valid_until <= valid_from:
        raise CatalogError("offer: valid_until must be after valid_from")

    source = _validate_repo_ref(obj["source"], "offer.source", SOURCE_FIELDS)
    evidence = _validate_evidence(obj["evidence"], "offer.evidence")
    scope = _validate_scope(obj["scope"], "offer.scope")

    hold_reasons: list[str] = []
    if as_of < valid_from:
        hold_reasons.append("NOT_YET_ACTIVE")
    if as_of >= valid_until:
        hold_reasons.append("EXPIRED")

    material = {
        "offer_id": offer_id,
        "version": version,
        "family": "EXPERTISE",
        "title": title,
        "summary": summary,
        "deliverable_type": deliverable_type,
        "currency": currency,
        "price_cents": price_cents,
        "valid_from": valid_from_text,
        "valid_until": valid_until_text,
        "delivery_window_days": delivery_window_days,
        "source": source,
        "evidence": evidence,
        "scope": scope,
    }
    offer_digest = _sha256_json(material)
    return {
        **material,
        "offer_digest": offer_digest,
        "status": "CATALOG_REVIEW_PACKET_READY" if not hold_reasons else "HOLD",
        "hold_reasons": hold_reasons,
        "publication_authorized": False,
        "buyer_contact_authorized": False,
        "checkout_or_payment_authorized": False,
        "contract_or_signature_authorized": False,
        "delivery_start_authorized": False,
        "revenue_recognized": False,
    }


def _money(currency: str, cents: int) -> str:
    major, minor = divmod(cents, 100)
    grouped = f"{major:,}"
    if currency == "USD":
        return f"${grouped}.{minor:02d} USD"
    return f"{currency} {grouped}.{minor:02d}"


def _render_markdown(manifest: Mapping[str, Any]) -> str:
    lines = [
        "# Expertise catalog review packet",
        "",
        f"Schema: `{manifest['schema']}`  ",
        f"Trusted evaluation time: `{manifest['as_of']}`  ",
        f"Catalog digest: `{manifest['catalog_digest']}`",
        "",
        "> Evidence-bound draft only. No listing publication, buyer contact, checkout/payment, contract/signature, delivery start, or revenue recognition is authorized by this packet.",
        "",
    ]
    for item in manifest["offers"]:
        lines.extend(
            [
                f"## {item['title']}",
                "",
                f"- **ID/version:** `{item['offer_id']}@{item['version']}`",
                f"- **State:** `{item['status']}`",
                f"- **Deliverable:** `{item['deliverable_type']}`",
                f"- **Review price:** {_money(item['currency'], item['price_cents'])}",
                f"- **Delivery window:** {item['delivery_window_days']} day(s)",
                f"- **Validity:** `{item['valid_from']}` → `{item['valid_until']}`",
                f"- **Source pin:** `{item['source']['repository']}@{item['source']['commit']}` · `{item['source']['path']}` · sha256 `{item['source']['sha256']}`",
                f"- **Offer digest:** `{item['offer_digest']}`",
            ]
        )
        if item["hold_reasons"]:
            lines.append(f"- **HOLD reasons:** {', '.join(f'`{reason}`' for reason in item['hold_reasons'])}")
        lines.extend(["", item["summary"], "", "### Included", ""])
        lines.extend(f"- {entry}" for entry in item["scope"]["included"])
        lines.extend(["", "### Explicitly excluded", ""])
        lines.extend(f"- {entry}" for entry in item["scope"]["excluded"])
        lines.extend(["", "### Evidence", ""])
        for evidence in item["evidence"]:
            lines.append(
                f"- `{evidence['evidence_id']}` · `{evidence['kind']}` · "
                f"`{evidence['repository']}@{evidence['commit']}` · `{evidence['path']}` · sha256 `{evidence['sha256']}`"
            )
        lines.extend(["", "---", ""])
    return "\n".join(lines).rstrip() + "\n"


def compile_catalog(offers: Sequence[Any], *, as_of: str) -> CompiledCatalog:
    if type(offers) is not list:
        raise CatalogError("offers: expected list")
    if not offers:
        raise CatalogError("offers: at least one offer is required")
    as_of_dt = _parse_timestamp(as_of, "as_of")

    normalized = [_validate_offer(raw, as_of=as_of_dt) for raw in offers]
    normalized.sort(key=lambda item: (item["offer_id"], item["version"], item["offer_digest"]))

    deduped: list[dict[str, Any]] = []
    keys: dict[tuple[str, str], str] = {}
    for item in normalized:
        key = (item["offer_id"], item["version"])
        previous = keys.get(key)
        if previous is None:
            keys[key] = item["offer_digest"]
            deduped.append(item)
        elif previous != item["offer_digest"]:
            raise CatalogError(f"offers: conflicting duplicate {key[0]}@{key[1]}")

    ready = sum(item["status"] == "CATALOG_REVIEW_PACKET_READY" for item in deduped)
    hold = len(deduped) - ready
    # Bind the canonical logical offer set, not caller-provided list order.
    input_digest = _sha256_json([item["offer_digest"] for item in deduped])
    body = {
        "schema": SCHEMA,
        "as_of": as_of,
        "family": "EXPERTISE",
        "input_digest": input_digest,
        "counts": {"total": len(deduped), "review_packet_ready": ready, "hold": hold},
        "offers": deduped,
        "authority": {
            "publication_authorized": False,
            "buyer_contact_authorized": False,
            "checkout_or_payment_authorized": False,
            "contract_or_signature_authorized": False,
            "delivery_start_authorized": False,
            "revenue_recognized": False,
        },
    }
    catalog_digest = _sha256_json(body)
    manifest = {**body, "catalog_digest": catalog_digest}
    markdown = _render_markdown(manifest)
    return CompiledCatalog(manifest=manifest, markdown=markdown)


def verify_catalog(
    manifest: Any,
    markdown: str | None = None,
    *,
    expected_catalog_digest: str | None = None,
) -> bool:
    if type(manifest) is not dict:
        return False
    expected_fields = {
        "schema",
        "as_of",
        "family",
        "input_digest",
        "counts",
        "offers",
        "authority",
        "catalog_digest",
    }
    if set(manifest) != expected_fields:
        return False
    if manifest.get("schema") != SCHEMA or manifest.get("family") != "EXPERTISE":
        return False
    digest = manifest.get("catalog_digest")
    if type(digest) is not str or not HEX64_RE.fullmatch(digest):
        return False
    if expected_catalog_digest is not None:
        if type(expected_catalog_digest) is not str or not HEX64_RE.fullmatch(expected_catalog_digest):
            return False
        if digest != expected_catalog_digest:
            return False

    offers = manifest.get("offers")
    if type(offers) is not list or not offers:
        return False
    derived_fields = {
        "family",
        "offer_digest",
        "status",
        "hold_reasons",
        "publication_authorized",
        "buyer_contact_authorized",
        "checkout_or_payment_authorized",
        "contract_or_signature_authorized",
        "delivery_start_authorized",
        "revenue_recognized",
    }
    expected_offer_fields = OFFER_FIELDS | derived_fields
    reconstructed: list[dict[str, Any]] = []
    for item in offers:
        if type(item) is not dict or set(item) != expected_offer_fields:
            return False
        reconstructed.append({key: item[key] for key in OFFER_FIELDS})

    # Recompile from the manifest's own normalized offer material. This proves
    # schema, derived status/counts, ordering, authority ceilings, and every
    # canonical digest are mutually consistent. It intentionally does not
    # claim authenticity of a coherently rewritten catalog; callers that need
    # that binding must supply the independently retained expected digest.
    try:
        expected = compile_catalog(reconstructed, as_of=manifest.get("as_of"))
    except (CatalogError, TypeError, ValueError):
        return False
    if manifest != expected.manifest:
        return False
    if markdown is not None and markdown != expected.markdown:
        return False
    return True


def canonical_manifest_bytes(manifest: Mapping[str, Any]) -> bytes:
    return _canonical_bytes(manifest) + b"\n"
