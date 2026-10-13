#!/usr/bin/env python3
"""Service facts, exception resolution, billing custody, and exports."""

from desk_common import *
from desk_state import WasteRouteState


class WasteRouteDesk(WasteRouteState):
    def record_stop(
        self,
        stop_id: str,
        outcome: str,
        op_key: str,
        exception_code: str | None = None,
    ):
        stop_id = ident(stop_id, "stop_id")
        if outcome not in {"SERVICED", "SKIPPED"}:
            raise ValidationError("outcome must be SERVICED or SKIPPED")
        if outcome == "SKIPPED":
            exception_code = text(exception_code, "exception_code")
        elif exception_code is not None:
            raise ValidationError("exception_code is only valid for SKIPPED")
        request = {
            "stop_id": stop_id,
            "outcome": outcome,
            "exception_code": exception_code,
        }

        def mutate():
            r = self.conn.execute(
                """
                SELECT st.status,p.price_minor,rt.service_date
                FROM stops st JOIN plans p ON p.id=st.plan_id
                JOIN routes rt ON rt.id=st.route_id WHERE st.id=?
                """,
                (stop_id,),
            ).fetchone()
            if not r:
                raise StateConflict(f"unknown stop {stop_id}")
            today = self.business_date()
            if date.fromisoformat(r["service_date"]) > today:
                raise StateConflict(
                    f"cannot record a service outcome for future route {r['service_date']}; "
                    f"trusted business date is {today.isoformat()}"
                )
            if r["status"] != "PENDING":
                raise StateConflict(
                    f"stop {stop_id} is already terminal or exception-owned: {r['status']}"
                )
            if outcome == "SERVICED":
                status, charge = "SERVICE_CONFIRMED", r["price_minor"]
                cur = self.conn.execute(
                    "UPDATE stops SET status=?,exception_code=NULL,resolution=NULL,makeup_service_date=NULL,charge_minor=? WHERE id=? AND status='PENDING'",
                    (status, charge, stop_id),
                )
            else:
                status, charge = "EXCEPTION_OPEN", 0
                cur = self.conn.execute(
                    "UPDATE stops SET status=?,exception_code=?,resolution=NULL,makeup_service_date=NULL,charge_minor=0 WHERE id=? AND status='PENDING'",
                    (status, exception_code, stop_id),
                )
            if cur.rowcount != 1:
                raise StateConflict(f"stop {stop_id} transition lost a race")
            out = {
                "ok": True,
                "stop_id": stop_id,
                "service_date": r["service_date"],
                "recorded_business_date": today.isoformat(),
                "status": status,
                "exception_code": exception_code,
                "charge_minor": charge,
            }
            return out, "STOP_OUTCOME_RECORDED", "stop", stop_id, out

        return self._op(op_key, "record_stop", request, mutate)

    def resolve_exception(
        self,
        stop_id: str,
        resolution: str,
        op_key: str,
        makeup_service_date: str | None = None,
    ):
        stop_id = ident(stop_id, "stop_id")
        allowed = {"NO_SERVICE_NO_CHARGE", "MAKEUP_COMPLETED_BILLABLE"}
        if resolution not in allowed:
            raise ValidationError(f"resolution must be one of {sorted(allowed)}")
        if resolution == "MAKEUP_COMPLETED_BILLABLE":
            makeup_service_date = iso(
                makeup_service_date, "makeup_service_date"
            )
        elif makeup_service_date is not None:
            raise ValidationError(
                "makeup_service_date is only valid for MAKEUP_COMPLETED_BILLABLE"
            )
        request = {
            "stop_id": stop_id,
            "resolution": resolution,
            "makeup_service_date": makeup_service_date,
        }

        def mutate():
            r = self.conn.execute(
                """
                SELECT st.status,p.price_minor,rt.service_date
                FROM stops st JOIN plans p ON p.id=st.plan_id
                JOIN routes rt ON rt.id=st.route_id WHERE st.id=?
                """,
                (stop_id,),
            ).fetchone()
            if not r:
                raise StateConflict(f"unknown stop {stop_id}")
            today = self.business_date()
            service_day = date.fromisoformat(r["service_date"])
            if service_day > today:
                raise StateConflict(
                    f"cannot resolve an exception for future route {r['service_date']}; "
                    f"trusted business date is {today.isoformat()}"
                )
            if r["status"] != "EXCEPTION_OPEN":
                raise StateConflict(f"stop {stop_id} does not have an open exception")
            if resolution == "NO_SERVICE_NO_CHARGE":
                status, charge = "RESOLVED_NO_CHARGE", 0
            else:
                assert makeup_service_date is not None
                makeup_day = date.fromisoformat(makeup_service_date)
                if makeup_day < service_day:
                    raise ValidationError(
                        "makeup_service_date may not precede the original service date"
                    )
                if makeup_day > today:
                    raise StateConflict(
                        f"makeup service date {makeup_service_date} is in the future; "
                        f"trusted business date is {today.isoformat()}"
                    )
                status, charge = "RESOLVED_BILLABLE", r["price_minor"]
            cur = self.conn.execute(
                "UPDATE stops SET status=?,resolution=?,makeup_service_date=?,charge_minor=? WHERE id=? AND status='EXCEPTION_OPEN'",
                (status, resolution, makeup_service_date, charge, stop_id),
            )
            if cur.rowcount != 1:
                raise StateConflict(
                    f"stop {stop_id} exception resolution lost a race"
                )
            out = {
                "ok": True,
                "stop_id": stop_id,
                "service_date": r["service_date"],
                "resolved_business_date": today.isoformat(),
                "status": status,
                "resolution": resolution,
                "makeup_service_date": makeup_service_date,
                "charge_minor": charge,
            }
            return out, "EXCEPTION_RESOLVED", "stop", stop_id, out

        return self._op(op_key, "resolve_exception", request, mutate)

    def draft_invoice(
        self,
        customer_id: str,
        period_start: str,
        period_end: str,
        op_key: str,
    ):
        customer_id = ident(customer_id, "customer_id")
        period_start = iso(period_start, "period_start")
        period_end = iso(period_end, "period_end")
        if period_end < period_start:
            raise ValidationError("period_end must be on or after period_start")
        start, end = date.fromisoformat(period_start), date.fromisoformat(period_end)
        if (end - start).days > 366:
            raise ValidationError("invoice period may not exceed 367 calendar days")
        request = {
            "customer_id": customer_id,
            "period_start": period_start,
            "period_end": period_end,
        }

        def mutate():
            cu = self.conn.execute(
                "SELECT id,name,currency FROM customers WHERE id=?", (customer_id,)
            ).fetchone()
            if not cu:
                raise StateConflict(f"unknown customer {customer_id}")
            today = self.business_date()
            if end > today:
                raise BillingBlocked(
                    f"invoice period ends {period_end}, after trusted business date "
                    f"{today.isoformat()}"
                )
            if self.conn.execute(
                "SELECT 1 FROM invoice_drafts WHERE customer_id=? AND period_start=? AND period_end=?",
                (customer_id, period_start, period_end),
            ).fetchone():
                raise StateConflict(
                    f"invoice draft already exists for {customer_id} "
                    f"{period_start}..{period_end}"
                )
            plans = self.conn.execute(
                """
                SELECT p.id plan_id,p.weekday FROM plans p
                JOIN containers c ON c.id=p.container_id
                JOIN sites s ON s.id=c.site_id
                WHERE s.customer_id=? AND p.active=1 ORDER BY p.id
                """,
                (customer_id,),
            ).fetchall()
            expected, d = [], start
            while d <= end:
                expected.extend(
                    (d.isoformat(), p["plan_id"])
                    for p in plans
                    if p["weekday"] == d.weekday()
                )
                d += timedelta(days=1)
            if not expected:
                raise BillingBlocked(
                    "no scheduled service is due for this customer in the invoice period"
                )
            rows = self.conn.execute(
                """
                SELECT st.id stop_id,r.service_date,st.customer_id,st.plan_id,st.site_id,st.container_id,
                       st.status,st.exception_code,st.resolution,st.makeup_service_date,
                       st.charge_minor,p.service_code
                FROM stops st JOIN routes r ON r.id=st.route_id
                JOIN plans p ON p.id=st.plan_id
                WHERE st.customer_id=? AND r.service_date BETWEEN ? AND ?
                ORDER BY r.service_date,st.sequence,st.id
                """,
                (customer_id, period_start, period_end),
            ).fetchall()
            actual = {(r["service_date"], r["plan_id"]) for r in rows}
            missing = [
                {"service_date": d, "plan_id": p}
                for d, p in expected
                if (d, p) not in actual
            ]
            if missing:
                raise BillingBlocked(
                    "invoice blocked by missing scheduled route stops: " + canon(missing)
                )
            blocked = [
                {"stop_id": r["stop_id"], "status": r["status"]}
                for r in rows
                if r["status"] in {"PENDING", "EXCEPTION_OPEN"}
            ]
            if blocked:
                raise BillingBlocked(
                    "invoice blocked by unresolved service state: " + canon(blocked)
                )
            claims = []
            for r in rows:
                existing = self.conn.execute(
                    """
                    SELECT il.stop_id,il.invoice_id,d.period_start,d.period_end
                    FROM invoice_lines il JOIN invoice_drafts d ON d.id=il.invoice_id
                    WHERE il.stop_id=?
                    """,
                    (r["stop_id"],),
                ).fetchone()
                if existing:
                    claims.append(dict(existing))
            if claims:
                raise BillingBlocked(
                    "invoice blocked because settled stops already belong to retained "
                    "invoice drafts: "
                    + canon(claims)
                )
            lines = [
                {
                    "stop_id": r["stop_id"],
                    "service_date": r["service_date"],
                    "customer_id": r["customer_id"],
                    "plan_id": r["plan_id"],
                    "site_id": r["site_id"],
                    "container_id": r["container_id"],
                    "service_code": r["service_code"],
                    "status": r["status"],
                    "resolution": r["resolution"],
                    "makeup_service_date": r["makeup_service_date"],
                    "charge_minor": r["charge_minor"],
                }
                for r in rows
            ]
            total = sum(x["charge_minor"] for x in lines)
            if total > MAX_SQLITE_INTEGER:
                raise BillingBlocked("invoice total exceeds SQLite-safe integer range")
            basis = {
                "customer_id": customer_id,
                "period_start": period_start,
                "period_end": period_end,
                "business_date": today.isoformat(),
                "currency": cu["currency"],
                "lines": lines,
                "total_minor": total,
            }
            receipt = digest(basis)
            iid = "inv:" + receipt[:24]
            payload = {
                "invoice_id": iid,
                "customer_id": customer_id,
                "customer_name": cu["name"],
                "period_start": period_start,
                "period_end": period_end,
                "business_date": today.isoformat(),
                "currency": cu["currency"],
                "lines": lines,
                "total_minor": total,
                "receipt_digest": receipt,
                "payment_mutation": False,
            }
            self.conn.execute(
                "INSERT INTO invoice_drafts VALUES(?,?,?,?,?,?,?,?)",
                (
                    iid,
                    customer_id,
                    period_start,
                    period_end,
                    total,
                    cu["currency"],
                    receipt,
                    canon(payload),
                ),
            )
            try:
                for line in lines:
                    self.conn.execute(
                        "INSERT INTO invoice_lines(invoice_id,stop_id) VALUES(?,?)",
                        (iid, line["stop_id"]),
                    )
            except sqlite3.IntegrityError as exc:
                raise BillingBlocked(
                    "invoice line custody lost a concurrent claim race"
                ) from exc
            out = {"ok": True, **payload}
            return out, "INVOICE_DRAFT_CREATED", "invoice_draft", iid, {
                "invoice_id": iid,
                "customer_id": customer_id,
                "period_start": period_start,
                "period_end": period_end,
                "business_date": today.isoformat(),
                "stop_ids": [line["stop_id"] for line in lines],
                "total_minor": total,
                "currency": cu["currency"],
                "receipt_digest": receipt,
            }

        return self._op(op_key, "draft_invoice", request, mutate)

    def route_snapshot(self, service_date: str):
        service_date = iso(service_date, "service_date")
        r = self.conn.execute(
            "SELECT id,service_date FROM routes WHERE service_date=?", (service_date,)
        ).fetchone()
        if not r:
            raise StateConflict(f"unknown route date {service_date}")
        rows = self.conn.execute(
            """
            SELECT st.id stop_id,st.sequence,st.customer_id,cu.name customer_name,
                   st.site_id,s.name site_name,st.container_id,c.label container_label,
                   c.container_type,st.plan_id,p.service_code,p.price_minor,st.status,
                   st.exception_code,st.resolution,st.makeup_service_date,st.charge_minor
            FROM stops st JOIN customers cu ON cu.id=st.customer_id
            JOIN sites s ON s.id=st.site_id JOIN containers c ON c.id=st.container_id
            JOIN plans p ON p.id=st.plan_id WHERE st.route_id=?
            ORDER BY st.sequence,st.id
            """,
            (r["id"],),
        ).fetchall()
        return {
            "route_id": r["id"],
            "service_date": r["service_date"],
            "stop_count": len(rows),
            "stops": [dict(x) for x in rows],
            "external_provider_calls": 0,
            "autonomous_dispatch": False,
        }

    def route_csv(self, service_date: str) -> str:
        s = self.route_snapshot(service_date)
        fields = [
            "sequence",
            "stop_id",
            "customer_id",
            "customer_name",
            "site_id",
            "site_name",
            "container_id",
            "container_label",
            "container_type",
            "plan_id",
            "service_code",
            "price_minor",
            "status",
            "exception_code",
            "resolution",
            "makeup_service_date",
            "charge_minor",
        ]
        out = io.StringIO(newline="")
        writer = csv.DictWriter(out, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in s["stops"]:
            writer.writerow({k: row.get(k) for k in fields})
        return out.getvalue()

    def route_markdown(self, service_date: str) -> str:
        s = self.route_snapshot(service_date)
        lines = [
            f"# Route {s['service_date']}",
            "",
            f"Stops: {s['stop_count']}",
            "",
            "| Seq | Customer | Site | Container | Service | Status | Charge minor |",
            "|---:|---|---|---|---|---|---:|",
        ]
        clean = lambda v: str(v).replace("|", "\\|").replace("\n", "<br>")
        for x in s["stops"]:
            lines.append(
                f"| {x['sequence']} | {clean(x['customer_name'])} | "
                f"{clean(x['site_name'])} | {clean(x['container_label'])} | "
                f"{clean(x['service_code'])} | {x['status']} | "
                f"{x['charge_minor']} |"
            )
        return "\n".join(lines + [""])

    def event_log(self):
        rows = self.conn.execute(
            "SELECT id,op_key,event_type,entity_kind,entity_id,payload_json,event_digest FROM events ORDER BY id"
        ).fetchall()
        return [
            {
                "id": r["id"],
                "op_key": r["op_key"],
                "event_type": r["event_type"],
                "entity_kind": r["entity_kind"],
                "entity_id": r["entity_id"],
                "payload": json.loads(r["payload_json"]),
                "event_digest": r["event_digest"],
            }
            for r in rows
        ]

