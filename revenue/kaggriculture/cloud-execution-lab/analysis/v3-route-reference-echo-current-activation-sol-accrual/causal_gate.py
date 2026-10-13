# SPDX-License-Identifier: Apache-2.0
"""Fail closed unless normalization precedes every returned-action and score effect."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from panel_evidence import (
    OPERATION,
    EvidenceError,
    action_steps,
    activation_events,
    index,
    scores,
)


def panel_index(panel):
    if panel.get("schema_version") != 1 or panel.get("operation") != OPERATION:
        raise EvidenceError("panel identity mismatch")
    rows = panel.get("rows")
    if not isinstance(rows, list) or not rows:
        raise EvidenceError("panel has no rows")
    result = {}
    for row in rows:
        if not isinstance(row, dict):
            raise EvidenceError("malformed panel row")
        key = (row.get("opponent"), row.get("seed"), row.get("seat"))
        if (
            not isinstance(key[0], str)
            or not key[0]
            or isinstance(key[1], bool)
            or not isinstance(key[1], int)
            or isinstance(key[2], bool)
            or key[2] not in (0, 1)
            or key in result
        ):
            raise EvidenceError(f"invalid or duplicate panel row {key}")
        result[key] = row
    if panel.get("cells") != len(result):
        raise EvidenceError("panel cell count mismatch")
    return result


def bind(control, candidate, panel):
    controls = index(control, "control")
    candidates = index(candidate, "candidate")
    panel_rows = panel_index(panel)
    if set(controls) != set(candidates) or set(controls) != set(panel_rows):
        raise EvidenceError("control/candidate/panel schedules differ")

    rows = []
    action_cells = score_cells = bound_action_cells = bound_score_cells = 0
    for key in sorted(controls):
        base, repair = controls[key], candidates[key]
        base_actions = action_steps(base, "control", key)
        repair_actions = action_steps(repair, "candidate", key)
        if len(base_actions) != len(repair_actions):
            raise EvidenceError(f"action lengths differ {key}")
        first = next(
            (
                step
                for step, pair in enumerate(zip(base_actions, repair_actions))
                if pair[0] != pair[1]
            ),
            None,
        )
        events = activation_events(repair, key)
        if base.get("candidate_agent_evidence") != []:
            raise EvidenceError(f"control emitted candidate evidence {key}")
        event_steps = [event["step"] for event in events]
        if any(step < 0 or step >= len(repair_actions) for step in event_steps):
            raise EvidenceError(f"activation outside interpreted range {key}")

        action_changed = first is not None
        activation_precedes = (
            action_changed and bool(event_steps) and min(event_steps) <= first
        )
        if action_changed and not activation_precedes:
            if not event_steps:
                raise EvidenceError(f"action changed without normalization {key}")
            raise EvidenceError(
                f"action diverged at {first} before normalization at "
                f"{min(event_steps)} {key}"
            )

        own0, rival0, _ = scores(base, "control", key)
        own1, rival1, _ = scores(repair, "candidate", key)
        score_changed = (own0, rival0) != (own1, rival1)
        if score_changed and not action_changed:
            raise EvidenceError(f"score changed without returned-action divergence {key}")
        if score_changed and not activation_precedes:
            raise EvidenceError(f"score changed without activation-bound action {key}")

        expected = panel_rows[key]
        checks = {
            "action_changed": action_changed,
            "first_action_divergence_step": first,
            "activation_count": len(events),
            "own_delta": own1 - own0,
            "rival_delta": rival1 - rival0,
        }
        for field, value in checks.items():
            if expected.get(field) != value:
                raise EvidenceError(f"panel {field} mismatch {key}")

        action_cells += int(action_changed)
        score_cells += int(score_changed)
        bound_action_cells += int(activation_precedes)
        bound_score_cells += int(score_changed and activation_precedes)
        rows.append(
            {
                "opponent": key[0],
                "seed": key[1],
                "seat": key[2],
                "activation_steps": event_steps,
                "first_action_divergence_step": first,
                "action_changed": action_changed,
                "score_changed": score_changed,
                "activation_precedes_action": activation_precedes,
            }
        )

    return {
        "schema_version": 1,
        "operation": OPERATION,
        "verdict": "CAUSAL_CHAIN_BOUND" if action_cells else "NO_ACTION_ACTIVATION",
        "promotion_authorized": False,
        "cells": len(rows),
        "action_changed_cells": action_cells,
        "score_changed_cells": score_cells,
        "activation_bound_action_cells": bound_action_cells,
        "activation_bound_score_cells": bound_score_cells,
        "all_action_divergences_activation_preceded": bound_action_cells == action_cells,
        "all_score_changes_returned_action_and_activation_bound": (
            bound_score_cells == score_cells
        ),
        "rows": rows,
    }


def digest(path):
    payload = path.read_bytes()
    return {
        "path_name": path.name,
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        value, indent=2, sort_keys=True, allow_nan=False
    ) + "\n"
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(payload, encoding="utf-8")
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--panel", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--provenance", type=Path, required=True)
    args = parser.parse_args()

    control = json.loads(args.control.read_text(encoding="utf-8"))
    candidate = json.loads(args.candidate.read_text(encoding="utf-8"))
    panel = json.loads(args.panel.read_text(encoding="utf-8"))
    report = bind(control, candidate, panel)
    write_json(args.output, report)
    provenance = {
        "schema_version": 1,
        "operation": OPERATION,
        "gate": "normalization-before-returned-action-before-score-v1",
        "verdict": report["verdict"],
        "promotion_authorized": False,
        "inputs": {
            "control": digest(args.control),
            "candidate": digest(args.candidate),
            "panel": digest(args.panel),
        },
        "output": digest(args.output),
    }
    write_json(args.provenance, provenance)
    print(
        json.dumps(
            {
                "verdict": report["verdict"],
                "cells": report["cells"],
                "action_changed_cells": report["action_changed_cells"],
                "score_changed_cells": report["score_changed_cells"],
                "activation_bound_action_cells": report[
                    "activation_bound_action_cells"
                ],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
