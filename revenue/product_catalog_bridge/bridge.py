from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from datetime import datetime, timezone
from typing import Any, Mapping

SCHEMA_INPUT = "commons-product-catalog-bridge-input/v1"
SCHEMA_RECEIPT = "commons-product-catalog-bridge-receipt/v1"
MAX_EVIDENCE_AGE_SECONDS = 30 * 24 * 60 * 60

HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
IDENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+\-]{0,63}$")
EMAIL = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
SECRETS = tuple(re.compile(x) for x in (
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    r"(?i)\b(?:sk|rk|pk)_(?:live|test)_[A-Za-z0-9_-]{8,}\b",
    r"(?i)\bgh[pousr]_[A-Za-z0-9]{20,}\b",
    r"(?i)\b(?:api[_-]?key|secret|password|token)\s*[:=]\s*\S{8,}",
))
BOUNDARIES = {"SOURCE_ARCHIVE", "BINARY_PACKAGE", "LOCAL_APPLICATION", "LICENSED_DATA_BUNDLE", "DOCUMENTED_SERVICE_BUNDLE"}
LISTING_STATUSES = {"DRAFT", "INTERNAL_READY", "PUBLISHED"}
VERIFICATION_KINDS = {"SOURCE_TEST", "PACKAGE_TEST", "REPRODUCIBILITY_CHECK", "INSTALL_CHECK", "MANIFEST_CHECK"}
INPUT_KEYS = {"schema", "artifacts", "listings", "evidence"}
ARTIFACT_KEYS = {"artifactId", "repository", "commitSha", "sourcePath", "contentSha256", "version", "licenseId", "licenseEvidenceSha256", "transferBoundary", "catalogListingId"}
LISTING_KEYS = {"listingId", "title", "family", "status", "version", "artifactIds"}
EVIDENCE_KEYS = {"evidenceId", "artifactId", "contentSha256", "verificationKind", "outcome", "capturedAt", "sourceSha256"}


class CatalogBridgeError(ValueError):
    pass


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _keys(obj: Mapping[str, Any], expected: set[str], label: str) -> None:
    missing, extra = sorted(expected - set(obj)), sorted(set(obj) - expected)
    if missing or extra:
        raise CatalogBridgeError(f"{label} schema mismatch: missing={missing} extra={extra}")


def _str(value: Any, label: str, max_len: int = 512) -> str:
    if not isinstance(value, str) or not value or len(value) > max_len or "\x00" in value:
        raise CatalogBridgeError(f"{label} must be a non-empty safe string <= {max_len} chars")
    return value


def _id(value: Any, label: str) -> str:
    value = _str(value, label, 128)
    if not IDENT.fullmatch(value):
        raise CatalogBridgeError(f"{label} has invalid identifier syntax")
    return value


def _digest(value: Any, label: str, length: int = 64) -> str:
    value = _str(value, label, length)
    if not (HEX64 if length == 64 else HEX40).fullmatch(value):
        raise CatalogBridgeError(f"{label} must be lowercase {length}-hex")
    return value


def _instant(value: Any, label: str) -> datetime:
    value = _str(value, label, 32)
    if not value.endswith("Z"):
        raise CatalogBridgeError(f"{label} must use explicit UTC Z suffix")
    try:
        dt = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise CatalogBridgeError(f"{label} is not an ISO-8601 UTC instant") from exc
    if dt.tzinfo is None or dt.utcoffset() != timezone.utc.utcoffset(dt):
        raise CatalogBridgeError(f"{label} must be UTC")
    return dt


def _path(value: Any, label: str) -> str:
    value = _str(value, label)
    parts = value.split("/")
    if value.startswith(("/", "\\")) or "\\" in value or any(x in {"", ".", ".."} for x in parts):
        raise CatalogBridgeError(f"{label} must be a normalized repository-relative POSIX path")
    if any(x.lower().endswith((".lnk", ".url")) for x in parts):
        raise CatalogBridgeError(f"{label} contains link-shaped segment")
    return value


def _sensitive(value: Any) -> bool:
    if isinstance(value, str):
        return bool(EMAIL.search(value) or any(p.search(value) for p in SECRETS))
    if isinstance(value, Mapping):
        return any(_sensitive(k) or _sensitive(v) for k, v in value.items())
    if isinstance(value, (list, tuple)):
        return any(_sensitive(x) for x in value)
    return False


def _artifact(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise CatalogBridgeError("artifact must be an object")
    _keys(raw, ARTIFACT_KEYS, "artifact")
    repo = _str(raw["repository"], "artifact.repository", 200)
    version = _str(raw["version"], "artifact.version", 64)
    license_id = _str(raw["licenseId"], "artifact.licenseId", 96)
    boundary = _str(raw["transferBoundary"], "artifact.transferBoundary", 64)
    if not REPO.fullmatch(repo): raise CatalogBridgeError("artifact.repository must be owner/name")
    if not VERSION.fullmatch(version): raise CatalogBridgeError("artifact.version has invalid syntax")
    if license_id.upper() in {"UNKNOWN", "NONE", "UNVERIFIED", "TBD"}: raise CatalogBridgeError("artifact.licenseId is not transfer-ready")
    if boundary not in BOUNDARIES: raise CatalogBridgeError(f"artifact.transferBoundary unsupported: {boundary}")
    out = {
        "artifactId": _id(raw["artifactId"], "artifact.artifactId"),
        "repository": repo,
        "commitSha": _digest(raw["commitSha"], "artifact.commitSha", 40),
        "sourcePath": _path(raw["sourcePath"], "artifact.sourcePath"),
        "contentSha256": _digest(raw["contentSha256"], "artifact.contentSha256"),
        "version": version,
        "licenseId": license_id,
        "licenseEvidenceSha256": _digest(raw["licenseEvidenceSha256"], "artifact.licenseEvidenceSha256"),
        "transferBoundary": boundary,
        "catalogListingId": _id(raw["catalogListingId"], "artifact.catalogListingId"),
    }
    if _sensitive(out): raise CatalogBridgeError(f"artifact {out['artifactId']} contains secret/PII-shaped metadata")
    return out


def _listing(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, Mapping): raise CatalogBridgeError("listing must be an object")
    _keys(raw, LISTING_KEYS, "listing")
    family, status = _str(raw["family"], "listing.family", 32), _str(raw["status"], "listing.status", 32)
    version = _str(raw["version"], "listing.version", 64)
    if family != "PRODUCT": raise CatalogBridgeError("listing.family must be PRODUCT")
    if status not in LISTING_STATUSES: raise CatalogBridgeError(f"listing.status unsupported: {status}")
    if not VERSION.fullmatch(version): raise CatalogBridgeError("listing.version has invalid syntax")
    ids = raw["artifactIds"]
    if not isinstance(ids, list) or not ids: raise CatalogBridgeError("listing.artifactIds must be a non-empty list")
    ids = [_id(x, "listing.artifactIds[]") for x in ids]
    if len(ids) != len(set(ids)): raise CatalogBridgeError("listing has duplicate artifactIds")
    out = {"listingId": _id(raw["listingId"], "listing.listingId"), "title": _str(raw["title"], "listing.title", 160), "family": family, "status": status, "version": version, "artifactIds": sorted(ids)}
    if _sensitive(out): raise CatalogBridgeError(f"listing {out['listingId']} contains secret/PII-shaped metadata")
    return out


def _evidence(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, Mapping): raise CatalogBridgeError("evidence must be an object")
    _keys(raw, EVIDENCE_KEYS, "evidence")
    kind, outcome = _str(raw["verificationKind"], "evidence.verificationKind", 64), _str(raw["outcome"], "evidence.outcome", 16)
    if kind not in VERIFICATION_KINDS: raise CatalogBridgeError(f"evidence.verificationKind unsupported: {kind}")
    if outcome not in {"PASS", "FAIL"}: raise CatalogBridgeError("evidence.outcome must be PASS or FAIL")
    captured = _str(raw["capturedAt"], "evidence.capturedAt", 32); _instant(captured, "evidence.capturedAt")
    out = {"evidenceId": _id(raw["evidenceId"], "evidence.evidenceId"), "artifactId": _id(raw["artifactId"], "evidence.artifactId"), "contentSha256": _digest(raw["contentSha256"], "evidence.contentSha256"), "verificationKind": kind, "outcome": outcome, "capturedAt": captured, "sourceSha256": _digest(raw["sourceSha256"], "evidence.sourceSha256")}
    if _sensitive(out): raise CatalogBridgeError(f"evidence {out['evidenceId']} contains secret/PII-shaped metadata")
    return out


def normalize_input(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, Mapping): raise CatalogBridgeError("input must be an object")
    _keys(raw, INPUT_KEYS, "input")
    if raw["schema"] != SCHEMA_INPUT: raise CatalogBridgeError(f"input.schema must equal {SCHEMA_INPUT}")
    if not all(isinstance(raw[x], list) and raw[x] for x in ("artifacts", "listings", "evidence")):
        raise CatalogBridgeError("artifacts, listings, and evidence must be non-empty lists")
    groups = {"artifacts": [_artifact(x) for x in raw["artifacts"]], "listings": [_listing(x) for x in raw["listings"]], "evidence": [_evidence(x) for x in raw["evidence"]]}
    for name, key in (("artifacts", "artifactId"), ("listings", "listingId"), ("evidence", "evidenceId")):
        ids = [x[key] for x in groups[name]]
        if len(ids) != len(set(ids)): raise CatalogBridgeError(f"duplicate {name[:-1]} identity")
        groups[name].sort(key=lambda x: x[key])
    return {"schema": SCHEMA_INPUT, **groups}


def _hold(code: str, subject: str, detail: str) -> dict[str, str]:
    return {"code": code, "subject": subject, "detail": detail}


def compile_catalog_bridge(raw: Any, *, as_of: str) -> dict[str, Any]:
    data, now = normalize_input(raw), _instant(as_of, "as_of")
    artifacts, listings, evidence = data["artifacts"], data["listings"], data["evidence"]
    by_artifact, by_listing, ev_by_artifact, holds = {x["artifactId"]: x for x in artifacts}, {x["listingId"]: x for x in listings}, {}, []
    for ev in evidence:
        ev_by_artifact.setdefault(ev["artifactId"], []).append(ev)
        if ev["artifactId"] not in by_artifact: holds.append(_hold("ORPHAN_EVIDENCE", ev["evidenceId"], "evidence names an unknown artifact"))
    for artifact in artifacts:
        aid, listing = artifact["artifactId"], by_listing.get(artifact["catalogListingId"])
        if listing is None: holds.append(_hold("MISSING_LISTING", aid, "artifact catalogListingId is absent"))
        else:
            if aid not in listing["artifactIds"]: holds.append(_hold("LISTING_BACKREF_MISMATCH", aid, "listing does not name the mapped artifact"))
            if listing["version"] != artifact["version"]: holds.append(_hold("LISTING_VERSION_MISMATCH", aid, "listing version differs from artifact version"))
        rows = ev_by_artifact.get(aid, [])
        if not rows:
            holds.append(_hold("MISSING_VERIFICATION_EVIDENCE", aid, "artifact has no verification evidence")); continue
        passing = 0
        for ev in rows:
            if ev["contentSha256"] != artifact["contentSha256"]: holds.append(_hold("EVIDENCE_CONTENT_MISMATCH", ev["evidenceId"], "evidence content digest differs from artifact")); continue
            age = (now - _instant(ev["capturedAt"], "evidence.capturedAt")).total_seconds()
            if age < 0: holds.append(_hold("EVIDENCE_FROM_FUTURE", ev["evidenceId"], "evidence captured after trusted evaluation time")); continue
            if age > MAX_EVIDENCE_AGE_SECONDS: holds.append(_hold("EVIDENCE_STALE", ev["evidenceId"], "verification evidence exceeds 30-day freshness window")); continue
            if ev["outcome"] != "PASS": holds.append(_hold("VERIFICATION_FAILED", ev["evidenceId"], "verification evidence outcome is not PASS")); continue
            passing += 1
        if not passing: holds.append(_hold("NO_CURRENT_PASSING_EVIDENCE", aid, "artifact lacks current digest-bound PASS evidence"))
    mapped: dict[str, set[str]] = {}
    for a in artifacts: mapped.setdefault(a["catalogListingId"], set()).add(a["artifactId"])
    for listing in listings:
        listed, expected = set(listing["artifactIds"]), mapped.get(listing["listingId"], set())
        unknown = sorted(listed - set(by_artifact))
        if unknown: holds.append(_hold("LISTING_NAMES_UNKNOWN_ARTIFACT", listing["listingId"], ",".join(unknown)))
        if listed != expected: holds.append(_hold("LISTING_COVERAGE_MISMATCH", listing["listingId"], f"listed={sorted(listed)} mapped={sorted(expected)}"))
    paths: dict[tuple[str, str], str] = {}
    for a in artifacts:
        key = (a["repository"], a["sourcePath"])
        if key in paths and paths[key] != a["artifactId"]: holds.append(_hold("CONFLICTING_ARTIFACT_IDENTITY", a["artifactId"], f"same repository/path also claimed by {paths[key]}"))
        paths[key] = a["artifactId"]
    holds.sort(key=lambda x: (x["code"], x["subject"], x["detail"]))
    summary_artifacts = [{k: a[k] for k in ("artifactId", "catalogListingId", "repository", "commitSha", "sourcePath", "contentSha256", "version", "licenseId", "licenseEvidenceSha256", "transferBoundary")} for a in artifacts]
    summary_listings = [{k: x[k] for k in ("listingId", "title", "status", "version", "artifactIds")} for x in listings]
    body = {
        "schema": SCHEMA_RECEIPT, "asOf": as_of, "state": "READY_FOR_HUMAN_CATALOG_PUBLICATION" if not holds else "HOLD",
        "inputDigest": sha256_text(canonical_json(data)),
        "inventoryDigest": sha256_text(canonical_json({"artifacts": artifacts, "listings": listings, "evidence": evidence})),
        "counts": {"artifacts": len(artifacts), "listings": len(listings), "evidence": len(evidence), "holds": len(holds)}, "holds": holds,
        "authority": {k: False for k in ("catalogPublicationAuthorized", "checkoutCreationAuthorized", "buyerContactAuthorized", "contractAuthorized", "paymentAuthorized", "transferAuthorized", "deploymentAuthorized", "acceptanceEstablished", "revenueRecognized")},
        "artifacts": summary_artifacts, "listings": summary_listings,
    }
    return {**body, "receiptSha256": sha256_text(canonical_json(body))}


def verify_receipt(raw: Any, *, as_of: str, receipt: Any) -> bool:
    if not isinstance(receipt, Mapping): return False
    try: expected = compile_catalog_bridge(raw, as_of=as_of)
    except CatalogBridgeError: return False
    return canonical_json(expected) == canonical_json(receipt)


def render_csv(receipt: Mapping[str, Any]) -> str:
    out = io.StringIO(newline="")
    fields = ["artifactId", "catalogListingId", "repository", "commitSha", "sourcePath", "contentSha256", "version", "licenseId", "licenseEvidenceSha256", "transferBoundary", "state"]
    writer = csv.DictWriter(out, fieldnames=fields, lineterminator="\n"); writer.writeheader()
    for artifact in receipt.get("artifacts", []): writer.writerow({**artifact, "state": receipt.get("state", "HOLD")})
    return out.getvalue()


def render_markdown(receipt: Mapping[str, Any]) -> str:
    counts = receipt.get("counts", {})
    lines = ["# Product catalog bridge receipt", "", f"**State:** `{receipt.get('state', 'HOLD')}`", f"**Trusted evaluation time:** `{receipt.get('asOf', '')}`", f"**Artifacts:** {counts.get('artifacts', 0)} · **Listings:** {counts.get('listings', 0)} · **Holds:** {counts.get('holds', 0)}", "", "## Artifact coverage", "", "| Artifact | Listing | Repository | Commit | Version | Transfer boundary |", "|---|---|---|---|---|---|"]
    for a in receipt.get("artifacts", []): lines.append("| {artifactId} | {catalogListingId} | {repository} | `{commitSha}` | {version} | {transferBoundary} |".format(**a))
    lines += ["", "## Holds", ""]
    holds = receipt.get("holds", [])
    lines += [f"- `{h['code']}` · `{h['subject']}` · {h['detail']}" for h in holds] if holds else ["None. The evidence packet is ready for **human catalog publication review** only."]
    lines += ["", "## Authority boundary", "", "This receipt never publishes a catalog listing, creates checkout, contacts a buyer, signs a contract, accepts payment, transfers artifacts, deploys software, establishes acceptance, or recognizes revenue.", "", f"Receipt SHA-256: `{receipt.get('receiptSha256', '')}`", ""]
    return "\n".join(lines)
