#!/usr/bin/env python3
"""Local-first commercial waste route, exception, and invoice-draft desk."""

from desk_common import *
from desk_migration import WasteRouteDesk


def parser():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", required=True)
    sp = ap.add_subparsers(dest="cmd", required=True)
    q = sp.add_parser("init")
    q.add_argument("--manifest", required=True)
    q.add_argument("--op-key", required=True)
    q = sp.add_parser("route")
    q.add_argument("--date", required=True)
    q.add_argument("--op-key", required=True)
    q = sp.add_parser("record")
    q.add_argument("--stop-id", required=True)
    q.add_argument("--outcome", choices=["SERVICED", "SKIPPED"], required=True)
    q.add_argument("--exception-code")
    q.add_argument("--op-key", required=True)
    q = sp.add_parser("resolve")
    q.add_argument("--stop-id", required=True)
    q.add_argument(
        "--resolution",
        choices=["NO_SERVICE_NO_CHARGE", "MAKEUP_COMPLETED_BILLABLE"],
        required=True,
    )
    q.add_argument("--makeup-service-date")
    q.add_argument("--op-key", required=True)
    q = sp.add_parser("invoice")
    q.add_argument("--customer-id", required=True)
    q.add_argument("--period-start", required=True)
    q.add_argument("--period-end", required=True)
    q.add_argument("--op-key", required=True)
    q = sp.add_parser("export-route")
    q.add_argument("--date", required=True)
    q.add_argument("--format", choices=["json", "csv", "markdown"], default="json")
    sp.add_parser("events")
    sp.add_parser("business-date")
    return ap


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        with WasteRouteDesk(args.db) as desk:
            if args.cmd == "init":
                with open(args.manifest, encoding="utf-8") as f:
                    out = desk.import_manifest(json.load(f), args.op_key)
                print(json.dumps(out, indent=2, sort_keys=True))
            elif args.cmd == "route":
                print(
                    json.dumps(
                        desk.generate_route(args.date, args.op_key),
                        indent=2,
                        sort_keys=True,
                    )
                )
            elif args.cmd == "record":
                print(
                    json.dumps(
                        desk.record_stop(
                            args.stop_id,
                            args.outcome,
                            args.op_key,
                            args.exception_code,
                        ),
                        indent=2,
                        sort_keys=True,
                    )
                )
            elif args.cmd == "resolve":
                print(
                    json.dumps(
                        desk.resolve_exception(
                            args.stop_id,
                            args.resolution,
                            args.op_key,
                            args.makeup_service_date,
                        ),
                        indent=2,
                        sort_keys=True,
                    )
                )
            elif args.cmd == "invoice":
                print(
                    json.dumps(
                        desk.draft_invoice(
                            args.customer_id,
                            args.period_start,
                            args.period_end,
                            args.op_key,
                        ),
                        indent=2,
                        sort_keys=True,
                    )
                )
            elif args.cmd == "export-route":
                if args.format == "json":
                    print(
                        json.dumps(
                            desk.route_snapshot(args.date),
                            indent=2,
                            sort_keys=True,
                        )
                    )
                elif args.format == "csv":
                    sys.stdout.write(desk.route_csv(args.date))
                else:
                    sys.stdout.write(desk.route_markdown(args.date))
            elif args.cmd == "business-date":
                print(
                    json.dumps(
                        {"business_date": desk.business_date().isoformat()},
                        sort_keys=True,
                    )
                )
            else:
                print(json.dumps(desk.event_log(), indent=2, sort_keys=True))
        return 0
    except DeskError as exc:
        print(
            json.dumps(
                {"ok": False, "error": type(exc).__name__, "message": str(exc)},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())