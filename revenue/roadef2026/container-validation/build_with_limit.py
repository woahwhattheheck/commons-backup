#!/usr/bin/env python3
"""Build one unchanged context under a measured 4 GiB BuildKit container cap.

Uses the existing Docker daemon, an invocation-specific docker-container builder,
and --load. No builder is selected globally and no image is pushed.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time
import uuid


LIMIT = 4 * 1024 ** 3
CGROUP_PROBE = r'''
set -eu
show() {
  printf '%s\t' "$1"
  if [ -r "$2" ]; then tr '\n' ' ' < "$2"; else printf 'UNAVAILABLE'; fi
  printf '\n'
}
show proc_self_cgroup /proc/self/cgroup
if [ -f /sys/fs/cgroup/cgroup.controllers ]; then
  relative=$(awk -F: '$1 == "0" { print $3; exit }' /proc/self/cgroup)
  mount=/sys/fs/cgroup
  names='memory.max memory.swap.max memory.current memory.peak memory.events memory.events.local'
  printf 'version\t2\n'
else
  relative=$(awk -F: '$2 ~ /(^|,)memory(,|$)/ { print $3; exit }' /proc/self/cgroup)
  mount=/sys/fs/cgroup/memory
  names='memory.limit_in_bytes memory.memsw.limit_in_bytes memory.usage_in_bytes memory.max_usage_in_bytes memory.failcnt memory.oom_control memory.use_hierarchy'
  printf 'version\t1\n'
fi
mount_group=$(awk -v target="$mount" '$5 == target { print $4; exit }' /proc/self/mountinfo)
case "$relative:$mount_group" in *'/..'*|*'/./'*) echo 'Unresolved cgroup namespace path' >&2; exit 1 ;; esac
case "$mount_group" in
  /) suffix="$relative" ;;
  '') echo 'Memory controller mount root unavailable' >&2; exit 1 ;;
  *) case "$relative" in
       "$mount_group") suffix='' ;;
       "$mount_group"/*) suffix=${relative#"$mount_group"} ;;
       *) echo 'Process cgroup is outside the visible controller mount' >&2; exit 1 ;;
     esac ;;
esac
root=${mount}${suffix}
root=${root%/}
printf 'root\t%s\nmount_root\t%s\nmount_cgroup\t%s\n' "$root" "$mount" "$mount_group"
index=0
while :; do
  suffix=${root#"$mount"}
  group=${mount_group%/}${suffix}
  if [ -z "$group" ]; then group=/; fi
  printf 'ancestor.%s.path\t%s\nancestor.%s.cgroup\t%s\n' "$index" "$root" "$index" "$group"
  for name in $names; do show "ancestor.$index.$name" "$root/$name"; done
  if [ "$root" = "$mount" ]; then break; fi
  root=${root%/*}
  case "$root" in "$mount"|"$mount"/*) ;; *) echo 'Cgroup ancestor escaped controller mount' >&2; exit 1 ;; esac
  index=$((index + 1))
done
'''
COMPILER_PROBE = r'''
for file in /proc/[0-9]*/comm; do
  name=$(cat "$file" 2>/dev/null) || continue
  case "$name" in g++|c++|cc1|cc1plus|clang|clang++) ;;
    *) continue ;;
  esac
  pid=${file#/proc/}; pid=${pid%/comm}
  group=$(tr '\n' ' ' < "/proc/$pid/cgroup" 2>/dev/null) || continue
  printf '%s\t%s\t%s\n' "$pid" "$name" "$group"
done
'''


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def parse_cgroup(raw):
    values = dict(line.split("\t", 1) for line in raw.splitlines())
    values = {key: value.strip() for key, value in values.items()}
    version = int(values["version"])
    maximum = "memory.max" if version == 2 else "memory.limit_in_bytes"
    swap = "memory.swap.max" if version == 2 else "memory.memsw.limit_in_bytes"
    peak = "memory.peak" if version == 2 else "memory.max_usage_in_bytes"
    event_name = "memory.events" if version == 2 else "memory.oom_control"
    ancestors = []
    index = 0
    while f"ancestor.{index}.path" in values:
        prefix = f"ancestor.{index}."
        row = {key[len(prefix):]: value for key, value in values.items() if key.startswith(prefix)}
        number = lambda name: int(row[name]) if row.get(name, "").isdigit() else None
        # v1 uses a page-counter sentinel near LONG_MAX for an unlimited limit.
        bound = lambda name: number(name) if number(name) is not None and (version == 2 or number(name) < 2 ** 60) else None
        tokens = row.get(event_name, "").split()
        events = {tokens[i]: int(tokens[i + 1]) for i in range(0, len(tokens) - 1, 2)
                  if tokens[i + 1].isdigit()}
        ancestors.append({"path": row["path"], "memory_cgroup": row["cgroup"], "raw": row,
                          "memory_limit_bytes": bound(maximum), "swap_limit_bytes": bound(swap),
                          "memory_peak_bytes": number(peak), "events": events,
                          "hierarchical": version == 2 or row.get("memory.use_hierarchy") == "1"})
        index += 1
    if not ancestors:
        raise ValueError("Memory controller ancestor readback is absent")
    finite = [row["memory_limit_bytes"] for row in ancestors if row["memory_limit_bytes"] is not None]
    effective_memory = min(finite) if finite else None
    # Prefer the outermost equally restrictive ancestor. Its counters include
    # the entire capped domain, including compiler siblings of BuildKit's /init.
    governing_index = next((i for i in range(len(ancestors) - 1, -1, -1)
                            if effective_memory is not None and ancestors[i]["memory_limit_bytes"] == effective_memory), None)
    governing = ancestors[governing_index] if governing_index is not None else None
    # A swap cap applying only to /init cannot constrain compiler siblings. Only
    # this RAM-governing domain and its ancestors can establish no extra swap.
    swap_domain = ancestors[governing_index:] if governing_index is not None else []
    swap_bounds = [row["swap_limit_bytes"] for row in swap_domain if row["swap_limit_bytes"] is not None]
    effective_swap = min(swap_bounds) if swap_bounds else None
    swap_governing = next((row for row in reversed(swap_domain)
                           if effective_swap is not None and row["swap_limit_bytes"] == effective_swap), None)
    cap_confirmed = (effective_memory == LIMIT and effective_swap == (0 if version == 2 else LIMIT)
                     and governing["hierarchical"] and swap_governing["hierarchical"])
    return {"version": version, "raw": values, "ancestors": ancestors, "memory_limit_bytes": effective_memory,
            "swap_limit_bytes": effective_swap,
            "governing_memory_cgroup": governing["memory_cgroup"] if governing else None,
            "governing_memory_path": governing["path"] if governing else None,
            "governing_swap_cgroup": swap_governing["memory_cgroup"] if swap_governing else None,
            "memory_peak_bytes": governing["memory_peak_bytes"] if governing else None,
            "events": governing["events"] if governing else {}, "cap_confirmed": cap_confirmed}


def memory_group(raw, version):
    for row in raw.split():
        hierarchy, controllers, path = row.split(":", 2)
        if (version == 2 and hierarchy == "0") or (version == 1 and "memory" in controllers.split(",")):
            return path
    return None


def descendant_group(parent, child):
    if not parent or not child or ".." in parent.split("/") or ".." in child.split("/"):
        return False
    return child == parent or child.startswith(parent.rstrip("/") + "/")


def context_matches_manifest(context):
    manifest = json.loads((context / "source-manifest.json").read_text())
    return all(digest(context / row["path"]) == row["sha256"] for row in manifest["files"])


class Build:
    def __init__(self, output):
        self.output = output
        self.commands = output / "commands"
        self.commands.mkdir()
        self.sequence = 0
        self.builder = "roadef-build-" + uuid.uuid4().hex
        self.node = self.builder + "-node"
        self.container = "buildx_buildkit_" + self.node
        self.volume = self.container + "_state"
        self.creation_attempted = False
        self.compiler_samples = []
        self.compiler_sample_errors = []
        self.cgroup_before = None

    def command(self, arguments, *, timeout=30, check=True, build_log=False):
        self.sequence += 1
        prefix = self.commands / f"{self.sequence:04d}"
        command = ["docker", *map(str, arguments)]
        started, result = time.monotonic(), None
        metadata = {"argv": command, "timeout_seconds": timeout}
        try:
            if build_log:
                with (self.output / "BUILD.log").open("wb") as stream:
                    process = subprocess.Popen(command, stdout=stream, stderr=subprocess.STDOUT)
                    try:
                        while process.poll() is None:
                            remaining = timeout - (time.monotonic() - started)
                            if remaining <= 0:
                                raise subprocess.TimeoutExpired(command, timeout)
                            try:
                                process.wait(timeout=min(0.5, remaining))
                            except subprocess.TimeoutExpired:
                                self.sample_compilers()
                        result = subprocess.CompletedProcess(command, process.returncode)
                    finally:
                        if process.poll() is None:
                            process.kill()
                            process.wait(timeout=5)
                stdout = ""
                metadata["combined_log"] = "BUILD.log"
            else:
                result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        timeout=timeout, check=False)
                prefix.with_suffix(".stdout").write_bytes(result.stdout)
                prefix.with_suffix(".stderr").write_bytes(result.stderr)
                stdout = result.stdout.decode("utf-8")
            if check and result.returncode:
                raise RuntimeError(f"Docker command {prefix.name} exited {result.returncode}; see retained logs")
            return result.returncode, stdout
        except subprocess.TimeoutExpired as error:
            metadata["timed_out"] = True
            if not build_log:
                prefix.with_suffix(".stdout").write_bytes(error.stdout or b"")
                prefix.with_suffix(".stderr").write_bytes(error.stderr or b"")
            raise RuntimeError(f"Docker command {prefix.name} exceeded {timeout}s") from error
        finally:
            metadata.update(wall_seconds=time.monotonic() - started,
                            returncode=None if result is None else result.returncode)
            write_json(prefix.with_suffix(".json"), metadata)

    def sample_compilers(self):
        try:
            _, raw = self.command(["exec", self.container, "/bin/sh", "-c", COMPILER_PROBE], timeout=10)
            parent = self.cgroup_before["governing_memory_cgroup"]
            for row in raw.splitlines():
                pid, command, groups = row.split("\t", 2)
                child = memory_group(groups, self.cgroup_before["version"])
                self.compiler_samples.append({"observed_unix_seconds": time.time(), "pid": int(pid),
                    "command": command, "proc_cgroup": groups.strip(), "memory_cgroup": child,
                    "capped_builder_memory_cgroup": parent,
                    "within_capped_builder_cgroup": descendant_group(parent, child)})
        except InterruptedError:
            raise
        except Exception as error:
            self.compiler_sample_errors.append(f"{type(error).__name__}: {error}")

    def inspect(self, phase):
        _, raw = self.command(["inspect", self.container])
        container = json.loads(raw)[0]
        write_json(self.output / f"BUILDER-{phase}-INSPECT.json", container)
        _, raw = self.command(["exec", self.container, "/bin/sh", "-c", CGROUP_PROBE])
        cgroup = parse_cgroup(raw)
        write_json(self.output / f"BUILDER-{phase}-CGROUP.json", cgroup)
        host = container["HostConfig"]
        return {"container_id": container["Id"], "image_id": container["Image"],
                "state": container["State"], "host_memory_bytes": host["Memory"],
                "host_memory_swap_bytes": host["MemorySwap"],
                "restart_policy": host["RestartPolicy"], "cgroup": cgroup,
                "cap_confirmed": host["Memory"] == LIMIT and host["MemorySwap"] == LIMIT
                and host["RestartPolicy"]["Name"] == "no" and cgroup["cap_confirmed"]}

    def cleanup(self):
        """Remove only this randomly named builder, its container and state volume."""
        result = {"builder": self.builder, "container": self.container,
                  "cache_volume": self.volume, "errors": []}
        if not self.creation_attempted:
            return dict(result, complete=True, creation_attempted=False)
        try:
            code, _ = self.command(["buildx", "rm", "--force", self.builder], timeout=60, check=False)
            result["buildx_rm_returncode"] = code
        except Exception as error:
            result["errors"].append(f"builder removal: {error}")
        try:
            _, text = self.command(["ps", "-aq", "--filter", f"name=^/{self.container}$"])
            identifiers = text.split()
            result["fallback_removed_containers"] = identifiers
            if identifiers:
                self.command(["rm", "--force", *identifiers], timeout=30)
            _, text = self.command(["volume", "ls", "-q", "--filter", f"name=^{self.volume}$"])
            volumes = [name for name in text.split() if name == self.volume]
            result["fallback_removed_volumes"] = volumes
            if volumes:
                self.command(["volume", "rm", *volumes], timeout=30)
            _, containers = self.command(["ps", "-aq", "--filter", f"name=^/{self.container}$"])
            _, volumes = self.command(["volume", "ls", "-q", "--filter", f"name=^{self.volume}$"])
            # inspect may recreate a removed metadata record only with --bootstrap;
            # here an absent explicitly named builder produces a nonzero status.
            status, _ = self.command(["buildx", "inspect", self.builder], check=False)
            result.update(containers_remaining=containers.split(),
                          cache_volumes_remaining=[name for name in volumes.split() if name == self.volume],
                          builder_remaining=status == 0)
            result["complete"] = not result["containers_remaining"] and not result["cache_volumes_remaining"] and not result["builder_remaining"]
        except Exception as error:
            result["errors"].append(f"cleanup verification: {error}")
            result["complete"] = False
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", type=Path, required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    build = Build(output)
    report = {"passed": False, "scope": "Actual image build under a measured 4 GiB BuildKit cap",
              "requested_memory_bytes": LIMIT, "requested_memory_swap_bytes": LIMIT,
              "builder": build.builder, "node": build.node, "container_name": build.container,
              "image_tag": args.image, "host_uid": os.getuid(), "host_euid": os.geteuid()}
    started = time.monotonic()
    try:
        context = args.context.resolve(strict=True)
        if not context.is_dir():
            raise ValueError("Build context must be a directory")
        report.update(context=str(context), dockerfile_sha256=digest(context / "Dockerfile"),
                      source_manifest_sha256=digest(context / "source-manifest.json"))
        if not context_matches_manifest(context):
            raise RuntimeError("Supplied build context differs from its source manifest")
        build.command(["version"])
        build.command(["buildx", "version"])
        build.creation_attempted = True
        build.command(["buildx", "create", "--name", build.builder, "--node", build.node,
                       "--driver", "docker-container", "--driver-opt",
                       "memory=4g,memory-swap=4g,restart-policy=no"])
        build.command(["buildx", "inspect", "--bootstrap", build.builder], timeout=180)
        report["before"] = build.inspect("BEFORE")
        _, image_raw = build.command(["image", "inspect", report["before"]["image_id"]])
        write_json(output / "BUILDKIT-IMAGE.json", json.loads(image_raw)[0])
        if not report["before"]["cap_confirmed"]:
            raise RuntimeError("Actual BuildKit HostConfig and cgroup do not confirm the 4 GiB cap with no extra swap")
        build.cgroup_before = report["before"]["cgroup"]
        report["build_started"] = True
        try:
            build.command(["buildx", "build", "--builder", build.builder, "--load", "--progress", "plain",
                           "--tag", args.image, str(context)], timeout=900, build_log=True)
            report["build_exit_success"] = True
        except Exception as error:
            report["build_error"] = f"{type(error).__name__}: {error}"
            raise
        finally:
            # Collect the actual cgroup peak/events even when compilation fails.
            try:
                report["after"] = build.inspect("AFTER")
            except Exception as error:
                report["after_probe_error"] = f"{type(error).__name__}: {error}"
                if report.get("build_exit_success"):
                    raise
        if not report["after"]["cap_confirmed"]:
            raise RuntimeError("BuildKit memory enforcement changed during the build")
        if report["after"]["container_id"] != report["before"]["container_id"]:
            raise RuntimeError("BuildKit container identity changed during the build")
        if report["after"]["cgroup"]["governing_memory_cgroup"] != report["before"]["cgroup"]["governing_memory_cgroup"]:
            raise RuntimeError("The compiler-governing memory domain changed during the build")
        report['observed_build_memory_peak_bytes'] = report['after']['cgroup']['memory_peak_bytes']
        if report['observed_build_memory_peak_bytes'] is None:
            raise RuntimeError('The requested build memory peak could not be read back')
        report["compiler_cgroup_inheritance_confirmed"] = bool(build.compiler_samples) and all(
            row["within_capped_builder_cgroup"] for row in build.compiler_samples)
        if not report["compiler_cgroup_inheritance_confirmed"]:
            raise RuntimeError("Actual compiler processes were not observed within the capped BuildKit memory cgroup")
        before_events = report["before"]["cgroup"]["events"]
        after_events = report["after"]["cgroup"]["events"]
        report["memory_event_delta"] = {name: count - before_events.get(name, 0)
                                        for name, count in after_events.items()}
        if report["after"]["state"].get("OOMKilled") or report["memory_event_delta"].get("oom_kill", 0):
            raise RuntimeError("An OOM kill occurred in the BuildKit container")
        _, image_raw = build.command(["image", "inspect", args.image])
        image = json.loads(image_raw)[0]
        write_json(output / "BUILT-IMAGE.json", image)
        report["built_image_id"] = image["Id"]
        report["context_identity_unchanged"] = report["dockerfile_sha256"] == digest(context / "Dockerfile") and report["source_manifest_sha256"] == digest(context / "source-manifest.json") and context_matches_manifest(context)
        report["passed"] = report["context_identity_unchanged"]
    except (Exception, KeyboardInterrupt) as error:
        report["error"] = f"{type(error).__name__}: {error}"
    finally:
        write_json(output / "COMPILER-CGROUP-SAMPLES.json", {"samples": build.compiler_samples,
                                                           "errors": build.compiler_sample_errors})
        report["cleanup"] = build.cleanup()
        report["passed"] = report["passed"] and report["cleanup"]["complete"]
        report["wall_seconds"] = time.monotonic() - started
        write_json(output / "RESULTS.json", report)
        write_json(output / "ARTIFACT-MANIFEST.json", {"files": [
            {"path": path.relative_to(output).as_posix(), "bytes": path.stat().st_size, "sha256": digest(path)}
            for path in sorted(output.rglob("*")) if path.is_file()]})
    print(json.dumps({"passed": report["passed"], "image_id": report.get("built_image_id"),
                      "result": str(output / "RESULTS.json")}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    def interrupted(signum, frame):
        raise InterruptedError(f"Build harness received signal {signum}")

    signal.signal(signal.SIGTERM, interrupted)
    raise SystemExit(main())
