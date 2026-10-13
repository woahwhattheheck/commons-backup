#!/usr/bin/env python3
"""Persistent state, migration, manifest, and route planning for the waste desk."""

from desk_common import *


class WasteRouteState:
    def __init__(self, db_path: str | os.PathLike[str]):
        self.db_path = str(Path(db_path))
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(
            self.db_path,
            timeout=10,
            isolation_level=None,
            check_same_thread=False,
        )
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute("PRAGMA busy_timeout=10000")
        self.conn.execute("PRAGMA journal_mode=WAL")
        try:
            self.conn.executescript(SCHEMA)
            self._migrate_schema()
            self._backfill_invoice_line_custody()
        except Exception:
            self.conn.close()
            raise

    def close(self):
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def _migrate_schema(self):
        stop_columns = {
            row["name"] for row in self.conn.execute("PRAGMA table_info(stops)")
        }
        if "makeup_service_date" not in stop_columns:
            self.conn.execute("ALTER TABLE stops ADD COLUMN makeup_service_date TEXT")

        has_customers = self.conn.execute(
            "SELECT 1 FROM customers LIMIT 1"
        ).fetchone()
        has_timezone = self.conn.execute(
            "SELECT 1 FROM workspace_settings WHERE key='business_timezone'"
        ).fetchone()
        if has_customers and not has_timezone:
            self.conn.execute(
                "INSERT INTO workspace_settings(key,value) VALUES('business_timezone',?)",
                (SYSTEM_LOCAL_TIMEZONE,),
            )

    def _backfill_invoice_line_custody(self):
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            drafts = self.conn.execute(
                "SELECT id,payload_json FROM invoice_drafts ORDER BY id"
            ).fetchall()
            for draft in drafts:
                try:
                    payload = json.loads(draft["payload_json"])
                    lines = payload["lines"]
                except (json.JSONDecodeError, KeyError, TypeError) as exc:
                    raise StateConflict(
                        f"invoice draft {draft['id']} has invalid retained payload"
                    ) from exc
                if not isinstance(lines, list) or not lines:
                    raise StateConflict(
                        f"invoice draft {draft['id']} has no retained line evidence"
                    )
                seen: set[str] = set()
                for line in lines:
                    if not isinstance(line, dict):
                        raise StateConflict(
                            f"invoice draft {draft['id']} has invalid line evidence"
                        )
                    try:
                        stop_id = ident(line.get("stop_id"), "invoice line stop_id")
                    except ValidationError as exc:
                        raise StateConflict(
                            f"invoice draft {draft['id']} has invalid stop custody"
                        ) from exc
                    if stop_id in seen:
                        raise StateConflict(
                            f"invoice draft {draft['id']} repeats stop {stop_id}"
                        )
                    seen.add(stop_id)
                    existing = self.conn.execute(
                        "SELECT invoice_id FROM invoice_lines WHERE stop_id=?",
                        (stop_id,),
                    ).fetchone()
                    if existing and existing["invoice_id"] != draft["id"]:
                        raise StateConflict(
                            "existing invoice drafts contain duplicate stop custody: "
                            f"{stop_id} is claimed by {existing['invoice_id']} and {draft['id']}"
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
                if retained != seen:
                    raise StateConflict(
                        f"invoice draft {draft['id']} custody does not match its retained payload"
                    )
            self.conn.execute("COMMIT")
        except Exception as exc:
            if self.conn.in_transaction:
                self.conn.execute("ROLLBACK")
            if isinstance(exc, DeskError):
                raise
            raise StateConflict("invoice custody migration failed closed") from exc

    def _op(self, key: str, action: str, request: dict[str, Any], fn):
        key = ident(key, "op_key")
        rd = digest({"action": action, "request": request})
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            old = self.conn.execute(
                "SELECT action,request_digest,result_json FROM operations WHERE op_key=?",
                (key,),
            ).fetchone()
            if old:
                if old["action"] != action or old["request_digest"] != rd:
                    raise OperationConflict(
                        f"operation key {key!r} was already used with different input"
                    )
                out = json.loads(old["result_json"])
                self.conn.execute("COMMIT")
                return out
            out, etype, ekind, eid, epayload = fn()
            self.conn.execute(
                "INSERT INTO operations VALUES(?,?,?,?)",
                (key, action, rd, canon(out)),
            )
            ej = canon(epayload)
            ed = digest(
                {
                    "op_key": key,
                    "event_type": etype,
                    "entity_kind": ekind,
                    "entity_id": eid,
                    "payload": epayload,
                }
            )
            self.conn.execute(
                "INSERT INTO events(op_key,event_type,entity_kind,entity_id,payload_json,event_digest) VALUES(?,?,?,?,?,?)",
                (key, etype, ekind, eid, ej, ed),
            )
            self.conn.execute("COMMIT")
            return out
        except Exception:
            if self.conn.in_transaction:
                self.conn.execute("ROLLBACK")
            raise

    @staticmethod
    def _closed_object(
        value: Any, field: str, allowed: set[str]
    ) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise ValidationError(f"{field} must be an object")
        unknown = [
            repr(key)
            for key in value
            if not isinstance(key, str) or key not in allowed
        ]
        if unknown:
            raise ValidationError(
                f"{field} contains unknown fields: {', '.join(unknown)}"
            )
        return value

    @staticmethod
    def _normalize_manifest(m: Any) -> dict[str, Any]:
        m = WasteRouteState._closed_object(
            m, "manifest", {"business_timezone", "customers"}
        )
        if not isinstance(m.get("customers"), list) or not m["customers"]:
            raise ValidationError("manifest.customers must be a non-empty list")
        tz = business_timezone(m.get("business_timezone", SYSTEM_LOCAL_TIMEZONE))
        out, seen_cu, seen_s, seen_k, seen_p = [], set(), set(), set(), set()
        for c in m["customers"]:
            c = WasteRouteState._closed_object(
                c, "customer", {"id", "name", "currency", "sites"}
            )
            cid = ident(c.get("id"), "customer.id")
            if cid in seen_cu:
                raise ValidationError(f"duplicate customer id {cid}")
            seen_cu.add(cid)
            co = {
                "id": cid,
                "name": text(c.get("name"), "customer.name"),
                "currency": currency(c.get("currency", "USD")),
                "sites": [],
            }
            if not isinstance(c.get("sites"), list) or not c["sites"]:
                raise ValidationError(f"customer {cid} must have sites")
            for s in c["sites"]:
                s = WasteRouteState._closed_object(
                    s, "site", {"id", "name", "containers"}
                )
                sid = ident(s.get("id"), "site.id")
                if sid in seen_s:
                    raise ValidationError(f"duplicate site id {sid}")
                seen_s.add(sid)
                so = {
                    "id": sid,
                    "name": text(s.get("name"), "site.name"),
                    "containers": [],
                }
                if not isinstance(s.get("containers"), list) or not s["containers"]:
                    raise ValidationError(f"site {sid} must have containers")
                for k in s["containers"]:
                    k = WasteRouteState._closed_object(
                        k,
                        "container",
                        {"id", "label", "container_type", "plans"},
                    )
                    kid = ident(k.get("id"), "container.id")
                    if kid in seen_k:
                        raise ValidationError(f"duplicate container id {kid}")
                    seen_k.add(kid)
                    ko = {
                        "id": kid,
                        "label": text(k.get("label"), "container.label"),
                        "container_type": text(
                            k.get("container_type"), "container.container_type"
                        ),
                        "plans": [],
                    }
                    if not isinstance(k.get("plans"), list) or not k["plans"]:
                        raise ValidationError(f"container {kid} must have plans")
                    for p in k["plans"]:
                        p = WasteRouteState._closed_object(
                            p,
                            "plan",
                            {
                                "id",
                                "weekday",
                                "service_code",
                                "price_minor",
                            },
                        )
                        pid = ident(p.get("id"), "plan.id")
                        if pid in seen_p:
                            raise ValidationError(f"duplicate plan id {pid}")
                        seen_p.add(pid)
                        wd = p.get("weekday")
                        if (
                            isinstance(wd, bool)
                            or not isinstance(wd, int)
                            or wd not in range(7)
                        ):
                            raise ValidationError(
                                "plan.weekday must be an integer 0..6"
                            )
                        ko["plans"].append(
                            {
                                "id": pid,
                                "weekday": wd,
                                "service_code": text(
                                    p.get("service_code"), "plan.service_code"
                                ),
                                "price_minor": money(
                                    p.get("price_minor"), "plan.price_minor"
                                ),
                            }
                        )
                    so["containers"].append(ko)
                co["sites"].append(so)
            out.append(co)
        return {"business_timezone": tz, "customers": out}

    def business_date(self) -> date:
        row = self.conn.execute(
            "SELECT value FROM workspace_settings WHERE key='business_timezone'"
        ).fetchone()
        if not row:
            raise StateConflict("workspace business timezone is not initialized")
        policy = row["value"]
        if policy == SYSTEM_LOCAL_TIMEZONE:
            return datetime.now().astimezone().date()
        if policy == "UTC":
            return datetime.now(timezone.utc).date()
        try:
            zone = ZoneInfo(policy)
        except ZoneInfoNotFoundError as exc:
            raise StateConflict(
                f"retained business timezone {policy!r} is unavailable on this host"
            ) from exc
        return datetime.now(zone).date()

    def import_manifest(self, manifest: Any, op_key: str):
        m = self._normalize_manifest(manifest)
        admitted_request = json.loads(canon(manifest))

        def mutate():
            if self.conn.execute("SELECT 1 FROM customers LIMIT 1").fetchone():
                raise StateConflict(
                    "workspace manifest is already initialized; reuse the original "
                    "operation key for an exact retry"
                )
            if self.conn.execute(
                "SELECT 1 FROM workspace_settings LIMIT 1"
            ).fetchone():
                raise StateConflict("workspace settings are already initialized")
            self.conn.execute(
                "INSERT INTO workspace_settings(key,value) VALUES('business_timezone',?)",
                (m["business_timezone"],),
            )
            n = {"customers": 0, "sites": 0, "containers": 0, "plans": 0}
            for c in m["customers"]:
                self.conn.execute(
                    "INSERT INTO customers VALUES(?,?,?)",
                    (c["id"], c["name"], c["currency"]),
                )
                n["customers"] += 1
                for s in c["sites"]:
                    self.conn.execute(
                        "INSERT INTO sites VALUES(?,?,?)",
                        (s["id"], c["id"], s["name"]),
                    )
                    n["sites"] += 1
                    for k in s["containers"]:
                        self.conn.execute(
                            "INSERT INTO containers VALUES(?,?,?,?)",
                            (
                                k["id"],
                                s["id"],
                                k["label"],
                                k["container_type"],
                            ),
                        )
                        n["containers"] += 1
                        for p in k["plans"]:
                            self.conn.execute(
                                "INSERT INTO plans VALUES(?,?,?,?,?,1)",
                                (
                                    p["id"],
                                    k["id"],
                                    p["weekday"],
                                    p["service_code"],
                                    p["price_minor"],
                                ),
                            )
                            n["plans"] += 1
            out = {
                "ok": True,
                "counts": n,
                "manifest_digest": digest(m),
                "business_timezone": m["business_timezone"],
            }
            return out, "MANIFEST_IMPORTED", "workspace", "manifest", out

        return self._op(op_key, "import_manifest", admitted_request, mutate)

    def generate_route(self, service_date: str, op_key: str):
        service_date = iso(service_date, "service_date")
        wd = date.fromisoformat(service_date).weekday()

        def mutate():
            if self.conn.execute(
                "SELECT 1 FROM routes WHERE service_date=?", (service_date,)
            ).fetchone():
                raise StateConflict(f"route already exists for {service_date}")
            rows = self.conn.execute(
                """
                SELECT p.id plan_id,p.service_code,p.price_minor,c.id container_id,s.id site_id,cu.id customer_id,
                       cu.name customer_name,s.name site_name,c.label container_label
                FROM plans p JOIN containers c ON c.id=p.container_id JOIN sites s ON s.id=c.site_id
                JOIN customers cu ON cu.id=s.customer_id WHERE p.active=1 AND p.weekday=?
                ORDER BY cu.id,s.id,c.id,p.id
                """,
                (wd,),
            ).fetchall()
            if not rows:
                raise StateConflict(f"no active plans are due on {service_date}")
            rid = f"route:{service_date}"
            self.conn.execute("INSERT INTO routes VALUES(?,?)", (rid, service_date))
            stops = []
            for seq, r in enumerate(rows, 1):
                sid = f"stop:{service_date}:{r['plan_id']}"
                self.conn.execute(
                    "INSERT INTO stops(id,route_id,plan_id,customer_id,site_id,container_id,sequence,status,charge_minor) VALUES(?,?,?,?,?,?,?,'PENDING',0)",
                    (
                        sid,
                        rid,
                        r["plan_id"],
                        r["customer_id"],
                        r["site_id"],
                        r["container_id"],
                        seq,
                    ),
                )
                stops.append(
                    {
                        "id": sid,
                        "sequence": seq,
                        "customer_id": r["customer_id"],
                        "customer_name": r["customer_name"],
                        "site_id": r["site_id"],
                        "site_name": r["site_name"],
                        "container_id": r["container_id"],
                        "container_label": r["container_label"],
                        "plan_id": r["plan_id"],
                        "service_code": r["service_code"],
                        "price_minor": r["price_minor"],
                        "status": "PENDING",
                    }
                )
            out = {
                "ok": True,
                "route_id": rid,
                "service_date": service_date,
                "stop_count": len(stops),
                "stops": stops,
            }
            return out, "ROUTE_GENERATED", "route", rid, {
                "service_date": service_date,
                "stop_ids": [s["id"] for s in stops],
            }

        return self._op(
            op_key, "generate_route", {"service_date": service_date}, mutate
        )
