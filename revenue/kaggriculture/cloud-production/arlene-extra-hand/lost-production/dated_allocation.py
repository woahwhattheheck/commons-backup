"""Bounded, dependency-free scheduling and dated-stock allocation.

The executor borrows only modelling ideas from pinned OR-Tools and Stockpyl
sources: jobs are optional, route tasks are ordered, one worker cannot overlap
jobs, and inventory is earmarked once at the time it becomes accessible.
"""


def allocate_dated_stock(requirements, supplies):
    """Allocate shared stock before each consumer and return allocations/shorts.

    `supplies` entries are ``(accessible_step, product, quantity, source)``.
    `requirements` entries are ``(consume_step, product, quantity, job_id)``.
    Market purchases must therefore use the step after the BUY_PRODUCT order.
    """
    available = {}
    ordered_supplies = sorted(supplies, key=lambda row: (row[0], row[1], row[3]))
    supply_index = 0
    allocated, shorts = {}, {}
    for step, product, quantity, job_id in sorted(requirements, key=lambda row: (row[0], row[3], row[1])):
        while supply_index < len(ordered_supplies) and ordered_supplies[supply_index][0] <= step:
            _, item, units, _ = ordered_supplies[supply_index]
            available[item] = available.get(item, 0) + max(0, int(units))
            supply_index += 1
        wanted = max(0, int(quantity))
        take = min(wanted, available.get(product, 0))
        available[product] = available.get(product, 0) - take
        allocated[(job_id, product, step)] = take
        if take < wanted:
            shorts[(job_id, product, step)] = wanted - take
    return {"allocated": allocated, "shorts": shorts, "remaining": available}


def select_optional_jobs(jobs, supplies=(), max_jobs=1):
    """Choose a deterministic non-overlapping feasible subset of <=16 jobs.

    This is deliberately a tiny executor, not an OR-Tools runtime dependency.
    Each job has start/end, value, id, and optional dated requirements.
    """
    rows = sorted(jobs[:16], key=lambda j: (j["end_step"], j["start_step"], j["id"]))
    best = (0, ())

    def visit(index, chosen):
        nonlocal best
        value = sum(int(j["value"]) for j in chosen)
        ids = tuple(j["id"] for j in chosen)
        if value > best[0] or (value == best[0] and ids < tuple(j["id"] for j in best[1])):
            best = (value, tuple(chosen))
        if index >= len(rows) or len(chosen) >= max_jobs:
            return
        for pos in range(index, len(rows)):
            job = rows[pos]
            if chosen and job["start_step"] <= chosen[-1]["end_step"]:
                continue
            requirements = []
            for row in (*chosen, job):
                requirements.extend(row.get("requirements", ()))
            if allocate_dated_stock(requirements, supplies)["shorts"]:
                continue
            visit(pos + 1, [*chosen, job])

    visit(0, [])
    return list(best[1])
