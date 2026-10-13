# SPDX-License-Identifier: Apache-2.0
"""Behavioral negative controls for the exact owner's source, never production."""
from __future__ import annotations
from contextlib import redirect_stderr
import io
import json
from pathlib import Path
import tempfile

from fruitproof_engine import git_blob
from fruitproof_owner import verify_owner


def verify_owner_controls(path, expected, engine, Struct, output):
    data = Path(path).read_bytes()
    if git_blob(data) != expected:
        raise ValueError("control source identity mismatch")
    source = data.decode("utf-8")
    mutations = [
        ("enabled_ignored", "if enabled is not True:", "if False:"),
        ("retained_input_spent", "if sum(shed.values()) < 100:", "if False:"),
        ("already_covered", "coverage >= day", "coverage > day"),
        ("no_increment_at_cap", "held > 2", "held > 3"),
        ("missing_water", "tile.get('watered_today') is not True", "False"),
        ("wrong_service_night", "not 8 <= day + 1 - planted <= 11", "not 8 <= day - planted <= 11"),
        ("collocated_double_spend", "if any(i != actor and tuple(pos) == (x, y)", "if False and any(i != actor and tuple(pos) == (x, y)"),
        ("mutates_parent", "out = deepcopy(action)", "out = action"),
        ("proposal_without_action", "out['farmer'] = ['FERTILIZE']", "out['farmer'] = ['PASS']"),
    ]
    reports = []
    for name, old, new in mutations:
        if source.count(old) != 1:
            raise ValueError(f"owner control span changed: {name}")
        mutant = source.replace(old, new).encode()
        directory = Path(output) / ("owner-control-" + name)
        directory.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / "discarded_fertilizer_tomato.py"
            file.write_bytes(mutant)
            captured = io.StringIO()
            try:
                with redirect_stderr(captured):
                    verify_owner(file, git_blob(mutant), engine, Struct, directory)
            except AssertionError as error:
                report = json.loads(str(error))
            else:
                raise ValueError(f"broken owner passed: {name}")
        if report["errors"] or report["skips"] or report["failures"] < 1 or report["tests"] != 8:
            raise ValueError(f"not an assertion-only owner rejection: {report}")
        report["name"] = name
        reports.append(report)
    return reports
