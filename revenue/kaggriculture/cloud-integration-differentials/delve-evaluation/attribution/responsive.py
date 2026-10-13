"""Execute targeted development ablations through the unchanged retained driver."""
from __future__ import annotations
import argparse
import gzip
import json
from pathlib import Path
import platform
import time
from attribute import load, digest

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--arms", nargs="+", choices=("suppress360", "due381", "joint"),
                        default=["suppress360", "due381", "joint"])
    args = parser.parse_args()
    root, out = args.package.resolve(), args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    manifest = json.loads((root / "MANIFEST.json").read_text())
    for name, record in manifest["files"].items():
        source = root / name
        if source.stat().st_size != record["bytes"] or digest(source) != record["sha256"]:
            raise ValueError("Saved input differs: " + name)
    prefix = "/mnt/data/delve-work"
    def relocate(value):
        if isinstance(value, str) and value.startswith(prefix):
            return str(root) + value[len(prefix):]
        if isinstance(value, dict):
            return {key: relocate(item) for key, item in value.items()}
        if isinstance(value, list):
            return [relocate(item) for item in value]
        return value
    setup = relocate(json.loads((root / "evaluation/SETUP-AS-EXECUTED.json").read_text()))
    for label, record in setup["source_files"].items():
        if digest(Path(record["path"])) != record["sha256"]:
            raise ValueError("Source changed: " + label)
    ev = load("delve_attr_live_eval", Path(setup["evaluator"]))
    runner = load("delve_attr_retained_runner", root / "evaluation/run.py")
    engine, hashes = ev.get_engine(Path(setup["engine_dir"]), Path(setup["loader"]), prepare=False)
    seed, position = 9965019, 0
    summaries = json.loads((root / "evaluation/SUMMARY.json").read_text())
    cell = next(c for c in summaries["cells"] if (c["seed"], c["player"]) == (seed, position))
    original = json.loads((root / "evaluation" / cell["arms"]["funded"]["result_path"]).read_text())
    experiment = {"kind": "responsive_targeted_development_ablation", "seed": seed,
                  "position": position, "arms": args.arms, "reused_control": cell["arms"]["funded"],
                  "engine_sha256": hashes, "setup": setup, "python": platform.python_version(),
                  "started_unix": time.time(),
                  "sources": {p.name: digest(p) for p in (HERE/"responsive.py", HERE/"ablation_agent.py", HERE/"attribute.py")},
                  "limits": {"action_seconds": 1.0, "startup_seconds": 10.0, "game_seconds": 120.0},
                  "interpretation": "One already-used development regime; no held data or general policy."}
    (out / "EXPERIMENT.json").write_text(json.dumps(experiment, indent=2) + "\n")
    (out / "ablation_agent.py").write_bytes((HERE / "ablation_agent.py").read_bytes())
    completed = []
    for arm in args.arms:
        telemetry = out / (arm + ".telemetry.jsonl")
        (out / "responsive-setup.json").write_text(json.dumps({"package": str(root), "telemetry": str(telemetry)})+"\n")
        recorder = runner.RecordedEngine(engine, out / (arm + ".frames.jsonl.gz"))
        try:
            result = ev.play(recorder, [str(out/"ablation_agent.py")+"::"+arm, setup["opponent"]],
                             Path(setup["engine_dir"]), Path(setup["loader"]), seed, position,
                             action_timeout=1.0, startup_timeout=10.0, game_timeout=120.0)
        finally:
            recorder.close()
        lines = [json.loads(line) for line in telemetry.read_text().splitlines()] if telemetry.exists() else []
        data = telemetry.read_bytes() if telemetry.exists() else b""
        (out / (arm + ".telemetry.jsonl.gz")).write_bytes(gzip.compress(data, mtime=0))
        result.update(arm=arm, frame_count=recorder.frames,
                      interventions=[r["intervention"] for r in lines if r["intervention"]["applied"]],
                      max_inner_seconds=max((r["decision_seconds"] for r in lines), default=None))
        if result["status"] == "complete":
            result["own_rival_delta"] = [result["scores"][s] - original["scores"][s] for s in (position, 1-position)]
            result["margin_delta"] = result["own_rival_delta"][0]-result["own_rival_delta"][1]
        result["files"] = {p.name: {"sha256": digest(p), "bytes": p.stat().st_size}
                           for p in (out/(arm+".frames.jsonl.gz"), out/(arm+".telemetry.jsonl.gz"))}
        (out/(arm+".json")).write_text(json.dumps(result, indent=2)+"\n")
        completed.append(result)
        print(json.dumps({k:result.get(k) for k in ("arm","status","scores","failure","own_rival_delta","margin_delta","wall_seconds","max_inner_seconds","interventions")}), flush=True)
        (out / "RESULTS.json").write_text(json.dumps(completed, indent=2)+"\n")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
