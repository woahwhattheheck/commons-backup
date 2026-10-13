# SPDX-License-Identifier: Apache-2.0
"""Tighten SOL-AMPLIFIER panel evidence without changing gameplay bytes."""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import statistics
import tempfile
from typing import Any, Mapping, MutableMapping, Sequence

EXPECTED_OPPONENTS = ("arlene", "apex", "public_bt12", "v1")
EXPECTED_SEEDS = (2611092201, 2611092203, 2611092205, 2611092207)
EXPECTED_SEATS = (0, 1)
MARKDOWN_MARKER = "## Supplemental causal and robustness gate"


def _finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _outcome(margin: float) -> str:
    return "W" if margin > 0 else "L" if margin < 0 else "T"


def _expected_keys() -> set[tuple[str, int, int]]:
    return {
        (opponent, seed, seat)
        for opponent in EXPECTED_OPPONENTS
        for seed in EXPECTED_SEEDS
        for seat in EXPECTED_SEATS
    }


def _scores(value: Any, label: str, key: tuple[str, int, int]) -> list[float]:
    if not (
        isinstance(value, list)
        and len(value) == 2
        and all(_finite_number(item) for item in value)
    ):
        raise ValueError(f"{label} scores malformed for {key}")
    return [float(value[0]), float(value[1])]


def _close(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=0.0, abs_tol=1e-9)


def evaluate(report: MutableMapping[str, Any]) -> dict[str, Any]:
    """Validate cell arithmetic and return fail-closed supplemental checks."""
    if report.get("status") != "complete":
        raise ValueError("panel report is not complete")
    cells = report.get("cells")
    if not isinstance(cells, list):
        raise ValueError("panel cells are missing")

    expected = _expected_keys()
    seen: set[tuple[str, int, int]] = set()
    action_identity_violations: list[dict[str, Any]] = []
    new_losses: list[dict[str, Any]] = []
    strata: dict[tuple[str, int], list[float]] = {}

    for raw in cells:
        if not isinstance(raw, Mapping):
            raise ValueError("panel cell is not a mapping")
        opponent = raw.get("opponent")
        seed = raw.get("seed")
        seat = raw.get("candidate_seat")
        if (
            not isinstance(opponent, str)
            or type(seed) is not int
            or type(seat) is not int
        ):
            raise ValueError("panel cell key has an invalid type")
        key = (opponent, seed, seat)
        if key not in expected or key in seen:
            raise ValueError(f"panel cell key is invalid or duplicate: {key}")
        seen.add(key)

        base_action = raw.get("baseline_candidate_action_sha256")
        candidate_action = raw.get("candidate_candidate_action_sha256")
        base_trace = raw.get("baseline_trace_sha256")
        candidate_trace = raw.get("candidate_trace_sha256")
        if not all(_sha256(value) for value in (
            base_action, candidate_action, base_trace, candidate_trace
        )):
            raise ValueError(f"panel digest malformed for {key}")
        action_changed = raw.get("candidate_action_changed")
        trace_changed = raw.get("trace_changed")
        if type(action_changed) is not bool or action_changed != (base_action != candidate_action):
            raise ValueError(f"candidate action flag disagrees with digest for {key}")
        if type(trace_changed) is not bool or trace_changed != (base_trace != candidate_trace):
            raise ValueError(f"trace flag disagrees with digest for {key}")

        baseline_scores = _scores(raw.get("baseline_scores"), "baseline", key)
        candidate_scores = _scores(raw.get("candidate_scores"), "candidate", key)
        own_delta = raw.get("own_delta")
        margin_delta = raw.get("margin_delta")
        if not _finite_number(own_delta) or not _finite_number(margin_delta):
            raise ValueError(f"panel deltas malformed for {key}")
        own_delta = float(own_delta)
        margin_delta = float(margin_delta)
        expected_own = candidate_scores[seat] - baseline_scores[seat]
        expected_margin = (
            candidate_scores[seat]
            - candidate_scores[1 - seat]
            - baseline_scores[seat]
            + baseline_scores[1 - seat]
        )
        if not _close(own_delta, expected_own):
            raise ValueError(f"own delta disagrees with scores for {key}")
        if not _close(margin_delta, expected_margin):
            raise ValueError(f"margin delta disagrees with scores for {key}")

        baseline_outcome = _outcome(
            baseline_scores[seat] - baseline_scores[1 - seat]
        )
        candidate_outcome = _outcome(
            candidate_scores[seat] - candidate_scores[1 - seat]
        )
        if raw.get("baseline_outcome") != baseline_outcome:
            raise ValueError(f"baseline outcome disagrees with scores for {key}")
        if raw.get("candidate_outcome") != candidate_outcome:
            raise ValueError(f"candidate outcome disagrees with scores for {key}")

        if not action_changed and (
            trace_changed or baseline_scores != candidate_scores
        ):
            action_identity_violations.append(
                {
                    "opponent": opponent,
                    "seed": seed,
                    "candidate_seat": seat,
                    "trace_changed": trace_changed,
                    "scores_changed": baseline_scores != candidate_scores,
                }
            )
        if baseline_outcome != "L" and candidate_outcome == "L":
            new_losses.append(
                {
                    "opponent": opponent,
                    "seed": seed,
                    "candidate_seat": seat,
                    "transition": f"{baseline_outcome}->L",
                }
            )
        strata.setdefault((opponent, seat), []).append(own_delta)

    if seen != expected:
        missing = sorted(expected - seen)
        raise ValueError(f"panel grid is incomplete: {missing[:8]}")

    stratum_means = {
        f"{opponent}|seat={seat}": statistics.fmean(strata[(opponent, seat)])
        for opponent in EXPECTED_OPPONENTS
        for seat in EXPECTED_SEATS
    }
    checks = {
        "action_identity_implies_trace_and_score_identity": not action_identity_violations,
        "all_opponent_seat_strata_present": (
            set(strata)
            == {
                (opponent, seat)
                for opponent in EXPECTED_OPPONENTS
                for seat in EXPECTED_SEATS
            }
            and all(len(values) == len(EXPECTED_SEEDS) for values in strata.values())
        ),
        "no_opponent_seat_mean_own_regression": all(
            value >= 0.0 for value in stratum_means.values()
        ),
        "no_new_losses": not new_losses,
    }
    return {
        "schema_version": 1,
        "decision": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "per_opponent_seat_mean_own_delta": stratum_means,
        "action_identity_violations": action_identity_violations,
        "new_losses": new_losses,
    }


def apply(report: MutableMapping[str, Any]) -> dict[str, Any]:
    gate = evaluate(report)
    verdict = report.get("verdict")
    if not isinstance(verdict, dict):
        raise ValueError("panel verdict is missing")
    current = verdict.get("decision")
    original = verdict.get("pre_supplemental_decision", current)
    if original not in ("ADVANCE", "REJECT"):
        raise ValueError("panel decision is invalid")
    checks = verdict.get("checks")
    if not isinstance(checks, dict):
        raise ValueError("panel verdict checks are missing")
    checks.update(gate["checks"])
    verdict["pre_supplemental_decision"] = original
    verdict["decision"] = (
        "ADVANCE"
        if original == "ADVANCE" and all(gate["checks"].values())
        else "REJECT"
    )
    report["supplemental_gate"] = gate
    return gate


def _atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", newline="\n", dir=path.parent, delete=False
    ) as handle:
        temporary = Path(handle.name)
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _markdown(text: str, report: Mapping[str, Any], gate: Mapping[str, Any]) -> str:
    prefix = text.split("\n" + MARKDOWN_MARKER + "\n", 1)[0].rstrip()
    lines = prefix.splitlines()
    for index, line in enumerate(lines):
        if line.startswith("Verdict: **"):
            lines[index] = f"Verdict: **{report['verdict']['decision']}**"
            break
    lines.extend(("", MARKDOWN_MARKER, ""))
    for name, passed in gate["checks"].items():
        lines.append(f"- {'PASS' if passed else 'FAIL'} — `{name}`")
    lines.extend((
        "",
        f"Action-identity violations: {len(gate['action_identity_violations'])}",
        f"New losses: {len(gate['new_losses'])}",
        "",
    ))
    return "\n".join(lines)


def verify_files(panel: Path, markdown: Path) -> dict[str, Any]:
    report = json.loads(panel.read_text(encoding="utf-8"))
    if not isinstance(report, dict):
        raise ValueError("panel report root is not a mapping")
    gate = apply(report)
    _atomic_text(
        panel,
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
    )
    _atomic_text(markdown, _markdown(markdown.read_text(encoding="utf-8"), report, gate))
    return {
        "decision": report["verdict"]["decision"],
        "supplemental_gate": gate,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", type=Path, required=True)
    parser.add_argument("--markdown", type=Path, required=True)
    args = parser.parse_args(argv)
    result = verify_files(args.panel, args.markdown)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
