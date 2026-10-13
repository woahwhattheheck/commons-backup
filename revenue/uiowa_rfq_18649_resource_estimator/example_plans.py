"""Three fictional planning cases, not University findings or staffing estimates."""


def band(low, central=None, high=None):
    return {"low": low, "central": low if central is None else central,
            "high": low if high is None else high}


def make_plan(case):
    assumptions = [
        {"id": "A-SCOPE", "text": "Application, participant and event counts are fictional scope assumptions; replace after discovery.", "source": "SYNTHETIC_PLANNING_ASSUMPTION"},
        {"id": "A-EFFORT", "text": "Low/central/high unit effort is planning judgement, not measured productivity or a confidence interval.", "source": "SYNTHETIC_PLANNING_ASSUMPTION"},
        {"id": "A-CAPACITY", "text": "Capacity is net monthly person-hours reserved after other commitments. Implementation and maintenance pools are separate, nonoverlapping allocations.", "source": "SYNTHETIC_PLANNING_ASSUMPTION"},
        {"id": "A-ADOPTION", "text": "Learner attendance and facilitator preparation are separate activities. Attendance alone does not establish changed practice or maturity.", "source": "SYNTHETIC_PLANNING_ASSUMPTION"},
    ]

    def role(key, name, skill, build, maintain):
        return {"id": key, "name": name, "skills": [skill],
                "implementation_hours_per_month": build, "maintenance_hours_per_month": maintain,
                "assumption_ids": ["A-CAPACITY"]}

    def rec(key, title, group, area, dependencies, adoption, evidence):
        return {"id": key, "title": title, "group_id": group, "area": area,
                "dependencies": dependencies, "adoption_notes": adoption, "success_evidence": evidence}

    def activity(key, description, rec_ids, role_id, kind, unit_label, units, hours):
        return {"id": key, "description": description, "recommendation_ids": rec_ids,
                "role_id": role_id, "kind": kind, "unit_label": unit_label,
                "units": band(units), "hours_per_unit": hours,
                "assumption_ids": ["A-SCOPE", "A-EFFORT"] + (["A-ADOPTION"] if kind == "training" else [])}

    plan = {"schema": "uiowa.resource-plan/v1", "plan_id": "SYN-" + case.upper(),
            "title": "Fictional " + case + " improvement", "evidence_class": "SYNTHETIC",
            "planning_months": 3, "assumptions": assumptions, "roles": [], "recommendations": [], "activities": []}
    if case == "release":
        plan["roles"] = [role("dev", "Application developers", "Release documentation", band(40, 56, 72), band(8, 12, 16)),
                         role("ops", "Service operations", "Operational handoff", band(24, 32, 40), band(10, 16, 24))]
        plan["recommendations"] = [
            rec("SYN-REL-1", "Define a usable handoff", "Fictional enterprise applications", "deployment", [], "Co-design the handoff with operators; try it on one release before wider adoption.", "A sampled handoff links changes, rollback, ownership and support evidence."),
            rec("SYN-REL-2", "Maintain application runbooks", "Fictional enterprise applications", "deployment", ["SYN-REL-1"], "Train maintainers and include refresh in existing release reviews.", "A later operator can use a sampled runbook and record missing steps."),
        ]
        plan["activities"] = [
            activity("REL-INVENTORY", "Inspect eight fictional application handoffs", ["SYN-REL-1"], "dev", "implementation", "applications", 8, band(1, 2, 3)),
            activity("REL-DESIGN", "Co-design the common handoff process", ["SYN-REL-1"], "ops", "process_change", "workshops including preparation", 1, band(12, 20, 32)),
            activity("REL-RUNBOOK", "Populate initial runbooks", ["SYN-REL-2"], "ops", "implementation", "applications", 8, band(2, 3, 5)),
            activity("REL-LEARN", "Shared learner attendance, counted once", ["SYN-REL-1", "SYN-REL-2"], "dev", "training", "learners", 12, band(1, "1.5", 2)),
            activity("REL-FACILITATE", "Facilitate and prepare shared sessions", ["SYN-REL-1", "SYN-REL-2"], "ops", "training", "sessions", 2, band(2, 3, 4)),
            activity("REL-REVIEW", "Monthly handoff review", ["SYN-REL-1"], "ops", "maintenance", "reviews per month", 4, band(1, "1.5", 2)),
            activity("REL-REFRESH", "Monthly runbook refresh", ["SYN-REL-2"], "ops", "maintenance", "applications per month", 8, band("0.25", "0.5", 1)),
        ]
    elif case == "security":
        plan["planning_months"] = 2
        plan["roles"] = [role("dev", "Application developers", "Development practice adaptation", band(32, 48, 64), band(4, 8, 12)),
                         role("specialist", "Security practice specialist", "Facilitated design and review", band(4, 6, 8), band(2, 4, 6))]
        plan["recommendations"] = [rec("SYN-SEC-1", "Integrate security practice into development", "Fictional research services", "security", [], "Use facilitated examples and existing review touchpoints; do not buy a new product as the default response.", "Later sampled changes demonstrate that the agreed practice is used and unresolved concerns are followed up.")]
        plan["activities"] = [
            activity("SEC-ADAPT", "Adapt six application workflows", ["SYN-SEC-1"], "dev", "implementation", "applications", 6, band(2, 4, 6)),
            activity("SEC-CLINIC", "Specialist-supported practice clinics", ["SYN-SEC-1"], "specialist", "implementation", "applications", 6, band(3, 4, 6)),
            activity("SEC-TRAINER", "Specialist preparation and instruction", ["SYN-SEC-1"], "specialist", "training", "sessions", 2, band(1, 2, 3)),
            activity("SEC-LEARN", "Learner attendance", ["SYN-SEC-1"], "dev", "training", "learners", 16, band(1, "1.5", 2)),
            activity("SEC-TRIAGE", "Agree concern ownership and follow-through", ["SYN-SEC-1"], "dev", "process_change", "process changes", 1, band(4, 8, 12)),
            activity("SEC-MAINTAIN", "Monthly specialist-supported sample reviews", ["SYN-SEC-1"], "specialist", "maintenance", "reviews per month", 4, band("0.5", 1, "1.5")),
        ]
    elif case == "reliability":
        plan["planning_months"] = 6
        plan["roles"] = [role("ops", "Service operations", "Recovery exercises", band(12, 20, 28), None),
                         role("dev", "Application maintainers", "Application observability", None, band(2, 4, 8))]
        plan["recommendations"] = [
            rec("SYN-OPS-1", "Rehearse service recovery", "Fictional identity services", "deployment", [], "Start with a bounded non-production exercise and assign follow-through ownership.", "Exercise records show actual recovery steps, unresolved gaps and subsequent corrections."),
            rec("SYN-OPS-2", "Improve actionable operational signals", "Fictional identity services", "deployment", ["SYN-OPS-1"], "Inspect existing signals before estimating instrumentation work.", "Future sampled signals connect a symptom to a support response without unreviewed production changes."),
        ]
        plan["activities"] = [
            activity("OPS-DESIGN", "Design recovery exercises", ["SYN-OPS-1"], "ops", "implementation", "services", 3, band(8, 12, 20)),
            activity("OPS-SIGNALS", "Instrumentation effort not yet assessed", ["SYN-OPS-2"], "dev", "implementation", "applications", 6, None),
            activity("OPS-TRAIN", "Shared practitioner exercise attendance", ["SYN-OPS-1", "SYN-OPS-2"], "ops", "training", "learners", 10, band(1, 2, 3)),
            activity("OPS-REHEARSE", "Recurring rehearsal and action review", ["SYN-OPS-1"], "ops", "maintenance", "exercises per month", 1, band(3, 4, 6)),
        ]
    else:
        raise ValueError(f"Unknown synthetic case: {case}")
    return plan
