#!/usr/bin/env python3
"""Reproducible fictional inputs. None describe University operations or prices."""
from __future__ import annotations
import json
from economics import FIELDS, VERSION


def synthetic_document():
    """Return four explicitly fictional cases with no real-person productivity data."""
    defaults = {
        "monthly_tasks": ("300", "400", "500"),
        "adoption_fraction": ("0.7", "0.8", "0.9"),
        "baseline_minutes": ("30", "40", "50"),
        "author_minutes": ("5", "6", "8"),
        "checking_minutes": ("5", "7", "10"),
        "rework_fraction": ("0.10", "0.15", "0.20"),
        "rework_minutes": ("10", "15", "20"),
        "attempts_per_task": ("1", "1.5", "2"),
        "generation_cash_per_attempt": ("0.03", "0.05", "0.08"),
        "loaded_hourly_rate": ("50", "60", "70"),
        "integration_hours": ("12", "18", "24"),
        "setup_cash": ("100", "150", "200"),
        "support_hours": ("1", "1.5", "2"),
        "maintenance_hours": ("1", "1.5", "2"),
        "platform_cash": ("20", "35", "50"),
        "cash_conversion_fraction": ("0", "0", "0"),
    }
    scenarios = []

    def add(sid, group, label, notes, overrides):
        values = dict(defaults, **overrides)
        inputs = {}
        for field, limits in values.items():
            inputs[field] = {
                "range": None if limits is None else dict(zip(("low", "base", "high"), limits)),
                "unit": FIELDS[field][0], "basis": "unknown" if limits is None else "synthetic",
                "source": f"synthetic_cases.py::{sid}::{field}; fictional training assumption, not observed evidence",
            }
        scenarios.append({"id": sid, "group": group, "label": label, "notes": notes, "inputs": inputs})

    add("SYN-ESS-DOCS", "ESS", "Fictional documentation drafting",
        "High-volume synthetic case. Comparable accepted-output quality is an assumption to test separately. Cash conversion is explicitly zero, so positive capacity value does not claim a cash saving.", {})
    add("SYN-RIS-REVIEW", "RIS", "Fictional low-volume, high-review workflow",
        "Verification and repair dominate this synthetic task. More volume is not a cure for a negative per-task contribution. No claim is made about research staff or University practices.", {
            "monthly_tasks": ("10", "15", "20"), "adoption_fraction": ("0.5", "0.75", "1"),
            "baseline_minutes": ("15", "20", "25"), "author_minutes": ("10", "12", "15"),
            "checking_minutes": ("20", "25", "35"), "rework_fraction": ("0.3", "0.4", "0.6"),
            "rework_minutes": ("20", "30", "45"), "integration_hours": ("30", "40", "50"),
            "support_hours": ("4", "6", "8"), "maintenance_hours": ("3", "4", "6"),
            "platform_cash": ("30", "60", "90"), "generation_cash_per_attempt": ("0.1", "0.2", "0.3"),
            "attempts_per_task": ("1", "2", "3"),
        })
    add("SYN-IAM-SUMMARY", "IAM", "Fictional requirements summarization",
        "Independent synthetic ranges intentionally span both signs of net value. The base case is not a prediction, median, percentile or promised productivity multiplier.", {
            "monthly_tasks": ("60", "90", "120"), "adoption_fraction": ("0.5", "0.7", "0.9"),
            "baseline_minutes": ("30", "40", "50"), "author_minutes": ("5", "8", "10"),
            "checking_minutes": ("8", "15", "25"), "rework_fraction": ("0.1", "0.25", "0.4"),
            "rework_minutes": ("10", "15", "25"), "support_hours": ("2", "3", "4"),
            "maintenance_hours": ("2", "3", "4"), "integration_hours": ("10", "18", "25"),
            "platform_cash": ("30", "50", "70"), "cash_conversion_fraction": ("0", "0.1", "0.2"),
        })
    add("SYN-ESS-UNKNOWN", "ESS", "Fictional test drafting with missing verification evidence",
        "Checking and rework incidence are deliberately unmeasured. Generation speed alone cannot support a net-value result. Null is unknown, never zero.", {
            "checking_minutes": None, "rework_fraction": None,
        })
    return {"schema_version": VERSION, "input_basis": "SYNTHETIC", "currency": "USD", "horizon_months": 12, "scenarios": scenarios}


if __name__ == "__main__":
    print(json.dumps(synthetic_document(), ensure_ascii=False, indent=2))
