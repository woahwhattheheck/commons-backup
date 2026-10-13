"""Create an isolated synthetic Git repository, plan, audits and replay receipts.

Never points at Commons, contacts a provider, or modifies an existing directory.
For a scaling case use --retained-files 100000. Audit timing excludes fixture setup.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
import treeguard as g
from test_treeguard import Fixture, REPOSITORY


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--retained-files", type=int, default=3)
    args = parser.parse_args()
    if not 3 <= args.retained_files <= 100000:
        parser.error("retained-files must be between 3 and 100000")
    try:
        args.out.mkdir(mode=0o700)
    except OSError as exc:
        parser.error("out must be a new directory: " + type(exc).__name__)
    out = args.out.resolve()
    repo = out / "synthetic-repo"
    repo.mkdir()
    env = dict(os.environ, GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
    for name in list(env):
        if name.startswith("GIT_") and name not in {"GIT_CONFIG_NOSYSTEM", "GIT_CONFIG_GLOBAL"}:
            del env[name]
    setup_started = time.perf_counter()
    f = Fixture()
    if args.retained_files > 3:
        retained = {f"file-{i:06d}.txt".encode(): f.old for i in range(args.retained_files - 2)}
        f.product_tree = f.store.tree(retained)
        f.base_entries[b"products"] = g.Entry("040000", f.product_tree)
        f.base_tree = f.store.tree(f.base_entries)
        f.base = f.store.commit(f.base_tree)
        f.contract["base_commit"] = f.base
        entries = dict(f.base_entries)
        entries[b"p"] = f.good_entries[b"p"]
        f.good_tree = f.store.tree(entries)
        f.good = f.store.commit(f.good_tree, [f.base])
        f.bad = f.store.commit(f.bad_tree, [f.base], b"synthetic omitted-base-tree regression")
    def git(*cmd, data=None):
        r = subprocess.run(["git", "-C", str(repo), *cmd], input=data,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, check=False)
        if r.returncode:
            raise RuntimeError("synthetic Git setup failed: " + r.stderr.decode("utf-8", "replace"))
        return r.stdout
    git("init", "-q")
    for oid, (kind, raw) in f.store.objects.items():
        got = git("hash-object", "-w", "-t", kind, "--stdin", data=raw).decode().strip()
        if got != oid:
            raise RuntimeError("fixture object mismatch")
    git("update-ref", "refs/heads/main", f.base)
    contract = g.canonical(f.contract)
    pin = g.sha256(contract)
    (out / "contract.json").write_bytes(contract)
    setup_seconds = time.perf_counter() - setup_started
    py = [sys.executable] + (["-O"] if sys.flags.optimize else [])
    script = str(Path(g.__file__).resolve())
    common = ["--contract", str(out / "contract.json"), "--contract-sha256", pin,
              "--repository", REPOSITORY]
    records = []
    def invoke(label, mode, extra, expected_rc):
        cmd = [*py, script, mode, *common, *extra, "--output", str(out / (label + ".json"))]
        started = time.perf_counter()
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        elapsed = time.perf_counter() - started
        (out / (label + ".stderr.txt")).write_bytes(r.stderr)
        records.append({"label": label, "command": cmd, "exit_code": r.returncode,
                        "expected_exit_code": expected_rc, "wall_seconds": round(elapsed, 6)})
        if r.returncode != expected_rc:
            raise RuntimeError(label + " failed: " + r.stderr.decode("utf-8", "replace"))
    invoke("plan", "plan", ["--repo", str(repo), "--ref", "refs/heads/main"], 0)
    for label, candidate, expected in [("good", f.good, 0), ("omitted-base", f.bad, 1)]:
        invoke(label, "audit", ["--repo", str(repo), "--candidate", candidate, "--ref", "refs/heads/main"], expected)
        invoke(label + "-replay", "replay", ["--report", str(out / (label + ".json")), "--candidate", candidate], 0)
    good = g.load_json((out / "good.json").read_bytes())
    bad = g.load_json((out / "omitted-base.json").read_bytes())
    result = {"evidence_class": "SYNTHETIC_LOCAL_REAL_GIT_DEMONSTRATION",
              "is_commons_repository_audit": False, "retained_leaf_paths": args.retained_files,
              "python": platform.python_version(), "git": git("--version").decode().strip(),
              "platform": platform.platform(), "python_optimization": sys.flags.optimize,
              "fixture_setup_seconds": round(setup_seconds, 6), "base_commit": f.base,
              "good_candidate": f.good, "omitted_base_candidate": f.bad,
              "contract_sha256": pin, "good_state": good["state"], "bad_state": bad["state"],
              "base_tree_objects_read": good["base_tree_objects_read"],
              "retained_product_subtree_read": f.product_tree in [o["oid"] for o in good["witness"]["objects"]],
              "commands": records, "remote_mutation_performed": False, "merge_authorized": False}
    g.publish(str(out / "demo-receipt.json"), result)
    print(json.dumps({key: value for key, value in result.items() if key != "commands"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
