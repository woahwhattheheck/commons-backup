#!/usr/bin/env python3
"""Compare official checker outputs generated with --max-decimal-places 6.

Rules 2.5 defines lexicographic saturation ordering, with NO cost tiebreak.
No locally reconstructed or rounded objective is substituted for checker output.
Inputs may be two files or roots containing <instance>/checker-6.json.
"""
import argparse
import csv
import io
from decimal import Decimal, DecimalException
import hashlib
import json
from pathlib import Path


def load_result(path):
    raw = path.read_bytes()
    try:
        result = json.loads(raw, parse_float=Decimal)
    except DecimalException as error:
        raise ValueError(f"{path}: malformed checker number") from error
    if not isinstance(result, dict):
        raise ValueError(f"{path}: expected checker result object")
    if result.get("valid") not in (True, False) or type(result.get("valid")) is not bool:
        raise ValueError(f"{path}: expected checker valid boolean")
    record = {"valid": result["valid"], "path": str(path.resolve()),
              "sha256": hashlib.sha256(raw).hexdigest(), "total_cost": result.get("total_cost")}
    if not result["valid"]:
        return record
    saturations = result.get("saturations")
    if not isinstance(saturations, list) or not saturations:
        raise ValueError(f"{path}: valid output has no saturation vector")
    vector, keys = [], set()
    for row in saturations:
        try:
            value = Decimal(row["sat"])
            if not value.is_finite() or value < 0:
                raise ValueError(f"{path}: nonfinite or negative saturation")
            scaled = value * 1_000_000
            # The pinned RapidJSON writer emits [1e-7, 1e-6) in scientific
            # notation even with SetMaxDecimalPlaces(6). Keep those official
            # values exactly; rounding them would change the objective vector.
            native_scientific = Decimal("1e-7") <= value < Decimal("1e-6")
            if scaled != scaled.to_integral_value() and not native_scientific:
                raise ValueError(f"{path}: saturation has >6 decimal places; rerun official checker at 6")
        except DecimalException as error:
            # Malformed numeric output belongs to the supervisor's existing
            # report retry path, not an uncaught arithmetic exception.
            raise ValueError(f"{path}: malformed saturation number") from error
        key = (row["t"], str(row["from"]), str(row["to"]))
        if key in keys:
            raise ValueError(f"{path}: duplicate link/time coordinate {key}")
        keys.add(key)
        vector.append(value)
    record.update(vector=sorted(vector, reverse=True), keys=keys)
    return record


def compare(left, right):
    report = {"left_valid": left["valid"], "right_valid": right["valid"],
              "left_total_cost_diagnostic": left.get("total_cost"),
              "right_total_cost_diagnostic": right.get("total_cost"),
              "cost_used_in_ranking": False, "first_changed_rank": None}
    if not left["valid"] and not right["valid"]:
        report["winner"] = "no_feasible_solution"
        return report
    if left["valid"] != right["valid"]:
        report["winner"] = "left" if left["valid"] else "right"
        return report
    if left["keys"] != right["keys"]:
        raise ValueError("Outputs have different link/time coordinates: cannot compare instances or incomplete vectors")
    report.update(compare_vectors(left["vector"], right["vector"]))
    return report


def compare_vectors(a, b):
    """The same full-vector ordering for checker and published-reference inputs."""
    if not a or len(a) != len(b):
        raise ValueError("Cannot compare empty or unequal-length saturation vectors")
    report = {"first_changed_rank": None, "load_count": len(a),
              "left_mlu": str(a[0]), "right_mlu": str(b[0])}
    difference = next((i for i, pair in enumerate(zip(a, b)) if pair[0] != pair[1]), None)
    report["winner"] = "tie" if difference is None else ("left" if a[difference] < b[difference] else "right")
    if difference is not None:
        report.update(first_changed_rank=difference + 1,
                      left_at_first_change=str(a[difference]), right_at_first_change=str(b[difference]))
    return report


SPRINT_COMMIT = "d84d319a7fdb8de3b1866830d2eaa2937871e5ae"
SPRINT_SHA256 = "b6218e41ac204e73c4688aa9e0e56825c1f5b864440675c4f7ffba27a75f45ca"
SPRINT_SOURCE = ("https://gitlab.com/Orange-OpenSource/network-optimization-tools/"
                 "challenge-roadef-2026/-/blob/" + SPRINT_COMMIT + "/sprint_results/loads_vector.csv")


def parse_sprint_csv(raw):
    """Parse the published variable-width schema, without padding or sorting it.

    This format parser does not authenticate a source. Use load_sprint_reference
    for the hash-bound official input; arbitrary parsed bytes are not that input.
    """
    try:
        rows = csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline=""), strict=True)
        header = next(rows)
        if (header[:2] != ["Instance", "Best team"] or len(header) <= 2 or
                header[2:] != [str(i) for i in range(1, len(header) - 1)]):
            raise ValueError("Sprint CSV requires Instance,Best team and consecutive rank columns")
        records = {}
        for line, row in enumerate(rows, 2):
            if len(row) < 3 or len(row) > len(header):
                raise ValueError(f"Sprint CSV line {line}: empty or oversized vector")
            instance, team = row[:2]
            if (not instance or not team or instance != instance.strip() or team != team.strip()):
                raise ValueError(f"Sprint CSV line {line}: missing or padded instance/team label")
            if instance in records:
                raise ValueError(f"Sprint CSV line {line}: duplicate instance {instance}")
            vector = []
            for rank, text in enumerate(row[2:], 1):
                value = Decimal(text)
                scaled = value * 1_000_000
                if not value.is_finite() or value < 0 or scaled != scaled.to_integral_value():
                    raise ValueError(f"Sprint CSV line {line}, rank {rank}: invalid six-decimal value")
                if vector and value > vector[-1]:
                    raise ValueError(f"Sprint CSV line {line}: vector is not ranked in descending order")
                vector.append(value)
            records[instance] = {"instance": instance, "best_team": team,
                                 "csv_line": line, "vector": vector}
        if not records:
            raise ValueError("Sprint CSV contains no instance vectors")
        return records
    except (UnicodeError, csv.Error, StopIteration, DecimalException) as error:
        raise ValueError("Malformed sprint reference CSV") from error


def load_sprint_reference(path):
    """Bind the original public reference bytes, not an inferred current ranking."""
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != SPRINT_SHA256:
        raise ValueError("Sprint CSV SHA-256 differs from the pinned official reference")
    records = parse_sprint_csv(raw)
    return {"path": str(path.resolve()), "sha256": digest, "bytes": len(raw),
            "source": SPRINT_SOURCE, "source_commit": SPRINT_COMMIT, "records": records}


def compare_sprint(candidate, reference, instance):
    """Compare one explicitly named instance; CSV has ranks, not coordinates.

    Instance identity is the caller's assertion. The checker format and this CSV
    cannot prove which input files produced a candidate, even if lengths agree.
    """
    if instance not in reference["records"]:
        raise ValueError(f"No published sprint vector for instance {instance!r}")
    target = reference["records"][instance]
    report = {"instance": instance, "candidate_valid": candidate["valid"],
              "reference_best_team": target["best_team"], "reference_csv_line": target["csv_line"],
              "reference_vector_length": len(target["vector"]),
              "candidate_checker_path": candidate["path"],
              "candidate_checker_sha256": candidate["sha256"],
              "candidate_total_cost_diagnostic": candidate.get("total_cost"),
              "cost_used_in_ranking": False, "first_changed_rank": None,
              "instance_binding": "caller-declared exact instance label; vector length checked when valid",
              "input_file_identity_verified": False,
              "reference_link_time_coordinates_available": False}
    if not candidate["valid"]:
        report.update(winner="reference", comparison_status="candidate_invalid")
        return report
    ranked = compare_vectors(candidate["vector"], target["vector"])
    report.update(ranked)
    report["winner"] = {"left": "candidate", "right": "reference", "tie": "tie"}[ranked["winner"]]
    report["comparison_status"] = "compared"
    report["candidate_mlu"] = report.pop("left_mlu")
    report["reference_mlu"] = report.pop("right_mlu")
    if ranked["first_changed_rank"] is not None:
        report["candidate_at_first_change"] = report.pop("left_at_first_change")
        report["reference_at_first_change"] = report.pop("right_at_first_change")
    return report


def sprint_report(left_path, csv_path, checker_name="checker-6.json", instance=None):
    reference = load_sprint_reference(csv_path)
    if left_path.is_file():
        if not instance:
            raise ValueError("--sprint with one checker file requires --instance (for example setA-01)")
        pairs = [(instance, left_path)]
    elif left_path.is_dir():
        if instance is not None:
            raise ValueError("For a benchmark root, instance names come from its subdirectories")
        pairs = [(p.parent.name, p) for p in sorted(left_path.glob("*/" + checker_name))]
        if not pairs:
            raise ValueError("Benchmark root has no checker outputs")
    else:
        raise ValueError("Provide a checker output file or an existing benchmark root")
    # Resolve labels before reading candidate outputs; never match by length alone.
    unknown = [name for name, _ in pairs if name not in reference["records"]]
    if unknown:
        raise ValueError(f"Instances absent from pinned sprint reference: {unknown}")
    rows = [compare_sprint(load_result(path), reference, name) for name, path in pairs]
    compared = {name for name, _ in pairs}
    return {"comparison": "official six-decimal saturation vectors versus published sprint reference; no cost tiebreak",
            "competition_rank": "unknown; historical per-instance best teams are not a qualification ranking",
            "resource_budgets_matched": False,
            "reference": {key: value for key, value in reference.items() if key != "records"},
            "reference_instances_not_compared": sorted(set(reference["records"]) - compared),
            "counts": {outcome: sum(row["winner"] == outcome for row in rows)
                       for outcome in ("candidate", "reference", "tie")},
            "invalid_candidate_count": sum(not row["candidate_valid"] for row in rows),
            "instances": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("left", type=Path)
    parser.add_argument("right", type=Path)
    parser.add_argument("--checker-name", default="checker-6.json")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--sprint", action="store_true",
                        help="right is the pinned public sprint CSV; left is saved checker output(s)")
    parser.add_argument("--instance", help="exact sprint instance label for a single checker file")
    args = parser.parse_args()
    if args.sprint:
        result = sprint_report(args.left, args.right, args.checker_name, args.instance)
        text = json.dumps(result, indent=2, default=str) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(text, encoding="utf-8")
        print(text, end="")
        return
    if args.instance is not None:
        parser.error("--instance requires --sprint")
    if args.left.is_file() and args.right.is_file():
        pairs = [("instance", args.left, args.right)]
    elif args.left.is_dir() and args.right.is_dir():
        left = {p.parent.name: p for p in args.left.glob("*/" + args.checker_name)}
        right = {p.parent.name: p for p in args.right.glob("*/" + args.checker_name)}
        if not left or left.keys() != right.keys():
            raise ValueError(f"Instance sets differ or empty: left={sorted(left)}, right={sorted(right)}")
        pairs = [(name, left[name], right[name]) for name in sorted(left)]
    else:
        raise ValueError("Provide two files or two existing benchmark roots")
    rows = []
    for name, lp, rp in pairs:
        left, right = load_result(lp), load_result(rp)
        row = {"instance": name, **compare(left, right),
               "left_checker_sha256": left["sha256"], "right_checker_sha256": right["sha256"],
               "left_checker_path": left["path"], "right_checker_path": right["path"]}
        rows.append(row)
    result = {"comparison": "official six-decimal saturation vectors; no cost tiebreak",
              "competition_rank": "unknown; these pairwise results do not establish rank against other teams",
              "counts": {outcome: sum(row["winner"] == outcome for row in rows)
                         for outcome in ("left", "right", "tie", "no_feasible_solution")}, "instances": rows}
    text = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
