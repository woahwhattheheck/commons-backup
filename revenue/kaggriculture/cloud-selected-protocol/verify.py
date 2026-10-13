# SPDX-License-Identifier: MIT
"""Replay published development observations through a standalone TITAN package.

This executes policy functions, not games. Historical action labels never enter
an actor. Python import/socket canaries detect accidental dependencies; they are
not an operating-system sandbox. Run only trusted code in a cloud container.
"""
from __future__ import annotations

import argparse
import contextlib
import gzip
import hashlib
import importlib.abc
import importlib.util
import json
import math
import os
from pathlib import Path, PurePosixPath
import platform
import random
import selectors
import shutil
import socket
import subprocess
import sys
import sysconfig
import tarfile
import tempfile
import time

SOURCE_REF = "c533e7ce210dbe77e078e566a71b15b175db0da9"
ENGINE_REF = "28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c"
SPEC_BLOB = "b354d06b742fe48402513792253f1a5c29366b20"
SCHEDULER_SHA = "32c8610c9827d1686a6f831e2c4b6af4c00d32d2aa04dcf25699d976d6d97dd9"
ARCHIVES = {
    "selected.tar.gz": (181166, "5d3a2bf3878808679820ff7f5a5ca7533c41888366c5dcd358f15ff0213f1f10"),
    "reference.tar.gz": (59966, "a14f9bbc7e10753fef2d5e983e9746e107940d7081b8934fb499561191e9c3c7"),
}
PARTS = (
    (8000000, "a354bd1603b76d9d449991f5edfa2f18874accec0b739a8e2bb0793efe5d8b7c"),
    (7407052, "15e47251bc665eed88af93ca734d8cc97560bb4825fc00496cc78d6c169f373a"),
)
EVIDENCE_SHA = "f0459fa624221267dc73ff9fa56f8cfd6a91649157fd3e28b4f337c53f1dcab8"
TRACE_PINS = {
    "candidate-apex-9600803-seat0.jsonl.gz": (212977, "f9167296fe312f3b488a7e9a32e4d37c321f5ac268983d3bf7b873c0f6ab7b53"),
    "candidate-apex-9600803-seat1.jsonl.gz": (213023, "8f84be3b7b7caf3815bd966933c718c48f7b084da9eef5d2ffb0a3dc9b85a77a"),
    "candidate-arlene-9600803-seat0.jsonl.gz": (207692, "81cf8ad7126b3887bbdb9ac2856da96a8ba1e8ffaedfa92409bb38d0c994cd74"),
    "candidate-arlene-9600803-seat1.jsonl.gz": (207910, "68781e1470ade80fda286897fef477b10ca759ffb54a9e4fa231b483314cc060"),
}
MAX_PACKET = 2 * 1024 * 1024


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_pin(path, expected):
    data = Path(path).read_bytes()
    if (len(data), hashlib.sha256(data).hexdigest()) != tuple(expected):
        raise ValueError(f"Published input differs: {Path(path).name}")
    return data


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def member_name(name):
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or "\\" in name:
        raise ValueError("Unsafe archive member")
    return str(path)


def extract_runtime(archive, destination):
    """Extract regular source files without following archive links."""
    destination = Path(destination)
    if destination.exists():
        raise ValueError("Runtime destination must be fresh")
    destination.mkdir(parents=True)
    seen = set()
    with tarfile.open(archive, "r:gz") as source:
        for member in source:
            name = member_name(member.name)
            if member.isdir():
                continue
            if not member.isfile() or name in seen:
                raise ValueError("Non-regular or duplicate runtime member")
            seen.add(name)
            output = destination / name
            output.parent.mkdir(parents=True, exist_ok=True)
            with source.extractfile(member) as stream:
                output.write_bytes(stream.read())
    if not seen:
        raise ValueError("Empty runtime archive")


def prepare(checkout, output):
    """Transport exact artifacts and four spent development traces, not policies."""
    checkout, output = Path(checkout).resolve(), Path(output).resolve()
    actual = subprocess.check_output(["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True).strip()
    if actual != SOURCE_REF:
        raise ValueError("Source checkout is not the recorded integration commit")
    output.mkdir(parents=True, exist_ok=True)
    root = checkout / "revenue/kaggriculture"
    exports = root / "cloud-execution-lab/exports"
    inputs = {
        "selected.tar.gz": root / "cloud-titan-composition/artifacts/titan-selected.tar.gz",
        "reference.tar.gz": exports / "titan-sell-v3-source.tar.gz",
    }
    for name, path in inputs.items():
        (output / name).write_bytes(verify_pin(path, ARCHIVES[name]))
    with tempfile.TemporaryDirectory(prefix="titan-evidence-") as temporary:
        evidence = Path(temporary) / "evidence.tar.gz"
        with evidence.open("wb") as joined:
            for number, pin in enumerate(PARTS, 1):
                part = exports / f"titan-sell-lab-evidence.tar.gz.part{number:02d}"
                joined.write(verify_pin(part, pin))
        if sha(evidence) != EVIDENCE_SHA:
            raise ValueError("Complete evidence archive digest differs")
        wanted = {"runtime/development-v3-traces/" + name: "traces/" + name for name in TRACE_PINS}
        wanted["reference/engine/kaggriculture.json"] = "kaggriculture.json"
        found = set()
        # Unselected members are not extracted, parsed, or evaluated.
        with tarfile.open(evidence, "r:gz") as source:
            for member in source:
                name = member_name(member.name)
                if name not in wanted:
                    continue
                if not member.isfile() or name in found:
                    raise ValueError("Invalid selected evidence member")
                found.add(name)
                path = output / wanted[name]
                path.parent.mkdir(parents=True, exist_ok=True)
                with source.extractfile(member) as stream:
                    path.write_bytes(stream.read())
        if found != set(wanted):
            raise ValueError(f"Evidence members absent: {sorted(set(wanted) - found)}")
    for name, pin in TRACE_PINS.items():
        verify_pin(output / "traces" / name, pin)
    spec_bytes = (output / "kaggriculture.json").read_bytes()
    blob = hashlib.sha1(b"blob " + str(len(spec_bytes)).encode() + b"\0" + spec_bytes).hexdigest()
    if blob != SPEC_BLOB:
        raise ValueError("Official configuration specification differs")
    specification = json.loads(spec_bytes)
    configuration = {k: v.get("default") if isinstance(v, dict) else v
                     for k, v in specification["configuration"].items()}
    # The existing evaluator requires the engine to clear its seed before actors.
    configuration["seed"] = None
    write_json(output / "configuration.json", configuration)
    write_json(output / "INPUTS.json", {
        "schema": "titan.selected-protocol.inputs.v1", "source_commit": SOURCE_REF,
        "engine_commit": ENGINE_REF, "specification_git_blob": SPEC_BLOB,
        "configuration_sha256": sha(output / "configuration.json"),
        "archives": ARCHIVES, "traces": TRACE_PINS,
        "scope": "Four previously recorded DEVELOPMENT observation streams; no held evaluation.",
    })
    return {"source_commit": actual, "traces": len(TRACE_PINS), "output": str(output)}


class Struct(dict):
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key) from None

    def __setattr__(self, key, value):
        self[key] = value


def structify(value):
    if isinstance(value, dict):
        return Struct({key: structify(item) for key, item in value.items()})
    if isinstance(value, list):
        return [structify(item) for item in value]
    return value


def worker(entry):
    """One persistent actor; only current observation/configuration crosses IPC."""
    output = sys.stdout.buffer
    counts = {"blocked_import_attempts": 0, "network_attempts": 0}

    def send(message):
        payload = encoded(message) + b"\n"
        if len(payload) > MAX_PACKET:
            raise ValueError("Actor response exceeds packet limit")
        output.write(payload)
        output.flush()

    class NoInstalledEngine(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path=None, target=None):
            if fullname.split(".")[0] == "kaggle_environments":
                counts["blocked_import_attempts"] += 1
                raise ModuleNotFoundError("Installed Kaggle engine intentionally unavailable")
            return None

    def no_network(*args, **kwargs):
        counts["network_attempts"] += 1
        raise RuntimeError("Network unavailable in offline replay canary")

    sys.meta_path.insert(0, NoInstalledEngine())
    socket.socket.connect = no_network
    socket.socket.connect_ex = no_network
    socket.create_connection = no_network
    socket.getaddrinfo = no_network
    random.seed(20260907)  # Same candidate-role RNG as the published evaluator.
    entry = Path(entry).resolve()
    sys.path.insert(0, str(entry.parent))
    with contextlib.redirect_stdout(sys.stderr):
        try:
            started = time.perf_counter()
            spec = importlib.util.spec_from_file_location("selected_protocol_agent", entry)
            if spec is None or spec.loader is None:
                raise ValueError("Cannot load actor entrypoint")
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            function = module.agent
            if not callable(function):
                raise TypeError("Agent entrypoint is not callable")
            send({"kind": "ready", "pid": os.getpid(), "import_seconds": time.perf_counter() - started,
                  "isolated": sys.flags.isolated, "no_site": sys.flags.no_site,
                  "stdlib": sysconfig.get_path("stdlib"), "sys_path": sys.path, **counts})
            for line in sys.stdin.buffer:
                if len(line) > MAX_PACKET:
                    raise ValueError("Request exceeds packet limit")
                request = json.loads(line)
                if set(request) != {"observation", "configuration"}:
                    raise ValueError("Only current observation and configuration are accepted")
                if request["configuration"].get("seed") is not None:
                    raise ValueError("Environment seed must not enter an actor")
                obs, cfg = structify(request["observation"]), structify(request["configuration"])
                began = time.perf_counter()
                action = function(obs, cfg)
                elapsed = time.perf_counter() - began
                if not isinstance(action, dict):
                    raise TypeError("Action must be a JSON object")
                send({"kind": "action", "action": action, "call_seconds": elapsed, **counts})
        except BaseException as exc:
            send({"kind": "error", "error": f"{type(exc).__name__}: {exc}"[:1000], **counts})
            return 1
    return 0


class Actor:
    def __init__(self, entry, cwd, timeout=5.0):
        self.timeout = timeout
        self.log = tempfile.TemporaryFile()
        self.started = time.perf_counter()
        self.process = subprocess.Popen(
            [sys.executable, "-I", "-S", "-B", "-u", str(Path(__file__).resolve()), "worker", str(entry)],
            cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.log, bufsize=0,
            env={"PATH": os.defpath, "HOME": str(cwd), "LANG": "C.UTF-8"},
        )
        self.buffer = bytearray()
        self.calls, self.rpc = [], []
        self.cold_seconds = None
        try:
            self.ready = self._receive(time.perf_counter() + timeout)
            if self.ready.get("kind") != "ready":
                raise RuntimeError(f"Actor import failed: {self.ready}")
            self.startup_seconds = time.perf_counter() - self.started
        except BaseException:
            self.close()
            raise

    def _receive(self, deadline):
        with selectors.DefaultSelector() as selector:
            selector.register(self.process.stdout, selectors.EVENT_READ)
            while b"\n" not in self.buffer:
                left = deadline - time.perf_counter()
                if left <= 0 or not selector.select(left):
                    raise TimeoutError("Actor response deadline exceeded")
                data = os.read(self.process.stdout.fileno(), 65536)
                if not data:
                    raise RuntimeError("Actor exited before complete JSON response")
                self.buffer.extend(data)
                if len(self.buffer) > MAX_PACKET:
                    raise ValueError("Actor response exceeds packet limit")
        line, _, self.buffer = self.buffer.partition(b"\n")
        return json.loads(line)

    def act(self, observation, configuration):
        started = time.perf_counter()
        deadline = started + self.timeout
        payload = encoded({"observation": observation, "configuration": configuration}) + b"\n"
        if len(payload) > MAX_PACKET:
            raise ValueError("Request exceeds packet limit")
        # Nonblocking writes keep malformed or stalled actors within the deadline.
        os.set_blocking(self.process.stdin.fileno(), False)
        with selectors.DefaultSelector() as selector:
            selector.register(self.process.stdin, selectors.EVENT_WRITE)
            while payload:
                left = deadline - time.perf_counter()
                if left <= 0 or not selector.select(left):
                    raise TimeoutError("Actor request deadline exceeded")
                try:
                    count = os.write(self.process.stdin.fileno(), payload)
                except BlockingIOError:
                    continue
                payload = payload[count:]
        response = self._receive(deadline)
        if response.get("kind") != "action":
            raise RuntimeError(f"Actor action failed: {response}")
        if response.get("network_attempts") or response.get("blocked_import_attempts"):
            raise RuntimeError("Actor attempted unavailable network or engine dependency")
        self.calls.append(response["call_seconds"])
        self.rpc.append(time.perf_counter() - started)
        if self.cold_seconds is None:
            self.cold_seconds = self.startup_seconds + self.rpc[0]
        return response["action"]

    def report(self):
        values = sorted(self.calls)
        return {"pid": self.process.pid, "ready": self.ready, "actions": len(values),
                "startup_seconds": self.startup_seconds, "cold_start_plus_first_rpc_seconds": self.cold_seconds,
                "max_call_seconds": max(values, default=0.0),
                "p99_call_seconds": values[max(0, math.ceil(len(values) * .99) - 1)] if values else None,
                "max_rpc_seconds": max(self.rpc, default=0.0)}

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
        try:
            self.process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=2)
        self.process.stdin.close()
        self.process.stdout.close()
        self.log.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def load_rows(path, seat, expected_steps=719):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream]
    if len(rows) != expected_steps:
        raise ValueError("Historical stream is incomplete")
    for step, row in enumerate(rows):
        if row["step"] != step or row["observation"]["step"] != step or row["candidate_seat"] != seat:
            raise ValueError("Historical stream has discontinuous steps or wrong seat")
        if len(row["actions"]) != 2 or not isinstance(row["actions"][seat], dict):
            raise ValueError("Historical candidate action is missing")
    if not rows[-1].get("done"):
        raise ValueError("Historical stream lacks terminal observation transition")
    return rows


def replay(selected_entry, reference_entry, rows, seat, configuration, cwd, timeout):
    result = {"steps": len(rows), "mismatches": [], "recorded_action_sha256": None}
    digests = [hashlib.sha256() for _ in range(3)]
    with Actor(selected_entry, cwd, timeout) as selected, Actor(reference_entry, cwd, timeout) as reference:
        for row in rows:
            # The labels and future rows stay in this process, never in a request.
            actions = [selected.act(row["observation"], configuration),
                       reference.act(row["observation"], configuration), row["actions"][seat]]
            packets = [encoded(action) for action in actions]
            for digest, packet in zip(digests, packets):
                digest.update(packet + b"\n")
            if packets[0] != packets[1] or packets[0] != packets[2]:
                result["mismatches"].append({"step": row["step"], "selected": actions[0],
                                              "reference": actions[1], "recorded": actions[2]})
        result["actors"] = {"selected": selected.report(), "reference": reference.report()}
    result.update(zip(("selected_action_sha256", "reference_action_sha256", "recorded_action_sha256"),
                      (digest.hexdigest() for digest in digests)))
    return result


def run(inputs, output, timeout=5.0):
    inputs, output = Path(inputs).resolve(), Path(output).resolve()
    report = {"schema": "titan.selected-protocol.report.v1", "source_commit": SOURCE_REF,
              "verifier_sha256": sha(__file__), "python": platform.python_version(),
              "platform": platform.platform(), "status": "failed", "streams": [],
              "new_games": 0, "held_observation_evaluations": 0,
              "limits": "Development observation replay, not engine execution, game outcomes, hosted timing or an OS sandbox."}
    began = time.perf_counter()
    try:
        for name, pin in ARCHIVES.items():
            verify_pin(inputs / name, pin)
        configuration = json.loads((inputs / "configuration.json").read_text())
        spec_data = (inputs / "kaggriculture.json").read_bytes()
        if hashlib.sha1(b"blob " + str(len(spec_data)).encode() + b"\0" + spec_data).hexdigest() != SPEC_BLOB:
            raise ValueError("Official specification pin differs")
        expected_configuration = {k: v.get("default") if isinstance(v, dict) else v
                                  for k, v in json.loads(spec_data)["configuration"].items()}
        expected_configuration["seed"] = None
        if configuration != expected_configuration:
            raise ValueError("Public configuration differs from the pinned defaults")
        with tempfile.TemporaryDirectory(prefix="titan-protocol-") as temporary:
            root = Path(temporary)
            for name in ("selected", "reference"):
                extract_runtime(inputs / (name + ".tar.gz"), root / name)
            entry = root / "selected/main.py"
            references = list((root / "reference").rglob("scheduler.py"))
            if not entry.is_file() or len(references) != 1:
                raise ValueError("Standalone or reference entrypoint absent/ambiguous")
            reference = references[0]
            if sha(reference) != SCHEDULER_SHA or sha(root / "selected/vendor/sell/scheduler.py") != SCHEDULER_SHA:
                raise ValueError("Frozen scheduler pin differs")
            initial_files = {str(p.relative_to(root)): sha(p) for p in root.rglob("*") if p.is_file()}
            (root / "empty-cwd").mkdir()
            for name, pin in TRACE_PINS.items():
                path = inputs / "traces" / name
                verify_pin(path, pin)
                seat = int(name.split("-seat")[1][0])
                rows = load_rows(path, seat)
                stream = replay(entry, reference, rows, seat, configuration, root / "empty-cwd", timeout)
                stream.update(trace=name, trace_sha256=pin[1], seat=seat, development_seed=9600803)
                report["streams"].append(stream)
                write_json(output, report)
                print(json.dumps({"trace": name, "steps": len(rows), "mismatches": len(stream["mismatches"])}), flush=True)
            final_files = {str(p.relative_to(root)): sha(p) for p in root.rglob("*") if p.is_file()}
            if initial_files != final_files:
                raise ValueError("Runtime sources changed during replay")
            report["runtime_file_sha256"] = initial_files
        report["compared_steps"] = sum(s["steps"] for s in report["streams"])
        report["mismatch_count"] = sum(len(s["mismatches"]) for s in report["streams"])
        report["status"] = "passed" if report["mismatch_count"] == 0 else "failed"
        report["archives"] = ARCHIVES
        report["scheduler_sha256"] = SCHEDULER_SHA
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
    report["elapsed_seconds"] = time.perf_counter() - began
    write_json(output, report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    stage = sub.add_parser("prepare")
    stage.add_argument("--checkout", type=Path, required=True)
    stage.add_argument("--output", type=Path, required=True)
    check = sub.add_parser("run")
    check.add_argument("--inputs", type=Path, required=True)
    check.add_argument("--output", type=Path, required=True)
    check.add_argument("--timeout", type=float, default=5.0)
    child = sub.add_parser("worker")
    child.add_argument("entry", type=Path)
    args = parser.parse_args()
    if args.command == "worker":
        return worker(args.entry)
    if args.command == "prepare":
        print(json.dumps(prepare(args.checkout, args.output)))
        return 0
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("timeout must be a finite positive number")
    result = run(args.inputs, args.output, args.timeout)
    print(json.dumps({key: result.get(key) for key in ("status", "compared_steps", "mismatch_count", "error")}))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
