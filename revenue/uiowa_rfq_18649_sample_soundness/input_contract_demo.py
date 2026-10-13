#!/usr/bin/env python3
"""Run fictional ingress cases through the real soundness CLI, without network I/O."""
from __future__ import annotations
import argparse
import contextlib
import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import check_soundness as CLI
import soundness as S

HERE = Path(__file__).resolve().parent


def _packet(**changes):
    record = dict(id="M-SYN-DEMO", label="fictional records", kind="COUNT",
                  components={"observed": 4}, stated_total=4)
    record.update(changes)
    return {"synthetic": True, "measures": [record]}


def _model():
    return dict(method="BINOMIAL_ZERO_UPPER", confidence=0.95,
                independent_trials=True, constant_probability=True,
                rationale="Fictional independent trials from one unchanged process.")


def cases():
    rate = _packet(kind="PROPORTION", numerator=58, denominator=100,
                   reported_value=58, sampling="RANDOM", components=None, stated_total=None)
    zero = _packet(kind="PROPORTION", numerator=0, denominator=8,
                   presentation="COUNT", components=None, stated_total=None)
    census = copy.deepcopy(zero)
    census["measures"][0].update(sampling="CENSUS", scope="POPULATION",
                                claim="POPULATION_ABSENCE",
                                population="all eight records in this fictional collection")
    conditional = copy.deepcopy(zero)
    conditional["measures"][0].update(sampling="RANDOM", population="fictional stable process",
                                     inference=_model())
    unsupported = copy.deepcopy(conditional)
    unsupported["measures"][0]["sampling"] = "UNKNOWN"
    duplicate = _packet()
    duplicate["measures"].append(copy.deepcopy(duplicate["measures"][0]))
    # Consecutive overrides and defaults deliberately execute in one process.
    return [
        ("clean_count", _packet(), (), 0, None),
        ("threshold_override", rate, ("--min-denominator", "200"), 1, "DENOMINATOR_TOO_SMALL"),
        ("default_after_override", rate, (), 0, None),
        ("negative_component", _packet(components={"observed": -4}, stated_total=-4), (), 2, None),
        ("boolean_component", _packet(components={"observed": True}, stated_total=1), (), 2, None),
        ("median_as_text", _packet(kind="MEDIAN", observations="12345"), (), 2, None),
        ("median_with_nan", _packet(kind="MEDIAN", observations=[1, 2, 3, 4, float("nan")]), (), 2, None),
        ("components_as_list", _packet(components=[]), (), 2, None),
        ("duplicate_identity", duplicate, (), 2, None),
        ("missing_measures", {"synthetic": True}, (), 2, None),
        ("empty_collection", {"synthetic": True, "measures": []}, (), 1, "EMPTY_MEASURE_SET"),
        ("unknown_component", _packet(components={"observed": 4, "unrecorded": None}), (), 1, "COMPONENT_UNKNOWN"),
        ("observed_zero_components", _packet(components={"observed": 0}, stated_total=0), (), 0, None),
        ("scoped_descriptive_zero", zero, (), 0, None),
        ("named_complete_census", census, (), 0, None),
        ("conditional_zero_limit", conditional, (), 0, "ZERO_EVENT_MODEL_LIMIT"),
        ("unsupported_population_limit", unsupported, (), 1, "ZERO_EVENT_MODEL_UNSUPPORTED"),
        ("duplicate_json_member", '{"synthetic":true,"measures":[],"measures":[]}', (), 2, None),
        ("invalid_utf8", b"\xff\xfe not UTF8", (), 2, None),
    ]


def git_blob(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def run() -> dict:
    initial_threshold = S.MIN_DENOMINATOR_FOR_RATE
    results = []
    with tempfile.TemporaryDirectory(prefix="soundness-input-demo-") as temporary:
        source = Path(temporary) / "records.json"
        for name, payload, extra, expected_exit, expected_code in cases():
            data = (payload if isinstance(payload, bytes) else
                    (payload if isinstance(payload, str) else json.dumps(payload)).encode("utf-8"))
            source.write_bytes(data)
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                status = CLI.main(["--measures", str(source), "--format", "json", *extra])
            report = json.loads(stdout.getvalue()) if stdout.getvalue() else None
            found = sorted({item["code"] for item in report["findings"]}) if report else []
            if status != expected_exit or (expected_code and expected_code not in found):
                raise RuntimeError(f"{name}: expected exit {expected_exit}/{expected_code}, got {status}/{found}")
            if source.read_bytes() != data:
                raise RuntimeError(f"{name}: input bytes changed")
            if status == 2 and (report is not None or "Traceback" in stderr.getvalue()):
                raise RuntimeError(f"{name}: malformed input produced a report or traceback")
            if report and report["passed"] != (status == 0):
                raise RuntimeError(f"{name}: report and exit status disagree")
            if S.MIN_DENOMINATOR_FOR_RATE != initial_threshold:
                raise RuntimeError(f"{name}: invocation changed the default threshold")
            results.append(dict(case=name, exit=status, codes=found,
                                report=report, diagnostic=stderr.getvalue().strip(),
                                input_unchanged=True))
    return dict(synthetic=True, notice="Prepared fictional cases, not University findings or independently verified observations.",
                source_blobs={name: git_blob(HERE / name) for name in
                              ("soundness.py", "check_soundness.py", "input_contract_demo.py")},
                cases_checked=len(results), cases=results)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)
    report = run()
    if args.format == "json":
        print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
    else:
        print(report["notice"])
        print(f"{report['cases_checked']} cases matched their expected behavior; all input bytes unchanged.")
        for case in report["cases"]:
            label = {0: "NO_ERROR", 1: "FINDING", 2: "INPUT_ERROR"}[case["exit"]]
            detail = ", ".join(case["codes"]) or case["diagnostic"] or "no configured rule reported an error"
            print(f"{case['case']:30} {label:12} {detail}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
