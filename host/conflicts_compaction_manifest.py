#!/usr/bin/env python3
"""Regenerate or validate conflicts_compaction_manifest.json.

This is the existing leftover regen path for DETAIL 29 /
same-id-different-body-conflicts. It hashes current conflicts/*.jsonl
blobs into before_sha256 and records an in-memory first-occurrence
unique-row proposal. It does not compact, delete, rewrite, or merge
any conflict record.

  python3 host/conflicts_compaction_manifest.py validate
  python3 host/conflicts_compaction_manifest.py regenerate --write
  python3 host/conflicts_compaction_manifest.py apply
  python3 host/conflicts_compaction_manifest.py --self-test

Apply is refuse-only. Compaction stays unapproved until a later
explicit apply order against a valid matching manifest.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "conflicts_compaction_manifest.json"
DEFAULT_CONFLICTS = ROOT / "conflicts"
ORDER_ID = "inquisitor-record-integrity-dedupe-guard-order-20260818-016"
HOLD_ID = "inquisitor-conflict-manifest-invalid-hold-20260818-027"
REGEN_ID = "same-id-different-body-conflicts-20260830-01"
POLICY = (
    "exact duplicate full rows removed; first-occurrence order preserved; "
    "every distinct ts/event/hash kept"
)


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def unique_rows(raw: bytes) -> dict:
    """First-occurrence exact nonempty lines. In-memory only."""
    lines = [line for line in raw.decode("utf-8").splitlines() if line.strip()]
    seen = set()
    kept = []
    for line in lines:
        if line in seen:
            continue
        seen.add(line)
        kept.append(line)
    after = ("\n".join(kept) + "\n").encode("utf-8") if kept else b""
    return {
        "lines": len(lines),
        "unique": len(kept),
        "after_bytes": after,
    }


def measure_file(path: Path) -> dict:
    raw = path.read_bytes()
    rows = unique_rows(raw)
    return {
        "file": path.name,
        "before_sha256": hashlib.sha256(raw).hexdigest(),
        "before_bytes": len(raw),
        "lines": rows["lines"],
        "unique": rows["unique"],
        "after_sha256": hashlib.sha256(rows["after_bytes"]).hexdigest(),
        "after_bytes": len(rows["after_bytes"]),
    }


def list_conflict_files(conflicts_dir: Path) -> list[str]:
    return sorted(path.name for path in conflicts_dir.glob("*.jsonl"))


def load_manifest(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("manifest is not an object")
    return data


def git_rev_parse(rev: str, cwd: Path) -> str:
    proc = subprocess.run(
        ["git", "rev-parse", rev],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return ""
    return proc.stdout.strip()


def validate_manifest(manifest: dict, conflicts_dir: Path) -> dict:
    """Compare every named before_sha256 to the current blob."""
    mismatches = []
    missing = []
    matched = 0
    for entry in manifest.get("files") or []:
        name = str(entry.get("file") or "")
        claimed = str(entry.get("before_sha256") or "").strip().lower()
        path = conflicts_dir / name
        if not name or not path.is_file():
            missing.append(name or "<empty>")
            continue
        actual = file_sha256(path)
        if actual != claimed:
            mismatches.append(
                {
                    "file": name,
                    "claimed": claimed,
                    "actual": actual,
                }
            )
        else:
            matched += 1
    invalid_flag = bool(manifest.get("invalid"))
    applied = bool(manifest.get("applied"))
    named = len(manifest.get("files") or [])
    ok = not mismatches and not missing and named > 0
    return {
        "ok": ok,
        "named": named,
        "matched": matched,
        "stale": len(mismatches),
        "missing": missing,
        "mismatches": mismatches,
        "invalid_flag": invalid_flag,
        "applied": applied,
        "hash_match": ok,
    }


def can_apply(manifest: dict, conflicts_dir: Path) -> dict:
    """Apply is allowed only when hashes match and the hold is lifted.

    This leftover keeps compaction unapproved. A valid matching
    manifest is still not an apply order.
    """
    check = validate_manifest(manifest, conflicts_dir)
    reasons = []
    if check["invalid_flag"]:
        reasons.append("manifest.invalid is true")
    if check["applied"]:
        reasons.append("manifest.applied is already true")
    if check["missing"]:
        reasons.append("named conflict file missing: %s" % ",".join(check["missing"][:8]))
    if check["stale"]:
        reasons.append("%d/%d before_sha256 stale" % (check["stale"], check["named"]))
    if str(manifest.get("compaction_status") or "UNAPPROVED") != "APPROVED":
        reasons.append("compaction_status is UNAPPROVED")
    return {
        "allowed": False if reasons else True,
        "reasons": reasons,
        "validate": check,
    }


def apply_compaction(manifest: dict, conflicts_dir: Path) -> dict:
    """Refuse-only. Never writes a conflict jsonl body."""
    decision = can_apply(manifest, conflicts_dir)
    decision["wrote"] = []
    decision["refused"] = True
    if decision["validate"]["invalid_flag"] or not decision["validate"]["hash_match"]:
        decision["status"] = "REFUSED_INVALID"
    else:
        decision["status"] = "REFUSED_UNAPPROVED"
    return decision


def regenerate_manifest(
    conflicts_dir: Path,
    source_head: str = "",
    source_tree: str = "",
    prepared_ts: str = "",
) -> dict:
    names = list_conflict_files(conflicts_dir)
    files = [measure_file(conflicts_dir / name) for name in names]
    rows = sum(item["lines"] for item in files)
    unique_row_count = sum(item["unique"] for item in files)
    before_bytes = sum(item["before_bytes"] for item in files)
    after_bytes = sum(item["after_bytes"] for item in files)
    duplicate_rows = rows - unique_row_count
    redundancy_pct = round((100.0 * duplicate_rows / rows), 2) if rows else 0.0
    ts = prepared_ts or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "invalid": False,
        "applied": False,
        "compaction_status": "UNAPPROVED",
        "prepared_ts": ts,
        "order": ORDER_ID,
        "hold": HOLD_ID,
        "regenerated_by": REGEN_ID,
        "source_head": source_head,
        "source_conflicts_tree": source_tree,
        "coverage": "all conflicts/*.jsonl at source_head",
        "policy": POLICY,
        "files": files,
        "aggregate": {
            "files": len(files),
            "before_bytes": before_bytes,
            "after_bytes": after_bytes,
            "rows": rows,
            "unique_rows": unique_row_count,
            "duplicate_rows": duplicate_rows,
            "bytes_removed": before_bytes - after_bytes,
            "redundancy_pct": redundancy_pct,
        },
    }


def dump_manifest(manifest: dict) -> str:
    return json.dumps(manifest, indent=1, ensure_ascii=True) + "\n"


def write_manifest(path: Path, manifest: dict) -> None:
    path.write_text(dump_manifest(manifest), encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Regenerate or validate the conflicts compaction manifest"
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="validate",
        choices=("validate", "regenerate", "apply"),
    )
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--conflicts", default=str(DEFAULT_CONFLICTS))
    parser.add_argument("--write", action="store_true", help="write regenerated manifest")
    parser.add_argument("--source-head", default="")
    parser.add_argument("--source-tree", default="")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        return 0 if _self_test() else 1

    manifest_path = Path(args.manifest)
    conflicts_dir = Path(args.conflicts)
    if args.command == "regenerate":
        source_head = args.source_head or git_rev_parse("HEAD", ROOT)
        source_tree = args.source_tree or git_rev_parse("HEAD:conflicts", ROOT)
        manifest = regenerate_manifest(conflicts_dir, source_head, source_tree)
        check = validate_manifest(manifest, conflicts_dir)
        if not check["ok"]:
            json.dump({"status": "REGEN_INVALID", "validate": check}, sys.stdout, indent=2)
            sys.stdout.write("\n")
            return 2
        if args.write:
            write_manifest(manifest_path, manifest)
        payload = {
            "status": "REGENERATED",
            "wrote": bool(args.write),
            "path": str(manifest_path),
            "validate": {k: check[k] for k in ("ok", "named", "matched", "stale", "missing", "invalid_flag", "applied", "hash_match")},
            "aggregate": manifest["aggregate"],
            "source_head": source_head,
            "source_conflicts_tree": source_tree,
            "applied": False,
        }
        json.dump(payload, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    manifest = load_manifest(manifest_path)
    if args.command == "apply":
        decision = apply_compaction(manifest, conflicts_dir)
        json.dump(
            {
                "status": decision["status"],
                "refused": True,
                "wrote": [],
                "reasons": decision["reasons"],
                "validate": {
                    k: decision["validate"][k]
                    for k in ("ok", "named", "matched", "stale", "invalid_flag", "hash_match")
                },
            },
            sys.stdout,
            indent=2,
        )
        sys.stdout.write("\n")
        return 3

    check = validate_manifest(manifest, conflicts_dir)
    json.dump(
        {
            "status": "VALID" if check["ok"] and not check["invalid_flag"] else "INVALID",
            "validate": {
                k: check[k]
                for k in (
                    "ok",
                    "named",
                    "matched",
                    "stale",
                    "missing",
                    "invalid_flag",
                    "applied",
                    "hash_match",
                )
            },
        },
        sys.stdout,
        indent=2,
    )
    sys.stdout.write("\n")
    return 0 if check["ok"] and not check["invalid_flag"] else 2


def _self_test() -> bool:
    raw = b'{"a":1}\n{"a":1}\n{"b":2}\n'
    rows = unique_rows(raw)
    assert rows["lines"] == 3
    assert rows["unique"] == 2
    assert rows["after_bytes"] == b'{"a":1}\n{"b":2}\n'
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        conflicts = root / "conflicts"
        conflicts.mkdir()
        name = "sample.jsonl"
        (conflicts / name).write_bytes(raw)
        manifest = regenerate_manifest(conflicts, "head", "tree", "2026-08-30T00:00:00Z")
        assert manifest["invalid"] is False
        assert manifest["applied"] is False
        assert manifest["files"][0]["before_sha256"] == hashlib.sha256(raw).hexdigest()
        assert validate_manifest(manifest, conflicts)["ok"] is True
        stale = json.loads(json.dumps(manifest))
        stale["files"][0]["before_sha256"] = "0" * 64
        stale["invalid"] = True
        decision = apply_compaction(stale, conflicts)
        assert decision["status"] == "REFUSED_INVALID"
        assert decision["wrote"] == []
        assert (conflicts / name).read_bytes() == raw
        valid_refuse = apply_compaction(manifest, conflicts)
        assert valid_refuse["status"] == "REFUSED_UNAPPROVED"
        assert (conflicts / name).read_bytes() == raw
    return True


if __name__ == "__main__":
    sys.exit(main())
