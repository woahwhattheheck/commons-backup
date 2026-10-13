#!/usr/bin/env python3
"""Fail-closed verifier for TITAN V4's durable mechanism/falsification registry."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path, PurePosixPath
from typing import Any

SCHEMA = "titan-v4-mechanism-claims/v1"
STATUSES = {"CONFIRMED", "FALSIFIED", "CONDITIONAL"}
CLAIM_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
BLOB_RE = re.compile(r"^[0-9a-f]{40}$")
ALLOWED_PREFIX = "revenue/kaggriculture/cloud-execution-lab/"


class RegistryError(ValueError):
    pass


def _pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise RegistryError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def load_json_bytes(data: bytes) -> Any:
    try:
        return json.loads(data.decode("utf-8"), object_pairs_hook=_pairs)
    except UnicodeDecodeError as exc:
        raise RegistryError(f"registry is not UTF-8: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RegistryError(f"invalid JSON: {exc}") from exc


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def canonical_relpath(raw: Any) -> str:
    if not isinstance(raw, str) or not raw:
        raise RegistryError("evidence path must be a non-empty string")
    if "\\" in raw or raw.startswith("/"):
        raise RegistryError(f"evidence path must be repository-relative POSIX: {raw!r}")
    pure = PurePosixPath(raw)
    if any(part in ("", ".", "..") for part in pure.parts):
        raise RegistryError(f"evidence path is not canonical: {raw!r}")
    if not raw.startswith(ALLOWED_PREFIX):
        raise RegistryError(f"evidence path escapes allowed source root: {raw!r}")
    return raw


def _norm_proposition(text: str) -> str:
    return " ".join(text.casefold().split())


def verify(registry: Any, repo_root: Path) -> dict[str, Any]:
    if not isinstance(registry, dict):
        raise RegistryError("registry root must be an object")
    if registry.get("schema") != SCHEMA:
        raise RegistryError(f"schema must be {SCHEMA}")
    if registry.get("canonical_branch") != "main":
        raise RegistryError("canonical_branch must be main")
    claims = registry.get("claims")
    if not isinstance(claims, list) or not claims:
        raise RegistryError("claims must be a non-empty array")

    repo_root = repo_root.resolve(strict=True)
    seen_ids: set[str] = set()
    seen_props: set[str] = set()
    output_claims = []
    ids = []

    for idx, claim in enumerate(claims):
        where = f"claims[{idx}]"
        if not isinstance(claim, dict):
            raise RegistryError(f"{where} must be an object")
        cid = claim.get("id")
        if not isinstance(cid, str) or not CLAIM_ID_RE.fullmatch(cid):
            raise RegistryError(f"{where}.id is invalid")
        if cid in seen_ids:
            raise RegistryError(f"duplicate claim id: {cid}")
        seen_ids.add(cid)
        ids.append(cid)

        status = claim.get("status")
        if status not in STATUSES:
            raise RegistryError(f"{cid}: invalid status {status!r}")
        proposition = claim.get("proposition")
        if not isinstance(proposition, str) or not proposition.strip():
            raise RegistryError(f"{cid}: proposition must be non-empty")
        norm = _norm_proposition(proposition)
        if norm in seen_props:
            raise RegistryError(f"duplicate normalized proposition: {cid}")
        seen_props.add(norm)

        scope = claim.get("scope")
        disposition = claim.get("disposition")
        next_gate = claim.get("next_gate")
        for name, value in (("scope", scope), ("disposition", disposition), ("next_gate", next_gate)):
            if not isinstance(value, str) or not value.strip():
                raise RegistryError(f"{cid}: {name} must be non-empty")
        tags = claim.get("tags")
        if not isinstance(tags, list) or not tags or any(not isinstance(t, str) or not t for t in tags):
            raise RegistryError(f"{cid}: tags must be a non-empty string array")
        if tags != sorted(set(tags)):
            raise RegistryError(f"{cid}: tags must be sorted and unique")
        if status == "FALSIFIED" and claim.get("do_not_repeat_without_new_evidence") is not True:
            raise RegistryError(f"{cid}: FALSIFIED claims must set do_not_repeat_without_new_evidence=true")

        evidence = claim.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            raise RegistryError(f"{cid}: evidence must be non-empty")
        verified = []
        for eidx, item in enumerate(evidence):
            if not isinstance(item, dict):
                raise RegistryError(f"{cid}: evidence[{eidx}] must be an object")
            path = canonical_relpath(item.get("path"))
            expected = item.get("git_blob")
            if not isinstance(expected, str) or not BLOB_RE.fullmatch(expected):
                raise RegistryError(f"{cid}: invalid git_blob for {path}")
            anchors = item.get("anchors")
            if not isinstance(anchors, list) or not anchors or any(not isinstance(a, str) or not a for a in anchors):
                raise RegistryError(f"{cid}: evidence anchors must be non-empty strings")
            if anchors != sorted(set(anchors)):
                raise RegistryError(f"{cid}: evidence anchors must be sorted and unique")

            candidate = repo_root.joinpath(*PurePosixPath(path).parts)
            try:
                resolved = candidate.resolve(strict=True)
            except FileNotFoundError as exc:
                raise RegistryError(f"{cid}: evidence file missing: {path}") from exc
            try:
                resolved.relative_to(repo_root)
            except ValueError as exc:
                raise RegistryError(f"{cid}: evidence path resolves outside repo: {path}") from exc
            st = os.lstat(candidate)
            if stat.S_ISLNK(st.st_mode) or not resolved.is_file():
                raise RegistryError(f"{cid}: evidence must be a regular non-symlink file: {path}")
            data = resolved.read_bytes()
            actual = git_blob(data)
            if actual != expected:
                raise RegistryError(f"{cid}: blob drift for {path}: expected={expected} actual={actual}")
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise RegistryError(f"{cid}: evidence is not UTF-8: {path}") from exc
            missing = [anchor for anchor in anchors if anchor not in text]
            if missing:
                raise RegistryError(f"{cid}: missing evidence anchor in {path}: {missing[0]!r}")
            verified.append({"path": path, "git_blob": actual, "anchors": len(anchors)})

        output_claims.append({
            "id": cid,
            "status": status,
            "evidence": verified,
        })

    if ids != sorted(ids):
        raise RegistryError("claims must be sorted by id")

    status_counts = {status: 0 for status in sorted(STATUSES)}
    for row in output_claims:
        status_counts[row["status"]] += 1
    canonical = json.dumps(registry, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return {
        "schema": SCHEMA,
        "valid": True,
        "claim_count": len(output_claims),
        "status_counts": status_counts,
        "registry_sha256": hashlib.sha256(canonical).hexdigest(),
        "claims": output_claims,
        "authority": "coordination-memory-only-not-policy-or-promotion",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("registry", type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    try:
        result = verify(load_json_bytes(args.registry.read_bytes()), args.repo_root)
    except (OSError, RegistryError) as exc:
        print(json.dumps({"valid": False, "error": str(exc)}, sort_keys=True, separators=(",", ":")), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
