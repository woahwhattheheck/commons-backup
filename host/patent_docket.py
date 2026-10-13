#!/usr/bin/env python3
"""Validate and summarize the public, source-pinned Commons patent docket."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
DOCKET_PATH = Path("revenue/ip/patent_docket.json")
SCHEMA_PATH = Path("revenue/ip/patent_docket.schema.json")
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
PRIVATE_KEYS = {
    "application_number",
    "filing_receipt",
    "legal_correspondence",
    "attorney_notes",
}
LEGAL_SCOPE_KEYS = {
    "patentability_claimed",
    "validity_claimed",
    "ownership_adjudicated",
    "filing_receipt_verified",
    "application_numbers_public",
}
PROVENANCE_SUCCESSORS = {
    "ground/INVENTION_BURST_INDEX.md": (
        (
            "spy-ground-live-cash-v1",
            (
                "\n## Live cash\n\n"
                "Verified product pages only — no invented Stripe links.\n\n"
                "- [$29 Autopsy checkout](../agent-rescue.html) — one failed coding-agent run\n"
                "- [$199 dealer diagnostic](../dealer-service-lead-rescue.html)\n"
                "- [$199 referral diagnostic](../referral-intake-completeness.html)\n"
                "- [$199 repair diagnostic](../repair-booking-preflight.html)\n"
                "- [$199 plant diagnostic](../plant-downtime-handoff.html)\n\n"
                "Shelf: [tools-cash.html](../tools-cash.html). Catalog: "
                "[commerce.html](../commerce.html). Cite "
                "spy-ground-batch-live-cash-20260905-18 — do not remint.\n"
            ).encode("utf-8"),
        ),
        (
            "grok-patent-docket-md-keep-larger-fixed-20260916-01",
            (
                "\n"
                "Larger fixed engagements (separate product pages; checkout/intent stays there): "
                "[GGUF diagnostic · $12,000 / 10 days](../diagnostic.html) · "
                "[White Box pilot · $30,000 / 30 days](../commercial.html). "
                "Not remints of tip SKUs.\n"
            ).encode("utf-8"),
        ),
        (
            "anvil-invention-burst-autopsy-retirement-20260918-01",
            (
                "\n## Live cash\n\n"
                "Verified product pages only — no invented Stripe links.\n\n"
                "- [$199 dealer diagnostic](../dealer-service-lead-rescue.html)\n"
                "- [$199 referral diagnostic](../referral-intake-completeness.html)\n"
                "- [$199 repair diagnostic](../repair-booking-preflight.html)\n"
                "- [$199 plant diagnostic](../plant-downtime-handoff.html)\n\n"
                "Shelf: [tools-cash.html](../tools-cash.html). Catalog: "
                "[commerce.html](../commerce.html). Cite "
                "spy-ground-batch-live-cash-20260905-18 — do not remint.\n"
            ).encode("utf-8"),
        ),
    ),
    "GRANTS.md": (
        (
            "bass-grants-live-cash-v2",
            (
                "\n## Live cash\n\n"
                "Verified product pages only — no invented Stripe links.\n\n"
                "- [$29 Autopsy checkout](./agent-rescue.html)\n"
                "- [$199 dealer diagnostic](./dealer-service-lead-rescue.html)\n"
                "- [$199 referral diagnostic](./referral-intake-completeness.html)\n"
                "- [$199 repair diagnostic](./repair-booking-preflight.html)\n"
                "- [$199 plant diagnostic](./plant-downtime-handoff.html)\n\n"
                "Shelf: [tools-cash.html](./tools-cash.html) · "
                "[commerce.html](./commerce.html).\n\n"
            ).encode("utf-8"),
        ),
        (
            "grok-grants-md-keep-larger-fixed-20260916-01",
            (
                "Larger fixed engagements (separate product pages; checkout/intent stays there): "
                "[GGUF diagnostic · $12,000 / 10 days](./diagnostic.html) · "
                "[White Box pilot · $30,000 / 30 days](./commercial.html). "
                "Not remints of tip SKUs.\n"
            ).encode("utf-8"),
        ),
        (
            "anvil-grants-autopsy-retirement-20260918-01",
            (
                "\n## Live cash\n\n"
                "Verified product pages only — no invented Stripe links.\n\n"
                "- [$199 dealer diagnostic](./dealer-service-lead-rescue.html)\n"
                "- [$199 referral diagnostic](./referral-intake-completeness.html)\n"
                "- [$199 repair diagnostic](./repair-booking-preflight.html)\n"
                "- [$199 plant diagnostic](./plant-downtime-handoff.html)\n\n"
                "Shelf: [tools-cash.html](./tools-cash.html) · "
                "[commerce.html](./commerce.html).\n\n"
            ).encode("utf-8"),
        ),
    ),
}


class DocketError(ValueError):
    """The docket does not match its public evidence contract."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise DocketError(message)


def _exact_keys(value: dict, required: set[str], at: str) -> None:
    _require(isinstance(value, dict), "%s must be an object" % at)
    missing = sorted(required - set(value))
    extra = sorted(set(value) - required)
    _require(not missing, "%s missing keys %r" % (at, missing))
    _require(not extra, "%s has extra keys %r" % (at, extra))


def _safe_path(value: str, at: str) -> str:
    _require(isinstance(value, str) and value, "%s path is empty" % at)
    _require("\\" not in value, "%s path must use POSIX separators" % at)
    parsed = PurePosixPath(value)
    _require(not parsed.is_absolute(), "%s path must be relative" % at)
    _require(".." not in parsed.parts, "%s path escapes root" % at)
    _require(str(parsed) == value, "%s path is not canonical" % at)
    return value


def _git(root: Path, *args: str, binary: bool = False):
    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode:
        detail = completed.stderr.decode("utf-8", "replace").strip()
        raise DocketError("git %s failed: %s" % (" ".join(args), detail))
    return completed.stdout if binary else completed.stdout.decode("utf-8").strip()


def _blob_bytes(root: Path, oid: str) -> bytes:
    _require(isinstance(oid, str) and bool(HEX40.fullmatch(oid)), "invalid blob sha %r" % oid)
    return _git(root, "cat-file", "blob", oid, binary=True)


def _current_blob(root: Path, path: str) -> str:
    return _git(root, "rev-parse", "HEAD:%s" % path)


def _git_blob_oid(data: bytes) -> str:
    header = b"blob " + str(len(data)).encode("ascii") + b"\0"
    return hashlib.sha1(header + data).hexdigest()


def _normalize_provenance_successors(path: str, data: bytes) -> tuple[bytes, list[str]]:
    data = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    applied: list[str] = []
    for label, successor in PROVENANCE_SUCCESSORS.get(path, ()):
        count = data.count(successor)
        _require(count <= 1, "%s successor %s is ambiguous" % (path, label))
        if count == 1:
            data = data.replace(successor, b"", 1)
            applied.append(label)
    return data, applied


def _earliest_add_record(root: Path, path: str) -> tuple[str, str, str]:
    # Follow renames newest-to-oldest before selecting the oldest addition.
    # Combining --follow with --reverse can lose the pre-rename creation record.
    # NUL framing keeps historical names containing tabs/newlines byte-exact.
    raw = _git(
        root,
        "log",
        "--follow",
        "--diff-filter=A",
        "--format=%H|%cI",
        "--name-only",
        "-z",
        "HEAD",
        "--",
        path,
        binary=True,
    )
    fields = raw.split(b"\0")
    if fields and fields[-1] == b"":
        fields.pop()
    _require(bool(fields) and len(fields) % 2 == 0, "no add commit for %s" % path)
    header, name = fields[-2:]
    _require(b"|" in header and name.startswith(b"\n"), "invalid add record for %s" % path)
    commit, timestamp = header.decode("utf-8").split("|", 1)
    original_path = name[1:].decode("utf-8")
    _require(bool(HEX40.fullmatch(commit)) and bool(original_path), "invalid add record for %s" % path)
    return commit, timestamp, original_path


def _earliest_add(root: Path, path: str) -> tuple[str, str]:
    commit, timestamp, _ = _earliest_add_record(root, path)
    return commit, timestamp


def _is_shallow(root: Path) -> bool:
    return _git(root, "rev-parse", "--is-shallow-repository") == "true"


def _validate_pinned_add(root: Path, commit: str, path: str, at: str) -> str:
    try:
        status = _git(
            root,
            "diff-tree",
            "--root",
            "--no-commit-id",
            "--name-status",
            "-r",
            commit,
            "--",
            path,
        )
        timestamp = _git(root, "show", "-s", "--format=%cI", commit)
        _git(root, "cat-file", "-e", "%s:%s" % (commit, path))
    except DocketError:
        raise DocketError("%s earliest commit drift" % at) from None
    _require(status == "A\t%s" % path, "%s earliest commit drift" % at)
    return timestamp


def _walk_private_keys(value, at: str = "$.") -> None:
    if isinstance(value, dict):
        found = sorted(PRIVATE_KEYS.intersection(value))
        _require(not found, "%s publishes private keys %r" % (at, found))
        for key, child in value.items():
            _walk_private_keys(child, "%s%s." % (at, key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _walk_private_keys(child, "%s[%d]." % (at, index))


def _validate_source(root: Path, source: dict, at: str) -> bytes:
    required = {"path", "blob_sha", "sha256", "byte_count", "public_url"}
    _exact_keys(source, required, at)
    path = _safe_path(source["path"], at)
    _require(isinstance(source["blob_sha"], str) and bool(HEX40.fullmatch(source["blob_sha"])), "%s blob_sha invalid" % at)
    _require(isinstance(source["sha256"], str) and bool(HEX64.fullmatch(source["sha256"])), "%s sha256 invalid" % at)
    _require(type(source["byte_count"]) is int and source["byte_count"] > 0, "%s byte_count invalid" % at)
    expected_url = "https://github.com/woahwhattheheck/commons/blob/main/%s" % path
    _require(source["public_url"] == expected_url, "%s public_url mismatch" % at)
    actual_oid = _current_blob(root, path)
    _require(actual_oid == source["blob_sha"], "%s source blob drift: %s" % (at, actual_oid))
    raw = _blob_bytes(root, actual_oid)
    _require(len(raw) == source["byte_count"], "%s byte_count drift" % at)
    _require(hashlib.sha256(raw).hexdigest() == source["sha256"], "%s sha256 drift" % at)
    return raw


def _validate_provenance(root: Path, value: dict, at: str, phrase: str) -> None:
    required = {
        "path", "blob_sha", "sha256", "byte_count", "public_url",
        "evidence_key", "statement",
    }
    _exact_keys(value, required, at)
    source = {key: value[key] for key in (
        "path", "blob_sha", "sha256", "byte_count", "public_url"
    )}
    path = _safe_path(source["path"], at)
    _require(isinstance(source["blob_sha"], str) and bool(HEX40.fullmatch(source["blob_sha"])), "%s blob_sha invalid" % at)
    _require(isinstance(source["sha256"], str) and bool(HEX64.fullmatch(source["sha256"])), "%s sha256 invalid" % at)
    _require(type(source["byte_count"]) is int and source["byte_count"] > 0, "%s byte_count invalid" % at)
    expected_url = "https://github.com/woahwhattheheck/commons/blob/main/%s" % path
    _require(source["public_url"] == expected_url, "%s public_url mismatch" % at)
    actual_oid = _current_blob(root, path)
    current_raw = _blob_bytes(root, actual_oid)
    baseline_raw, _ = _normalize_provenance_successors(path, current_raw)
    _require(
        _git_blob_oid(baseline_raw) == source["blob_sha"],
        "%s source blob drift: %s" % (at, actual_oid),
    )
    _require(len(baseline_raw) == source["byte_count"], "%s byte_count drift" % at)
    _require(
        hashlib.sha256(baseline_raw).hexdigest() == source["sha256"],
        "%s sha256 drift" % at,
    )
    _require(isinstance(value["evidence_key"], str) and value["evidence_key"], "%s evidence_key empty" % at)
    _require(isinstance(value["statement"], str) and value["statement"], "%s statement empty" % at)
    _require(phrase.lower() in current_raw.decode("utf-8").lower(), "%s evidence phrase missing" % at)


def _validate_receipt(root: Path, receipt: dict, source_path: str, at: str) -> None:
    required = {"path", "commit_sha", "disclosed_at", "public_url"}
    _exact_keys(receipt, required, at)
    path = _safe_path(receipt["path"], at)
    _require(isinstance(receipt["commit_sha"], str) and bool(HEX40.fullmatch(receipt["commit_sha"])), "%s commit_sha invalid" % at)
    earliest_commit, earliest_at = _earliest_add(root, source_path)
    if path != source_path:
        # A historical receipt keeps the path that existed at creation, but it
        # must be linked to this exact current source by Git's rename history.
        # Compare the whole record as well, so moving HEAD cannot mix queries.
        origin_commit, origin_at, origin_path = _earliest_add_record(root, source_path)
        _require(
            (origin_commit, origin_at, origin_path) == (earliest_commit, earliest_at, path),
            "%s path must equal source path at its earliest add" % at,
        )
    if receipt["commit_sha"] != earliest_commit:
        # A shallow boundary makes every path present at that boundary look newly
        # added to `git log --diff-filter=A`. In that environment, validate the
        # pinned public receipt itself as an add commit instead of accepting the
        # synthetic boundary. Full-history checkouts retain the stronger exact-
        # earliest comparison above.
        _require(_is_shallow(root), "%s earliest commit drift" % at)
        earliest_commit = receipt["commit_sha"]
        earliest_at = _validate_pinned_add(root, earliest_commit, path, at)
    _require(receipt["disclosed_at"] == earliest_at, "%s disclosure timestamp drift" % at)
    expected_url = "https://github.com/woahwhattheheck/commons/blob/%s/%s" % (
        earliest_commit,
        path,
    )
    _require(receipt["public_url"] == expected_url, "%s public_url mismatch" % at)
    _git(root, "cat-file", "-e", "%s:%s" % (earliest_commit, path))


def load(root: Path = ROOT) -> tuple[dict, dict]:
    docket = json.loads((root / DOCKET_PATH).read_text(encoding="utf-8"))
    schema = json.loads((root / SCHEMA_PATH).read_text(encoding="utf-8"))
    return docket, schema


def validate(root: Path, docket: dict, schema: dict) -> dict:
    _require(isinstance(schema, dict), "schema must be an object")
    _require(schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema", "schema draft mismatch")
    _require(isinstance(schema.get("$id"), str) and schema["$id"].endswith("/revenue/ip/patent_docket.schema.json"), "schema id mismatch")
    _require(schema.get("type") == "object" and schema.get("additionalProperties") is False, "schema root must be closed")
    top_keys = {
        "schema_version", "kind", "generated_at", "generated_from_main", "scope",
        "legal_scope", "omitted_private_fields", "inventor_provenance",
        "status_provenance", "entries",
    }
    _exact_keys(docket, top_keys, "docket")
    _require(docket["schema_version"] == "commons-patent-docket/v1", "schema_version mismatch")
    _require(docket["kind"] == "PATENT_DOCKET", "kind mismatch")
    _require(isinstance(docket["generated_from_main"], str) and bool(HEX40.fullmatch(docket["generated_from_main"])), "generated_from_main invalid")
    _require(isinstance(docket["generated_at"], str) and "T" in docket["generated_at"], "generated_at invalid")
    _require(isinstance(docket["scope"], str) and docket["scope"], "scope empty")
    _exact_keys(docket["legal_scope"], LEGAL_SCOPE_KEYS, "legal_scope")
    _require(all(isinstance(value, bool) for value in docket["legal_scope"].values()), "legal_scope values must be booleans")
    _require(not any(docket["legal_scope"].values()), "legal_scope may not claim legal conclusions")
    omitted = docket["omitted_private_fields"]
    _require(isinstance(omitted, list) and all(isinstance(value, str) for value in omitted) and len(omitted) == len(set(omitted)), "omitted_private_fields invalid")
    _require(PRIVATE_KEYS.issubset(set(omitted)), "omitted_private_fields incomplete")
    _walk_private_keys(docket)
    _validate_provenance(root, docket["inventor_provenance"], "inventor_provenance", "Inventor: Bryce Muhlnickel")
    _validate_provenance(root, docket["status_provenance"], "status_provenance", "provisionals are filed")

    entries = docket["entries"]
    _require(isinstance(entries, list) and entries, "entries must be nonempty")
    ids = []
    statuses = {}
    for index, entry in enumerate(entries):
        at = "entries[%d]" % index
        required = {
            "id", "title", "invention_summary", "inventors", "jurisdiction",
            "filing_type", "filing_status", "source", "earliest_public_receipt",
            "counsel_questions",
        }
        _exact_keys(entry, required, at)
        _require(isinstance(entry["id"], str) and re.fullmatch(r"[a-z0-9][a-z0-9-]{7,79}", entry["id"]) is not None, "%s id invalid" % at)
        ids.append(entry["id"])
        _require(isinstance(entry["title"], str) and entry["title"], "%s title empty" % at)
        _require(isinstance(entry["invention_summary"], str) and entry["invention_summary"], "%s summary empty" % at)
        _require(entry["inventors"] == ["Bryce Muhlnickel"], "%s inventor provenance mismatch" % at)
        _require(entry["jurisdiction"] == "US", "%s jurisdiction mismatch" % at)
        _require(entry["filing_type"] == "PROVISIONAL", "%s filing_type mismatch" % at)
        _require(isinstance(entry["filing_status"], str) and entry["filing_status"] in {"DRAFT_READY_TO_FILE", "OWNER_REPORTED_FILED", "UNKNOWN"}, "%s filing_status invalid" % at)
        _require(entry["filing_status"] != "DRAFT_READY_TO_FILE", "%s contradicts current owner-reported filing status" % at)
        questions = entry["counsel_questions"]
        _require(isinstance(questions, list) and questions and all(isinstance(q, str) and q for q in questions), "%s counsel_questions invalid" % at)
        _validate_source(root, entry["source"], "%s.source" % at)
        _validate_receipt(root, entry["earliest_public_receipt"], entry["source"]["path"], "%s.earliest_public_receipt" % at)
        statuses[entry["filing_status"]] = statuses.get(entry["filing_status"], 0) + 1
    _require(len(ids) == len(set(ids)), "duplicate entry ids")
    return {
        "status": "VALID",
        "entries": len(entries),
        "filing_statuses": dict(sorted(statuses.items())),
        "jurisdictions": sorted({entry["jurisdiction"] for entry in entries}),
        "patentability_claimed": docket["legal_scope"]["patentability_claimed"],
        "private_application_numbers": 0,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs="?", choices=("validate", "summary"), default="validate")
    parser.add_argument("--root", default=str(ROOT), help="Commons repository root")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    try:
        docket, schema = load(root)
        result = validate(root, docket, schema)
    except (DocketError, OSError, ValueError, json.JSONDecodeError) as exc:
        print("PATENT DOCKET INVALID: %s" % exc, file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
