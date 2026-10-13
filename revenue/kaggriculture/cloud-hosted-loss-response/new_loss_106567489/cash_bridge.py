"""Exact, descriptive cash-gap attribution over ROWAN's reconciled replay trace.

This module never runs an opponent or makes a policy decision. It consumes the
existing trace, keeps unverified changes unassigned, and writes arithmetic
volume/realized-price decompositions, not causal estimates of strategy value.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import importlib.util
import json
import math
from fractions import Fraction
from pathlib import Path
import sys
from typing import Any

HERE = Path(__file__).resolve().parent
TRACE_PATH = HERE.parents[1] / "cloud-frontier-trace/analyze.py"
TRACE_BLOB = "9c7cd95005ce9c84b862f218049fd71e16ccd604"
ENGINE_REF = "28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c"


def number(value: Any) -> Fraction:
    if isinstance(value, bool) or not isinstance(value, (int, float, Fraction)):
        raise ValueError("Cash values must be finite numbers, not strings or booleans")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("Cash values must be finite")
    return Fraction(str(value)) if isinstance(value, float) else Fraction(value)


def seat_index(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value not in (0, 1):
        raise ValueError("Expected a two-player seat index")
    return value


def pair(values: Any) -> list[Fraction]:
    if not isinstance(values, list) or len(values) != 2:
        raise ValueError("Expected two seat-ordered values")
    return [number(v) for v in values]


def jsonable(value: Any) -> Any:
    """Represent nonintegral rationals exactly, without float rounding."""
    if isinstance(value, Fraction):
        return int(value) if value.denominator == 1 else {
            "numerator": value.numerator, "denominator": value.denominator}
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    return value


def price_volume(quantities: list[int], proceeds: list[Fraction], own_seat: int) -> dict:
    """Symmetric exact revenue identity, conditional on positive sales both sides.

    Delta(q*p) = Delta(q) * mean(p) + Delta(p) * mean(q).
    Realized average price includes differences in timing and market interaction.
    Neither term is a counterfactual or a causal decomposition.
    """
    own = seat_index(own_seat)
    if len(quantities) != 2 or any(isinstance(q, bool) or not isinstance(q, int) or q < 0
                                    for q in quantities):
        raise ValueError("Sale quantities must be two nonnegative integers")
    amounts = pair(proceeds)
    if any(q == 0 and p != 0 for q, p in zip(quantities, amounts)):
        raise ValueError("Nonzero sale proceeds require positive executed quantity")
    average = [amounts[s] / quantities[s] if quantities[s] else None for s in (0, 1)]
    result = {"units_by_seat": quantities, "proceeds_by_seat": amounts,
              "average_price_by_seat": average,
              "own_minus_rival_proceeds": amounts[own] - amounts[1-own],
              "volume_component": None, "realized_price_component": None,
              "undecomposed_proceeds": amounts[own] - amounts[1-own]}
    if all(quantities):
        volume = (quantities[own] - quantities[1-own]) * (average[own] + average[1-own]) / 2
        price = (average[own] - average[1-own]) * Fraction(sum(quantities), 2)
        assert volume + price == result["own_minus_rival_proceeds"]
        result.update(volume_component=volume, realized_price_component=price,
                      undecomposed_proceeds=Fraction(0))
    return result


def build_bridge(trace: dict, own_seat: int, *, top_n: int = 8) -> dict:
    """Account for the complete observed cash path, without attributing unknowns."""
    own = seat_index(own_seat)
    if isinstance(top_n, bool) or not isinstance(top_n, int) or top_n < 1:
        raise ValueError("top_n must be a positive integer")
    opening = pair([s["cash"] for s in trace["opening"]])
    terminal = pair([s["cash"] for s in trace["terminal"]])
    tpd = trace["configuration"]["turnsPerDay"]
    if isinstance(tpd, bool) or not isinstance(tpd, int) or tpd < 1:
        raise ValueError("turnsPerDay must be a positive integer")
    bank = opening[:]
    causes = defaultdict(lambda: [Fraction(0), Fraction(0)])
    quantities = defaultdict(lambda: [0, 0])
    proceeds = defaultdict(lambda: [Fraction(0), Fraction(0)])
    statuses = Counter()
    daily = {}
    rows = []
    unknown = [Fraction(0), Fraction(0)]
    residuals = [Fraction(0), Fraction(0)]
    previous_step = -1
    for expected_frame, row in enumerate(trace["transitions"], 1):
        step, frame = row["action_step"], row["frame"]
        if (isinstance(step, bool) or not isinstance(step, int) or step <= previous_step
                or isinstance(frame, bool) or frame != expected_frame):
            raise ValueError("Trace frames must be consecutive and action steps increasing")
        previous_step = step
        observed = pair(row["observed_cash_delta"])
        bank = [bank[s] + observed[s] for s in (0, 1)]
        if "farms_after" in row and pair([f["cash"] for f in row["farms_after"]]) != bank:
            raise ValueError(f"Observed cash path disagrees with frame {frame}")
        status = row["audit"]["status"]
        statuses[status] += 1
        accounted = [Fraction(0), Fraction(0)]
        row_causes = defaultdict(lambda: [Fraction(0), Fraction(0)])
        if status == "RECONCILED":
            for event in row["audit"].get("events", []):
                if "cash_delta" not in event:
                    continue
                seat = seat_index(event["seat"])
                amount = number(event["cash_delta"])
                kind = event["kind"]
                if kind == "trade":
                    label = f"trade:{event['op']}:{event['item']}"
                    if event["op"] == "SELL" and event["success"]:
                        quantities[event["item"]][seat] += 1
                        proceeds[event["item"]][seat] += amount
                else:
                    label = str(kind)
                accounted[seat] += amount
                row_causes[label][seat] += amount
                causes[label][seat] += amount
            residual = [observed[s] - accounted[s] for s in (0, 1)]
            if "cash_residual" in row and pair(row["cash_residual"]) != residual:
                raise ValueError(f"Stored cash residual disagrees at frame {frame}")
            residuals = [residuals[s] + residual[s] for s in (0, 1)]
            unverified = [Fraction(0), Fraction(0)]
        else:
            # Even if a malformed provider includes events here, never attribute them.
            residual = [Fraction(0), Fraction(0)]
            unverified = observed
            unknown = [unknown[s] + observed[s] for s in (0, 1)]
        day = step // tpd
        d = daily.setdefault(day, {"day": day, "opening_cash_by_seat": [bank[s]-observed[s] for s in (0, 1)],
            "observed_delta_by_seat": [Fraction(0), Fraction(0)],
            "attributed_delta_by_seat": [Fraction(0), Fraction(0)],
            "unverified_delta_by_seat": [Fraction(0), Fraction(0)],
            "residual_delta_by_seat": [Fraction(0), Fraction(0)],
            "status_counts": Counter(), "ending_cash_by_seat": bank[:]})
        for key, values in (("observed_delta_by_seat", observed), ("attributed_delta_by_seat", accounted),
                            ("unverified_delta_by_seat", unverified), ("residual_delta_by_seat", residual)):
            d[key] = [d[key][s] + values[s] for s in (0, 1)]
        d["status_counts"][status] += 1
        d["ending_cash_by_seat"] = bank[:]
        d["own_minus_rival_delta"] = d["observed_delta_by_seat"][own] - d["observed_delta_by_seat"][1-own]
        rows.append({"frame": frame, "action_step": step, "day": day,
            "status": status, "observed_delta_by_seat": observed,
            "own_minus_rival_delta": observed[own]-observed[1-own],
            "margin_after": bank[own]-bank[1-own],
            "cash_by_cause": dict(row_causes) if status == "RECONCILED" else None,
            "unverified_delta_by_seat": unverified, "residual_delta_by_seat": residual})
    if bank != terminal:
        raise ValueError("Opening plus observed transitions does not equal terminal cash")
    attributed = [sum(v[s] for v in causes.values()) for s in (0, 1)]
    for s in (0, 1):
        if opening[s] + attributed[s] + unknown[s] + residuals[s] != terminal[s]:
            raise ValueError("Cash attribution bridge is incomplete")
    by_cause = [{"cause": key, "cash_delta_by_seat": values,
                 "own_minus_rival_delta": values[own]-values[1-own]}
                for key, values in causes.items() if any(values)]
    by_cause.sort(key=lambda r: (r["own_minus_rival_delta"], r["cause"]))
    attribution_complete = all(s == "RECONCILED" for s in statuses) and all(
        not any(row["residual_delta_by_seat"]) for row in rows)
    result = {"schema": "titan.cash-gap-bridge.v1", "episode_id": trace.get("episode_id"),
        "own_seat": own, "engine_ref": trace.get("engine_ref"), "source": trace.get("source", {}),
        "opening_cash_by_seat": opening, "terminal_cash_by_seat": terminal,
        "opening_margin": opening[own]-opening[1-own],
        "terminal_margin": terminal[own]-terminal[1-own],
        "attributed_cash_delta_by_seat": attributed,
        "unverified_cash_delta_by_seat": unknown,
        "reconciled_cash_residual_by_seat": residuals,
        "arithmetic_bridge_exact": True, "all_cash_attributed": attribution_complete,
        "transition_status_counts": dict(statuses), "cash_by_cause": by_cause,
        "sales_by_product": {item: price_volume(quantities[item], proceeds[item], own)
                             for item in sorted(quantities)},
        "daily": list(daily.values()),
        "largest_adverse_changes": sorted((r for r in rows if r["own_minus_rival_delta"] < 0),
            key=lambda r: (r["own_minus_rival_delta"], r["frame"]))[:top_n],
        "largest_favorable_changes": sorted((r for r in rows if r["own_minus_rival_delta"] > 0),
            key=lambda r: (-r["own_minus_rival_delta"], r["frame"]))[:top_n],
        "limitations": [
            "Cash causes use only ROWAN-reconciled official transitions; all other changes remain unassigned.",
            "Revenue volume/average-price terms are an arithmetic identity, not causal strategy estimates.",
            "One-sided sales have no comparable realized price; their revenue difference remains undecomposed.",
            "A large intermediate cash gap may be spending or delayed sales, not an avoidable loss.",
            "Submission/seat identity comes from the supplied provider binding, never cash matching alone.",
            "Recorded rival actions and replay metadata are offline evidence, never runtime policy inputs."]}
    return jsonable(result)


def load_trace_module(path: Path = TRACE_PATH):
    data = path.read_bytes()
    blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
    if blob != TRACE_BLOB:
        raise ValueError("This reproduction expects the documented ROWAN analyzer revision")
    spec = importlib.util.spec_from_file_location("delve_rowan_trace", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("replay", type=Path)
    parser.add_argument("--engine-dir", type=Path, required=True)
    parser.add_argument("--trace-source", type=Path, default=TRACE_PATH)
    parser.add_argument("--episode-id", type=int, required=True)
    parser.add_argument("--player-index", type=int, required=True)
    parser.add_argument("--our-submission-id", type=int, required=True)
    parser.add_argument("--rival-submission-id", type=int, required=True)
    parser.add_argument("--expected-cash", required=True, help="Own,rival order")
    parser.add_argument("--provider-source", required=True, help="Recorded match-result reference")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    rowan = load_trace_module(args.trace_source)
    replay, source = rowan.load_replay(args.replay)
    embedded_episode_id = replay.get("info", {}).get("EpisodeId")
    if args.episode_id < 1:
        raise ValueError("Requested episode must be positive")
    if embedded_episode_id is not None and str(embedded_episode_id) != str(args.episode_id):
        raise ValueError("Replay EpisodeId does not match the requested episode")
    own = seat_index(args.player_index)
    expected = [Fraction(v.strip()) for v in args.expected_cash.split(",")]
    if len(expected) != 2:
        raise ValueError("Expected own,rival cash")
    last = rowan.observations(replay["steps"][-1])
    actual = [number(last[0]["farms"][s]["money"]) for s in (own, 1-own)]
    if actual != expected:
        raise ValueError("Replay terminal cash does not match the supplied provider receipt")
    ev = rowan.evaluator()
    engine, engine_hashes = ev.get_engine(args.engine_dir)
    source.update(analyzer_git_blob=TRACE_BLOB, engine_sha256=engine_hashes,
                  provider_binding={"source": args.provider_source, "own_seat": own,
                    "requested_episode_id": args.episode_id,
                    "embedded_episode_id": embedded_episode_id,
                    "our_submission_id": args.our_submission_id,
                    "rival_submission_id": args.rival_submission_id,
                    "expected_cash_own_rival": jsonable(expected)})
    trace = rowan.analyze(replay, engine, ev, source)
    bridge = build_bridge(trace, own)
    bridge["requested_episode_id"] = args.episode_id
    witness_frames = sorted({r["frame"] for r in bridge["largest_adverse_changes"]})
    witnesses = {"schema": "titan.observed-cash-witnesses.v1", "episode_id": args.episode_id,
        "source": source, "note": "Observed paired frames, not proposed actions or counterfactuals.",
        "cases": [{"frame": i, "before": replay["steps"][i-1], "after": replay["steps"][i]}
                  for i in witness_frames]}
    outputs = {"trace.json.gz": trace, "cash-bridge.json": bridge,
               "observed-witnesses.json.gz": witnesses}
    args.output.mkdir(parents=True, exist_ok=False)
    manifest = {"schema": "titan.cash-bridge-artifact.v1", "episode_id": args.episode_id,
                "tool_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), "files": {}}
    for filename, value in outputs.items():
        data = (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()
        if filename.endswith(".gz"):
            data = gzip.compress(data, mtime=0)
        (args.output / filename).write_bytes(data)
        manifest["files"][filename] = {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
    (args.output / "MANIFEST.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
    print(json.dumps({k: bridge[k] for k in ("requested_episode_id", "episode_id", "own_seat", "terminal_margin",
        "all_cash_attributed", "transition_status_counts")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
