#!/usr/bin/env python3
from __future__ import annotations

import json
from visual_gate import compile_trace, synthetic_scene, verify_trace, opencv5_runtime_evidenced

CASES = [
    ("none", "CAPTURE_NEXT_FRAME"),
    ("left", "INSPECT_LEFT_ZONE"),
    ("center", "NO_ACTION"),
    ("right", "INSPECT_RIGHT_ZONE"),
]


def run_suite() -> dict:
    results = []
    for hazard, expected_tool in CASES:
        trace = compile_trace(synthetic_scene(hazard=hazard), observed_ms=1000, now_ms=1100)
        results.append({
            "hazard": hazard,
            "expected_tool": expected_tool,
            "actual_tool": trace["decision"]["tool_plan"],
            "trace_verified": verify_trace(trace),
            "pass": trace["decision"]["tool_plan"] == expected_tool and verify_trace(trace),
        })
    passed = sum(1 for r in results if r["pass"])
    return {
        "schema": "visual-evidence-gate-evaluation/v1",
        "synthetic_cases": len(results),
        "passed": passed,
        "success_ppm": (passed * 1_000_000) // len(results),
        "results": results,
        "claims": {
            "synthetic_task_success_measured": True,
            "natural_video_accuracy_measured": False,
            "opencv5_runtime_evidenced": opencv5_runtime_evidenced(),
            "aws_runtime_evidenced": False,
            "competition_submission_evidenced": False,
        },
    }


if __name__ == "__main__":
    print(json.dumps(run_suite(), indent=2, sort_keys=True))
