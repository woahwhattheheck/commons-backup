from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from datetime import datetime, timezone
from typing import Any, Mapping

INPUT_SCHEMA = "commons-catalog-currentness-input/v1"
RECEIPT_SCHEMA = "commons-catalog-currentness-receipt/v1"
MAX_SNAPSHOT_AGE_SECONDS = 86400
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
FAMILIES = {"PRODUCT", "SERVICE", "EXPERTISE", "DATA"}
POLICIES = {"PINNED_RELEASE", "FOLLOW_DEFAULT_BRANCH"}
INPUT_KEYS = {"schema", "catalogs", "providerSnapshots"}
CATALOG_KEYS = {"catalogId", "family", "catalogDigestSha256", "entries"}
ENTRY_KEYS = {"entryId", "artifactId", "repository", "releaseCommitSha", "sourcePath", "sourceContentSha256", "sourceEvidenceSha256", "version", "currentnessPolicy"}
SNAPSHOT_KEYS = {"snapshotId", "repository", "defaultBranch", "defaultBranchHeadSha", "capturedAt", "complete", "providerEvidenceSha256", "paths"}
PATH_KEYS = {"sourcePath", "contentSha256"}


class CatalogCurrentnessError(ValueError):
    pass


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def repository_identity(value: str) -> str:
    return value.casefold()


def strict_json_loads(text: str) -> Any:
    def pairs_hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in pairs:
            if key in out:
                raise CatalogCurrentnessError(f"duplicate JSON object key: {key}")
            out[key] = value
        return out

    def reject_constant(value: str) -> Any:
        raise CatalogCurrentnessError(f"non-finite JSON number is not supported: {value}")

    try:
        return json.loads(text, object_pairs_hook=pairs_hook, parse_constant=reject_constant)
    except json.JSONDecodeError as exc:
        raise CatalogCurrentnessError(f"invalid JSON: {exc.msg}") from exc


def _keys(raw: Mapping[str, Any], expected: set[str], label: str) -> None:
    missing, extra = sorted(expected - set(raw)), sorted(set(raw) - expected)
    if missing or extra:
        raise CatalogCurrentnessError(f"{label} schema mismatch: missing={missing} extra={extra}")


def _str(value: Any, label: str, n: int = 512) -> str:
    if not isinstance(value, str) or not value or len(value) > n or "\x00" in value:
        raise CatalogCurrentnessError(f"{label} must be a non-empty safe string <= {n} chars")
    return value


def _id(value: Any, label: str) -> str:
    value = _str(value, label, 128)
    if not IDENT.fullmatch(value):
        raise CatalogCurrentnessError(f"{label} has invalid identifier syntax")
    return value


def _digest(value: Any, label: str, n: int = 64) -> str:
    value = _str(value, label, n)
    if not (HEX40 if n == 40 else HEX64).fullmatch(value):
        raise CatalogCurrentnessError(f"{label} must be lowercase {n}-hex")
    return value


def _path(value: Any, label: str) -> str:
    value = _str(value, label)
    parts = value.split("/")
    if value.startswith(("/", "\\")) or "\\" in value or any(x in {"", ".", ".."} for x in parts):
        raise CatalogCurrentnessError(f"{label} must be a normalized repository-relative POSIX path")
    if any(x.lower().endswith((".lnk", ".url")) for x in parts):
        raise CatalogCurrentnessError(f"{label} contains a link-shaped segment")
    return value


def _instant(value: Any, label: str) -> datetime:
    value = _str(value, label, 32)
    if not value.endswith("Z"):
        raise CatalogCurrentnessError(f"{label} must use explicit UTC Z suffix")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise CatalogCurrentnessError(f"{label} is not ISO-8601 UTC") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise CatalogCurrentnessError(f"{label} must be UTC")
    return parsed


def _sensitive(value: Any) -> bool:
    if isinstance(value, str):
        return bool(EMAIL.search(value) or any(p.search(value) for p in SECRETS))
    if isinstance(value, Mapping):
        return any(_sensitive(k) or _sensitive(v) for k, v in value.items())
    if isinstance(value, (list, tuple)):
        return any(_sensitive(x) for x in value)
    return False


def _entry(raw: Any, catalog_id: str, family: str, catalog_digest: str) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise CatalogCurrentnessError("catalog entry must be an object")
    _keys(raw, ENTRY_KEYS, "catalog entry")
    repo = _str(raw["repository"], "entry.repository", 200)
    version = _str(raw["version"], "entry.version", 64)
    policy = _str(raw["currentnessPolicy"], "entry.currentnessPolicy", 64)
    if not REPO.fullmatch(repo):
        raise CatalogCurrentnessError("entry.repository must be owner/name")
    if not VERSION.fullmatch(version):
        raise CatalogCurrentnessError("entry.version has invalid syntax")
    if policy not in POLICIES:
        raise CatalogCurrentnessError(f"unsupported currentnessPolicy: {policy}")
    out = {
        "catalogId": catalog_id, "catalogFamily": family, "catalogDigestSha256": catalog_digest,
        "entryId": _id(raw["entryId"], "entry.entryId"), "artifactId": _id(raw["artifactId"], "entry.artifactId"),
        "repository": repo, "releaseCommitSha": _digest(raw["releaseCommitSha"], "entry.releaseCommitSha", 40),
        "sourcePath": _path(raw["sourcePath"], "entry.sourcePath"),
        "sourceContentSha256": _digest(raw["sourceContentSha256"], "entry.sourceContentSha256"),
        "sourceEvidenceSha256": _digest(raw["sourceEvidenceSha256"], "entry.sourceEvidenceSha256"),
        "version": version, "currentnessPolicy": policy,
    }
    if _sensitive(out):
        raise CatalogCurrentnessError(f"entry {out['entryId']} contains secret/PII-shaped metadata")
    return out


def _catalog(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise CatalogCurrentnessError("catalog must be an object")
    _keys(raw, CATALOG_KEYS, "catalog")
    cid, family = _id(raw["catalogId"], "catalog.catalogId"), _str(raw["family"], "catalog.family", 32)
    if family not in FAMILIES:
        raise CatalogCurrentnessError(f"unsupported catalog family: {family}")
    digest = _digest(raw["catalogDigestSha256"], "catalog.catalogDigestSha256")
    rows = raw["entries"]
    if not isinstance(rows, list) or not rows:
        raise CatalogCurrentnessError("catalog.entries must be a non-empty list")
    entries = [_entry(x, cid, family, digest) for x in rows]
    ids = [x["entryId"] for x in entries]
    if len(ids) != len(set(ids)):
        raise CatalogCurrentnessError(f"catalog {cid} has duplicate entryId")
    entries.sort(key=lambda x: x["entryId"])
    out = {"catalogId": cid, "family": family, "catalogDigestSha256": digest, "entries": entries}
    if _sensitive(out):
        raise CatalogCurrentnessError(f"catalog {cid} contains secret/PII-shaped metadata")
    return out


def _snapshot(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise CatalogCurrentnessError("provider snapshot must be an object")
    _keys(raw, SNAPSHOT_KEYS, "provider snapshot")
    repo = _str(raw["repository"], "snapshot.repository", 200)
    if not REPO.fullmatch(repo):
        raise CatalogCurrentnessError("snapshot.repository must be owner/name")
    if type(raw["complete"]) is not bool:
        raise CatalogCurrentnessError("snapshot.complete must be a JSON boolean")
    captured = _str(raw["capturedAt"], "snapshot.capturedAt", 32)
    _instant(captured, "snapshot.capturedAt")
    if not isinstance(raw["paths"], list):
        raise CatalogCurrentnessError("snapshot.paths must be a list")
    paths = []
    for item in raw["paths"]:
        if not isinstance(item, Mapping):
            raise CatalogCurrentnessError("snapshot path must be an object")
        _keys(item, PATH_KEYS, "snapshot path")
        paths.append({"sourcePath": _path(item["sourcePath"], "snapshot path.sourcePath"), "contentSha256": _digest(item["contentSha256"], "snapshot path.contentSha256")})
    names = [x["sourcePath"] for x in paths]
    if len(names) != len(set(names)):
        raise CatalogCurrentnessError("provider snapshot has duplicate sourcePath")
    paths.sort(key=lambda x: x["sourcePath"])
    out = {
        "snapshotId": _id(raw["snapshotId"], "snapshot.snapshotId"), "repository": repo,
        "defaultBranch": _id(raw["defaultBranch"], "snapshot.defaultBranch"),
        "defaultBranchHeadSha": _digest(raw["defaultBranchHeadSha"], "snapshot.defaultBranchHeadSha", 40),
        "capturedAt": captured, "complete": raw["complete"],
        "providerEvidenceSha256": _digest(raw["providerEvidenceSha256"], "snapshot.providerEvidenceSha256"), "paths": paths,
    }
    if _sensitive(out):
        raise CatalogCurrentnessError(f"snapshot {out['snapshotId']} contains secret/PII-shaped metadata")
    return out


def normalize_input(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise CatalogCurrentnessError("input must be an object")
    _keys(raw, INPUT_KEYS, "input")
    if raw["schema"] != INPUT_SCHEMA:
        raise CatalogCurrentnessError(f"input.schema must equal {INPUT_SCHEMA}")
    if not isinstance(raw["catalogs"], list) or not raw["catalogs"] or not isinstance(raw["providerSnapshots"], list) or not raw["providerSnapshots"]:
        raise CatalogCurrentnessError("input catalogs and providerSnapshots must be non-empty lists")
    catalogs, snapshots = [_catalog(x) for x in raw["catalogs"]], [_snapshot(x) for x in raw["providerSnapshots"]]
    for rows, key, label in ((catalogs, "catalogId", "catalog"), (snapshots, "snapshotId", "snapshot")):
        ids = [x[key] for x in rows]
        if len(ids) != len(set(ids)):
            raise CatalogCurrentnessError(f"duplicate {label} identity")
    entries = [e for c in catalogs for e in c["entries"]]
    entry_ids = [e["entryId"] for e in entries]
    if len(entry_ids) != len(set(entry_ids)):
        raise CatalogCurrentnessError("entryId must be globally unique across catalogs")
    repo_paths: dict[tuple[str, str], str] = {}
    bindings: dict[str, tuple[str, ...]] = {}
    for e in entries:
        repo_key = repository_identity(e["repository"])
        path_key = (repo_key, e["sourcePath"])
        if path_key in repo_paths and repo_paths[path_key] != e["artifactId"]:
            raise CatalogCurrentnessError(f"conflicting artifact identity for {repo_key}:{e['sourcePath']}")
        repo_paths[path_key] = e["artifactId"]
        binding = (repo_key, e["sourcePath"], e["releaseCommitSha"], e["sourceContentSha256"], e["sourceEvidenceSha256"], e["version"])
        if e["artifactId"] in bindings and bindings[e["artifactId"]] != binding:
            raise CatalogCurrentnessError(f"conflicting immutable binding for artifact {e['artifactId']}")
        bindings[e["artifactId"]] = binding
    catalogs.sort(key=lambda x: x["catalogId"])
    snapshots.sort(key=lambda x: x["snapshotId"])
    return {"schema": INPUT_SCHEMA, "catalogs": catalogs, "providerSnapshots": snapshots}


def _finding(code: str, subject: str, detail: str, severity: str) -> dict[str, str]:
    return {"code": code, "subject": subject, "detail": detail, "severity": severity}


def compile_currentness(raw: Any, *, as_of: str) -> dict[str, Any]:
    data, now = normalize_input(raw), _instant(as_of, "as_of")
    snapshots, findings = data["providerSnapshots"], []
    by_repo: dict[str, list[dict[str, Any]]] = {}
    for s in snapshots:
        key = repository_identity(s["repository"])
        by_repo.setdefault(key, []).append(s)
        age = (now - _instant(s["capturedAt"], "snapshot.capturedAt")).total_seconds()
        if age < 0:
            findings.append(_finding("SNAPSHOT_FROM_FUTURE", s["snapshotId"], "provider snapshot captured after trusted evaluation time", "HOLD"))
        elif age > MAX_SNAPSHOT_AGE_SECONDS:
            findings.append(_finding("SNAPSHOT_STALE", s["snapshotId"], "provider snapshot exceeds 24-hour freshness window", "HOLD"))
        if not s["complete"]:
            findings.append(_finding("SNAPSHOT_INCOMPLETE", s["snapshotId"], "provider snapshot is not complete", "HOLD"))
    for key, rows in by_repo.items():
        if len(rows) != 1:
            findings.append(_finding("AMBIGUOUS_REPOSITORY_SNAPSHOT", key, f"expected exactly one snapshot; found {len(rows)}", "HOLD"))

    results = []
    for e in [x for c in data["catalogs"] for x in c["entries"]]:
        rows = by_repo.get(repository_identity(e["repository"]), [])
        state, reason, head, current_digest = "HOLD", "MISSING_REPOSITORY_SNAPSHOT", None, None
        if not rows:
            findings.append(_finding("MISSING_REPOSITORY_SNAPSHOT", e["entryId"], "no provider snapshot for entry repository", "HOLD"))
        elif len(rows) == 1:
            s, head = rows[0], rows[0]["defaultBranchHeadSha"]
            if s["complete"]:
                current = {x["sourcePath"]: x for x in s["paths"]}.get(e["sourcePath"])
                if current is None:
                    reason = "SOURCE_PATH_MISSING"
                    findings.append(_finding(reason, e["entryId"], "catalog source path is absent from complete provider snapshot", "HOLD"))
                else:
                    current_digest = current["contentSha256"]
                    if current_digest == e["sourceContentSha256"]:
                        state, reason = "CURRENT", "SOURCE_CONTENT_MATCH"
                    elif e["currentnessPolicy"] == "PINNED_RELEASE":
                        state, reason = "REVIEW_REQUIRED", "PINNED_RELEASE_SOURCE_DRIFT"
                        findings.append(_finding(reason, e["entryId"], "default-branch source changed after immutable catalog release; human review required", "REVIEW_REQUIRED"))
                    else:
                        reason = "FOLLOW_DEFAULT_BRANCH_SOURCE_DRIFT"
                        findings.append(_finding(reason, e["entryId"], "default-branch source differs from catalog-bound source", "HOLD"))
        results.append({
            "entryId": e["entryId"], "catalogId": e["catalogId"], "family": e["catalogFamily"], "artifactId": e["artifactId"],
            "repository": e["repository"], "sourcePath": e["sourcePath"], "version": e["version"], "currentnessPolicy": e["currentnessPolicy"],
            "releaseCommitSha": e["releaseCommitSha"], "sourceContentSha256": e["sourceContentSha256"], "sourceEvidenceSha256": e["sourceEvidenceSha256"],
            "providerDefaultBranchHeadSha": head, "providerSourceContentSha256": current_digest, "entryState": state, "reason": reason,
        })
    findings.sort(key=lambda x: (x["severity"], x["code"], x["subject"], x["detail"]))
    results.sort(key=lambda x: x["entryId"])
    has_hold = any(x["severity"] == "HOLD" for x in findings) or any(x["entryState"] == "HOLD" for x in results)
    has_review = any(x["severity"] == "REVIEW_REQUIRED" for x in findings) or any(x["entryState"] == "REVIEW_REQUIRED" for x in results)
    state = "HOLD" if has_hold else "REVIEW_REQUIRED" if has_review else "READY_FOR_HUMAN_CATALOG_CURRENTNESS_REVIEW"
    body = {
        "schema": RECEIPT_SCHEMA, "asOf": as_of, "state": state, "inputDigest": sha256_text(canonical_json(data)),
        "catalogSetDigest": sha256_text(canonical_json([{"catalogId": c["catalogId"], "catalogDigestSha256": c["catalogDigestSha256"]} for c in data["catalogs"]])),
        "providerSnapshotSetDigest": sha256_text(canonical_json(snapshots)),
        "counts": {"catalogs": len(data["catalogs"]), "entries": len(results), "providerSnapshots": len(snapshots), "current": sum(x["entryState"] == "CURRENT" for x in results), "reviewRequired": sum(x["entryState"] == "REVIEW_REQUIRED" for x in results), "hold": sum(x["entryState"] == "HOLD" for x in results), "findings": len(findings)},
        "findings": findings, "entries": results,
        "authority": {k: False for k in ("catalogPublicationAuthorized", "catalogUpdateAuthorized", "catalogWithdrawalAuthorized", "buyerContactAuthorized", "pricingAuthorized", "checkoutAuthorized", "paymentAuthorized", "transferAuthorized", "acceptanceEstablished", "revenueRecognized")},
    }
    return {**body, "receiptSha256": sha256_text(canonical_json(body))}


def verify_receipt(raw: Any, *, as_of: str, receipt: Any) -> bool:
    if not isinstance(receipt, Mapping):
        return False
    try:
        expected = compile_currentness(raw, as_of=as_of)
    except CatalogCurrentnessError:
        return False
    return canonical_json(expected) == canonical_json(receipt)


def render_csv(receipt: Mapping[str, Any]) -> str:
    fields = ["entryId", "catalogId", "family", "artifactId", "repository", "sourcePath", "version", "currentnessPolicy", "releaseCommitSha", "sourceContentSha256", "sourceEvidenceSha256", "providerDefaultBranchHeadSha", "providerSourceContentSha256", "entryState", "reason"]
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for row in receipt.get("entries", []):
        writer.writerow({k: row.get(k) for k in fields})
    return output.getvalue()


def render_markdown(receipt: Mapping[str, Any]) -> str:
    counts = receipt.get("counts", {})
    lines = ["# Catalog currentness receipt", "", f"**State:** `{receipt.get('state', 'HOLD')}`", f"**Trusted evaluation time:** `{receipt.get('asOf', '')}`", f"**Entries:** {counts.get('entries', 0)} · **Current:** {counts.get('current', 0)} · **Review required:** {counts.get('reviewRequired', 0)} · **Hold:** {counts.get('hold', 0)}", "", "## Entries", "", "| Entry | Family | Repository | Version | Policy | State | Reason |", "|---|---|---|---|---|---|---|"]
    lines += ["| {entryId} | {family} | {repository} | {version} | {currentnessPolicy} | {entryState} | {reason} |".format(**row) for row in receipt.get("entries", [])]
    lines += ["", "## Findings", ""]
    findings = receipt.get("findings", [])
    lines += [f"- `{x['severity']}` · `{x['code']}` · `{x['subject']}` · {x['detail']}" for x in findings] if findings else ["None."]
    lines += ["", "## Authority boundary", "", "This receipt is evidence for human catalog-currentness review only. It never publishes, updates, withdraws, reprices, contacts buyers, creates checkout, accepts payment, transfers an artifact, establishes acceptance, or recognizes revenue.", "", f"Receipt SHA-256: `{receipt.get('receiptSha256', '')}`", ""]
    return "\n".join(lines)
