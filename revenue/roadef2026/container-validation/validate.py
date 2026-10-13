#!/usr/bin/env python3
"""Exercise one built ROADEF image with real Docker and pinned B01/B11/B12 inputs.

No image build, pull, solver modification or performance comparison is performed.
All execution uses the inspected immutable image ID and network-disabled containers.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import uuid


UID = "1006410000"
INPUTS = ("network.json", "traffic.json", "scenario.json")
INSTANCES = ("B01", "B11", "B12")
SIGNAL_EXIT_SECONDS = 10
GIB = 1024 ** 3


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def input_hashes(data):
    return {instance: {name: digest(data / instance / name) for name in INPUTS}
            for instance in INSTANCES}


def prepared_input_hashes(preparation):
    """Bind every prepared input to its explicit instance; never collapse paths."""
    result = {instance: {} for instance in INSTANCES}
    for row in preparation["inputs"]:
        instance, name = row["instance"], row["path"]
        if instance not in result or name not in INPUTS or name in result[instance]:
            raise ValueError("Expected one preparation row for each instance/input pair")
        result[instance][name] = row["sha256"]
    if any(set(files) != set(INPUTS) for files in result.values()):
        raise ValueError("Prepared inputs must cover B01/B11/B12 network, traffic and scenario")
    return result


def terminate_and_wait(docker, identifier):
    """Include signal delivery overhead in the external observation deadline."""
    started = time.monotonic()
    docker.command(["kill", "--signal", "TERM", identifier], timeout=5)
    remaining = SIGNAL_EXIT_SECONDS - (time.monotonic() - started)
    if remaining <= 0:
        raise RuntimeError("SIGTERM delivery exhausted the external 10s deadline")
    state = docker.wait(identifier, remaining)
    elapsed = time.monotonic() - started
    if elapsed > SIGNAL_EXIT_SECONDS:
        raise RuntimeError(f"SIGTERM exit observed at {elapsed:.6f}s, after the external 10s deadline")
    return state, elapsed


def optional_text(path):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return None


def host_capacity(docker):
    """Bound execution by observed host/daemon capacity, not competition hardware."""
    info = json.loads(docker.command([
        "info", "--format", '{"cpus":{{.NCPU}},"memory_bytes":{{.MemTotal}}}']))
    affinity = len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else os.cpu_count()
    cpu_max = optional_text("/sys/fs/cgroup/cpu.max")
    quota = None
    if cpu_max:
        amount, period = cpu_max.split()
        if amount != "max":
            quota = int(amount) / int(period)
    memory_max = optional_text("/sys/fs/cgroup/memory.max")
    cgroup_memory = int(memory_max) if memory_max and memory_max != "max" else None
    cpus = min(float(info["cpus"]), float(affinity or 1), quota or float("inf"), 4.0)
    memory = min(int(info["memory_bytes"]), cgroup_memory or int(info["memory_bytes"]))
    limit = min(8 * GIB, int(memory * 0.70))
    if cpus <= 0 or limit < 512 * 1024 ** 2:
        raise RuntimeError("Observed host capacity cannot support this bounded run")
    return {"docker_daemon": info, "host_affinity_cpus": affinity,
            "host_cgroup_cpu_max": cpu_max, "host_cgroup_memory_max": memory_max,
            "container_cpus": cpus, "container_memory_bytes": limit,
            "interpretation": "Host observations and applied limits; not official 8-CPU/32-GB hardware"}


class Docker:
    def __init__(self, output):
        self.output = output
        self.commands = output / "commands"
        self.commands.mkdir()
        self.scope = "roadef-validation-" + uuid.uuid4().hex
        self.containers = []
        self.sequence = 0
        self.image = None
        self.image_files = {}
        self.capacity = None

    def command(self, arguments, *, timeout=20, check=True):
        self.sequence += 1
        prefix = self.commands / f"{self.sequence:04d}"
        started = time.monotonic()
        command = ["docker", *map(str, arguments)]
        result = None
        try:
            result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    timeout=timeout, check=False)
            prefix.with_suffix(".stdout").write_bytes(result.stdout)
            prefix.with_suffix(".stderr").write_bytes(result.stderr)
            if check and result.returncode:
                raise RuntimeError(f"Docker command {self.sequence} exited {result.returncode}; see command logs")
            return result.stdout.decode("utf-8")
        except subprocess.TimeoutExpired as error:
            prefix.with_suffix(".stdout").write_bytes(error.stdout or b"")
            prefix.with_suffix(".stderr").write_bytes(error.stderr or b"")
            raise RuntimeError(f"Docker command {self.sequence} exceeded {timeout}s") from error
        finally:
            write_json(prefix.with_suffix(".json"), {
                "argv": command, "wall_seconds": time.monotonic() - started,
                "returncode": None if result is None else result.returncode})

    def create(self, label, command, *, data=None, output=None, environment=None):
        name = f"{self.scope}-{label}"
        args = ["create", "--pull=never", "--name", name, "--label", f"validation.scope={self.scope}",
                "--network", "none", "--cpus", str(self.capacity["container_cpus"]),
                "--memory", str(self.capacity["container_memory_bytes"]),
                "--memory-swap", str(self.capacity["container_memory_bytes"]), "--pids-limit", "512"]
        for source, target, mode in ((data, "/data", "ro"), (output, "/out", "rw")):
            if source is not None:
                args += ["--mount", f"type=bind,src={source},dst={target}" + (",readonly" if mode == "ro" else "")]
        for key, value in (environment or {}).items():
            args += ["--env", f"{key}={value}"]
        identifier = self.command([*args, self.image, *command]).strip()
        self.containers.append(identifier)
        record = self.inspect(identifier)
        if (record["Image"] != self.image or record["Config"]["User"] != UID or
                record["HostConfig"]["NetworkMode"] != "none"):
            raise RuntimeError("Created container does not match image/user/network contract")
        self.command(["start", identifier])
        return identifier, record

    def inspect(self, identifier):
        return json.loads(self.command(["inspect", identifier]))[0]

    def state(self, identifier):
        return json.loads(self.command(["inspect", "--format", "{{json .State}}", identifier], timeout=5))

    def wait(self, identifier, seconds):
        deadline = time.monotonic() + seconds
        while True:
            state = self.state(identifier)
            if not state["Running"]:
                return state
            if time.monotonic() >= deadline:
                raise RuntimeError(f"Container did not exit within {seconds}s observation window")
            time.sleep(0.2)

    def retain(self, identifier, directory):
        record = self.inspect(identifier)
        write_json(directory / "container-inspect.json", record)
        # Docker keeps stdout and stderr separate even though its logs CLI emits both.
        self.command(["logs", "--timestamps", identifier])
        prefix = self.commands / f"{self.sequence:04d}"
        (directory / "container-stdout.log").write_bytes(prefix.with_suffix(".stdout").read_bytes())
        (directory / "container-stderr.log").write_bytes(prefix.with_suffix(".stderr").read_bytes())
        return record

    def short(self, label, command, directory, *, data=None, output=None, seconds=45):
        directory.mkdir(parents=True, exist_ok=True)
        identifier, created = self.create(label, command, data=data, output=output)
        write_json(directory / "container-created.json", created)
        try:
            state = self.wait(identifier, seconds)
            if state["ExitCode"] != 0 or state.get("OOMKilled"):
                raise RuntimeError(f"{label} failed: {state}")
        finally:
            self.retain(identifier, directory)
        return directory / "container-stdout.log"

    def cleanup(self):
        # The random label selects only containers created by this invocation.
        identifiers = self.command(["ps", "-aq", "--filter", f"label=validation.scope={self.scope}"]).split()
        before = {identifier: self.state(identifier) for identifier in identifiers}
        if identifiers:
            self.command(["rm", "--force", *identifiers], timeout=30)
        remaining = self.command(["ps", "-aq", "--filter", f"label=validation.scope={self.scope}"]).split()
        return {"states_before_removal": before, "forced_running": [i for i, s in before.items() if s["Running"]],
                "owned_containers_remaining": remaining, "complete": not remaining}


PROBE = r'''
import hashlib,json,os,pathlib
root=pathlib.Path('/home')
paths=[p for p in root.rglob('*') if p.is_file()]
def read(p):
    try:return pathlib.Path(p).read_text().strip()
    except OSError:return None
print(json.dumps({'uid':os.getuid(),'euid':os.geteuid(),'gid':os.getgid(),
    'affinity_cpus':len(os.sched_getaffinity(0)),
    'cpu_max':read('/sys/fs/cgroup/cpu.max'),'memory_max':read('/sys/fs/cgroup/memory.max'),
    'files':{str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)},
    'source_manifest':json.loads((root/'source-manifest.json').read_text())}))
'''


def accepted_checkpoint(directory):
    """Take one self-consistent atomic-output/receipt pair without stopping the solver."""
    try:
        receipt = json.loads((directory / "solution.json.portfolio.json").read_text())
        solution = (directory / "solution.json").read_bytes()
    except (OSError, ValueError):
        return None
    if receipt.get("validated") is True and hashlib.sha256(solution).hexdigest() == receipt.get("solution_sha256"):
        return solution, receipt
    return None


def check_solution(docker, case, data, name):
    directory = case / f"{name}-check-container"
    command = ["/home/bin/checker", "--net", "/data/network.json", "--tm", "/data/traffic.json",
               "--scenario", "/data/scenario.json", "--srpaths", f"/out/{name}.json",
               "--max-decimal-places", "6"]
    docker.short(case.name + "-" + name + "-check", command, directory, data=data, output=case)
    # Timestamp-free bytes are needed for exact official checker parsing and hashing.
    identifier = json.loads((directory / "container-inspect.json").read_text())["Id"]
    raw = docker.command(["logs", identifier]).encode()
    target = case / f"{name}-checker-6.json"
    target.write_bytes(raw)
    result = json.loads(raw)
    if result.get("valid") is not True:
        raise RuntimeError(f"Official checker rejected {name}")
    return target


def compare_reports(docker, case, left, right, name, allowed):
    destination = case / f"{name}.json"
    docker.short(case.name + "-" + name,
                 ["python3", "/home/compare_checker.py", "/out/" + str(left.relative_to(case)),
                  "/out/" + str(right.relative_to(case)), "--output", "/out/" + destination.name],
                 case / (name + "-container"), output=case)
    result = json.loads(destination.read_text())
    if len(result["instances"]) != 1 or result["instances"][0]["winner"] not in allowed:
        raise RuntimeError(f"{name} did not establish expected official-vector relationship")
    return result


def run_case(docker, data, output, name, *, instance, terminate, configuration):
    case = output / f"{instance}-{name}"
    case.mkdir(mode=0o777)
    case.chmod(0o777)  # The image's required numeric UID must write its bind mount.
    budget = 90 if terminate else 30
    environment = dict(configuration['env'])
    environment.update(PORTFOLIO_SECONDS=str(budget), PORTFOLIO_ARTIFACTS='/out')
    first_container = len(docker.containers)
    identifier, created = docker.create(case.name,
        ["/home/run.sh", "/data/network.json", "/data/traffic.json", "/data/scenario.json", "/out/solution.json"],
        data=data, output=case, environment=environment)
    write_json(case / "container-created.json", created)
    started = time.monotonic()
    row = {"instance": instance, "case": name, "output_directory": case.name,
           "input_sha256": {name: digest(data / name) for name in INPUTS},
           "portfolio_budget_seconds": budget, "container_id": identifier,
           "applied_environment": environment,
           "image_id": docker.image, "command": created["Config"]["Cmd"]}
    try:
        actual_environment = dict(value.split('=', 1) for value in created['Config']['Env'] if '=' in value)
        if any(actual_environment.get(key) != str(value) for key, value in environment.items()):
            raise RuntimeError('Container did not receive the frozen configuration and smoke budget')
        if any(key in actual_environment for key in configuration['unset']):
            raise RuntimeError('Container inherited a control forbidden by the frozen configuration')
        if terminate:
            checkpoint_deadline = time.monotonic() + 60
            checkpoint = None
            while time.monotonic() < checkpoint_deadline:
                if not docker.state(identifier)["Running"]:
                    raise RuntimeError("TERM case exited before an accepted checkpoint could be signaled")
                checkpoint = accepted_checkpoint(case)
                if checkpoint is not None:
                    break
                time.sleep(0.1)
            if checkpoint is None:
                raise RuntimeError("No accepted checkpoint observed within 60s")
            solution, receipt = checkpoint
            (case / "preterm.json").write_bytes(solution)
            write_json(case / "preterm-receipt.json", receipt)
            row["preterm_selected_lane"] = receipt["selected_lane"]
            row["preterm_solution_sha256"] = hashlib.sha256(solution).hexdigest()
            row["signal_observation_window_seconds"] = SIGNAL_EXIT_SECONDS
            state, elapsed = terminate_and_wait(docker, identifier)
            row["signal_to_observed_exit_seconds"] = elapsed
        else:
            state = docker.wait(identifier, budget + 15)
        row["observed_wall_seconds"] = time.monotonic() - started
        if state["ExitCode"] != 0 or state.get("OOMKilled") or state["Pid"] != 0:
            raise RuntimeError(f"Portfolio did not exit cleanly: {state}")
        receipt = json.loads((case / "solution.json.portfolio.json").read_text())
        if receipt.get("status") != "complete" or receipt.get("validated") is not True:
            raise RuntimeError("Portfolio did not retain a completed validated incumbent")
        if receipt.get("solution_sha256") != digest(case / "solution.json"):
            raise RuntimeError("Final solution bytes differ from selected receipt")
        if receipt.get("checker_sha256") != docker.image_files["bin/checker"]:
            raise RuntimeError("Portfolio checker bytes differ from the inspected image")
        if ({lane["name"] for lane in receipt["lanes"]} != {"sedge", "flora", "candidate"} or
                any(lane.get("source_binary_sha256") != docker.image_files["bin/" + lane["name"]]
                    for lane in receipt["lanes"])):
            raise RuntimeError("Portfolio lane binary bytes differ from the inspected image")
        if receipt.get("input_sha256") != {"/data/" + name: digest(data / name) for name in INPUTS}:
            raise RuntimeError(f"Portfolio input bytes differ from the supplied {instance} files")
        if terminate and receipt.get("signal_received") != 15:
            raise RuntimeError("Portfolio did not record the delivered SIGTERM")
        final = check_solution(docker, case, data, "solution")
        selected = [p for p in case.glob("roadef-portfolio-*/*.checker-6.json")
                    if digest(p) == receipt["selected_checker_sha256"]]
        if not selected:
            raise RuntimeError("Selected official checker bytes missing from retained artifacts")
        row["selected_recheck"] = compare_reports(docker, case, selected[0], final,
                                                   "selected-recheck", {"tie"})
        if terminate:
            preterm = check_solution(docker, case, data, "preterm")
            row["checkpoint_preservation"] = compare_reports(docker, case, preterm, final,
                                                             "checkpoint-preservation", {"right", "tie"})
        row.update(passed=True, final_solution_sha256=digest(case / "solution.json"),
                   final_checker_sha256=digest(final), selected_lane=receipt["selected_lane"],
                   supervisor_wall_seconds=receipt["wall_seconds"])
    except Exception as error:
        row.update(passed=False, error=f"{type(error).__name__}: {error}")
    finally:
        # A failed case must not leave its solver/checker competing with the next
        # instance. Keep the stopped containers for inspection and final removal.
        row["forced_stops_before_next_case"] = []
        for owned in docker.containers[first_container:]:
            try:
                if docker.state(owned)["Running"]:
                    row["passed"] = False
                    row["forced_stops_before_next_case"].append(owned)
                    docker.command(["kill", "--signal", "KILL", owned], timeout=5)
                    docker.wait(owned, 5)
            except Exception as error:
                row["passed"] = False
                row.setdefault("case_cleanup_errors", []).append(f"{owned}: {type(error).__name__}: {error}")
        docker.retain(identifier, case)
        write_json(case / "RESULT.json", row)
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--preparation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    data, output = args.data.resolve(strict=True), args.output.resolve()
    inputs = input_hashes(data)
    preparation = json.loads(args.preparation.read_text())
    output.mkdir(parents=True, exist_ok=False)
    docker = Docker(output)
    report = {"scope": "B01/B11/B12 actual Docker integration and accepted-checkpoint SIGTERM retention",
              "instances": list(INSTANCES), "planned_cases": 2 * len(INSTANCES),
              "submitted": False, "input_sha256": inputs, "cases": [], "passed": False,
              "preparation_sha256": digest(args.preparation),
              "frozen_candidate": preparation['frozen'],
              "frozen_configuration": preparation['configuration'],
              "validator_host_uid": os.getuid(), "validator_host_euid": os.geteuid()}
    try:
        image = json.loads(docker.command(["image", "inspect", args.image]))[0]
        write_json(output / "image-inspect.json", image)
        if image["Config"]["User"] != UID:
            raise RuntimeError(f"Image must declare USER {UID}")
        docker.image = image["Id"]
        docker.capacity = host_capacity(docker)
        report.update(image_id=docker.image, image_reference=args.image, capacity=docker.capacity)
        docker.short("probe", ["python3", "-c", PROBE], output / "image-probe")
        probe_id = json.loads((output / "image-probe/container-inspect.json").read_text())["Id"]
        probe = json.loads(docker.command(["logs", probe_id]))
        write_json(output / "image-runtime.json", probe)
        docker.image_files = probe["files"]
        if probe["uid"] != int(UID) or probe["euid"] != int(UID):
            raise RuntimeError("Actual image process did not use the declared numeric UID")
        if inputs != prepared_input_hashes(preparation):
            raise RuntimeError("Runtime inputs differ from pinned preparation")
        if probe['files']['source-manifest.json'] != preparation['context_manifest_sha256']:
            raise RuntimeError("Image build manifest differs from pinned preparation")
        built_sources = {row['path']: row['sha256'] for row in probe['source_manifest']['files']}
        if built_sources.get('sources/candidate/main.cpp') != preparation['candidate']['used_sha256']:
            raise RuntimeError("Image source manifest differs from frozen candidate source")
        runtime = {row['path']: row for row in preparation['runtime_files']}
        for name in ('run.sh', 'supervisor.py', 'compare_checker.py'):
            if probe['files'].get(name) != runtime[name]['used_sha256']:
                raise RuntimeError(f"Image runtime differs from pinned preparation: {name}")
        report['runtime_source_identity_verified'] = True
        for instance in INSTANCES:
            for name in ("normal-30s", "term-after-checkpoint"):
                result = run_case(docker, data / instance, output, name,
                                  instance=instance, terminate=name.startswith("term"),
                                  configuration=preparation['configuration'])
                report["cases"].append(result)
                if result.get("case_cleanup_errors"):
                    raise RuntimeError("Case cleanup could not be verified; later instances were not started")
        report["input_hashes_unchanged"] = inputs == input_hashes(data)
        report["passed"] = (report["input_hashes_unchanged"] and
                            len(report["cases"]) == report["planned_cases"] and
                            all(row["passed"] for row in report["cases"]))
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
    finally:
        try:
            report["cleanup"] = docker.cleanup()
            report["passed"] = report["passed"] and report["cleanup"]["complete"] and not report["cleanup"]["forced_running"]
        except Exception as error:
            report["cleanup"] = {"complete": False, "error": f"{type(error).__name__}: {error}"}
            report["passed"] = False
        write_json(output / "RESULTS.json", report)
        files = [{"path": str(p.relative_to(output)), "bytes": p.stat().st_size, "sha256": digest(p)}
                 for p in sorted(output.rglob("*")) if p.is_file()]
        write_json(output / "ARTIFACT-MANIFEST.json", {"files": files})
    print(json.dumps({"passed": report["passed"], "result": str(output / "RESULTS.json")}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
