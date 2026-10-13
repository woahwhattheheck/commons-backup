#!/usr/bin/env python3
"""Offline manual-entry prompt-efficiency workbench for CrowdStrike Agents of Chaos.

This carrier never talks to the live contest. Token counts are operator-entered
observations only. Compliance output is SELF_ATTESTED_ONLY.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

SCHEMA = "crowdstrike-aoc-manual-ledger-v1"
COMPLIANCE_KIND = "SELF_ATTESTED_ONLY"
MAX_ATTEMPTS = 10_000
MAX_ID_BYTES = 128
MAX_PROMPT_BYTES = 20_000
MAX_NOTES_BYTES = 20_000
MAX_ACTIONS = 64
MAX_ACTION_BYTES = 128
REQUIRED_ATTEMPT_KEYS = (
    "attempt_id",
    "puzzle_id",
    "prompt_text",
    "observed_token_count",
    "outcome",
    "entry_mode",
    "declared_actions",
)
ALLOWED_ATTEMPT_KEYS = frozenset((*REQUIRED_ATTEMPT_KEYS, "notes"))
PROHIBITED_ACTIONS = frozenset(
    {
        "bot_live_interaction",
        "automated_live_interaction",
        "platform_attack",
        "backend_attack",
        "scoring_attack",
        "network_interception",
        "multi_accounting",
        "other_player_access",
    }
)
PROHIBITED_TEXT = (
    r"\bbot\b.*live|\bautomat(?:ed|ion)\b.*live|"
    r"backend.?attack|scoring.?attack|platform.?attack|"
    r"network.?intercept|multi.?account|other.?player"
)
PROHIBITED_RE = re.compile(PROHIBITED_TEXT, re.IGNORECASE)


class LedgerError(ValueError):
    pass


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    seen: set[str] = set()
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in seen:
            raise LedgerError(f"duplicate json key: {key}")
        seen.add(key)
        out[key] = value
    return out


def _reject_nonfinite(value: str) -> None:
    raise LedgerError(f"non-finite JSON constant is forbidden: {value}")


def load_strict_json(text: str) -> Any:
    if not isinstance(text, str):
        raise LedgerError("JSON input must be text")
    try:
        return json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonfinite,
        )
    except LedgerError:
        raise
    except json.JSONDecodeError as exc:
        raise LedgerError(f"invalid JSON: {exc.msg}") from exc


def load_strict_json_path(path: Path) -> Any:
    try:
        return load_strict_json(path.read_text(encoding="utf-8"))
    except LedgerError:
        raise
    except (OSError, UnicodeError) as exc:
        raise LedgerError(f"cannot read ledger: {exc}") from exc


def _norm_prompt(text: str) -> str:
    return " ".join(text.split())


def _prompt_digest(text: str) -> str:
    return hashlib.sha256(_norm_prompt(text).encode("utf-8")).hexdigest()


def _require_keys(obj: dict[str, Any], keys: tuple[str, ...], where: str) -> None:
    missing = [k for k in keys if k not in obj]
    if missing:
        raise LedgerError(f"{where} missing keys: {missing}")


def _require_string(
    raw: Any,
    field: str,
    *,
    max_bytes: int,
    allow_empty: bool = False,
    strip: bool = False,
) -> str:
    if not isinstance(raw, str):
        raise LedgerError(f"{field} must be a JSON string")
    value = raw.strip() if strip else raw
    if not allow_empty and not value:
        raise LedgerError(f"{field} must be non-empty")
    if len(value.encode("utf-8")) > max_bytes:
        raise LedgerError(f"{field} exceeds {max_bytes} UTF-8 bytes")
    return value


def _parse_token_count(raw: Any) -> int:
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise LedgerError(f"observed_token_count must be a JSON integer, got {type(raw).__name__}")
    if raw < 0:
        raise LedgerError("observed_token_count must be >= 0")
    return raw


def _parse_declared_actions(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        raise LedgerError("declared_actions must be a list")
    if len(raw) > MAX_ACTIONS:
        raise LedgerError(f"declared_actions exceeds {MAX_ACTIONS} entries")
    actions: list[str] = []
    for index, action in enumerate(raw):
        actions.append(
            _require_string(
                action,
                f"declared_actions[{index}]",
                max_bytes=MAX_ACTION_BYTES,
            )
        )
    return actions


def _scan_prohibited(prompt: str, notes: str, entry_mode: str, declared: list[str]) -> list[str]:
    hits = [action for action in declared if action in PROHIBITED_ACTIONS]
    blob = " ".join([prompt, notes, entry_mode, " ".join(declared)])
    if PROHIBITED_RE.search(blob):
        hits.append("prohibited_text_pattern")
    return sorted(set(hits))


def validate_attempt(attempt: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(attempt, dict):
        raise LedgerError("attempt must be an object")
    _require_keys(attempt, REQUIRED_ATTEMPT_KEYS, "attempt")
    unknown = sorted(set(attempt) - ALLOWED_ATTEMPT_KEYS)
    if unknown:
        raise LedgerError(f"attempt has unsupported keys: {unknown}")

    attempt_id = _require_string(
        attempt["attempt_id"], "attempt_id", max_bytes=MAX_ID_BYTES, strip=True
    )
    puzzle = _require_string(
        attempt["puzzle_id"], "puzzle_id", max_bytes=MAX_ID_BYTES, strip=True
    )
    prompt = _require_string(
        attempt["prompt_text"],
        "prompt_text",
        max_bytes=MAX_PROMPT_BYTES,
        allow_empty=True,
    )
    notes = _require_string(
        attempt.get("notes", ""),
        "notes",
        max_bytes=MAX_NOTES_BYTES,
        allow_empty=True,
    )
    entry_mode = _require_string(
        attempt["entry_mode"], "entry_mode", max_bytes=32
    )
    if entry_mode != "manual":
        raise LedgerError("entry_mode must be 'manual'")
    outcome = _require_string(attempt["outcome"], "outcome", max_bytes=32)
    if outcome not in {"success", "failure", "incomplete"}:
        raise LedgerError("outcome must be success|failure|incomplete")
    tokens = _parse_token_count(attempt["observed_token_count"])
    declared = _parse_declared_actions(attempt["declared_actions"])
    hits = _scan_prohibited(prompt, notes, entry_mode, declared)
    if hits:
        raise LedgerError(f"prohibited action declared or implied: {hits}")

    return {
        "attempt_id": attempt_id,
        "puzzle_id": puzzle,
        "prompt_text": prompt,
        "prompt_digest": _prompt_digest(prompt),
        "observed_token_count": tokens,
        "outcome": outcome,
        "entry_mode": "manual",
        "declared_actions": declared,
        "notes": notes,
    }


def frontier_for_puzzle(attempts: list[dict[str, Any]]) -> dict[str, Any]:
    successes = [a for a in attempts if a["outcome"] == "success"]
    if not successes:
        return {
            "puzzle_id": attempts[0]["puzzle_id"] if attempts else "",
            "best_observed_token_count": None,
            "best_attempt_ids": [],
            "successful_count": 0,
            "duplicate_prompt_groups": [],
        }
    best = min(a["observed_token_count"] for a in successes)
    best_ids = sorted(
        a["attempt_id"] for a in successes if a["observed_token_count"] == best
    )
    by_digest: dict[str, list[str]] = {}
    for a in successes:
        by_digest.setdefault(a["prompt_digest"], []).append(a["attempt_id"])
    dupes = [
        {"prompt_digest": d, "attempt_ids": sorted(ids)}
        for d, ids in sorted(by_digest.items())
        if len(ids) > 1
    ]
    return {
        "puzzle_id": successes[0]["puzzle_id"],
        "best_observed_token_count": best,
        "best_attempt_ids": best_ids,
        "successful_count": len(successes),
        "duplicate_prompt_groups": dupes,
    }


def _normalized_evidence(attempts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    fields = (
        "attempt_id",
        "puzzle_id",
        "prompt_text",
        "prompt_digest",
        "observed_token_count",
        "outcome",
        "entry_mode",
        "declared_actions",
        "notes",
    )
    return [
        {field: attempt[field] for field in fields}
        for attempt in sorted(attempts, key=lambda item: item["attempt_id"])
    ]


def _canonical_sha256(value: Any) -> str:
    canonical = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_receipt(ledger: dict[str, Any], frontiers: list[dict[str, Any]]) -> dict[str, Any]:
    normalized_evidence = _normalized_evidence(ledger.get("attempts", []))
    payload = {
        "schema": SCHEMA,
        "compliance_kind": COMPLIANCE_KIND,
        "eligibility_certificate": False,
        "sponsor_compliance_certificate": False,
        "live_contest_interaction": False,
        "tokenizer": "operator_entered_observation_only",
        "attempt_count": len(normalized_evidence),
        "normalized_ledger_sha256": _canonical_sha256(
            {"schema": SCHEMA, "attempts": normalized_evidence}
        ),
        "frontiers": frontiers,
    }
    payload["receipt_sha256"] = _canonical_sha256(payload)
    return payload


def evaluate_ledger(raw: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise LedgerError("ledger must be an object")
    if set(raw) != {"schema", "attempts"}:
        raise LedgerError("ledger must contain exactly schema and attempts")
    if raw.get("schema") != SCHEMA:
        raise LedgerError(f"unsupported schema: {raw.get('schema')}")
    attempts_raw = raw.get("attempts")
    if not isinstance(attempts_raw, list):
        raise LedgerError("attempts must be a list")
    if len(attempts_raw) > MAX_ATTEMPTS:
        raise LedgerError(f"attempts exceeds {MAX_ATTEMPTS} entries")

    seen_ids: set[str] = set()
    attempts: list[dict[str, Any]] = []
    for item in attempts_raw:
        parsed = validate_attempt(item)
        if parsed["attempt_id"] in seen_ids:
            raise LedgerError(f"duplicate attempt_id: {parsed['attempt_id']}")
        seen_ids.add(parsed["attempt_id"])
        attempts.append(parsed)
    attempts.sort(key=lambda item: item["attempt_id"])

    by_puzzle: dict[str, list[dict[str, Any]]] = {}
    for attempt in attempts:
        by_puzzle.setdefault(attempt["puzzle_id"], []).append(attempt)
    frontiers = [frontier_for_puzzle(group) for _, group in sorted(by_puzzle.items())]
    for front in frontiers:
        best = front["best_observed_token_count"]
        if best is None:
            continue
        for attempt in by_puzzle[front["puzzle_id"]]:
            if attempt["outcome"] == "success":
                attempt["delta_from_best"] = attempt["observed_token_count"] - best
            else:
                attempt["delta_from_best"] = None
    receipt = build_receipt({"attempts": attempts}, frontiers)
    return {
        "attempts": attempts,
        "frontiers": frontiers,
        "receipt": receipt,
        "compliance_kind": COMPLIANCE_KIND,
    }


def render_markdown(result: dict[str, Any]) -> str:
    rec = result["receipt"]
    lines = [
        "# CrowdStrike Agents of Chaos — manual workbench receipt",
        "",
        f"- schema: `{rec['schema']}`",
        f"- compliance: `{rec['compliance_kind']}` (not an eligibility certificate)",
        f"- live contest interaction: `{rec['live_contest_interaction']}`",
        f"- tokenizer: `{rec['tokenizer']}`",
        f"- normalized_ledger_sha256: `{rec['normalized_ledger_sha256']}`",
        f"- receipt_sha256: `{rec['receipt_sha256']}`",
        "",
        "## Frontiers",
        "",
    ]
    if not result["frontiers"]:
        lines.append("_No attempts._")
    for front in result["frontiers"]:
        lines.append(f"### {front['puzzle_id']}")
        lines.append(f"- best observed tokens: `{front['best_observed_token_count']}`")
        lines.append(f"- best attempts: `{', '.join(front['best_attempt_ids']) or 'none'}`")
        lines.append(f"- successful count: `{front['successful_count']}`")
        if front["duplicate_prompt_groups"]:
            lines.append("- duplicate successful prompts:")
            for group in front["duplicate_prompt_groups"]:
                lines.append(
                    f"  - `{group['prompt_digest'][:12]}` → {', '.join(group['attempt_ids'])}"
                )
        lines.append("")
    lines.extend(
        [
            "## Authority ceiling",
            "",
            "No live contest interaction, no bot/automated gameplay, no login/MFA,",
            "no prompt submission by this tool, no backend/scoring probing, no",
            "interception, no multi-accounting, no other-player access, and no",
            "prize/payment/revenue claim.",
            "",
        ]
    )
    return "\n".join(lines)


def publish(result: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json = Path(out_json)
    out_md = Path(out_md)
    if out_json.resolve(strict=False) == out_md.resolve(strict=False):
        raise LedgerError("JSON and Markdown outputs must be different paths")
    if out_json.exists() or out_md.exists():
        raise LedgerError("publication is create-exclusive; refuse overwrite")

    try:
        json_text = json.dumps(
            result,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        ) + "\n"
        markdown_text = render_markdown(result)
    except (TypeError, ValueError) as exc:
        raise LedgerError(f"cannot serialize publication: {exc}") from exc

    try:
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_md.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise LedgerError(f"cannot prepare publication directories: {exc}") from exc

    created: list[Path] = []
    try:
        json_handle = out_json.open("x", encoding="utf-8")
        created.append(out_json)
        with json_handle as handle:
            handle.write(json_text)

        md_handle = out_md.open("x", encoding="utf-8")
        created.append(out_md)
        with md_handle as handle:
            handle.write(markdown_text)
    except OSError as exc:
        for path in reversed(created):
            try:
                path.unlink()
            except OSError:
                pass
        raise LedgerError(f"publication failed without commit: {exc}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline CrowdStrike AOC manual workbench")
    parser.add_argument("ledger", type=Path)
    parser.add_argument("--out-json", type=Path)
    parser.add_argument("--out-md", type=Path)
    args = parser.parse_args(argv)
    try:
        raw = load_strict_json_path(args.ledger)
        result = evaluate_ledger(raw)
        if args.out_json or args.out_md:
            if not (args.out_json and args.out_md):
                raise LedgerError("both --out-json and --out-md are required to publish")
            publish(result, args.out_json, args.out_md)
        else:
            print(json.dumps(result["receipt"], indent=2, sort_keys=True, allow_nan=False))
        return 0
    except LedgerError as exc:
        print(f"LEDGER_ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
