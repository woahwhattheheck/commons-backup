from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from laundry_desk import InvoiceBlocked, LaundryDesk


def build_demo(db_path: str) -> dict:
    desk = LaundryDesk(db_path)
    service_date = "2026-09-21"  # Monday
    desk.add_customer("demo.customer.alpha", "cust-alpha", "Alpha Hotel Group")
    desk.add_customer("demo.customer.beta", "cust-beta", "Beta Bistro Group")
    desk.add_site("demo.site.alpha", "site-alpha", "cust-alpha", "Alpha Downtown")
    desk.add_site("demo.site.beta", "site-beta", "cust-beta", "Beta Riverside")
    for site, prefix in (("site-alpha", "alpha"), ("site-beta", "beta")):
        desk.add_agreement(f"demo.agreement.{prefix}.sheet", f"agr-{prefix}-sheet", site, "sheet", 185, "2026-01-01")
        desk.add_agreement(f"demo.agreement.{prefix}.towel", f"agr-{prefix}-towel", site, "towel", 95, "2026-01-01")
    desk.add_service_plan("demo.plan.alpha", "plan-alpha", "site-alpha", "route-louisville", 0, 10, "2026-01-01")
    desk.add_service_plan("demo.plan.beta", "plan-beta", "site-beta", "route-louisville", 0, 20, "2026-01-01")
    route = desk.create_daily_route("demo.route", service_date, "route-louisville").value
    alpha, beta = route["stops"]

    desk.pickup("demo.alpha.pickup", alpha["stop_id"], {"sheet": 100, "towel": 60}, ["A-001", "A-002"])
    desk.process("demo.alpha.process", alpha["stop_id"], {"sheet": 100, "towel": 60}, {"sheet": 0, "towel": 0})
    desk.deliver("demo.alpha.deliver", alpha["stop_id"], {"sheet": 100, "towel": 60}, ["A-001", "A-002"])
    alpha_invoice = desk.draft_invoice("demo.alpha.invoice", alpha["stop_id"]).value

    desk.pickup("demo.beta.pickup", beta["stop_id"], {"sheet": 40, "towel": 80}, ["B-001"])
    beta_process = desk.process("demo.beta.process", beta["stop_id"], {"sheet": 39, "towel": 79}, {"sheet": 1, "towel": 0}).value
    desk.deliver("demo.beta.deliver", beta["stop_id"], {"sheet": 39, "towel": 79}, ["B-001"])
    blocked = False
    try:
        desk.draft_invoice("demo.beta.invoice.blocked", beta["stop_id"])
    except InvoiceBlocked:
        blocked = True
    for idx, exc_id in enumerate(beta_process["open_exception_ids"], 1):
        desk.resolve_exception(f"demo.beta.resolve.{idx}", exc_id, "OWNER_REVIEWED", "Synthetic demo resolution")
    beta_invoice = desk.draft_invoice("demo.beta.invoice", beta["stop_id"]).value

    reopened = LaundryDesk(db_path)
    snapshot = reopened.route_snapshot(route["route_id"])
    exports = reopened.render_route_exports(route["route_id"])
    return {
        "route": snapshot,
        "invoice_blocked_before_resolution": blocked,
        "alpha_invoice_total_cents": alpha_invoice["total_cents"],
        "beta_invoice_total_cents": beta_invoice["total_cents"],
        "integrity": reopened.verify_integrity(),
        "export_sha256": {
            key: __import__("hashlib").sha256(value.encode()).hexdigest() for key, value in exports.items()
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the synthetic Commercial Laundry Operations Desk demo")
    parser.add_argument("--database", help="SQLite database path; temporary when omitted")
    args = parser.parse_args()
    if args.database:
        result = build_demo(args.database)
    else:
        with tempfile.TemporaryDirectory() as tmp:
            result = build_demo(str(Path(tmp) / "laundry-demo.sqlite3"))
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
