#!/usr/bin/env python3
"""Verify the exact retained snapshot, independent of JSON object-key order.

This deliberately verifies the retained snapshot, not live sponsor currentness.
Re-check primary sources before any theorem TAKE, submission, or reward claim.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

EXPECTED_NUMBERS = [3, 20, 30, 64, 142, 592, 625, 687, 1191]
EXPECTED_REWARDS = {
    3: 5000, 20: 1000, 30: 1000, 64: 1000, 142: 10000,
    592: 1000, 625: 1000, 687: 1000, 1191: 1000,
}
EXPECTED_TOTAL = 22000
SHA40 = re.compile(r"^[0-9a-f]{40}$")
FORMAL_PRESENT = {3, 20, 30, 64, 142, 592}
FORMAL_MISSING = {625, 687, 1191}


class CrosswalkError(ValueError):
    pass


def fail(message: str) -> None:
    raise CrosswalkError(message)


def load_strict(path: Path) -> dict:
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                fail(f"duplicate JSON key: {key!r}")
            out[key] = value
        return out

    def reject_constant(value: str):
        fail(f"non-finite JSON constant: {value}")

    try:
        return json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=pairs,
            parse_constant=reject_constant,
        )
    except CrosswalkError:
        raise
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        fail(f"cannot load strict JSON: {exc}")


def verify(doc: dict) -> str:
    if not isinstance(doc, dict):
        fail("root must be an object")
    if doc.get("schema_version") != 1:
        fail("schema_version must be 1")
    if doc.get("snapshot_date") != "2026-09-18":
        fail("unexpected snapshot_date")

    scope = doc.get("scope")
    if not isinstance(scope, dict):
        fail("scope must be an object")
    if scope.get("expected_problem_numbers") != EXPECTED_NUMBERS:
        fail("expected_problem_numbers drift")
    if scope.get("expected_total_usd") != EXPECTED_TOTAL:
        fail("expected_total_usd drift")
    if scope.get("parallel_platform_rewards_counted") is not False:
        fail("parallel platform rewards must not be counted")

    sources = doc.get("source_snapshot")
    if not isinstance(sources, dict):
        fail("source_snapshot must be an object")
    formal_commit = sources.get("formal_conjectures_commit")
    if not isinstance(formal_commit, str) or not SHA40.fullmatch(formal_commit):
        fail("formal_conjectures_commit must be a 40-hex SHA")

    problems = doc.get("problems")
    if not isinstance(problems, list) or len(problems) != len(EXPECTED_NUMBERS):
        fail("problems must contain exactly nine rows")

    seen = set()
    ppl_seen = set()
    total = 0
    for row in problems:
        if not isinstance(row, dict):
            fail("problem row must be an object")
        number = row.get("erdos_number")
        if type(number) is not int or number in seen:
            fail(f"invalid or duplicate erdos_number: {number!r}")
        seen.add(number)
        if number not in EXPECTED_REWARDS:
            fail(f"unexpected erdos_number: {number}")

        reward = row.get("reward_usd")
        if type(reward) is not int or reward != EXPECTED_REWARDS[number]:
            fail(f"reward drift for #{number}")
        total += reward

        direct = row.get("direct_source")
        if direct != f"https://www.erdosproblems.com/{number}":
            fail(f"direct source drift for #{number}")
        if row.get("direct_status") != "OPEN":
            fail(f"non-open row in open tranche: #{number}")

        ppl_id = row.get("ppl_id")
        ppl_source = row.get("ppl_source")
        ppl_status = row.get("ppl_status")
        if ppl_id is None:
            if ppl_source is not None or ppl_status != "NOT_MAPPED_IN_V1":
                fail(f"unmapped PPL row must remain explicit for #{number}")
        else:
            if type(ppl_id) is not int or ppl_id in ppl_seen:
                fail(f"invalid or duplicate PPL id for #{number}")
            ppl_seen.add(ppl_id)
            if ppl_status != "VERIFIED_OPEN":
                fail(f"mapped PPL row must be VERIFIED_OPEN for #{number}")
            if ppl_source != f"https://prizeproblems.org/problems/{ppl_id:03d}/":
                fail(f"PPL source drift for #{number}")

        formal = row.get("formal_target")
        if not isinstance(formal, dict):
            fail(f"formal_target must be an object for #{number}")
        expected_path = f"FormalConjectures/ErdosProblems/{number}.lean"
        if formal.get("path") != expected_path:
            fail(f"formal target path drift for #{number}")
        if number in FORMAL_PRESENT:
            if formal.get("status") != "PRESENT":
                fail(f"present formal target mislabeled for #{number}")
            blob = formal.get("blob_sha")
            if not isinstance(blob, str) or not SHA40.fullmatch(blob):
                fail(f"missing formal blob SHA for #{number}")
            if not isinstance(formal.get("theorem"), str) or not formal["theorem"]:
                fail(f"missing theorem name for #{number}")
        elif number in FORMAL_MISSING:
            if formal.get("status") != "MISSING_AT_CANONICAL_PATH":
                fail(f"missing formal target mislabeled for #{number}")
            if formal.get("blob_sha") is not None or formal.get("theorem") is not None:
                fail(f"missing target must not invent blob/theorem for #{number}")
        else:
            fail(f"formal status set is incomplete for #{number}")

        ownership = row.get("commons_ownership")
        if not isinstance(ownership, dict):
            fail(f"commons_ownership must be an object for #{number}")
        if number == 64:
            if ownership.get("status") != "ACTIVE_TAKE":
                fail("#64 must preserve active-take collision fence")
            if ownership.get("carrier") != "woahwhattheheck/commons#16031":
                fail("#64 carrier drift")
            if ownership.get("task_id") != "ERDOS64-N24-PROOF-BACKEND-ZSOL-20260918":
                fail("#64 task-id drift")
        elif ownership.get("status") != "NO_ACTIVE_TAKE_OBSERVED_IN_CENSUS":
            fail(f"unexpected ownership state for #{number}")

    if sorted(seen) != EXPECTED_NUMBERS:
        fail("problem-number set drift")
    if total != EXPECTED_TOTAL:
        fail(f"reward total drift: {total}")

    p625 = next(row for row in problems if row["erdos_number"] == 625)
    if p625.get("reward_scope") != "disproof_maximum":
        fail("#625 USD 1,000 value must remain labeled as the disproof-side maximum")

    # This is an immutable research snapshot, not a caller-defined new edition.
    # Keep the full canonical identity in trusted source; deriving the expected
    # identity from crosswalk.json would simply bless whatever input was changed.
    try:
        canonical = json.dumps(
            doc, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        fail(f"snapshot is not canonical JSON: {exc}")
    digest = hashlib.sha256(canonical).hexdigest()
    if digest != "7d7302297e166f50409f39d216462940312dc0dd013be5490f721e4b15669a93":
        fail("snapshot identity drift; a new edition requires separately reviewed source")
    return digest


def main(argv: list[str]) -> int:
    path = Path(argv[1]) if len(argv) > 1 else Path(__file__).with_name("crosswalk.json")
    try:
        doc = load_strict(path)
        digest = verify(doc)
    except CrosswalkError as exc:
        print(f"CROSSWALK_ERROR: {exc}", file=sys.stderr)
        return 2
    print(f"CROSSWALK_OK rows=9 total_usd={EXPECTED_TOTAL} sha256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
