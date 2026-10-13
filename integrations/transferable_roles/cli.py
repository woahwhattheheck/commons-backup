#!/usr/bin/env python3
"""CLI entry for transferable roles.

Examples:
  python3 integrations/transferable_roles/cli.py create --file fixtures/synthetic_crm_followup_role.json --store /tmp/roles
  python3 integrations/transferable_roles/cli.py equip ROLE --session A --harness cursor --seat HINGE --store /tmp/roles
  python3 integrations/transferable_roles/cli.py bind-route ROLE --route grokbot_control_g2 --session-id sess-1 --last-run-id run-9 --store /tmp/roles
  python3 integrations/transferable_roles/cli.py unbind-route ROLE --route grokbot_control_g2 --store /tmp/roles
  python3 integrations/transferable_roles/cli.py transfer ROLE --from-session A --to-session B --to-harness claude --seat TENON --store /tmp/roles
  python3 integrations/transferable_roles/cli.py release ROLE --from-session A --store /tmp/roles
  python3 integrations/transferable_roles/cli.py advance-obligation ROLE --id ob-1 --status done --evidence-pointer p/example.md --store /tmp/roles
  python3 integrations/transferable_roles/cli.py open-obligations --store /tmp/roles
  python3 integrations/transferable_roles/cli.py open-obligations --cash-only --store /tmp/roles
  python3 integrations/transferable_roles/cli.py diagnostic-contract ROLE --slug dealer --store /tmp/roles
  python3 integrations/transferable_roles/cli.py diagnostic-receipt ROLE --slug dealer --store /tmp/roles
  python3 integrations/transferable_roles/cli.py diagnostic-fulfill-deadline ROLE --slug dealer --usable-evidence-at 2026-09-04T15:00:00-04:00 --store /tmp/roles
  python3 integrations/transferable_roles/cli.py diagnostic-fulfill-sla ROLE --slug dealer --usable-evidence-at 2026-09-04T15:00:00-04:00 --as-of 2026-09-08T10:00:00-04:00 --store /tmp/roles
  python3 integrations/transferable_roles/cli.py prove-handoff ROLE --store /tmp/roles
  python3 integrations/transferable_roles/cli.py export ROLE --store /tmp/roles
  python3 integrations/transferable_roles/cli.py import --file /tmp/role-export.json --store /tmp/roles-successor
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from diagnostic_contract import load_contract_from_role
from diagnostic_fulfill import run_deadline as run_diagnostic_deadline
from diagnostic_fulfill import run_sla_status as run_diagnostic_sla
from diagnostic_receipt import load_receipt_from_role
from handoff_execute import prove_successor_executes
from roles import RoleError, RoleStore


def _load_json(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RoleError("JSON root must be an object")
    return data


def _print(obj: object) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--store",
        type=Path,
        default=Path(".transferable_roles"),
        help="directory for role JSON records",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("create", help="create a role record")
    c.add_argument("--file", type=Path, required=True)
    c.add_argument("--role-id")

    e = sub.add_parser("equip", help="bind an unoccupied role to a session")
    e.add_argument("role_id")
    e.add_argument("--session", required=True)
    e.add_argument("--harness", required=True)
    e.add_argument("--account-pool")
    e.add_argument(
        "--seat",
        help="optional occupant name (not role_id); never a gate",
    )

    t = sub.add_parser("transfer", help="hand role to another session/harness")
    t.add_argument("role_id")
    t.add_argument("--from-session")
    t.add_argument("--to-session", required=True)
    t.add_argument("--to-harness", required=True)
    t.add_argument("--account-pool")
    t.add_argument(
        "--seat",
        help="optional successor occupant name (not role_id); never a gate",
    )

    b = sub.add_parser(
        "bind-route",
        help="stamp durable G2 session_id/last_run_id onto a named access_route",
    )
    b.add_argument("role_id")
    b.add_argument("--route", required=True, help="access_route.name")
    b.add_argument("--session-id", help="durable G2 conversation id")
    b.add_argument("--last-run-id", help="last G2 run_id")
    b.add_argument("--pool-id", help="pool name only; never invent a second pool")

    u = sub.add_parser(
        "unbind-route",
        help="clear stamped session_id/last_run_id (optional pool_id) on a route",
    )
    u.add_argument("role_id")
    u.add_argument("--route", required=True, help="access_route.name")
    u.add_argument(
        "--fields",
        help="comma-separated subset of session_id,last_run_id,pool_id "
        "(default: session_id,last_run_id)",
    )

    r = sub.add_parser(
        "release",
        help="clear occupant so a later session can equip (keeps bound routes)",
    )
    r.add_argument("role_id")
    r.add_argument(
        "--from-session",
        help="optional guard: must match current occupant.session_id",
    )

    a = sub.add_parser(
        "advance-obligation",
        help="update one obligation status/next_action/evidence (not credentials)",
    )
    a.add_argument("role_id")
    a.add_argument("--id", required=True, dest="obligation_id", help="obligation.id")
    a.add_argument("--status", help="open|done|blocked|deferred")
    a.add_argument("--next-action")
    a.add_argument("--evidence-pointer")

    dc = sub.add_parser(
        "diagnostic-contract",
        help="load landed $199 diagnostic contract.json by slug "
        "(dealer|referral|repair|plant)",
    )
    dc.add_argument("role_id")
    dc.add_argument(
        "--slug",
        required=True,
        choices=("dealer", "referral", "repair", "plant"),
    )

    dr = sub.add_parser(
        "diagnostic-receipt",
        help="load landed $199 diagnostic receipt.json by slug "
        "(dealer|referral|plant)",
    )
    dr.add_argument("role_id")
    dr.add_argument(
        "--slug",
        required=True,
        choices=("dealer", "referral", "plant"),
    )

    dfd = sub.add_parser(
        "diagnostic-fulfill-deadline",
        help="compute $199 delivery_due_at via the one-business-day calendar "
        "after loading contract window",
    )
    dfd.add_argument("role_id")
    dfd.add_argument(
        "--slug",
        required=True,
        choices=("dealer", "referral", "repair", "plant"),
    )
    dfd.add_argument("--usable-evidence-at", required=True)

    dfs = sub.add_parser(
        "diagnostic-fulfill-sla",
        help="OPEN|MISSED $199 SLA vs as_of + landed miss-remedy refund card",
    )
    dfs.add_argument("role_id")
    dfs.add_argument(
        "--slug",
        required=True,
        choices=("dealer", "referral", "repair", "plant"),
    )
    dfs.add_argument("--usable-evidence-at", required=True)
    dfs.add_argument("--as-of", required=True)

    ph = sub.add_parser(
        "prove-handoff",
        help="prove role-gated executes still run after transfer/export handoff",
    )
    ph.add_argument("role_id")
    ph.add_argument("--case-ref", default="handoff_case")
    ph.add_argument(
        "--usable-evidence-at", default="2026-09-04T15:00:00-04:00"
    )
    ph.add_argument(
        "--slug",
        default="dealer",
        choices=("dealer", "referral", "repair", "plant"),
    )
    ph.add_argument(
        "--as-of",
        help="SLA as_of for diagnostic-fulfill-sla prove "
        "(default: usable-evidence-at → OPEN)",
    )

    i = sub.add_parser("inspect", help="print role record")
    i.add_argument("role_id")

    x = sub.add_parser("export", help="export portable package (no secrets)")
    x.add_argument("role_id")

    imp = sub.add_parser(
        "import",
        help="import export_package JSON without reminting role_id",
    )
    imp.add_argument("--file", type=Path, required=True, help="JSON package path")

    sub.add_parser("list", help="list role ids in the store")
    oo = sub.add_parser(
        "open-obligations",
        help="list open obligations across all roles as flat dicts",
    )
    oo.add_argument(
        "--cash-only",
        action="store_true",
        help="only rows marked payment_capability: true; this is not proof of payment",
    )
    for command_parser in sub.choices.values():
        command_parser.add_argument(
            "--store", type=Path, default=argparse.SUPPRESS,
            help="directory for role JSON records",
        )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    store = RoleStore(args.store)
    try:
        if args.cmd == "create":
            role = store.create(_load_json(args.file), role_id=args.role_id)
            _print(role)
        elif args.cmd == "equip":
            _print(
                store.equip(
                    args.role_id,
                    session_id=args.session,
                    harness=args.harness,
                    account_pool=args.account_pool,
                    seat=args.seat,
                )
            )
        elif args.cmd == "transfer":
            _print(
                store.transfer(
                    args.role_id,
                    to_session_id=args.to_session,
                    to_harness=args.to_harness,
                    from_session_id=args.from_session,
                    account_pool=args.account_pool,
                    seat=args.seat,
                )
            )
        elif args.cmd == "bind-route":
            _print(
                store.bind_access_route(
                    args.role_id,
                    route_name=args.route,
                    session_id=args.session_id,
                    last_run_id=args.last_run_id,
                    pool_id=args.pool_id,
                )
            )
        elif args.cmd == "unbind-route":
            fields = None
            if args.fields:
                fields = [f.strip() for f in args.fields.split(",") if f.strip()]
            _print(
                store.unbind_access_route(
                    args.role_id,
                    route_name=args.route,
                    fields=fields,
                )
            )
        elif args.cmd == "release":
            _print(
                store.release(
                    args.role_id,
                    from_session_id=args.from_session,
                )
            )
        elif args.cmd == "advance-obligation":
            _print(
                store.advance_obligation(
                    args.role_id,
                    args.obligation_id,
                    status=args.status,
                    next_action=args.next_action,
                    evidence_pointer=args.evidence_pointer,
                )
            )
        elif args.cmd == "diagnostic-contract":
            role = store.get(args.role_id)
            _print(load_contract_from_role(role, slug=args.slug))
        elif args.cmd == "diagnostic-receipt":
            role = store.get(args.role_id)
            _print(load_receipt_from_role(role, slug=args.slug))
        elif args.cmd == "diagnostic-fulfill-deadline":
            role = store.get(args.role_id)
            _print(
                run_diagnostic_deadline(
                    role,
                    slug=args.slug,
                    usable_evidence_at=args.usable_evidence_at,
                )
            )
        elif args.cmd == "diagnostic-fulfill-sla":
            role = store.get(args.role_id)
            _print(
                run_diagnostic_sla(
                    role,
                    slug=args.slug,
                    usable_evidence_at=args.usable_evidence_at,
                    as_of=args.as_of,
                )
            )
        elif args.cmd == "prove-handoff":
            _print(
                prove_successor_executes(
                    store,
                    args.role_id,
                    case_ref=args.case_ref,
                    usable_evidence_at=args.usable_evidence_at,
                    diagnostic_slug=args.slug,
                    as_of=args.as_of,
                )
            )
        elif args.cmd == "inspect":
            _print(store.inspect(args.role_id))
        elif args.cmd == "export":
            _print(store.export_package(args.role_id))
        elif args.cmd == "import":
            _print(store.import_package(_load_json(args.file)))
        elif args.cmd == "list":
            _print({"roles": store.list_ids()})
        elif args.cmd == "open-obligations":
            _print(
                {
                    "open_obligations": store.list_open_obligations(
                        cash_only=bool(getattr(args, "cash_only", False))
                    )
                }
            )
        else:
            raise RoleError(f"unknown command: {args.cmd}")
    except RoleError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
