#!/usr/bin/env python3
"""Dependency-free painting request, quote, acceptance, and scheduling workflow."""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import io
import json
import re
import os
import sqlite3
import stat
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse


SCHEMA = "commons-trade-quote-v1"
SCHEDULE_FIELDS = ["date", "start_time", "duration_hours", "quote_id", "request_id", "customer", "service", "status"]
REQUIRED_ROOM_FIELDS = ("name", "length_ft", "width_ft", "height_ft", "coats", "openings_sq_ft", "paint_ceiling")


class QuoteError(ValueError):
    """Raised when a request cannot safely advance."""


def _decimal(value: object, field: str, *, minimum: Decimal = Decimal("0")) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError) as exc:
        raise QuoteError(f"{field} must be a decimal") from exc
    if not number.is_finite() or number < minimum:
        raise QuoteError(f"{field} must be finite and >= {minimum}")
    return number


def _money(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.01")), "f")


def _number(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _read_json(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise QuoteError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise QuoteError(f"{path} must contain a JSON object")
    return value


def _source(path: Path) -> dict[str, str]:
    try:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise QuoteError(f"cannot read {path}: {exc}") from exc
    return {"path": str(path), "sha256": digest}


def _iso_date(value: str, field: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise QuoteError(f"{field} must be YYYY-MM-DD") from exc


def _clock(value: str, field: str) -> time:
    try:
        parsed = time.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise QuoteError(f"{field} must be HH:MM") from exc
    if parsed.tzinfo is not None:
        raise QuoteError(f"{field} must be local HH:MM without a UTC offset")
    if parsed.second or parsed.microsecond:
        raise QuoteError(f"{field} must be minute precision")
    return parsed


def _missing_measurements(request: dict[str, object]) -> list[dict[str, str]]:
    questions: list[dict[str, str]] = []
    rooms = request.get("rooms")
    if not isinstance(rooms, list) or not rooms:
        return [{"field": "rooms", "question": "Provide at least one room with measured dimensions."}]
    for index, room in enumerate(rooms, start=1):
        if not isinstance(room, dict):
            questions.append({"field": f"rooms[{index}]", "question": f"Provide room {index} as structured measurements."})
            continue
        label = str(room.get("name") or f"room {index}")
        for field in REQUIRED_ROOM_FIELDS:
            if field not in room or room[field] in (None, ""):
                questions.append({"field": f"rooms[{index}].{field}", "question": f"Provide {field.replace('_', ' ')} for {label}."})
    return questions


def _photo_sources(request: dict[str, object], request_path: Path) -> list[dict[str, str]]:
    raw = request.get("photo_paths", [])
    if not isinstance(raw, list):
        raise QuoteError("photo_paths must be a list")
    sources = []
    for value in raw:
        path = Path(str(value))
        if not path.is_absolute():
            path = request_path.parent / path
        sources.append(_source(path))
    return sources


def _rule(rules: dict[str, object], name: str) -> Decimal:
    if name not in rules:
        raise QuoteError(f"pricing rule {name!r} is required")
    return _decimal(rules[name], f"rules.{name}")


def build_quote(request_path: Path, rules_path: Path, issued_on: str, valid_days: int, base_url: str) -> dict[str, object]:
    request, rules = _read_json(request_path), _read_json(rules_path)
    request_ref, rules_ref = _source(request_path), _source(rules_path)
    issue_date = _iso_date(issued_on, "issued_on")
    if valid_days < 1:
        raise QuoteError("valid_days must be >= 1")
    request_id = str(request.get("request_id", "")).strip()
    customer = str(request.get("customer", "")).strip()
    service = str(request.get("service", "")).strip()
    if not request_id or not customer or service != "interior_painting":
        raise QuoteError("request_id, customer, and service='interior_painting' are required")

    missing = _missing_measurements(request)
    photo_refs = _photo_sources(request, request_path)
    fingerprint = hashlib.sha256((request_ref["sha256"] + rules_ref["sha256"] + issued_on).encode()).hexdigest()
    quote_id = "Q-" + fingerprint[:12].upper()
    sources = {"request": request_ref, "pricing_rules": rules_ref, "photos": photo_refs}
    if missing:
        return {
            "schema": SCHEMA, "quote_id": quote_id, "request_id": request_id,
            "status": "NEEDS_MEASUREMENTS", "measurement_requests": missing, "sources": sources,
            "amounts_calculated": False, "acceptance_url": None,
        }

    setup_rate = _rule(rules, "setup_flat")
    wall_rate = _rule(rules, "wall_sqft_per_coat")
    ceiling_rate = _rule(rules, "ceiling_sqft_per_coat")
    lines = [{"code": "SETUP", "description": "Protection, setup, and cleanup", "quantity": "1", "unit_price": _money(setup_rate), "total": _money(setup_rate)}]
    subtotal = setup_rate
    for index, raw_room in enumerate(request["rooms"], start=1):
        room = dict(raw_room)
        length = _decimal(room["length_ft"], f"rooms[{index}].length_ft", minimum=Decimal("0.01"))
        width = _decimal(room["width_ft"], f"rooms[{index}].width_ft", minimum=Decimal("0.01"))
        height = _decimal(room["height_ft"], f"rooms[{index}].height_ft", minimum=Decimal("0.01"))
        coats = _decimal(room["coats"], f"rooms[{index}].coats", minimum=Decimal("1"))
        if coats != coats.to_integral_value():
            raise QuoteError(f"rooms[{index}].coats must be an integer")
        openings = _decimal(room["openings_sq_ft"], f"rooms[{index}].openings_sq_ft")
        wall_area = Decimal("2") * (length + width) * height - openings
        if wall_area <= 0:
            raise QuoteError(f"rooms[{index}] openings must be less than measured wall area")
        wall_quantity = wall_area * coats
        wall_total = wall_quantity * wall_rate
        lines.append({"code": "WALL", "description": f"{room['name']} walls ({_number(coats)} coat(s))", "quantity": _number(wall_quantity), "unit_price": _money(wall_rate), "total": _money(wall_total)})
        subtotal += wall_total
        if room["paint_ceiling"] is True:
            ceiling_quantity = length * width * coats
            ceiling_total = ceiling_quantity * ceiling_rate
            lines.append({"code": "CEILING", "description": f"{room['name']} ceiling ({_number(coats)} coat(s))", "quantity": _number(ceiling_quantity), "unit_price": _money(ceiling_rate), "total": _money(ceiling_total)})
            subtotal += ceiling_total
        elif room["paint_ceiling"] is not False:
            raise QuoteError(f"rooms[{index}].paint_ceiling must be true or false")

    tax_rate = _rule(rules, "tax_rate")
    tax = subtotal * tax_rate
    total = subtotal + tax
    token = hashlib.sha256((quote_id + fingerprint + _money(total)).encode()).hexdigest()[:32]
    query = urlencode({"quote": quote_id, "token": token})
    return {
        "schema": SCHEMA, "quote_id": quote_id, "request_id": request_id, "customer": customer,
        "service": service, "status": "DRAFT_NOT_SENT", "issued_on": issued_on,
        "valid_until": str(issue_date + timedelta(days=valid_days)), "currency": str(rules.get("currency", "USD")),
        "line_items": lines, "subtotal": _money(subtotal), "tax": _money(tax), "total": _money(total),
        "measurement_requests": [], "amounts_calculated": True, "sources": sources,
        "acceptance_token": token, "acceptance_url": base_url.rstrip("/") + "/accept?" + query,
        "schedule_duration_hours": _number(_rule(rules, "schedule_duration_hours")),
    }


def _pdf_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def write_pdf(quote: dict[str, object], path: Path) -> None:
    if quote.get("status") != "DRAFT_NOT_SENT":
        raise QuoteError("a PDF is created only for a complete draft quote")
    lines = [
        f"PAINTING QUOTE {quote['quote_id']}", f"Customer: {quote['customer']}",
        f"Issued: {quote['issued_on']}  Valid until: {quote['valid_until']}", "",
    ]
    for item in quote["line_items"]:
        lines.append(f"{item['description']}: {item['quantity']} x {item['unit_price']} = {item['total']} {quote['currency']}")
    lines.extend(["", f"Subtotal: {quote['subtotal']} {quote['currency']}", f"Tax: {quote['tax']} {quote['currency']}", f"TOTAL: {quote['total']} {quote['currency']}", "", "Draft not sent. Review before sharing."])
    commands = ["BT", "/F1 11 Tf", "50 750 Td"]
    for index, line in enumerate(lines[:42]):
        if index:
            commands.append("0 -17 Td")
        commands.append(f"({_pdf_escape(line)}) Tj")
    commands.append("ET")
    stream = "\n".join(commands).encode("latin-1", errors="replace")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{number} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref = len(output)
    output.extend(f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode())
    output.extend(f"trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    path.write_bytes(output)


def write_quote_bundle(quote: dict[str, object], out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"{quote['quote_id']}.json"
    json_path.write_text(json.dumps(quote, indent=2) + "\n", encoding="utf-8")
    result = {"quote": json_path}
    if quote.get("status") == "DRAFT_NOT_SENT":
        pdf_path = out_dir / f"{quote['quote_id']}.pdf"
        write_pdf(quote, pdf_path)
        result["pdf"] = pdf_path
    return result


def _read_schedule(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if list(reader.fieldnames or []) != SCHEDULE_FIELDS:
                raise QuoteError(f"{path} has an incompatible schedule schema")
            return list(reader)
    except OSError as exc:
        raise QuoteError(f"cannot read {path}: {exc}") from exc


@contextmanager
def _schedule_transaction(path: Path):
    """Serialize participating threads/processes using a stable local SQLite lock."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(f".{path.name}.lock.sqlite3")
    connection = sqlite3.connect(lock_path, timeout=30, isolation_level=None)
    try:
        connection.execute("BEGIN IMMEDIATE")
        yield
    finally:
        # Closing rolls back this data-free transaction and releases the OS lock.
        # Keep the sidecar inode: deleting it can split simultaneous contenders.
        connection.close()


def _atomic_text(path: Path, content: str) -> None:
    """Replace a complete file; failed staging leaves the previous bytes intact."""
    mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else None
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    staged = Path(name)
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        if mode is not None:
            staged.chmod(mode)
        os.replace(staged, path)
    finally:
        staged.unlink(missing_ok=True)


def accept_quote(quote_path: Path, token: str, job_date: str, start_time: str, schedule_path: Path) -> dict[str, object]:
    quote = _read_json(quote_path)
    if quote.get("status") != "DRAFT_NOT_SENT" or token != quote.get("acceptance_token"):
        raise QuoteError("quote or acceptance token is invalid")
    day = _iso_date(job_date, "job_date")
    start = _clock(start_time, "start_time")
    if day > _iso_date(str(quote["valid_until"]), "valid_until"):
        raise QuoteError("quote has expired")
    duration = _decimal(quote["schedule_duration_hours"], "schedule_duration_hours", minimum=Decimal("0.25"))
    new_start = datetime.combine(day, start)
    new_end = new_start + timedelta(hours=float(duration))
    record = {
        "date": str(day), "start_time": start.strftime("%H:%M"), "duration_hours": _number(duration),
        "quote_id": str(quote["quote_id"]), "request_id": str(quote["request_id"]),
        "customer": str(quote["customer"]), "service": str(quote["service"]), "status": "ACCEPTED_SCHEDULED_LOCAL",
    }
    receipt = {"schema": SCHEMA, "status": "ACCEPTED_SCHEDULED_LOCAL", "quote_source": _source(quote_path), "schedule": record, "external_calendar_writes": 0, "messages_sent": 0, "payments_collected": 0}
    receipt_text = json.dumps(receipt, indent=2) + "\n"
    schedule_path = schedule_path.resolve()
    receipt_path = schedule_path.with_name(f"{quote['quote_id']}-acceptance.json")
    try:
        with _schedule_transaction(schedule_path):
            rows = _read_schedule(schedule_path)
            previous = [row for row in rows if row["quote_id"] == record["quote_id"]]
            if previous:
                if previous != [record]:
                    raise QuoteError(f"schedule collision: quote {record['quote_id']} already has different booking details")
                # The CSV is authoritative. A retry also repairs a receipt lost
                # between the two file publications, without adding another job.
                _atomic_text(receipt_path, receipt_text)
                return receipt
            for row in rows:
                existing_start = datetime.combine(_iso_date(row["date"], "schedule.date"), _clock(row["start_time"], "schedule.start_time"))
                existing_end = existing_start + timedelta(hours=float(_decimal(row["duration_hours"], "schedule.duration_hours")))
                if new_start < existing_end and existing_start < new_end:
                    raise QuoteError(f"schedule collision with quote {row['quote_id']}")
            content = io.StringIO(newline="")
            writer = csv.DictWriter(content, fieldnames=SCHEDULE_FIELDS)
            writer.writeheader()
            writer.writerows([*rows, record])
            _atomic_text(schedule_path, content.getvalue())
            _atomic_text(receipt_path, receipt_text)
    except (OSError, sqlite3.Error) as exc:
        raise QuoteError(f"cannot persist local acceptance: {exc}; retry the same booking to complete its receipt") from exc
    return receipt


@dataclass(frozen=True)
class ServeConfig:
    quotes_dir: Path
    schedule: Path


def make_handler(config: ServeConfig):
    class AcceptanceHandler(BaseHTTPRequestHandler):
        def _reply(self, status: int, body: str) -> None:
            payload = body.encode()
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):  # noqa: N802
            query = parse_qs(urlparse(self.path).query)
            quote_id, token = query.get("quote", [""])[0], query.get("token", [""])[0]
            path = config.quotes_dir / f"{quote_id}.json"
            try:
                quote = _read_json(path)
                if token != quote.get("acceptance_token"):
                    raise QuoteError("invalid acceptance link")
                form = f"<h1>Accept {html.escape(quote_id)}</h1><p>Total: {html.escape(str(quote['total']))} {html.escape(str(quote['currency']))}</p><form method='post'><input type='hidden' name='quote' value='{html.escape(quote_id)}'><input type='hidden' name='token' value='{html.escape(token)}'><label>Date <input name='date' type='date' required></label><label> Start <input name='start' type='time' required></label><button>Accept and schedule</button></form>"
                self._reply(200, form)
            except QuoteError as exc:
                self._reply(400, html.escape(str(exc)))

        def do_POST(self):  # noqa: N802
            length = int(self.headers.get("Content-Length", "0"))
            values = parse_qs(self.rfile.read(length).decode())
            quote_id = values.get("quote", [""])[0]
            try:
                receipt = accept_quote(config.quotes_dir / f"{quote_id}.json", values.get("token", [""])[0], values.get("date", [""])[0], values.get("start", [""])[0], config.schedule)
                self._reply(200, f"<h1>Accepted</h1><p>{html.escape(receipt['schedule']['date'])} at {html.escape(receipt['schedule']['start_time'])}</p>")
            except QuoteError as exc:
                self._reply(400, html.escape(str(exc)))

        def log_message(self, *_args):
            return

    return AcceptanceHandler


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    quote = commands.add_parser("quote")
    quote.add_argument("--request", type=Path, required=True); quote.add_argument("--rules", type=Path, required=True)
    quote.add_argument("--issued-on", required=True); quote.add_argument("--valid-days", type=int, default=14)
    quote.add_argument("--base-url", default="http://127.0.0.1:8080"); quote.add_argument("--out-dir", type=Path, required=True)
    accept = commands.add_parser("accept")
    accept.add_argument("--quote", type=Path, required=True); accept.add_argument("--token", required=True)
    accept.add_argument("--date", required=True); accept.add_argument("--start", required=True); accept.add_argument("--schedule", type=Path, required=True)
    serve = commands.add_parser("serve")
    serve.add_argument("--quotes-dir", type=Path, required=True); serve.add_argument("--schedule", type=Path, required=True)
    serve.add_argument("--host", default="127.0.0.1"); serve.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    try:
        if args.command == "quote":
            result = write_quote_bundle(build_quote(args.request, args.rules, args.issued_on, args.valid_days, args.base_url), args.out_dir)
            print(json.dumps({key: str(value) for key, value in result.items()}, sort_keys=True))
        elif args.command == "accept":
            print(json.dumps(accept_quote(args.quote, args.token, args.date, args.start, args.schedule), sort_keys=True))
        else:
            server = ThreadingHTTPServer((args.host, args.port), make_handler(ServeConfig(args.quotes_dir, args.schedule)))
            print(f"Acceptance server: http://{args.host}:{args.port}")
            server.serve_forever()
    except QuoteError as exc:
        parser.exit(2, f"error: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
