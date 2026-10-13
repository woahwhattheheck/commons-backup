"""Shard the UNMODIFIED official evaluator across cores by seed.

Faithfulness: evaluate.py is never edited. Each shard is an independent
evaluator process over a disjoint seed subset. Per-game state (cfg, env,
state, agent processes) is rebuilt inside play() from (seed, candidate_seat,
rng_seed, specs) only, so shard assignment cannot change any game result.
"""
import argparse, json, os, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

SP = Path(os.environ.get("V25_WORK","/tmp/v25"))
PY = str(SP / ".venv/bin/python")
EVAL = str(SP / "v2/checks/reference/evaluator/evaluate.py")
R = Path(os.environ.get("V25_REPO", Path(__file__).resolve().parents[2])) / "revenue/kaggriculture"

POOL = {
    "starter":      "official_starter",
    "arlene":       f"{R}/cloud-execution-lab/runtime/variants/v1/reference/next-panel/vendor/arlene.py::agent",
    "apex":         f"{R}/cloud-policy-portfolio/vendor/apex/main.py::agent",
    "kaito_v43":    f"{R}/cloud-frontier-policy/vendor/kaito_v43.py::agent",
    "cok_v10":      f"{R}/cloud-policy-portfolio/revision2/vendor/opponents/cok-v10.py::agent",
    "public_bt12":  f"{R}/cloud-frontier-decision/public-opponent/submission.py::agent",
    "v1_submitted": str(SP / "v1/main.py") + "::agent",
    # S11 adversarial bank (new; licensed public opponents). Paths are absolute /tmp/bank.
    "official_starter": "/tmp/bank/official_starter/agent.py::agent",
    "official_random":  "/tmp/bank/official_random/agent.py::agent",
    "official_pass":    "/tmp/bank/official_pass/agent.py::agent",
    "deepesh_wheat":    "/tmp/bank/deepesh_wheat/agent.py::agent",
    "amey_premium":     "/tmp/bank/amey_premium/agent.py::agent",
    "amey_plan":        "/tmp/bank/amey_plan/agent.py::agent",
    "barnyard_v5":      "/tmp/bank/barnyard_v5/agent.py::agent",
    "moon_melons":      "/tmp/bank/moon_melons/agent.py::agent",
    "lonespear_care":   "/tmp/bank/lonespear_care/agent.py::agent",
    "soil_rain":        "/tmp/bank/soil_rain/agent.py::agent",
    "c95_highscore":    "/tmp/bank/c95_highscore/agent.py::agent",
    "apache_builder":   "/tmp/bank/apache_builder/agent.py::agent",
}

def shard(seeds, n):
    out = [[] for _ in range(n)]
    for i, s in enumerate(seeds):
        out[i % n].append(s)
    return [x for x in out if x]

def run_shard(idx, seeds, opps, outdir, action_timeout, candidate):
    out = outdir / f"shard{idx:02d}.json"
    cmd = [PY, "-B", EVAL,
           "--engine-dir", str(SP / "engine"),
           "--loader", f"{R}/20260907-offline-agent/evaluate.py",
           "--candidate", candidate,
           "--seeds", ",".join(str(s) for s in seeds),
           "--action-timeout", str(action_timeout),
           "--startup-timeout", "60", "--game-timeout", "1800",
           "--output", str(out)]
    for o in opps:
        cmd += ["--opponent", f"{o}={POOL[o]}"]
    t0 = time.time()
    p = subprocess.run(cmd, capture_output=True, text=True)
    lines = [l for l in p.stdout.splitlines() if l.startswith('{"opponent"')]
    games = [json.loads(l) for l in lines]
    for g in games:
        print(json.dumps(g), flush=True)
    return {"shard": idx, "seeds": seeds, "seconds": round(time.time() - t0, 1),
            "games": games, "rc": p.returncode, "stderr": p.stderr[-2000:]}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", required=True)
    ap.add_argument("--opponents", required=True)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--action-timeout", type=float, default=15.0)
    ap.add_argument("--candidate", default=str(SP / "v2/main.py"))
    ap.add_argument("--outdir", required=True)
    a = ap.parse_args()

    seeds = [int(s) for s in a.seeds.split(",")]
    opps = a.opponents.split(",")
    outdir = Path(a.outdir); outdir.mkdir(parents=True, exist_ok=True)
    groups = shard(seeds, a.workers)

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=len(groups)) as ex:
        futs = [ex.submit(run_shard, i, g, opps, outdir, a.action_timeout, a.candidate)
                for i, g in enumerate(groups)]
        shards = [f.result() for f in futs]
    wall = time.time() - t0

    games = [g for s in shards for g in s["games"]]
    done = [g for g in games if g["status"] == "complete"]
    agg = {}
    for g in done:
        cs = g["candidate_seat"]; m = g["scores"][cs] - g["scores"][1 - cs]
        d = agg.setdefault(g["opponent"], {"games": 0, "W": 0, "T": 0, "L": 0, "margins": []})
        d["games"] += 1; d["margins"].append(m)
        d["W" if m > 0 else ("T" if m == 0 else "L")] += 1
    for d in agg.values():
        d["mean_margin"] = round(sum(d["margins"]) / len(d["margins"]), 3) if d["margins"] else None
        del d["margins"]

    summary = {"wall_seconds": round(wall, 1), "workers": len(groups),
               "scheduled": len(seeds) * len(opps) * 2, "completed": len(done),
               "failed": len(games) - len(done),
               "throughput_games_per_min": round(len(games) / (wall / 60), 2),
               "shard_seconds": [s["seconds"] for s in shards],
               "per_opponent": agg,
               "failures": [g for g in games if g["status"] != "complete"]}
    (outdir / "SUMMARY.json").write_text(json.dumps(summary, indent=2))
    (outdir / "GAMES.jsonl").write_text("".join(json.dumps(g) + "\n" for g in games))
    if len(done) == 0:
        sys.stderr.write("FATAL: 0 games completed. shard stderr:\n")
        for sh in shards:
            sys.stderr.write("shard %d rc=%s\n%s\n" % (sh["shard"], sh["rc"], sh["stderr"]))
        sys.exit(2)
    print("SUMMARY " + json.dumps(summary))

main()
