#!/usr/bin/env python3
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile

from sentinel import (
    RULE_EXACT_ROW_LEN3,
    RULE_INPUT_ERROR,
    RULE_PUBLIC_OBS_COERCION,
    RULE_RAW_OPCODE_INDEX,
    RULE_TRUTHY_CONFIG_COERCION,
    main as sentinel_main,
    scan_paths,
    scan_source,
)


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def rules(source):
    return [finding.rule for finding in scan_source(source)]


def main():
    check(RULE_RAW_OPCODE_INDEX in rules("def f(order):\n    return order[0]\n"), "raw opcode")
    check(RULE_EXACT_ROW_LEN3 in rules("def f(order):\n    return len(order) == 3\n"), "len3")
    check(
        RULE_PUBLIC_OBS_COERCION in rules(
            "def f(observation):\n    return int(observation['step'])\n"
        ),
        "observation subscript coercion",
    )
    check(
        RULE_PUBLIC_OBS_COERCION in rules(
            "def f(obs):\n    return int(obs.get('player', 0))\n"
        ),
        "observation get coercion",
    )
    check(
        RULE_TRUTHY_CONFIG_COERCION in rules(
            "def f(feature_data):\n    return bool(feature_data['town_procurement'])\n"
        ),
        "truthy config coercion",
    )

    guarded = """\
def f(order):
    if not isinstance(order, list) or not order:
        return None
    # contract-sentinel: ignore=RAW_OPCODE_INDEX
    return order[0]
"""
    check(RULE_RAW_OPCODE_INDEX not in rules(guarded), "single suppression")

    multi = """\
def f(order):
    # contract-sentinel: ignore=EXACT_ROW_LEN3
    if len(order) == 3:
        # contract-sentinel: ignore=RAW_OPCODE_INDEX
        return order[0]
"""
    check(rules(multi) == [], "multiple suppressions")

    safe = """\
def f(observation, configuration):
    step = observation['step']
    if isinstance(step, bool) or not isinstance(step, int):
        return None
    enabled = configuration['feature']
    if type(enabled) is not bool:
        return None
    return step, enabled
"""
    check(rules(safe) == [], "exact-type safe fixture")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "b.py").write_text("def f(order):\n    return order[0]\n", encoding="utf-8")
        (root / "a.py").write_text("def f(obs):\n    return int(obs['day'])\n", encoding="utf-8")
        findings = scan_paths([root], display_root=root)
        check(
            [(f.path, f.rule) for f in findings] == [
                ("a.py", RULE_PUBLIC_OBS_COERCION),
                ("b.py", RULE_RAW_OPCODE_INDEX),
            ],
            "deterministic path/rule ordering",
        )

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        findings = scan_paths([root / "missing.py"], display_root=root)
        check(
            [(f.path, f.rule, f.message) for f in findings]
            == [("missing.py", RULE_INPUT_ERROR, "scan root does not exist")],
            "missing root was silently treated as clean",
        )

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        note = root / "notes.txt"
        note.write_text("def f(order): return order[0]\n", encoding="utf-8")
        findings = scan_paths([note], display_root=root)
        check(
            [(f.path, f.rule) for f in findings] == [("notes.txt", RULE_INPUT_ERROR)],
            "non-Python file root was silently ignored",
        )

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        bad = root / "bad.py"
        bad.write_bytes(b"\xff\xfe\x00")
        findings = scan_paths([bad], display_root=root)
        check(
            [(f.path, f.rule, f.message) for f in findings]
            == [("bad.py", RULE_INPUT_ERROR, "cannot read Python source as UTF-8")],
            "invalid UTF-8 source was silently ignored",
        )

    with tempfile.TemporaryDirectory() as tmp:
        missing = Path(tmp, "missing.py")
        output = io.StringIO()
        with redirect_stdout(output):
            rc = sentinel_main([str(missing), "--json", "--repo-root", tmp])
        payload = json.loads(output.getvalue())
        check(rc == 2, "input custody error did not fail closed at CLI")
        check(
            payload == [{
                "column": 0,
                "line": 1,
                "message": "scan root does not exist",
                "path": "missing.py",
                "rule": RULE_INPUT_ERROR,
            }],
            "CLI input-error receipt is not deterministic",
        )

    print("source-contract-sentinel: 13/13 OK")


if __name__ == "__main__":
    main()
