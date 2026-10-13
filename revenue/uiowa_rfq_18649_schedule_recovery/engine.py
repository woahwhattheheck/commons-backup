"""Deterministic generalized-precedence scheduling. No I/O or appointments."""
from __future__ import annotations

import heapq
import math
from dataclasses import dataclass
from typing import Mapping, Sequence

ROLES = ("Clark", "TJLabs", "University")
EPS = 1e-8


def number(value: object, name: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name}: finite number required")
    if value < 0 or (positive and value == 0):
        raise ValueError(f"{name}: {'positive' if positive else 'nonnegative'} number required")
    return float(value)


def role_values(values: object, name: str, *, nullable: bool = False) -> dict:
    if not isinstance(values, dict) or set(values) != set(ROLES):
        raise ValueError(f"{name}: exactly {ROLES} required")
    return {r: None if nullable and values[r] is None else number(values[r], f"{name}.{r}") for r in ROLES}


@dataclass(frozen=True)
class Task:
    id: str
    duration: float
    release: float | None = 0
    label: str = ""


@dataclass(frozen=True)
class Edge:
    predecessor: str
    successor: str
    relation: str = "FS"
    lag: float = 0
    reason: str = ""


def schedule(tasks: Sequence[Task], edges: Sequence[Edge]) -> dict:
    """ES successor >= ES predecessor + edge weight, in relative workdays.

    FS: weight = predecessor duration + lag.
    SS: weight = lag.
    FF: weight = predecessor duration + lag - successor duration.
    A null release means UNKNOWN, not zero. Unknowns propagate downstream.
    """
    if not tasks or len(tasks) > 500:
        raise ValueError("provide between 1 and 500 tasks")
    nodes = {}
    for t in tasks:
        if not isinstance(t.id, str) or not t.id or t.id in nodes:
            raise ValueError("task IDs must be unique nonempty strings")
        number(t.duration, f"{t.id}.duration")
        if t.release is not None:
            number(t.release, f"{t.id}.release")
        nodes[t.id] = t
    incoming = {key: [] for key in nodes}
    outgoing = {key: [] for key in nodes}
    seen = set()
    for e in edges:
        if e.predecessor not in nodes or e.successor not in nodes:
            raise ValueError("edge references an unknown task")
        if e.predecessor == e.successor or e.relation not in ("FS", "SS", "FF"):
            raise ValueError("invalid dependency relation")
        number(e.lag, "edge.lag")
        key = (e.predecessor, e.successor, e.relation)
        if key in seen:
            raise ValueError("duplicate dependency relation")
        seen.add(key)
        weight = e.lag
        if e.relation in ("FS", "FF"):
            weight += nodes[e.predecessor].duration
        if e.relation == "FF":
            weight -= nodes[e.successor].duration
        incoming[e.successor].append((e, weight))
        outgoing[e.predecessor].append((e, weight))
    degrees = {key: len(incoming[key]) for key in nodes}
    ready = [key for key, value in degrees.items() if value == 0]
    heapq.heapify(ready)
    order = []
    while ready:
        key = heapq.heappop(ready)
        order.append(key)
        for e, _ in outgoing[key]:
            degrees[e.successor] -= 1
            if degrees[e.successor] == 0:
                heapq.heappush(ready, e.successor)
    if len(order) != len(nodes):
        raise ValueError("dependency graph contains a cycle")
    rows = {}
    for key in order:
        task = nodes[key]
        blockers = {key} if task.release is None else set()
        constraints = [(task.release or 0, None, "planned release")]
        for e, weight in sorted(incoming[key], key=lambda pair: (pair[0].predecessor, pair[0].relation)):
            pred = rows[e.predecessor]
            blockers.update(pred["unknown_inputs"])
            if pred["start"] is not None:
                constraints.append((pred["start"] + weight, e.predecessor, e.reason or e.relation))
        if blockers:
            start, drivers = None, []
        else:
            start = max(c[0] for c in constraints)
            drivers = [{"predecessor": p, "reason": reason} for v, p, reason in constraints if abs(v-start) < EPS]
        end = None if start is None else start + task.duration
        if end is not None and end > 10000:
            raise ValueError("schedule exceeds 10000 workdays")
        rows[key] = {"id": key, "label": task.label or key, "start": start, "finish": end,
                     "duration": task.duration, "unknown_inputs": sorted(blockers),
                     "drivers": drivers, "float_days": None}
    known_finish = max((r["finish"] for r in rows.values() if r["finish"] is not None), default=0)
    complete = all(r["finish"] is not None for r in rows.values())
    critical, critical_edges, chain = None, None, None
    if complete:
        latest = {key: known_finish-nodes[key].duration for key in nodes}
        for key in reversed(order):
            for e, weight in outgoing[key]:
                latest[key] = min(latest[key], latest[e.successor]-weight)
            rows[key]["float_days"] = max(0.0, latest[key]-rows[key]["start"])
        critical = [key for key in order if rows[key]["float_days"] < EPS]
        critical_edges = [{"from": e.predecessor, "to": e.successor, "relation": e.relation, "lag": e.lag}
                          for key in order for e, weight in outgoing[key]
                          if key in critical and e.successor in critical
                          and abs(rows[e.successor]["start"]-rows[key]["start"]-weight) < EPS]
        # One representative chain; all critical tasks/edges remain available.
        end_key = next(key for key in reversed(order) if abs(rows[key]["finish"]-known_finish) < EPS)
        chain = [end_key]
        while True:
            parents = [d["predecessor"] for d in rows[chain[-1]]["drivers"] if d["predecessor"] is not None]
            if not parents:
                break
            chain.append(sorted(parents)[0])
        chain.reverse()
    return {"complete": complete, "finish": known_finish if complete else None,
            "finish_lower_bound": known_finish, "tasks": rows,
            "critical_tasks": critical, "critical_edges": critical_edges, "driving_chain": chain}


def load_profile(rows: Mapping[str, dict], hours: Mapping[str, Mapping[str, float]],
                 capacities: Mapping[str, float]) -> dict:
    """Uniform planned effort over each work window; NOT resource leveling."""
    intervals = []
    unscheduled = []
    for key, workload in hours.items():
        row = rows[key]
        if row["start"] is None:
            unscheduled.append(key)
        elif row["finish"] > row["start"]:
            intervals.append((row["start"], row["finish"], workload))
        elif any(workload[r] > 0 for r in ROLES):
            raise ValueError(f"{key}: nonzero effort on a zero-duration task")
    points = sorted({x for a, b, _ in intervals for x in (a, b)})
    peaks = {r: 0.0 for r in ROLES}
    overloads = []
    for a, b in zip(points, points[1:]):
        demand = {r: sum(h[r]/(end-start) for start, end, h in intervals if start <= a < end) for r in ROLES}
        for r in ROLES:
            peaks[r] = max(peaks[r], demand[r])
            if demand[r] > capacities[r]/5 + EPS:
                overloads.append({"role": r, "start": a, "finish": b,
                                  "hours_per_day": demand[r], "assumed_capacity_per_day": capacities[r]/5})
    horizon = max((b for _, b, _ in intervals), default=0)
    weekly = []
    for i in range(math.ceil(horizon/5)):
        a, b = i*5, (i+1)*5
        demand = {r: sum(max(0, min(b, end)-max(a, start))*h[r]/(end-start)
                         for start, end, h in intervals) for r in ROLES}
        weekly.append({"week": i+1, "hours": demand})
    return {"peak_hours_per_day": peaks, "overloads": overloads, "weekly": weekly,
            "unscheduled_tasks": sorted(unscheduled), "resource_leveled": False,
            "availability_confirmed": False}
