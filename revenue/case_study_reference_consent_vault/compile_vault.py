#!/usr/bin/env python3
"""Evidence + explicit permission -> case-study/reference owner-review vault.

Technical success, delivery, merge, or payment evidence never mints publication or
reference permission. This tool is internal decision support only.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Any

SCHEMA = "case-study-reference-consent-vault/v1"
STATES = ("PUBLIC_CASE_STUDY_OK", "REFERENCE_OK", "INTERNAL_ONLY", "HOLD_PERMISSION")
USES = ("PUBLIC_CASE_STUDY", "REFERENCE")
EVIDENCE_KINDS = ("MERGED_WORK", "DELIVERY", "PAYMENT", "OWNER_APPROVED_FACT")
VISIBILITY = ("PUBLIC", "PRIVATE")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")

class InputError(ValueError):
    pass

def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode()

def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def _pairs(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise InputError(f"duplicate JSON key: {k}")
        out[k] = v
    return out

def _constant(v):
    raise InputError(f"non-finite JSON number prohibited: {v}")

def load_strict(path: Path) -> Any:
    try:
        return json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_pairs,
            parse_constant=_constant,
        )
    except json.JSONDecodeError as exc:
        raise InputError(f"invalid JSON: {exc}") from exc

def _req_str(obj: dict[str, Any], key: str, where: str) -> str:
    v = obj.get(key)
    if not isinstance(v, str) or not v.strip():
        raise InputError(f"{where}.{key}: required non-empty string")
    return v.strip()

def _req_id(obj: dict[str, Any], key: str, where: str) -> str:
    v = _req_str(obj, key, where)
    if not ID_RE.fullmatch(v):
        raise InputError(f"{where}.{key}: invalid identifier")
    return v

def _sha(v: Any, where: str) -> str:
    if not isinstance(v, str) or not SHA_RE.fullmatch(v):
        raise InputError(f"{where}: lowercase SHA-256 required")
    return v

def _dt(v: Any, where: str) -> datetime:
    if not isinstance(v, str) or not v.strip():
        raise InputError(f"{where}: ISO-8601 timestamp required")
    raw = v.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise InputError(f"{where}: invalid ISO-8601") from exc
    if dt.tzinfo is None:
        raise InputError(f"{where}: timezone required")
    return dt.astimezone(timezone.utc)

def _dt_s(v: Any, where: str) -> str:
    return _dt(v, where).isoformat().replace("+00:00", "Z")

def _opt_dt_s(v: Any, where: str) -> str | None:
    if v is None:
        return None
    return _dt_s(v, where)

def _safe_source(v: str, where: str) -> str:
    if v.startswith("https://"):
        authority = v.split("/", 3)[2]
        if "@" in authority or any(c.isspace() for c in v):
            raise InputError(f"{where}: unsafe HTTPS URL")
        return v
    if v.startswith("/") or "\\" in v:
        raise InputError(f"{where}: unsafe repository-relative source")
    if any(p in {"", ".", ".."} for p in v.split("/")):
        raise InputError(f"{where}: unsafe repository-relative source")
    return v

def _list(obj: dict[str, Any], key: str, where: str) -> list[Any]:
    v = obj.get(key)
    if not isinstance(v, list):
        raise InputError(f"{where}.{key}: list required")
    return v

def _str_list(v: Any, where: str, allowed: set[str] | None = None) -> list[str]:
    if not isinstance(v, list):
        raise InputError(f"{where}: list required")
    out = []
    for i, item in enumerate(v):
        if not isinstance(item, str) or not item.strip():
            raise InputError(f"{where}[{i}]: non-empty string required")
        item = item.strip()
        if allowed is not None and item not in allowed:
            raise InputError(f"{where}[{i}]: unsupported value {item}")
        out.append(item)
    if len(set(out)) != len(out):
        raise InputError(f"{where}: duplicate value")
    return sorted(out)

def _bool(v: Any, where: str) -> bool:
    if not isinstance(v, bool):
        raise InputError(f"{where}: boolean required")
    return v

def _unique(values, where):
    seen = set()
    for value in values:
        if value in seen:
            raise InputError(f"{where}: duplicate id {value}")
        seen.add(value)

def normalize(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise InputError("root: object required")
    if raw.get("schema") != SCHEMA:
        raise InputError(f"schema: expected {SCHEMA}")
    as_of = _dt_s(raw.get("as_of"), "as_of")

    counterparties_raw = _list(raw, "counterparties", "root")
    counterparties = []
    for i, cp in enumerate(counterparties_raw):
        where = f"counterparties[{i}]"
        if not isinstance(cp, dict):
            raise InputError(f"{where}: object required")
        counterparties.append({
            "id": _req_id(cp, "id", where),
            "internal_name": _req_str(cp, "internal_name", where),
            "default_public_label": _req_str(cp, "default_public_label", where),
        })
    _unique([x["id"] for x in counterparties], "counterparties")
    cp_ids = {x["id"] for x in counterparties}

    evidence_raw = _list(raw, "evidence", "root")
    evidence = []
    for i, ev in enumerate(evidence_raw):
        where = f"evidence[{i}]"
        if not isinstance(ev, dict):
            raise InputError(f"{where}: object required")
        subject = _req_id(ev, "subject_id", where)
        if subject not in cp_ids:
            raise InputError(f"{where}.subject_id: unknown counterparty")
        kind = _req_str(ev, "kind", where).upper()
        if kind not in EVIDENCE_KINDS:
            raise InputError(f"{where}.kind: unsupported")
        visibility = _req_str(ev, "visibility", where).upper()
        if visibility not in VISIBILITY:
            raise InputError(f"{where}.visibility: unsupported")
        evidence.append({
            "id": _req_id(ev, "id", where),
            "subject_id": subject,
            "kind": kind,
            "generation": _req_id(ev, "generation", where),
            "source": _safe_source(_req_str(ev, "source", where), f"{where}.source"),
            "source_sha256": _sha(ev.get("source_sha256"), f"{where}.source_sha256"),
            "observed_at": _dt_s(ev.get("observed_at"), f"{where}.observed_at"),
            "visibility": visibility,
            "category": _req_id(ev, "category", where),
            "claim_text": _req_str(ev, "claim_text", where),
        })
    _unique([x["id"] for x in evidence], "evidence")
    ev_by_id = {x["id"]: x for x in evidence}

    permissions_raw = _list(raw, "permissions", "root")
    permissions = []
    for i, perm in enumerate(permissions_raw):
        where = f"permissions[{i}]"
        if not isinstance(perm, dict):
            raise InputError(f"{where}: object required")
        subject = _req_id(perm, "subject_id", where)
        if subject not in cp_ids:
            raise InputError(f"{where}.subject_id: unknown counterparty")
        bindings_raw = _list(perm, "evidence_bindings", where)
        bindings = []
        for j, binding in enumerate(bindings_raw):
            loc = f"{where}.evidence_bindings[{j}]"
            if not isinstance(binding, dict):
                raise InputError(f"{loc}: object required")
            eid = _req_id(binding, "evidence_id", loc)
            if eid not in ev_by_id:
                raise InputError(f"{loc}.evidence_id: unknown evidence")
            bindings.append({
                "evidence_id": eid,
                "generation": _req_id(binding, "generation", loc),
                "source_sha256": _sha(binding.get("source_sha256"), f"{loc}.source_sha256"),
            })
        _unique([b["evidence_id"] for b in bindings], f"{where}.evidence_bindings")
        modes = _str_list(perm.get("modes"), f"{where}.modes", set(USES))
        categories = _str_list(perm.get("categories"), f"{where}.categories")
        exact_claims = _str_list(perm.get("exact_claims"), f"{where}.exact_claims")
        permissions.append({
            "id": _req_id(perm, "id", where),
            "subject_id": subject,
            "source": _safe_source(_req_str(perm, "source", where), f"{where}.source"),
            "source_sha256": _sha(perm.get("source_sha256"), f"{where}.source_sha256"),
            "observed_at": _dt_s(perm.get("observed_at"), f"{where}.observed_at"),
            "granted_at": _dt_s(perm.get("granted_at"), f"{where}.granted_at"),
            "valid_through": _opt_dt_s(perm.get("valid_through"), f"{where}.valid_through"),
            "revoked_at": _opt_dt_s(perm.get("revoked_at"), f"{where}.revoked_at"),
            "modes": modes,
            "categories": categories,
            "exact_claims": exact_claims,
            "allow_named_use": _bool(perm.get("allow_named_use"), f"{where}.allow_named_use"),
            "public_name": (
                _req_str(perm, "public_name", where) if perm.get("public_name") is not None else None
            ),
            "evidence_bindings": sorted(bindings, key=lambda b: b["evidence_id"]),
        })
    _unique([x["id"] for x in permissions], "permissions")
    perm_by_id = {x["id"]: x for x in permissions}

    requests_raw = _list(raw, "requests", "root")
    requests = []
    for i, req in enumerate(requests_raw):
        where = f"requests[{i}]"
        if not isinstance(req, dict):
            raise InputError(f"{where}: object required")
        subject = _req_id(req, "subject_id", where)
        if subject not in cp_ids:
            raise InputError(f"{where}.subject_id: unknown counterparty")
        use = _req_str(req, "desired_use", where).upper()
        if use not in USES:
            raise InputError(f"{where}.desired_use: unsupported")
        evidence_ids = _str_list(req.get("evidence_ids"), f"{where}.evidence_ids")
        for eid in evidence_ids:
            if eid not in ev_by_id:
                raise InputError(f"{where}.evidence_ids: unknown evidence {eid}")
        permission_id = req.get("permission_id")
        if permission_id is not None:
            if not isinstance(permission_id, str) or not ID_RE.fullmatch(permission_id):
                raise InputError(f"{where}.permission_id: invalid id")
            if permission_id not in perm_by_id:
                raise InputError(f"{where}.permission_id: unknown permission")
        requests.append({
            "id": _req_id(req, "id", where),
            "subject_id": subject,
            "desired_use": use,
            "category": _req_id(req, "category", where),
            "claim_text": _req_str(req, "claim_text", where),
            "named_use": _bool(req.get("named_use"), f"{where}.named_use"),
            "evidence_ids": evidence_ids,
            "permission_id": permission_id,
        })
    _unique([x["id"] for x in requests], "requests")

    return {
        "schema": SCHEMA,
        "as_of": as_of,
        "counterparties": sorted(counterparties, key=lambda x: x["id"]),
        "evidence": sorted(evidence, key=lambda x: x["id"]),
        "permissions": sorted(permissions, key=lambda x: x["id"]),
        "requests": sorted(requests, key=lambda x: x["id"]),
    }

def evaluate(normalized: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    as_of = _dt(normalized["as_of"], "as_of")
    ev = {x["id"]: x for x in normalized["evidence"]}
    perms = {x["id"]: x for x in normalized["permissions"]}
    cps = {x["id"]: x for x in normalized["counterparties"]}
    results = []
    public_rows = []

    for req in normalized["requests"]:
        reasons = []
        state = "INTERNAL_ONLY"
        permission = perms.get(req["permission_id"]) if req["permission_id"] else None

        for eid in req["evidence_ids"]:
            if ev[eid]["subject_id"] != req["subject_id"]:
                reasons.append(f"EVIDENCE_SUBJECT_MISMATCH:{eid}")

        if not req["evidence_ids"]:
            reasons.append("NO_SUPPORTING_EVIDENCE")

        if permission is None:
            reasons.append("NO_EXPLICIT_PERMISSION")
        else:
            if permission["subject_id"] != req["subject_id"]:
                reasons.append("PERMISSION_SUBJECT_MISMATCH")
            granted = _dt(permission["granted_at"], "permission.granted_at")
            if granted > as_of:
                reasons.append("PERMISSION_NOT_YET_GRANTED")
            if permission["valid_through"] and _dt(permission["valid_through"], "permission.valid_through") < as_of:
                reasons.append("PERMISSION_EXPIRED")
            if permission["revoked_at"] and _dt(permission["revoked_at"], "permission.revoked_at") <= as_of:
                reasons.append("PERMISSION_REVOKED")
            if req["desired_use"] not in permission["modes"]:
                reasons.append("USE_NOT_PERMITTED")
            if req["category"] not in permission["categories"]:
                reasons.append("CATEGORY_NOT_PERMITTED")
            if req["claim_text"] not in permission["exact_claims"]:
                reasons.append("CLAIM_TEXT_NOT_PERMITTED")
            if req["named_use"] and not permission["allow_named_use"]:
                reasons.append("NAMED_USE_NOT_PERMITTED")
            if req["named_use"] and not permission["public_name"]:
                reasons.append("PUBLIC_NAME_MISSING")

            binding_by_id = {b["evidence_id"]: b for b in permission["evidence_bindings"]}
            for eid in req["evidence_ids"]:
                if eid not in binding_by_id:
                    reasons.append(f"EVIDENCE_NOT_BOUND:{eid}")
                    continue
                binding = binding_by_id[eid]
                current = ev[eid]
                if binding["generation"] != current["generation"]:
                    reasons.append(f"EVIDENCE_GENERATION_DRIFT:{eid}")
                if binding["source_sha256"] != current["source_sha256"]:
                    reasons.append(f"EVIDENCE_SOURCE_DRIFT:{eid}")

        hard_hold = [r for r in reasons if r != "NO_EXPLICIT_PERMISSION"]
        if permission is None:
            state = "INTERNAL_ONLY"
        elif hard_hold:
            state = "HOLD_PERMISSION"
        else:
            state = "PUBLIC_CASE_STUDY_OK" if req["desired_use"] == "PUBLIC_CASE_STUDY" else "REFERENCE_OK"

        display = cps[req["subject_id"]]["default_public_label"]
        if permission and req["named_use"] and permission["public_name"]:
            display = permission["public_name"]

        result = {
            "request_id": req["id"],
            "subject_id": req["subject_id"],
            "desired_use": req["desired_use"],
            "category": req["category"],
            "claim_text": req["claim_text"],
            "state": state,
            "reasons": sorted(reasons),
            "permission_id": req["permission_id"],
            "evidence_ids": req["evidence_ids"],
            "public_label": display if state in {"PUBLIC_CASE_STUDY_OK", "REFERENCE_OK"} else None,
        }
        results.append(result)
        if state in {"PUBLIC_CASE_STUDY_OK", "REFERENCE_OK"}:
            # Intentionally exclude internal source IDs, paths, digests, private notes, and permission details.
            public_rows.append({
                "request_id": req["id"],
                "use": req["desired_use"],
                "category": req["category"],
                "public_label": display,
                "claim_text": req["claim_text"],
                "state": state,
            })

    return sorted(results, key=lambda r: r["request_id"]), sorted(public_rows, key=lambda r: r["request_id"])

def render_internal(normalized: dict[str, Any], results: list[dict[str, Any]]) -> str:
    lines = [
        "# Case Study / Reference Consent Vault — Internal Review",
        "",
        f"- **As of:** `{normalized['as_of']}`",
        "",
        "> Evidence of merge, delivery, payment, or owner-approved facts is never permission by itself.",
        "> This artifact authorizes no publication, reference contact, outbound message, or revenue claim.",
        "",
        "| Request | Desired use | State | Permission | Evidence | Reasons |",
        "|---|---|---|---|---|---|",
    ]
    for r in results:
        evs = ", ".join(r["evidence_ids"]) or "—"
        reasons = ", ".join(r["reasons"]) or "—"
        lines.append(
            f"| `{r['request_id']}` | `{r['desired_use']}` | `{r['state']}` | "
            f"`{r['permission_id'] or '—'}` | `{evs}` | {reasons} |"
        )
    lines += [
        "",
        "## Authority ceiling",
        "",
        "- `PUBLIC_CASE_STUDY_OK` means the retained permission covers exactly this claim/use/category/evidence generation.",
        "- `REFERENCE_OK` means the retained permission covers exactly this reference-use request; it does not contact anyone.",
        "- `INTERNAL_ONLY` means evidence may support internal qualification but no explicit permission is bound.",
        "- `HOLD_PERMISSION` means a supplied permission is expired, revoked, mismatched, stale, or otherwise insufficient.",
        "",
        "No state is customer acceptance, contract authority, payment authority, publication action, or revenue recognition.",
        "",
    ]
    return "\n".join(lines)

def render_public(public_rows: list[dict[str, Any]]) -> str:
    lines = [
        "# Approved Case Study / Reference Projection",
        "",
        "> Projection only. This file does not publish, send, contact, or submit anything.",
        "",
    ]
    if not public_rows:
        lines.append("_No approved public/reference rows._")
    else:
        for row in public_rows:
            lines += [
                f"## {row['public_label']}",
                "",
                f"- Use: `{row['use']}`",
                f"- Category: `{row['category']}`",
                f"- State: `{row['state']}`",
                f"- Claim: {row['claim_text']}",
                "",
            ]
    return "\n".join(lines)

def compile_vault(raw: Any) -> tuple[dict[str, Any], str, str, dict[str, Any]]:
    normalized = normalize(raw)
    results, public_rows = evaluate(normalized)
    internal = render_internal(normalized, results)
    public = render_public(public_rows)
    artifact = {
        "schema": SCHEMA,
        "as_of": normalized["as_of"],
        "results": results,
        "public_rows": public_rows,
    }
    receipt = {
        "schema": SCHEMA,
        "as_of": normalized["as_of"],
        "normalized_sha256": digest(canonical_json(normalized)),
        "artifact_sha256": digest(canonical_json(artifact)),
        "internal_packet_sha256": digest(internal.encode()),
        "public_projection_sha256": digest(public.encode()),
        "request_count": len(results),
        "public_case_study_ok": sum(r["state"] == "PUBLIC_CASE_STUDY_OK" for r in results),
        "reference_ok": sum(r["state"] == "REFERENCE_OK" for r in results),
        "internal_only": sum(r["state"] == "INTERNAL_ONLY" for r in results),
        "hold_permission": sum(r["state"] == "HOLD_PERMISSION" for r in results),
    }
    return artifact, internal, public, receipt

def _write(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass

def compile_to_dir(input_path: Path, out_dir: Path, fail_on_hold=False) -> int:
    raw = load_strict(input_path)
    artifact, internal, public, receipt = compile_vault(raw)
    out_dir.mkdir(parents=True, exist_ok=True)
    _write(out_dir/"artifact.json", canonical_json(artifact))
    _write(out_dir/"internal_packet.md", internal.encode())
    _write(out_dir/"public_projection.md", public.encode())
    _write(out_dir/"receipt.json", canonical_json(receipt))
    if fail_on_hold and receipt["hold_permission"]:
        return 2
    return 0

def verify(input_path: Path, artifact_path: Path, internal_path: Path, public_path: Path, receipt_path: Path) -> int:
    raw = load_strict(input_path)
    artifact, internal, public, receipt = compile_vault(raw)
    problems = []
    if load_strict(artifact_path) != artifact:
        problems.append("artifact mismatch")
    if internal_path.read_bytes() != internal.encode():
        problems.append("internal packet mismatch")
    if public_path.read_bytes() != public.encode():
        problems.append("public projection mismatch")
    if load_strict(receipt_path) != receipt:
        problems.append("receipt mismatch")
    if problems:
        for p in problems:
            print(f"VERIFY_FAIL: {p}", file=sys.stderr)
        return 1
    print(
        "VERIFY_OK "
        f"public={receipt['public_case_study_ok']} reference={receipt['reference_ok']} "
        f"internal={receipt['internal_only']} hold={receipt['hold_permission']}"
    )
    return 0

def parser():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("compile")
    c.add_argument("--input", type=Path, required=True)
    c.add_argument("--out-dir", type=Path, required=True)
    c.add_argument("--fail-on-hold", action="store_true")
    v = sub.add_parser("verify")
    v.add_argument("--input", type=Path, required=True)
    v.add_argument("--artifact", type=Path, required=True)
    v.add_argument("--internal", type=Path, required=True)
    v.add_argument("--public", type=Path, required=True)
    v.add_argument("--receipt", type=Path, required=True)
    return p

def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.cmd == "compile":
            return compile_to_dir(args.input, args.out_dir, args.fail_on_hold)
        return verify(args.input, args.artifact, args.internal, args.public, args.receipt)
    except (InputError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
