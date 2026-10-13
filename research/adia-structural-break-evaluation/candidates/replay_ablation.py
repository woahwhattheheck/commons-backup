"""Reproduce the three retained development-only one-factor ablations.

Uses the frozen candidate, the recorded literal patches and fixed development
seeds. Does not modify candidate source or inspect the held-out panel. Run from
the parent evaluation directory with: python candidates/replay_ablation.py.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation import digest, diagnostics, ts_auc
from stress import corpus, load_detector, run


def main() -> None:
    root = Path(__file__).resolve().parent
    expected = json.loads((root / "ablation_report.json").read_text())
    payload = {k: v for k, v in expected.items() if k != "report_sha256"}
    if digest(payload) != expected["report_sha256"]:
        raise ValueError("ablation record does not match its retained hash")
    source = (root / "calibrated.py").read_bytes()
    if hashlib.sha256(source).hexdigest() != expected["base_source_sha256"]:
        raise ValueError("candidate differs from the frozen ablation source")
    if expected["seeds"] != [10000, 10015]:
        raise ValueError("only the recorded development panel is allowed")
    cases = corpus(10000, 16)
    with tempfile.TemporaryDirectory(prefix="adia-ablation-") as directory:
        for name, record in sorted(expected["variants"].items()):
            before, after = (record["literal_patch"][k] for k in ("before", "after"))
            text = source.decode("utf-8")
            if text.count(before) != 1:
                raise ValueError(f"{name}: literal patch is absent or ambiguous")
            # Fixed temporary filename avoids using record keys as paths.
            path = Path(directory) / "variant.py"
            path.write_text(text.replace(before, after), encoding="utf-8")
            factory, _ = load_detector(path, record["source_sha256"], "OnlineBreakDetector")
            traces, _ = run(factory, cases)
            alarms = {k: v["null_false_alarms"] for k, v in diagnostics(traces).items()
                      if k.startswith("null_")}
            if ts_auc(traces) != record["metric"] or alarms != record["null_false_alarms"]:
                raise ValueError(f"{name}: retained diagnostic did not reproduce")
            print(f"PASS {name}: TS-AUC={record['metric']['ts_auc']:.12f}", flush=True)


if __name__ == "__main__":
    main()
