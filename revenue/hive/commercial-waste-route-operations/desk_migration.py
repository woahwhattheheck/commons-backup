#!/usr/bin/env python3
"""Authenticated legacy/current invoice custody migration."""

from desk_billing import WasteRouteDesk as BillingWasteRouteDesk
from desk_common import *


class WasteRouteDesk(BillingWasteRouteDesk):
    """Waste desk with fail-closed invoice-line custody backfill."""

    @staticmethod
    def _retained_json(raw: Any, label: str) -> dict[str, Any]:
        if not isinstance(raw, str):
            raise StateConflict(f"{label} is not retained JSON text")

        def no_duplicate_keys(pairs):
            out = {}
            for key, value in pairs:
                if key in out:
                    raise StateConflict(f"{label} contains duplicate key {key!r}")
                out[key] = value
            return out

        try:
            value = json.loads(raw, object_pairs_hook=no_duplicate_keys)
        except json.JSONDecodeError as exc:
            raise StateConflict(f"{label} is invalid JSON") from exc
        if not isinstance(value, dict):
            raise StateConflict(f"{label} must be a JSON object")
        if canon(value) != raw:
            raise StateConflict(f"{label} is not canonical retained JSON")
        return value

    @staticmethod
    def _exact_keys(value: dict[str, Any], expected: set[str], label: str):
        actual = set(value)
        if actual != expected:
            missing = sorted(expected - actual)
            extra = sorted(actual - expected)
            raise StateConflict(
                f"{label} shape mismatch; missing={missing}, extra={extra}"
            )

    @staticmethod
    def _retained_digest(value: Any, label: str) -> str:
        if (
            not isinstance(value, str)
            or len(value) != 64
            or any(ch not in "0123456789abcdef" for ch in value)
        ):
            raise StateConflict(f"{label} is not a canonical sha256 digest")
        return value

    @staticmethod
    def _canonical_ident(value: Any, label: str) -> str:
        try:
            normalized = ident(value, label)
        except ValidationError as exc:
            raise StateConflict(f"{label} is invalid") from exc
        if normalized != value:
            raise StateConflict(f"{label} is not canonical")
        return normalized

    @staticmethod
    def _canonical_date(value: Any, label: str) -> str:
        try:
            return iso(value, label)
        except ValidationError as exc:
            raise StateConflict(f"{label} is invalid") from exc

    @staticmethod
    def _canonical_currency(value: Any, label: str) -> str:
        try:
            normalized = currency(value)
        except ValidationError as exc:
            raise StateConflict(f"{label} is invalid") from exc
        if normalized != value:
            raise StateConflict(f"{label} is not canonical")
        return normalized

    @staticmethod
    def _canonical_money(value: Any, label: str) -> int:
        try:
            return money(value, label)
        except ValidationError as exc:
            raise StateConflict(f"{label} is invalid") from exc

    def _validate_invoice_draft_for_backfill(
        self, draft: sqlite3.Row
    ) -> list[str]:
        label = f"invoice draft {draft['id']}"
        invoice_id = self._canonical_ident(draft["id"], f"{label} id")
        customer_id = self._canonical_ident(
            draft["customer_id"], f"{label} customer_id"
        )
        period_start = self._canonical_date(
            draft["period_start"], f"{label} period_start"
        )
        period_end = self._canonical_date(
            draft["period_end"], f"{label} period_end"
        )
        if period_end < period_start:
            raise StateConflict(f"{label} has reversed retained period")
        total_minor = self._canonical_money(
            draft["total_minor"], f"{label} total_minor"
        )
        retained_currency = self._canonical_currency(
            draft["currency"], f"{label} currency"
        )
        retained_receipt = self._retained_digest(
            draft["receipt_digest"], f"{label} receipt_digest"
        )

        payload = self._retained_json(
            draft["payload_json"], f"{label} payload_json"
        )
        legacy_payload_keys = {
            "invoice_id",
            "customer_id",
            "customer_name",
            "period_start",
            "period_end",
            "currency",
            "lines",
            "total_minor",
            "receipt_digest",
            "payment_mutation",
        }
        is_current = "business_date" in payload
        payload_keys = (
            legacy_payload_keys | {"business_date"}
            if is_current
            else legacy_payload_keys
        )
        self._exact_keys(payload, payload_keys, f"{label} payload")

        row_identity = {
            "invoice_id": invoice_id,
            "customer_id": customer_id,
            "period_start": period_start,
            "period_end": period_end,
            "currency": retained_currency,
            "total_minor": total_minor,
            "receipt_digest": retained_receipt,
        }
        for field, expected in row_identity.items():
            if payload.get(field) != expected:
                raise StateConflict(
                    f"{label} payload {field} disagrees with retained row"
                )
        if payload.get("payment_mutation") is not False:
            raise StateConflict(f"{label} payload changes payment authority")

        customer = self.conn.execute(
            "SELECT name,currency FROM customers WHERE id=?", (customer_id,)
        ).fetchone()
        if not customer:
            raise StateConflict(f"{label} references unknown customer")
        if payload.get("customer_name") != customer["name"]:
            raise StateConflict(
                f"{label} customer_name disagrees with retained customer"
            )
        if retained_currency != customer["currency"]:
            raise StateConflict(f"{label} currency disagrees with retained customer")

        if is_current:
            business_date = self._canonical_date(
                payload["business_date"], f"{label} business_date"
            )
        else:
            business_date = None

        lines = payload.get("lines")
        if not isinstance(lines, list) or not lines:
            raise StateConflict(f"{label} has no retained line evidence")

        legacy_line_keys = {
            "stop_id",
            "service_date",
            "customer_id",
            "plan_id",
            "site_id",
            "container_id",
            "service_code",
            "status",
            "charge_minor",
        }
        current_line_keys = legacy_line_keys | {
            "resolution",
            "makeup_service_date",
        }
        line_keys = current_line_keys if is_current else legacy_line_keys

        seen: set[str] = set()
        stop_ids: list[str] = []
        computed_total = 0
        for index, line in enumerate(lines):
            line_label = f"{label} line[{index}]"
            if not isinstance(line, dict):
                raise StateConflict(f"{line_label} is not an object")
            self._exact_keys(line, line_keys, line_label)
            stop_id = self._canonical_ident(line["stop_id"], f"{line_label} stop_id")
            if stop_id in seen:
                raise StateConflict(f"{label} repeats stop {stop_id}")
            seen.add(stop_id)
            stop_ids.append(stop_id)

            row = self.conn.execute(
                """
                SELECT st.id stop_id,r.service_date,st.customer_id,st.plan_id,
                       st.site_id,st.container_id,p.service_code,st.status,
                       st.resolution,st.makeup_service_date,st.charge_minor
                FROM stops st
                JOIN routes r ON r.id=st.route_id
                JOIN plans p ON p.id=st.plan_id
                WHERE st.id=?
                """,
                (stop_id,),
            ).fetchone()
            if not row:
                raise StateConflict(f"{line_label} references unknown stop {stop_id}")

            expected = {key: row[key] for key in line_keys}
            if line != expected:
                raise StateConflict(
                    f"{line_label} disagrees with retained stop generation"
                )
            if line["customer_id"] != customer_id:
                raise StateConflict(f"{line_label} belongs to another customer")
            service_date = self._canonical_date(
                line["service_date"], f"{line_label} service_date"
            )
            if service_date < period_start or service_date > period_end:
                raise StateConflict(f"{line_label} falls outside retained invoice period")
            computed_total += self._canonical_money(
                line["charge_minor"], f"{line_label} charge_minor"
            )
            if computed_total > MAX_SQLITE_INTEGER:
                raise StateConflict(f"{label} line total exceeds SQLite-safe range")

        if computed_total != total_minor:
            raise StateConflict(f"{label} retained total does not equal its lines")

        basis = {
            "customer_id": customer_id,
            "period_start": period_start,
            "period_end": period_end,
            "currency": retained_currency,
            "lines": lines,
            "total_minor": total_minor,
        }
        if is_current:
            basis["business_date"] = business_date
        recomputed_receipt = digest(basis)
        if recomputed_receipt != retained_receipt:
            raise StateConflict(f"{label} retained receipt does not authenticate payload")
        if invoice_id != "inv:" + retained_receipt[:24]:
            raise StateConflict(f"{label} id does not derive from retained receipt")

        events = self.conn.execute(
            """
            SELECT op_key,event_type,entity_kind,entity_id,payload_json,event_digest
            FROM events
            WHERE event_type='INVOICE_DRAFT_CREATED'
              AND entity_kind='invoice_draft'
              AND entity_id=?
            ORDER BY id
            """,
            (invoice_id,),
        ).fetchall()
        if len(events) != 1:
            raise StateConflict(
                f"{label} lacks exactly one immutable invoice creation event"
            )
        event = events[0]
        event_payload = self._retained_json(
            event["payload_json"], f"{label} creation event payload"
        )
        if is_current:
            expected_event_payload = {
                "invoice_id": invoice_id,
                "customer_id": customer_id,
                "period_start": period_start,
                "period_end": period_end,
                "business_date": business_date,
                "stop_ids": stop_ids,
                "total_minor": total_minor,
                "currency": retained_currency,
                "receipt_digest": retained_receipt,
            }
        else:
            expected_event_payload = {
                "invoice_id": invoice_id,
                "customer_id": customer_id,
                "total_minor": total_minor,
                "currency": retained_currency,
                "receipt_digest": retained_receipt,
            }
        if event_payload != expected_event_payload:
            raise StateConflict(
                f"{label} retained creation event does not authenticate draft"
            )
        retained_event_digest = self._retained_digest(
            event["event_digest"], f"{label} event_digest"
        )
        recomputed_event_digest = digest(
            {
                "op_key": event["op_key"],
                "event_type": event["event_type"],
                "entity_kind": event["entity_kind"],
                "entity_id": event["entity_id"],
                "payload": event_payload,
            }
        )
        if recomputed_event_digest != retained_event_digest:
            raise StateConflict(f"{label} immutable creation event digest is invalid")

        return stop_ids

    def _backfill_invoice_line_custody(self):
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            drafts = self.conn.execute(
                """
                SELECT id,customer_id,period_start,period_end,total_minor,currency,
                       receipt_digest,payload_json
                FROM invoice_drafts
                ORDER BY id
                """
            ).fetchall()
            for draft in drafts:
                stop_ids = self._validate_invoice_draft_for_backfill(draft)
                for stop_id in stop_ids:
                    existing = self.conn.execute(
                        "SELECT invoice_id FROM invoice_lines WHERE stop_id=?",
                        (stop_id,),
                    ).fetchone()
                    if existing and existing["invoice_id"] != draft["id"]:
                        raise StateConflict(
                            "existing invoice drafts contain duplicate stop custody: "
                            f"{stop_id} is claimed by {existing['invoice_id']} "
                            f"and {draft['id']}"
                        )
                    if not existing:
                        self.conn.execute(
                            "INSERT INTO invoice_lines(invoice_id,stop_id) VALUES(?,?)",
                            (draft["id"], stop_id),
                        )
                retained = {
                    row["stop_id"]
                    for row in self.conn.execute(
                        "SELECT stop_id FROM invoice_lines WHERE invoice_id=?",
                        (draft["id"],),
                    )
                }
                if retained != set(stop_ids):
                    raise StateConflict(
                        f"invoice draft {draft['id']} custody does not match "
                        "authenticated retained evidence"
                    )
            self.conn.execute("COMMIT")
        except Exception as exc:
            if self.conn.in_transaction:
                self.conn.execute("ROLLBACK")
            if isinstance(exc, DeskError):
                raise
            raise StateConflict("invoice custody migration failed closed") from exc
