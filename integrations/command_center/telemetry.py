"""Lightweight observations of the runtime host; no inference or subprocesses."""
import ctypes
import os
import platform
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path


def _cgroup_path(value):
    # mountinfo escapes whitespace and backslashes with octal sequences.
    return Path(re.sub(r"\\([0-7]{3})", lambda match: chr(int(match[1], 8)), value))


def _linux_process_limits():
    """Read process affinity and visible cgroup-v2 limits without changing them.

    Ancestor limits are shared by their descendants. Memory headroom is the
    remaining hard-limit charge budget, excluding possible cache reclaim; it is
    not MemAvailable. A cgroup namespace may hide further ancestor constraints.
    """
    result = {
        "scope": "process_affinity_and_visible_cgroup_v2_ancestors",
        "cpu_affinity_processors": None,
        "cpu_quota_processors": None,
        "memory_limit_bytes": None,
        "memory_current_bytes": None,
        "memory_headroom_bytes": None,
        "memory_events": [],
        "memory_stats": [],
        "cgroup_version": None,
        "cgroup_status": "unavailable",
        "controller_status": {"cpu": "unavailable", "memory": "unavailable"},
        "unavailable_interfaces": [],
        "read_errors": [],
        "notes": (
            "CPU quota is a sustained CPU-time ceiling, not idle CPU capacity. "
            "Memory headroom is limit minus current usage, shared with descendants "
            "and excluding reclaim. Ancestors outside the visible mount are unmeasured. "
            "Memory event counters are cumulative, not attributed to a command. "
            "Hierarchical counters overlap and must not be summed across ancestors. "
            "Memory stat byte fields overlap; current usage is not process heap, "
            "and reclaimable or inactive bytes are not guaranteed available capacity."
        ),
    }
    try:
        result["cpu_affinity_processors"] = len(os.sched_getaffinity(0))
    except (AttributeError, OSError):
        pass
    try:
        memberships = Path("/proc/self/cgroup").read_text().splitlines()
        member = next((line.split(":", 2)[2] for line in memberships
                       if line.startswith("0::")), None)
        if member is None:
            result["cgroup_status"] = "no_cgroup_v2_membership"
            return result
        location = Path(member)
        if not location.is_absolute() or ".." in location.parts:
            result["cgroup_status"] = "membership_outside_visible_mount"
            return result
        matches = []
        for line in Path("/proc/self/mountinfo").read_text().splitlines():
            before, separator, after = line.partition(" - ")
            fields = before.split()
            filesystem = after.split()
            if (not separator or len(fields) < 5 or len(filesystem) < 3
                    or filesystem[0] != "cgroup2"):
                continue
            root, mount = _cgroup_path(fields[3]), _cgroup_path(fields[4])
            try:
                relative = location.relative_to(root)
            except ValueError:
                continue
            local_events = "memory_localevents" in filesystem[2].split(",")
            matches.append((len(root.parts), mount / relative, mount, local_events))
        if not matches:
            result["cgroup_status"] = "no_visible_cgroup_v2_mount"
            return result
        _, directory, mount, local_events = max(matches, key=lambda entry: entry[0])
        result.update(cgroup_version=2, cgroup_path=str(directory),
                      cgroup_status="observed", cgroup_mount=str(mount))
    except (OSError, ValueError, IndexError) as exc:
        result["read_errors"].append({"source": "cgroup_discovery", "error": type(exc).__name__})
        return result

    def read(path):
        try:
            return path.read_text().strip()
        except FileNotFoundError:
            # A controller may not be enabled; the hierarchy root also omits
            # limit files. Missing is not the same as an observed zero limit.
            result["unavailable_interfaces"].append(str(path))
            return None
        except OSError as exc:
            result["read_errors"].append({"source": str(path), "error": type(exc).__name__})
            return None

    def integer(value):
        if not value or not value.isascii() or not value.isdecimal():
            raise ValueError("expected nonnegative integer")
        return int(value)

    def minimum(key, value, source):
        if result[key] is None or value < result[key]:
            result[key] = value
            result[key.removesuffix("_bytes").removesuffix("_processors") + "_source"] = str(source)

    leaf = directory
    cpu_observed = memory_observed = False
    while True:
        cpu_path = directory / "cpu.max"
        cpu = read(cpu_path)
        if cpu is not None:
            try:
                quota, period = cpu.split()
                period = integer(period)
                if period == 0:
                    raise ValueError("CPU quota period must be positive")
                if quota != "max":
                    quota = integer(quota)
                    if quota == 0:
                        raise ValueError("CPU quota must be positive")
                    minimum("cpu_quota_processors", quota / period, cpu_path)
                cpu_observed = True
            except (ValueError, OverflowError):
                result["read_errors"].append({"source": str(cpu_path), "error": "invalid_cpu_quota"})
        limit_path = directory / "memory.max"
        usage_path = directory / "memory.current"
        limit, usage = read(limit_path), read(usage_path)
        try:
            usage = integer(usage) if usage is not None else None
            if directory == leaf:
                result["memory_current_bytes"] = usage
        except ValueError:
            usage = None
            result["read_errors"].append({"source": str(usage_path), "error": "invalid_memory_usage"})
        if limit is not None and limit != "max":
            try:
                limit = integer(limit)
                minimum("memory_limit_bytes", limit, limit_path)
                if usage is not None:
                    minimum("memory_headroom_bytes", max(0, limit - usage), directory)
                memory_observed = True
            except ValueError:
                result["read_errors"].append({"source": str(limit_path), "error": "invalid_memory_limit"})
        elif limit == "max":
            memory_observed = True
        for interface in ("memory.events", "memory.events.local"):
            event_path = directory / interface
            events = read(event_path)
            if events is None:
                continue
            try:
                counters = {}
                for line in events.splitlines():
                    name, count = line.split()
                    if name in counters:
                        raise ValueError("duplicate memory event counter")
                    counters[name] = integer(count)
                if not counters:
                    raise ValueError("empty memory event counters")
                result["memory_events"].append({
                    "source": str(event_path),
                    "scope": "local" if local_events or interface.endswith(".local")
                             else "cgroup_and_descendants",
                    "counters": counters,
                })
            except ValueError:
                result["read_errors"].append({"source": str(event_path),
                                              "error": "invalid_memory_events"})
        stat_path = directory / "memory.stat"
        stats = read(stat_path)
        if stats is not None:
            try:
                counters = {}
                for line in stats.splitlines():
                    name, count = line.split()
                    if name in counters:
                        raise ValueError("duplicate memory stat counter")
                    counters[name] = integer(count)
                if not counters:
                    raise ValueError("empty memory stat counters")
                result["memory_stats"].append({
                    "source": str(stat_path),
                    "scope": "cgroup_and_descendants",
                    "bytes": {name: counters[name] for name in (
                        "anon", "file", "kernel", "shmem", "inactive_file", "active_file",
                        "file_dirty", "file_writeback", "slab_reclaimable", "slab_unreclaimable",
                    ) if name in counters},
                })
            except ValueError:
                result["read_errors"].append({"source": str(stat_path),
                                              "error": "invalid_memory_stats"})
        if directory == mount:
            break
        directory = directory.parent
    for controller, observed, key in (
            ("cpu", cpu_observed, "cpu_quota_processors"),
            ("memory", memory_observed, "memory_limit_bytes")):
        state = "limited" if result[key] is not None else "no_visible_limit" if observed else "unavailable"
        if any(Path(error["source"]).name.startswith(controller + ".") for error in result["read_errors"]):
            state = "partial"
        result["controller_status"][controller] = state
    if result["read_errors"]:
        result["cgroup_status"] = "partial"
    elif not cpu_observed and not memory_observed:
        result["cgroup_status"] = "controllers_unavailable"
    elif not cpu_observed or not memory_observed:
        result["cgroup_status"] = "partial"
    return result


def _linux_cpu_stats(limits):
    """Read cumulative CPU accounting from the already discovered hierarchy."""
    result = {
        "scope": "visible_cgroup_v2_ancestors",
        "status": "unavailable", "sources": [],
        "unavailable_interfaces": [], "read_errors": [],
        "notes": (
            "Cumulative counters per source; *_usec values are microseconds. "
            "Usage includes descendants. cpu.stat bandwidth counters describe "
            "this group's limit; cpu.stat.local describes this group's runqueues "
            "including ancestor throttling. Keep sources separate: they overlap "
            "and are not a command's elapsed time or current utilization. "
            "Ancestors outside the visible mount are unmeasured."
        ),
    }
    if "cgroup_path" not in limits or "cgroup_mount" not in limits:
        return result
    leaf, mount = Path(limits["cgroup_path"]), Path(limits["cgroup_mount"])
    for directory in (leaf, *leaf.parents):
        if not directory.is_relative_to(mount):
            break
        for interface in ("cpu.stat", "cpu.stat.local"):
            source = directory / interface
            try:
                lines = source.read_text().splitlines()
            except FileNotFoundError:
                result["unavailable_interfaces"].append(str(source))
                continue
            except OSError as exc:
                result["read_errors"].append({"source": str(source),
                                              "error": type(exc).__name__})
                continue
            try:
                counters = {}
                for line in lines:
                    name, count = line.split()
                    if (name in counters or not count.isascii()
                            or not count.isdecimal()):
                        raise ValueError("invalid CPU counter")
                    counters[name] = int(count)
                # cpu.stat.local may be empty when the controller is disabled.
                if not counters and interface == "cpu.stat":
                    raise ValueError("empty CPU counters")
                result["sources"].append({"source": str(source),
                                          "counters": counters})
            except ValueError:
                result["read_errors"].append({"source": str(source),
                                              "error": "invalid_cpu_stats"})
    if result["sources"]:
        result["status"] = "observed"
    if result["read_errors"] or (result["sources"] and result["unavailable_interfaces"]):
        result["status"] = "partial"
    return result


def host_observation(state_dir):
    system = platform.system()
    item = {
        "id": "host:" + platform.node(), "label": platform.node() or "Runtime host",
        "kind": "machine", "provider": system, "status": "observed",
        "cpu": os.cpu_count(), "cpu_measure": "logical_processors",
        "ram_gib": None, "ram_available_gib": None, "gpu": None,
        "workspace": str(Path(state_dir)),
        "observed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "notes": "CPU count is logical processors. GPU capacity is unmeasured. This host runs the control interface, not model inference.",
    }
    try:
        disk = shutil.disk_usage(state_dir)
        item.update(
            disk_gib=round(disk.total / 2**30, 2),
            disk_free_gib=round(disk.free / 2**30, 2),
            disk_total_bytes=disk.total, disk_used_bytes=disk.used,
            disk_free_bytes=disk.free,
        )
    except OSError:
        item.update(disk_gib=None, disk_free_gib=None, disk_total_bytes=None,
                    disk_used_bytes=None, disk_free_bytes=None)
    try:
        if system == "Windows":
            class MemoryStatus(ctypes.Structure):
                _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong)] + [(name, ctypes.c_ulonglong) for name in ("total", "available", "page_total", "page_available", "virtual_total", "virtual_available", "extended")]
            status = MemoryStatus()
            status.length = ctypes.sizeof(status)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                item["ram_gib"] = round(status.total / 2**30, 2)
                item["ram_available_gib"] = round(status.available / 2**30, 2)
        elif system == "Linux":
            fields = {"MemTotal": "ram_gib", "MemAvailable": "ram_available_gib"}
            for line in Path("/proc/meminfo").read_text().splitlines():
                name, separator, value = line.partition(":")
                if not separator or name not in fields:
                    continue
                parts = value.split()
                # A damaged measurement must not hide the other usable one.
                # procfs reports these values as nonnegative integers in kB.
                if (len(parts) != 2 or parts[1] != "kB"
                        or not parts[0].isascii() or not parts[0].isdecimal()):
                    continue
                try:
                    gib = round(int(parts[0]) / 2**20, 2)
                except (ValueError, OverflowError):
                    continue
                item[fields[name]] = gib
    except (OSError, AttributeError, ValueError, KeyError):
        pass
    if system == "Linux":
        limits = _linux_process_limits()
        item["process_limits"] = limits
        item["cpu_cgroup_stats"] = _linux_cpu_stats(limits)
        cpu = [value for value in (item["cpu"], limits["cpu_affinity_processors"],
                                  limits["cpu_quota_processors"]) if value is not None]
        item["cpu_capacity"] = min(cpu) if cpu else None
        memory = [value for value in (item["ram_gib"],
                  limits["memory_limit_bytes"] / 2**30 if limits["memory_limit_bytes"] is not None else None)
                  if value is not None]
        item["ram_capacity_gib"] = round(min(memory), 2) if memory else None
        headroom = limits["memory_headroom_bytes"]
        item["ram_cgroup_headroom_gib"] = round(headroom / 2**30, 2) if headroom is not None else None
        item["notes"] += (
            f" Observed worker ceilings: {item['cpu_capacity']} CPUs, "
            f"{item['ram_capacity_gib']} GiB RAM; cgroup charge headroom "
            f"{item['ram_cgroup_headroom_gib']} GiB ({limits['cgroup_status']})."
            " cpu_capacity and ram_capacity_gib apply observed process limits; "
            "the original cpu/ram fields remain host measurements. "
            "ram_cgroup_headroom_gib is a charge budget, not reclaim-aware available RAM."
        )
    return item

def with_host(center, state):
    item = host_observation(center.state_dir)
    return {**state, "machines": [item], "sessions": [item] + state.get("sessions", [])}
