"""Staffing scheduler with dependencies, delays, capacity, and overflow."""

from __future__ import annotations

from decimal import Decimal

try:
    from .canonical import (
        AUTHORITY,
        GROUPS,
        INTERVIEW_SESSIONS,
        ONSITE_SUBSET_OF,
        ROLES,
        SPECIALIST_DEFAULT_LOCATION,
        SPECIALIST_HOURS_IN_BASE,
        TASKS,
        TRAVEL,
    )
    from .workbook import D, StaffingError
except ImportError:
    from canonical import (
        AUTHORITY,
        GROUPS,
        INTERVIEW_SESSIONS,
        ONSITE_SUBSET_OF,
        ROLES,
        SPECIALIST_DEFAULT_LOCATION,
        SPECIALIST_HOURS_IN_BASE,
        TASKS,
        TRAVEL,
    )
    from workbook import D, StaffingError

ZERO = Decimal("0.00")
CENT = Decimal("0.01")

DEPENDENCIES = {
    "preparation": [],
    "evidence_processing": ["preparation"],
    "interview_support": ["preparation"],
    "synthesis": ["evidence_processing", "interview_support"],
    "review": ["synthesis"],
    "correction": ["review"],
}
DELAY_FOR = {
    "evidence_processing": "evidence_access_delay_weeks",
    "interview_support": "interview_schedule_delay_weeks",
    "review": "review_delay_weeks",
    "correction": "review_delay_weeks",
}


def schedule(workbook):
    a = workbook["assumptions"]
    horizon = a["horizon_weeks"]
    spec_cap = D(a["specialist_capacity_hours_per_week"], "specialist_capacity")
    prime_cap = D(a["prime_capacity_hours_per_week"], "prime_capacity")
    spec_hours = {t: D(a["specialist_task_hours"][t], t) for t in TASKS}
    prime_hours = {
        "interviews": D(a["prime_task_hours"]["interviews"], "prime.interviews"),
        "review": D(a["prime_task_hours"]["review"], "prime.review"),
    }
    spec_capacity = [spec_cap for _ in range(horizon)]
    prime_capacity = [prime_cap for _ in range(horizon)]

    spec_used = [ZERO for _ in range(horizon)]
    spec_rows = {}
    finish = {}

    def earliest_for(task):
        deps = DEPENDENCIES[task]
        start = 0
        if deps:
            start = max(finish[d] for d in deps)
        delay_key = DELAY_FOR.get(task)
        if delay_key:
            start = max(start, a[delay_key])
        return start

    # Preparation has no delay; others wait on finish weeks of deps + delay.
    for task in TASKS:
        start = earliest_for(task)
        assigned, end, spec_used = _allocate_into(
            spec_hours[task], start, spec_capacity, spec_used, horizon, "specialist." + task
        )
        spec_rows[task] = {"hours": spec_hours[task], "earliest_week": start, "weekly": assigned}
        finish[task] = end

    prime_used = [ZERO for _ in range(horizon)]
    # Prime interviews track specialist interview_support start (grouped sessions).
    p_int_start = spec_rows["interview_support"]["earliest_week"]
    p_int_weekly, p_int_end, prime_used = _allocate_into(
        prime_hours["interviews"], p_int_start, prime_capacity, prime_used, horizon, "prime.interviews"
    )
    p_rev_start = max(p_int_end + 1, spec_rows["review"]["earliest_week"])
    p_rev_weekly, p_rev_end, prime_used = _allocate_into(
        prime_hours["review"], p_rev_start, prime_capacity, prime_used, horizon, "prime.review"
    )

    spec_weekly_total = [ZERO for _ in range(horizon)]
    for row in spec_rows.values():
        for i, qty in enumerate(row["weekly"]):
            spec_weekly_total[i] = (spec_weekly_total[i] + qty).quantize(CENT)
    prime_weekly_total = [(p_int_weekly[i] + p_rev_weekly[i]).quantize(CENT) for i in range(horizon)]

    for i, qty in enumerate(spec_weekly_total):
        if qty - spec_cap > Decimal("0.00"):
            raise StaffingError("specialist week %s exceeds capacity" % i)
    for i, qty in enumerate(prime_weekly_total):
        if qty - prime_cap > Decimal("0.00"):
            raise StaffingError("prime week %s exceeds capacity" % i)

    onsite_specialist = D(a["specialist_onsite_subset_hours"], "specialist_onsite")
    onsite_prime = D(a["prime_onsite_subset_hours"], "prime_onsite")
    # Subset check: onsite hours are taken from interview hours, not added.
    productive_specialist = sum(spec_hours.values(), ZERO)
    productive_prime = prime_hours["interviews"] + prime_hours["review"]

    peak_spec = max(spec_weekly_total) if spec_weekly_total else ZERO
    peak_prime = max(prime_weekly_total) if prime_weekly_total else ZERO

    return {
        "horizon_weeks": horizon,
        "participant_count": a["participant_count"],
        "interview_sessions": INTERVIEW_SESSIONS,
        "groups": list(GROUPS),
        "participant_count_is_not_session_count": True,
        "roles": dict(ROLES),
        "travel": TRAVEL,
        "specialist_location": SPECIALIST_DEFAULT_LOCATION,
        "onsite_subset_of": ONSITE_SUBSET_OF,
        "specialist": {
            "task_hours": spec_hours,
            "rows": spec_rows,
            "weekly_total": spec_weekly_total,
            "capacity_per_week": spec_cap,
            "peak_hours": peak_spec,
            "productive_hours": productive_specialist,
            "onsite_subset_hours": onsite_specialist,
            "onsite_is_additive": False,
            "hours_in_base": SPECIALIST_HOURS_IN_BASE,
        },
        "prime": {
            "task_hours": prime_hours,
            "weekly_interviews": p_int_weekly,
            "weekly_review": p_rev_weekly,
            "weekly_total": prime_weekly_total,
            "capacity_per_week": prime_cap,
            "peak_hours": peak_prime,
            "productive_hours": productive_prime,
            "onsite_subset_hours": onsite_prime,
            "onsite_is_additive": False,
        },
        "authority": dict(AUTHORITY),
        "delays": {
            "evidence_access_weeks": a["evidence_access_delay_weeks"],
            "interview_schedule_weeks": a["interview_schedule_delay_weeks"],
            "review_weeks": a["review_delay_weeks"],
        },
    }


def _allocate_into(hours, earliest, capacity, used, horizon, label):
    remaining = hours
    assigned = [ZERO for _ in range(horizon)]
    week = earliest
    used = list(used)
    while remaining > 0:
        if week >= horizon:
            raise StaffingError(
                "overflow hours %s for %s would be lost after week %s"
                % (remaining, label, horizon - 1)
            )
        room = (capacity[week] - used[week]).quantize(CENT)
        if room < 0:
            raise StaffingError("capacity already exceeded in week %s for %s" % (week, label))
        if room == 0:
            week += 1
            continue
        take = remaining if remaining <= room else room
        assigned[week] = (assigned[week] + take).quantize(CENT)
        used[week] = (used[week] + take).quantize(CENT)
        remaining = (remaining - take).quantize(CENT)
        if remaining > 0:
            week += 1
    finish = earliest
    for i, qty in enumerate(assigned):
        if qty > 0:
            finish = i
    if hours == 0:
        finish = max(earliest - 1, 0)
    return assigned, finish, used
