"""Reproducible Kaggriculture export and actual-extraction regression checks."""
from __future__ import annotations

import argparse
import ast
import gzip
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import sys
import tarfile
import tempfile
import time

HERE = Path(__file__).resolve().parent
EVALUATOR = HERE.parent / "cloud-eval/evaluate.py"
ARCHIVE_LIMIT = 100 * 1024**2
PAYLOAD_LIMIT = 8 * 1024**3
MANIFEST_NAME = "PACK-MANIFEST.json"


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def canonical(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def member_name(name):
    if (not isinstance(name, str) or not name or "\\" in name or
        name.startswith("/") or any(p in ("", ".", "..") for p in name.split("/"))):
        raise ValueError(f"Expected a relative archive file name: {name!r}")
    return str(PurePosixPath(name))


def read_spec(path):
    path = Path(path).resolve(strict=True)
    spec = json.loads(path.read_text())
    if spec.get("schema_version") != 1 or not isinstance(spec.get("files"), dict):
        raise ValueError("Expected schema_version 1 and a files mapping")
    if "main.py" not in spec["files"] or MANIFEST_NAME in spec["files"]:
        raise ValueError("Supply main.py; PACK-MANIFEST.json is generated")
    if not spec.get("label") or not isinstance(spec.get("provenance"), dict):
        raise ValueError("Supply a label and provenance with source/license attribution")
    callable_name = spec.get("source_callable", "agent")
    if not isinstance(callable_name, str) or not callable_name.isidentifier():
        raise ValueError("source_callable must be a Python identifier")
    sources = {}
    for target, item in spec["files"].items():
        member_name(target)
        source = (path.parent / item["source"]).resolve(strict=True)
        expected = item["sha256"]
        if (not isinstance(expected, str) or len(expected) != 64 or
                any(c not in "0123456789abcdef" for c in expected)):
            raise ValueError(f"Supply an exact SHA-256 for {target}")
        if not source.is_file() or digest(source) != expected:
            raise ValueError(f"Source bytes do not match the spec: {target}")
        if target.endswith(".py"):
            ast.parse(source.read_bytes(), filename=target)
        sources[target] = source
    return spec, sources


def build(spec_path, output):
    spec, sources = read_spec(spec_path)
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError(f"Use a new output directory: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="kag-pack-build-", dir=output.parent) as tmp:
        temporary = Path(tmp)
        payload = temporary / "payload"
        payload.mkdir()
        members = {}
        for name, source in sorted(sources.items()):
            target = payload / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            actual = digest(target)
            if actual != spec["files"][name]["sha256"]:
                raise ValueError(f"Source moved during export: {name}")
            members[name] = {"sha256": actual, "bytes": target.stat().st_size}
        manifest = {"schema_version": 1, "label": spec["label"],
                    "source_callable": spec.get("source_callable", "agent"),
                    "provenance": spec["provenance"], "members": members,
                    "generator_sha256": digest(__file__),
                    "archive_limit_bytes": ARCHIVE_LIMIT, "payload_limit_bytes": PAYLOAD_LIMIT}
        (payload / MANIFEST_NAME).write_bytes(canonical(manifest))
        total = sum(v["bytes"] for v in members.values()) + (payload / MANIFEST_NAME).stat().st_size
        if total > PAYLOAD_LIMIT:
            raise ValueError("Extracted payload exceeds 8 GiB")
        archive = temporary / "submission.tar.gz"
        with archive.open("wb") as raw:
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0, compresslevel=9) as zipped:
                with tarfile.open(fileobj=zipped, mode="w", format=tarfile.PAX_FORMAT) as tar:
                    for name in sorted([*members, MANIFEST_NAME]):
                        file = payload / name
                        info = tarfile.TarInfo(name)
                        info.size, info.mode, info.mtime = file.stat().st_size, 0o644, 0
                        info.uid = info.gid = 0
                        info.uname = info.gname = ""
                        with file.open("rb") as stream:
                            tar.addfile(info, stream)
        if archive.stat().st_size > ARCHIVE_LIMIT:
            raise ValueError("Submission archive exceeds 100 MiB")
        receipt = {"schema_version": 1, "archive": "submission.tar.gz",
                   "archive_sha256": digest(archive), "archive_bytes": archive.stat().st_size,
                   "payload_bytes": total, "manifest_sha256": digest(payload / MANIFEST_NAME),
                   "candidate_sha256": members["main.py"]["sha256"],
                   "spec_sha256": digest(spec_path), "label": spec["label"],
                   "build_python": sys.version, "selection": spec["provenance"].get("selection_status")}
        output.mkdir()
        shutil.copyfile(archive, output / "submission.tar.gz")
        (output / "receipt.json").write_bytes(canonical(receipt))
    verify(output)
    return receipt


def verify(bundle, extract_to=None):
    bundle = Path(bundle).resolve(strict=True)
    receipt = json.loads((bundle / "receipt.json").read_text())
    archive = bundle / "submission.tar.gz"
    if (receipt.get("schema_version") != 1 or receipt.get("archive") != archive.name or
        archive.stat().st_size != receipt["archive_bytes"] or
        archive.stat().st_size > ARCHIVE_LIMIT or digest(archive) != receipt["archive_sha256"]):
        raise ValueError("Archive differs from its receipt or exceeds the size limit")
    with tarfile.open(archive, "r:gz") as tar:
        entries = tar.getmembers()
        names = [member_name(e.name) for e in entries]
        if len(set(names)) != len(names) or any(not e.isfile() for e in entries):
            raise ValueError("Expected unique regular files in the archive")
        if MANIFEST_NAME not in names or tar.getmember(MANIFEST_NAME).size > 1024**2:
            raise ValueError("Missing or oversized package manifest")
        raw = tar.extractfile(MANIFEST_NAME).read()
        if hashlib.sha256(raw).hexdigest() != receipt["manifest_sha256"]:
            raise ValueError("Package manifest differs from the receipt")
        manifest = json.loads(raw)
        expected = manifest["members"]
        if manifest.get("schema_version") != 1 or set(names) != set(expected) | {MANIFEST_NAME}:
            raise ValueError("Archive member list differs from the manifest")
        if "main.py" not in expected or expected["main.py"]["sha256"] != receipt["candidate_sha256"]:
            raise ValueError("Candidate differs from the receipt")
        total = sum(e.size for e in entries)
        if total != receipt["payload_bytes"] or total > PAYLOAD_LIMIT:
            raise ValueError("Extracted payload differs from its receipt or exceeds 8 GiB")
        for name, item in expected.items():
            entry = tar.getmember(name)
            if entry.size != item["bytes"]:
                raise ValueError(f"Size mismatch: {name}")
            with tar.extractfile(entry) as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != item["sha256"]:
                    raise ValueError(f"Hash mismatch: {name}")
        if extract_to is not None:
            destination = Path(extract_to).resolve()
            destination.mkdir(parents=True, exist_ok=False)
            for entry in entries:
                target = destination / entry.name
                target.parent.mkdir(parents=True, exist_ok=True)
                with tar.extractfile(entry) as source, target.open("xb") as output:
                    shutil.copyfileobj(source, output)
                if entry.name in expected and digest(target) != expected[entry.name]["sha256"]:
                    raise ValueError(f"Extracted bytes changed: {entry.name}")
    return manifest


def load_evaluator():
    spec = importlib.util.spec_from_file_location("kag_pack_existing_eval", EVALUATOR)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_adapter(path, main):
    # Imports, compilation and source initialization run in the first timed call.
    path.write_text(
        "import importlib.util as _util\n_runner = None\n"
        "def agent(observation, configuration=None):\n"
        "    global _runner\n"
        "    if _runner is None:\n"
        f"        spec = _util.spec_from_file_location('kag_pack_contract', {str(HERE / 'official.py')!r})\n"
        "        module = _util.module_from_spec(spec)\n"
        "        spec.loader.exec_module(module)\n"
        f"        _runner = module.make_agent({str(main)!r})\n"
        "    return _runner(observation, configuration or {})\n")


def runtime():
    files = ["/sys/fs/cgroup/cpu.max", "/sys/fs/cgroup/memory.max",
             "/sys/fs/cgroup/pids.max", "/proc/net/route"]
    observed = {}
    for name in files:
        try:
            observed[name] = Path(name).read_text().strip()
        except OSError:
            observed[name] = None
    return {"python": sys.version, "platform": platform.platform(), "observed": observed,
            "tmp_disk_free_bytes": shutil.disk_usage(tempfile.gettempdir()).free,
            "hosted_runner": False,
            "measurement": "Parent RPC wall deadlines; child self-reported CPU and peak RSS. "
                "The first exported call includes adapter setup and pinned file-loader initialization. "
                "Cgroup/route observations do not certify the hosted runtime or its 8-GiB disk quota."}


def initial_state(ev, engine, seed):
    cfg = ev.Struct({k: v.get("default") if isinstance(v, dict) else v
                     for k, v in engine.specification["configuration"].items()})
    cfg.seed = seed
    env = ev.Struct(configuration=cfg, done=False, info={})
    state = [ev.Struct(observation=ev.Struct(), action={}, status="ACTIVE", reward=0) for _ in (0, 1)]
    engine.interpreter(state, env)
    if cfg.get("seed") is not None:
        raise ValueError("Engine seed must remain hidden from candidates")
    for item in state:
        item.observation.step = 0
        item.observation.remainingOverageTime = 0
    return cfg, state


def cold_probe(ev, spec, engine_dir, observation, configuration, action_timeout, rng_seed):
    started = time.perf_counter()
    actor = ev.Actor(spec, engine_dir, ev.LOADER, rng_seed)
    response = None
    try:
        if actor.ready.get("kind") == "ready":
            response = actor.act(observation, configuration, action_timeout)
        return {"ready": actor.ready, "first_response": response,
                "startup_seconds": actor.stats["startup_seconds"],
                "first_rpc_seconds": actor.stats["rpc_seconds"][0] if actor.stats["rpc_seconds"] else None,
                "process_start_through_first_response_seconds": time.perf_counter() - started}
    finally:
        actor.close()


def check(bundle, spec_path, engine_dir, opponent, output, seed=6100003,
          action_timeout=1.0, game_timeout=120.0):
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError(f"Use a new report directory: {output}")
    if any(not math.isfinite(t) or t <= 0 for t in (action_timeout, game_timeout)):
        raise ValueError("Timeouts must be finite and positive")
    spec, sources = read_spec(spec_path)
    manifest = verify(bundle)
    if (set(sources) != set(manifest["members"]) or
        any(digest(path) != manifest["members"][name]["sha256"] for name, path in sources.items()) or
        manifest["source_callable"] != spec.get("source_callable", "agent")):
        raise ValueError("Reference files/callable do not match the exported package")
    ev = load_evaluator()
    engine_dir = Path(engine_dir).resolve(strict=True)
    engine, hashes = ev.get_engine(engine_dir)
    rival = ev.resolve_spec(opponent)
    reference = str(sources["main.py"]) + "::" + manifest["source_callable"]
    output.mkdir(parents=True)
    report = {"schema_version": 1, "phase": "packaging_regression", "label": manifest["label"],
              "candidate_sha256": manifest["members"]["main.py"]["sha256"],
              "archive_receipt": json.loads((Path(bundle) / "receipt.json").read_text()),
              "evaluator_sha256": digest(EVALUATOR), "engine_ref": ev.ENGINE_REF,
              "engine_sha256": hashes, "engine_loader_sha256": digest(ev.LOADER),
              "pack_sha256": digest(__file__), "official_adapter_sha256": digest(HERE / "official.py"),
              "upstream": json.loads((HERE / "upstream/manifest.json").read_text()),
              "opponent": ev.fingerprint(rival), "source_files": manifest["members"],
              "seed": seed, "agent_rng_seed": 20260907, "runtime": runtime(),
              "limits": {"action_rpc_seconds": action_timeout, "startup_seconds": 10,
                         "game_seconds": game_timeout, "remaining_overage_time": 0},
              "cold_probes": [], "games": [], "parity": [], "complete": False}
    report_path = output / "report.json"
    def save():
        temporary = output / "report.tmp"
        temporary.write_bytes(canonical(report))
        os.replace(temporary, report_path)
    save()
    with tempfile.TemporaryDirectory(prefix="kag-pack-check-") as tmp:
        temp = Path(tmp)
        extracted = temp / "extracted"
        verify(bundle, extract_to=extracted)
        adapter = temp / "official_adapter.py"
        write_adapter(adapter, extracted / "main.py")
        cfg, state = initial_state(ev, engine, seed)
        for seat in (0, 1):
            pair = {}
            for label, entry in (("reference", reference), ("exported", str(adapter))):
                pair[label] = cold_probe(ev, entry, engine_dir, state[seat].observation,
                                        cfg, action_timeout, 20260907)
            first, second = (pair[x]["first_response"] for x in ("reference", "exported"))
            pair["same_action"] = (first is not None and second is not None and
                first.get("kind") == second.get("kind") == "action" and
                ev.encoded(first["action"]) == ev.encoded(second["action"]))
            pair["seat"] = seat
            report["cold_probes"].append(pair)
            save()
        if all(p["same_action"] for p in report["cold_probes"]):
            for seat in (0, 1):
                results = {}
                for label, entry in (("reference", reference), ("exported", str(adapter))):
                    roster = [entry, rival] if seat == 0 else [rival, entry]
                    game = ev.play(engine, roster, engine_dir, ev.LOADER, seed, seat,
                                   action_timeout=action_timeout, game_timeout=game_timeout)
                    game["loading"] = label
                    report["games"].append(game)
                    results[label] = game
                    save()
                first, second = results["reference"], results["exported"]
                report["parity"].append({"seat": seat,
                    "complete": first["status"] == second["status"] == "complete",
                    "same_scores": first["scores"] == second["scores"],
                    "same_trace": first["trace_sha256"] == second["trace_sha256"]})
                save()
        report["complete"] = (len(report["parity"]) == 2 and
            all(p["complete"] and p["same_scores"] and p["same_trace"] for p in report["parity"]))
    save()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    builder = sub.add_parser("build")
    builder.add_argument("--spec", type=Path, required=True)
    builder.add_argument("--output", type=Path, required=True)
    verifier = sub.add_parser("verify")
    verifier.add_argument("--bundle", type=Path, required=True)
    verifier.add_argument("--extract-to", type=Path)
    checker = sub.add_parser("check")
    checker.add_argument("--bundle", type=Path, required=True)
    checker.add_argument("--spec", type=Path, required=True)
    checker.add_argument("--engine-dir", type=Path, required=True)
    checker.add_argument("--opponent", required=True, help="Existing evaluator path.py::function or official_starter")
    checker.add_argument("--output", type=Path, required=True)
    checker.add_argument("--seed", type=int, default=6100003)
    checker.add_argument("--action-timeout", type=float, default=1.0)
    checker.add_argument("--game-timeout", type=float, default=120.0)
    args = parser.parse_args()
    try:
        if args.command == "build":
            result = build(args.spec, args.output)
        elif args.command == "verify":
            manifest = verify(args.bundle, args.extract_to)
            result = {"verified": True, "label": manifest["label"], "members": len(manifest["members"])}
        else:
            report = check(args.bundle, args.spec, args.engine_dir, args.opponent,
                           args.output, args.seed, args.action_timeout, args.game_timeout)
            result = {"complete": report["complete"], "parity": report["parity"],
                      "report": str(args.output / "report.json")}
            print(json.dumps(result, indent=2))
            return 0 if report["complete"] else 1
        print(json.dumps(result, indent=2))
        return 0
    except (ValueError, OSError, KeyError, TypeError, tarfile.TarError) as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
