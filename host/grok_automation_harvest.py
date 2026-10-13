#!/usr/bin/env python3
"""Reconcile Grok automation traces without depending on the Grok UI.

The harvester joins two durable evidence layers at one frozen main commit:

* remote-branch classifications produced by ``branch_truth_delta.py``; and
* canonical ``p/*.md`` receipts whose names match explicit prefixes.

It never fetches, checks out, merges, pushes, deletes, or moves a ref.  A
missing automation manifest is UNMEASURED rather than an invented zero.
Receipt filenames are discovery hints only; provenance is classified from
explicit metadata and is never inferred from a ``grok-*`` filename alone.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from branch_truth_delta import collect_remote_branches  # noqa: E402


SCHEMA = "commons.grok-automation-harvest.v1"
COMPLETE = "COMPLETE"
PARTIAL = "PARTIAL"
OBSERVED = "OBSERVED"
UNMEASURED = "UNMEASURED"
ACCOUNTED_STATES = frozenset({"ANCESTRAL", "LANDED", "EQUIVALENT"})
DEFAULT_BRANCH_PREFIXES = ("grok/", "grok-")
DEFAULT_RECEIPT_PREFIXES = ("grok",)
DATE_RE = re.compile(r"(?<!\d)(20\d{6})(?!\d)")
META_RE = re.compile(r"^([A-Za-z][A-Za-z0-9_-]{0,31})\s*:\s*(.*?)\s*$")
META_KEYS = frozenset(
    {
        "from",
        "harness",
        "model",
        "surface",
        "carrier",
        "adapter",
        "source",
        "source_harness",
        "source_surface",
        "id",
        "subject",
    }
)
GROK_ID_RE = re.compile(r"(?:^|[^a-z0-9])(?:grok|supergrok|grok_build)(?:$|[^a-z0-9])", re.I)
OTHER_ID_RE = re.compile(
    r"(?:^|[^a-z0-9])(?:gemini|claude|codex|cursor|chatgpt|kimi|flora)(?:$|[^a-z0-9])",
    re.I,
)
GROK_COM_RE = re.compile(r"(?:^|[^a-z0-9])grok\.com(?:$|[^a-z0-9])", re.I)
TAG_PATTERNS = {
    "pr_lifecycle": re.compile(r"(?:^|[-_/])pr[-_]?\d|pull[-_]?request", re.I),
    "repair": re.compile(r"repair|recovery|reconcile|failed|timeout|fix", re.I),
    "slack_discord": re.compile(r"slack|discord", re.I),
    "ci_watchdog": re.compile(r"workflow|watchdog|ci[-_]|check", re.I),
    "pixel": re.compile(r"pixel", re.I),
    "revenue": re.compile(r"revenue|outreach|gtm", re.I),
    "titan_android": re.compile(r"titan|android", re.I),
    "muhlnickel": re.compile(r"muhl|pfc", re.I),
    "charttrace": re.compile(r"charttrace", re.I),
}


class HarvestError(RuntimeError):
    """The requested evidence could not be measured exactly."""


def _git(repo: Path, *args: str, input_bytes: bytes | None = None) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode:
        detail = result.stderr.decode("utf-8", "replace").strip()
        raise HarvestError(f"git {' '.join(args)} failed ({result.returncode}): {detail}")
    return result.stdout


def _git_text(repo: Path, *args: str) -> str:
    return _git(repo, *args).decode("utf-8", "surrogateescape").strip()


def _sha256_lines(rows: Iterable[str]) -> str:
    payload = "".join(f"{row}\n" for row in sorted(rows)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _select_ledger(payload: Mapping[str, Any], repo: Path) -> Mapping[str, Any]:
    repositories = payload.get("repositories")
    if not isinstance(repositories, list):
        return payload
    if not repositories:
        raise HarvestError("branch-truth envelope has no repositories")
    if len(repositories) == 1:
        row = repositories[0]
        if not isinstance(row, Mapping):
            raise HarvestError("branch-truth repository row is not an object")
        return row
    resolved = str(repo.resolve())
    for row in repositories:
        if isinstance(row, Mapping) and str(row.get("repository") or "") == resolved:
            return row
    raise HarvestError("branch-truth envelope is ambiguous for this repository")


def _matches_prefix(value: str, prefixes: Sequence[str]) -> bool:
    folded = value.casefold()
    return any(folded.startswith(prefix.casefold()) for prefix in prefixes)


def summarize_branches(
    ledger_payload: Mapping[str, Any],
    *,
    repo: Path,
    prefixes: Sequence[str],
) -> dict[str, Any]:
    ledger = _select_ledger(ledger_payload, repo)
    rows = ledger.get("branches")
    if not isinstance(rows, list):
        raise HarvestError("branch-truth ledger has no branches array")
    selected = [
        row
        for row in rows
        if isinstance(row, Mapping) and _matches_prefix(str(row.get("branch") or ""), prefixes)
    ]
    state_counts = Counter(str(row.get("unique_delta_state") or UNMEASURED) for row in selected)
    unmeasured_count = sum(
        1 for row in selected if row.get("comparison_completeness") != COMPLETE
    )
    accounted = sum(state_counts[state] for state in ACCOUNTED_STATES)
    review_rows = []
    for row in selected:
        state = str(row.get("unique_delta_state") or UNMEASURED)
        if state in ACCOUNTED_STATES:
            continue
        changed = row.get("changed_path_blob_map")
        review_rows.append(
            {
                "branch": row.get("branch"),
                "ref": row.get("ref"),
                "head_sha": row.get("head_sha"),
                "merge_base_sha": row.get("merge_base_sha"),
                "ahead": row.get("ahead"),
                "behind": row.get("behind"),
                "state": state,
                "active_pr": row.get("active_pr"),
                "changed_paths": sorted(changed) if isinstance(changed, Mapping) else [],
                "comparison_completeness": row.get("comparison_completeness"),
                "comparison_errors": row.get("comparison_errors") or [],
            }
        )
    refs = [str(row.get("ref") or "") for row in selected]
    return {
        "completeness": COMPLETE if unmeasured_count == 0 else PARTIAL,
        "base_sha": ledger.get("base_sha") or ledger.get("default_head_sha"),
        "prefixes": list(prefixes),
        "count": len(selected),
        "accounted_count": accounted,
        "review_count": len(selected) - accounted,
        "unmeasured_count": unmeasured_count,
        "state_counts": dict(sorted(state_counts.items())),
        "ref_digest": _sha256_lines(refs),
        "review": sorted(review_rows, key=lambda row: str(row["branch"])),
    }


def _tree_receipts(
    repo: Path,
    base_sha: str,
    prefixes: Sequence[str],
) -> list[tuple[str, str]]:
    raw = _git(repo, "ls-tree", "-r", "-z", "--full-tree", base_sha, "--", "p")
    rows: list[tuple[str, str]] = []
    for record in raw.split(b"\0"):
        if not record:
            continue
        metadata, raw_path = record.split(b"\t", 1)
        _mode, kind, blob_sha = metadata.decode("ascii").split()
        path = raw_path.decode("utf-8", "surrogateescape")
        name = PurePosixPath(path).name
        if kind == "blob" and name.casefold().endswith(".md") and _matches_prefix(name, prefixes):
            rows.append((path, blob_sha))
    return sorted(rows)


def _read_blobs(repo: Path, rows: Sequence[tuple[str, str]]) -> list[str]:
    if not rows:
        return []
    request = "".join(f"{blob}\n" for _path, blob in rows).encode("ascii")
    raw = _git(repo, "cat-file", "--batch", input_bytes=request)
    cursor = 0
    texts: list[str] = []
    for path, expected_sha in rows:
        line_end = raw.find(b"\n", cursor)
        if line_end < 0:
            raise HarvestError(f"cat-file batch ended before {path}")
        header = raw[cursor:line_end].decode("ascii", "replace")
        cursor = line_end + 1
        parts = header.split()
        if len(parts) != 3 or parts[0] != expected_sha or parts[1] != "blob":
            raise HarvestError(f"unexpected cat-file header for {path}: {header}")
        size = int(parts[2])
        body = raw[cursor : cursor + size]
        cursor += size
        if raw[cursor : cursor + 1] != b"\n":
            raise HarvestError(f"cat-file batch framing failed for {path}")
        cursor += 1
        texts.append(body.decode("utf-8", "surrogateescape"))
    return texts


def _metadata(text: str) -> dict[str, list[str]]:
    values: dict[str, list[str]] = {}
    started = False
    for index, line in enumerate(text.splitlines()):
        if line.strip() == "---":
            if index == 0 and not started:
                continue
            break
        if not line.strip() and started:
            break
        match = META_RE.match(line)
        if not match:
            continue
        started = True
        key = match.group(1).casefold().replace("-", "_")
        if key not in META_KEYS:
            continue
        value = match.group(2).strip()
        if value:
            values.setdefault(key, []).append(value)
    return values


def classify_provenance(metadata: Mapping[str, Sequence[str]]) -> str:
    identity_values = []
    for key in (
        "from",
        "harness",
        "model",
        "surface",
        "carrier",
        "adapter",
        "source_harness",
        "source_surface",
    ):
        identity_values.extend(str(value) for value in metadata.get(key, ()))
    identity = "\n".join(identity_values)
    has_grok = bool(GROK_ID_RE.search(identity))
    has_grok_com = bool(GROK_COM_RE.search(identity))
    has_other = bool(OTHER_ID_RE.search(identity))
    if has_other and (has_grok or has_grok_com):
        return "MIXED_EXPLICIT"
    if has_other:
        return "EXPLICIT_OTHER_HARNESS"
    if has_grok_com:
        return "EXPLICIT_GROK_COM"
    if has_grok:
        return "EXPLICIT_GROK"
    return "GROK_NAMED_ONLY"


def _receipt_date(path: str) -> str:
    matches = DATE_RE.findall(PurePosixPath(path).stem)
    return matches[-1] if matches else "undated"


def _receipt_tags(path: str, metadata: Mapping[str, Sequence[str]]) -> list[str]:
    subject = " ".join(metadata.get("subject", ()))
    haystack = f"{path}\n{subject}"
    tags = [name for name, pattern in TAG_PATTERNS.items() if pattern.search(haystack)]
    return tags or ["other"]


def summarize_receipts(
    repo: Path,
    *,
    base_sha: str,
    prefixes: Sequence[str],
    recent_limit: int = 25,
) -> dict[str, Any]:
    rows = _tree_receipts(repo, base_sha, prefixes)
    texts = _read_blobs(repo, rows)
    records = []
    for (path, blob_sha), text in zip(rows, texts):
        metadata = _metadata(text)
        records.append(
            {
                "path": path,
                "blob_sha": blob_sha,
                "id": (metadata.get("id") or [PurePosixPath(path).stem])[0],
                "date": _receipt_date(path),
                "provenance": classify_provenance(metadata),
                "tags": _receipt_tags(path, metadata),
                "from": list(metadata.get("from", ())),
                "harness": list(metadata.get("harness", ())),
                "model": list(metadata.get("model", ())),
                "subject": list(metadata.get("subject", ())),
            }
        )
    date_counts = Counter(str(row["date"]) for row in records)
    provenance_counts = Counter(str(row["provenance"]) for row in records)
    tag_counts: Counter[str] = Counter()
    for row in records:
        tag_counts.update(row["tags"])
    recent = sorted(records, key=lambda row: (str(row["date"]), str(row["path"])), reverse=True)
    return {
        "completeness": COMPLETE,
        "base_sha": base_sha,
        "prefixes": list(prefixes),
        "logical_receipt_count": len(records),
        "path_blob_digest": _sha256_lines(f"{path}\t{blob}" for path, blob in rows),
        "date_counts": dict(sorted(date_counts.items())),
        "provenance_counts": dict(sorted(provenance_counts.items())),
        "tag_counts": dict(sorted(tag_counts.items())),
        "recent": recent[: max(0, recent_limit)],
    }


def summarize_automations(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {
            "completeness": UNMEASURED,
            "count": None,
            "trigger_counts": {},
            "source": None,
            "observed_at": None,
            "automations": [],
            "note": "No automation manifest supplied; missing inventory is not zero.",
        }
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping) or not isinstance(payload.get("automations"), list):
        raise HarvestError("automation manifest must be an object with an automations array")
    automations = []
    for index, row in enumerate(payload["automations"]):
        if not isinstance(row, Mapping) or not str(row.get("name") or "").strip():
            raise HarvestError(f"automation manifest row {index} needs a nonempty name")
        automations.append(
            {
                "name": str(row["name"]).strip(),
                "name_completeness": str(row.get("name_completeness") or COMPLETE),
                "trigger_kind": str(row.get("trigger_kind") or UNMEASURED),
                "schedule": row.get("schedule"),
            }
        )
    trigger_counts = Counter(str(row["trigger_kind"]) for row in automations)
    return {
        "completeness": str(payload.get("completeness") or OBSERVED),
        "count": len(automations),
        "trigger_counts": dict(sorted(trigger_counts.items())),
        "source": payload.get("source"),
        "observed_at": payload.get("observed_at"),
        "automations": automations,
        "note": payload.get("note") or "Observed inventory; prompt bodies and run history are not inferred.",
    }


def collect_harvest(
    repo: Path,
    *,
    branch_truth: Mapping[str, Any],
    base_sha: str,
    branch_prefixes: Sequence[str],
    receipt_prefixes: Sequence[str],
    automation_manifest: Path | None = None,
    generated_at: str | None = None,
    recent_limit: int = 25,
) -> dict[str, Any]:
    repo = repo.resolve()
    branches = summarize_branches(branch_truth, repo=repo, prefixes=branch_prefixes)
    branch_base = str(branches.get("base_sha") or "")
    if branch_base and branch_base != base_sha:
        raise HarvestError(
            f"branch-truth base {branch_base} does not match receipt base {base_sha}"
        )
    receipts = summarize_receipts(
        repo,
        base_sha=base_sha,
        prefixes=receipt_prefixes,
        recent_limit=recent_limit,
    )
    automations = summarize_automations(automation_manifest)
    return {
        "schema": SCHEMA,
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "repository": str(repo),
        "base_sha": base_sha,
        "truth_boundary": (
            "Frozen Git refs plus canonical p/*.md blobs. Grok UI state, prompt bodies, "
            "notifications, token accounting, and unrecorded runs remain unmeasured."
        ),
        "branches": branches,
        "receipts": receipts,
        "automations": automations,
        "summary": {
            "automation_count": automations["count"],
            "branch_count": branches["count"],
            "accounted_branch_count": branches["accounted_count"],
            "review_branch_count": branches["review_count"],
            "logical_receipt_count": receipts["logical_receipt_count"],
        },
    }


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--branch-truth", type=Path, help="precomputed branch_truth_delta JSON")
    parser.add_argument("--branch-prefix", action="append", dest="branch_prefixes")
    parser.add_argument("--receipt-prefix", action="append", dest="receipt_prefixes")
    parser.add_argument("--automation-manifest", type=Path)
    parser.add_argument("--recent-limit", type=int, default=25)
    parser.add_argument("--generated-at", help="fixed timestamp for reproducible output")
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    repo = args.repo.resolve()
    base_sha = _git_text(repo, "rev-parse", "--verify", f"{args.base}^{{commit}}")
    if args.branch_truth:
        branch_truth = json.loads(args.branch_truth.read_text(encoding="utf-8"))
    else:
        branch_truth = collect_remote_branches(repo, remote=args.remote, base=args.base)
    payload = collect_harvest(
        repo,
        branch_truth=branch_truth,
        base_sha=base_sha,
        branch_prefixes=tuple(args.branch_prefixes or DEFAULT_BRANCH_PREFIXES),
        receipt_prefixes=tuple(args.receipt_prefixes or DEFAULT_RECEIPT_PREFIXES),
        automation_manifest=args.automation_manifest,
        generated_at=args.generated_at,
        recent_limit=args.recent_limit,
    )
    if args.output:
        _write_json(args.output, payload)
    else:
        sys.stdout.write(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
