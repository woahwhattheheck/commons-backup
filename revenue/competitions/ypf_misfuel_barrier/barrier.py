#!/usr/bin/env python3
"""Local fictional-scenario assessment; no fueling or dispatch integration.

Original scope: Commons #16018, YPF-MISFUEL-20K, Z-Sol-3917.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
import sys

SCHEMA = "ypf-misfuel-simulation-v1"
EVIDENCE_CLASS = "FICTIONAL_SIMULATION"
MAX_INPUT_BYTES = 1_048_576
MEMBERS = {"input.json", "assessment.json", "assessment.md", "manifest.json"}
STAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")
LITRES = re.compile(r"(?:0|[1-9]\d{0,8})(?:\.\d{1,3})?\Z")


class InputError(ValueError):
    pass


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                       indent=2) + "\n").encode("utf-8")


def strict_json(raw):
    if len(raw) > MAX_INPUT_BYTES:
        raise InputError(f"JSON input exceeds {MAX_INPUT_BYTES} bytes")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if len(key) > 256:
                raise InputError("JSON field names must not exceed 256 characters")
            if key in result:
                raise InputError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def nonfinite(value):
        raise InputError(f"non-finite JSON number: {value}")

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique,
                           parse_constant=nonfinite)
        json_bytes(value)
        return value
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise InputError(f"invalid UTF-8 JSON: {exc}") from exc


def read_bytes(path):
    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_INPUT_BYTES + 1)
    if len(raw) > MAX_INPUT_BYTES:
        raise InputError(f"file exceeds {MAX_INPUT_BYTES} bytes: {path}")
    return raw


def timestamp(value):
    if not isinstance(value, str) or not STAMP.fullmatch(value):
        raise InputError("expected UTC timestamp YYYY-MM-DDTHH:MM:SSZ")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise InputError(f"invalid UTC timestamp: {value}") from exc


def utc_text(value):
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def pointer(parent, key):
    return parent + "/" + str(key).replace("~", "~0").replace("/", "~1")


class Scenario:
    """Validate supplied scenario facts and collect deterministic local findings."""

    def __init__(self, value, evaluated_at):
        self.value = value
        self.at = timestamp(evaluated_at)
        self.findings = []

    def fail(self, code, path, message):
        if len(self.findings) >= 512:
            raise InputError("scenario exceeds 512 local findings; reduce malformed input before assessment")
        self.findings.append({"code": code, "path": path, "message": message})

    def object(self, value, path, fields):
        if not isinstance(value, dict):
            self.fail("MISSING_OR_INVALID_OBJECT", path, "An object is required.")
            return {}
        if len(value) > 64:
            raise InputError(f"scenario object exceeds 64 fields: {path or '/'}")
        for key in sorted(set(value) - set(fields)):
            self.fail("UNKNOWN_FIELD", pointer(path, key), "Field is not part of this scenario schema.")
        return value

    def text(self, row, key, path):
        return self.text_value(row.get(key), pointer(path, key))

    def text_value(self, value, path):
        if (not isinstance(value, str) or not value or len(value) > 256
                or value != value.strip() or any(ord(c) < 32 or ord(c) == 127 for c in value)):
            self.fail("MISSING_OR_INVALID_TEXT", path,
                      "Supply nonempty text without surrounding whitespace or control characters (max 256).")
            return None
        return value

    def integer(self, row, key, path, minimum=1):
        value = row.get(key)
        if type(value) is not int or not minimum <= value <= 2_147_483_647:
            self.fail("MISSING_OR_INVALID_INTEGER", f"{path}/{key}",
                      f"Supply an integer from {minimum} to 2147483647.")
            return None
        return value

    def litres(self, row, key, path):
        value = row.get(key)
        if not isinstance(value, str) or not LITRES.fullmatch(value):
            self.fail("MISSING_OR_INVALID_QUANTITY", f"{path}/{key}",
                      "Supply a nonnegative decimal string with at most 9 whole and 3 fractional digits.")
            return None
        return Decimal(value)

    def time(self, row, key, path):
        try:
            return timestamp(row.get(key))
        except InputError:
            self.fail("MISSING_OR_INVALID_TIME", f"{path}/{key}",
                      "Supply a valid UTC timestamp YYYY-MM-DDTHH:MM:SSZ.")
            return None

    def same(self, left, right, path, label):
        if left is not None and right is not None and left != right:
            self.fail("IDENTITY_MISMATCH", path, f"Must equal the supplied {label}.")

    def fresh(self, issued, expires, maximum_age, path):
        if issued is not None:
            age = (self.at - issued).total_seconds()
            if age < 0:
                self.fail("FUTURE_RECORD", path, "Record is later than the assessment time.")
            elif maximum_age is not None and age > maximum_age:
                self.fail("STALE_RECORD", path, "Record exceeds the supplied maximum age.")
        if expires is not None:
            if self.at >= expires:
                self.fail("EXPIRED_RECORD", path, "Record has reached its expiry time.")
            if issued is not None and expires <= issued:
                self.fail("INVALID_TIME_WINDOW", path, "Expiry must follow the issue time.")

    def record(self, key, text_fields, extra_fields, maximum_age):
        path = "/" + key
        row = self.object(self.value.get(key), path,
                          text_fields + extra_fields + ["issued_at", "expires_at", "evidence_ref"])
        values = {field: self.text(row, field, path) for field in text_fields}
        self.text(row, "evidence_ref", path)
        issued = self.time(row, "issued_at", path)
        self.fresh(issued, self.time(row, "expires_at", path), maximum_age, path)
        return row, values, issued

    def assess(self, evaluated_at):
        root = self.object(self.value, "", ["schema", "evidence_class", "scenario_id", "policy",
                          "plan", "order", "aircraft", "equipment", "observation", "prechecks"])
        self.value = root
        if root.get("schema") != SCHEMA or root.get("evidence_class") != EVIDENCE_CLASS:
            raise InputError(f"only schema {SCHEMA} / evidence_class {EVIDENCE_CLASS} is supported")
        scenario_id = self.text(root, "scenario_id", "")
        ages = ["max_plan_age_seconds", "max_order_age_seconds", "max_asset_age_seconds",
                "max_observation_age_seconds", "max_precheck_age_seconds"]
        policy = self.object(root.get("policy"), "/policy", ages + ["required_prechecks"])
        age = {key: self.integer(policy, key, "/policy") for key in ages}

        plan, p, plan_time = self.record("plan", ["plan_id", "aircraft_id", "flight_id", "stand_id", "fuel_product"],
                                        ["revision", "min_uplift_litres", "max_uplift_litres"], age[ages[0]])
        p["revision"] = self.integer(plan, "revision", "/plan")
        lower = self.litres(plan, "min_uplift_litres", "/plan")
        upper = self.litres(plan, "max_uplift_litres", "/plan")
        if lower is not None and upper is not None and lower > upper:
            self.fail("INVALID_QUANTITY_WINDOW", "/plan", "Minimum uplift exceeds maximum uplift.")

        order, o, order_time = self.record("order", ["order_id", "plan_id", "aircraft_id", "flight_id", "stand_id",
                                                         "equipment_id", "fuel_product"],
                                           ["plan_revision", "uplift_litres"], age[ages[1]])
        o["plan_revision"] = self.integer(order, "plan_revision", "/order")
        for field in ["plan_id", "aircraft_id", "flight_id", "stand_id", "fuel_product"]:
            self.same(o[field], p[field], "/order/" + field, "current plan " + field)
        self.same(o["plan_revision"], p["revision"], "/order/plan_revision", "current plan revision")
        if plan_time is not None and order_time is not None and order_time < plan_time:
            self.fail("ORDER_PREDATES_PLAN", "/order/issued_at", "Order predates the supplied current plan.")
        quantity = self.litres(order, "uplift_litres", "/order")
        if quantity is not None and (quantity <= 0 or (lower is not None and quantity < lower)
                                     or (upper is not None and quantity > upper)):
            self.fail("UPLIFT_OUTSIDE_PLAN", "/order/uplift_litres", "Uplift must be positive and within the supplied plan window.")

        aircraft, a, aircraft_time = self.record("aircraft", ["aircraft_id"], ["allowed_fuel_products", "max_uplift_litres"], age[ages[2]])
        self.same(a["aircraft_id"], p["aircraft_id"], "/aircraft/aircraft_id", "current plan aircraft_id")
        maximum = self.litres(aircraft, "max_uplift_litres", "/aircraft")
        if quantity is not None and maximum is not None and quantity > maximum:
            self.fail("UPLIFT_EXCEEDS_AIRCRAFT_LIMIT", "/order/uplift_litres", "Uplift exceeds the supplied fictional aircraft limit.")
        products = aircraft.get("allowed_fuel_products")
        valid_products = []
        if not isinstance(products, list) or not 1 <= len(products) <= 100:
            self.fail("MISSING_OR_INVALID_PRODUCTS", "/aircraft/allowed_fuel_products", "Supply 1 to 100 product names.")
        else:
            for index, product in enumerate(products):
                parsed = self.text_value(product, f"/aircraft/allowed_fuel_products/{index}")
                if parsed is not None:
                    if parsed in valid_products:
                        self.fail("DUPLICATE_PRODUCT", "/aircraft/allowed_fuel_products", "Product names must be unique.")
                    valid_products.append(parsed)
            if o["fuel_product"] is not None and o["fuel_product"] not in valid_products:
                self.fail("FUEL_PRODUCT_NOT_PERMITTED", "/order/fuel_product", "Product is absent from the supplied fictional aircraft record.")

        equipment, e, equipment_time = self.record("equipment", ["equipment_id", "fuel_product"], [], age[ages[2]])
        self.same(e["equipment_id"], o["equipment_id"], "/equipment/equipment_id", "order equipment_id")
        self.same(e["fuel_product"], o["fuel_product"], "/equipment/fuel_product", "order fuel_product")

        observed_fields = ["observation_id", "order_id", "plan_id", "aircraft_id", "flight_id", "stand_id", "equipment_id", "fuel_product"]
        observation = self.object(root.get("observation"), "/observation", observed_fields + ["plan_revision", "observed_at", "evidence_ref"])
        obs = {key: self.text(observation, key, "/observation") for key in observed_fields}
        self.text(observation, "evidence_ref", "/observation")
        revision = self.integer(observation, "plan_revision", "/observation")
        self.same(revision, p["revision"], "/observation/plan_revision", "current plan revision")
        for key in observed_fields[1:]:
            self.same(obs[key], o[key], "/observation/" + key, "order " + key)
        observed_at = self.time(observation, "observed_at", "/observation")
        self.fresh(observed_at, None, age[ages[3]], "/observation")
        if observed_at is not None and any(t is not None and observed_at < t for t in [plan_time, order_time, aircraft_time, equipment_time]):
            self.fail("OBSERVATION_PREDATES_CONTEXT", "/observation/observed_at", "Observation predates a supplied current record.")

        requirements = policy.get("required_prechecks")
        expected = {}
        if not isinstance(requirements, list) or not 2 <= len(requirements) <= 100:
            self.fail("MISSING_OR_INVALID_CHECKLIST", "/policy/required_prechecks", "Supply 2 to 100 required checks, including operator and equipment checks.")
        else:
            for index, item in enumerate(requirements):
                path = f"/policy/required_prechecks/{index}"
                row = self.object(item, path, ["check_id", "kind"])
                check_id, kind = self.text(row, "check_id", path), self.text(row, "kind", path)
                if kind not in {"operator", "equipment"}:
                    self.fail("INVALID_CHECK_KIND", path + "/kind", "Kind must be operator or equipment.")
                if check_id is not None:
                    if check_id in expected:
                        self.fail("DUPLICATE_REQUIRED_CHECK", path + "/check_id", "Check ID occurs more than once.")
                    expected[check_id] = kind
            if not {"operator", "equipment"}.issubset(set(expected.values())):
                self.fail("MISSING_CHECK_KIND", "/policy/required_prechecks", "At least one operator and one equipment check are mandatory.")

        prechecks = root.get("prechecks")
        seen = set()
        if not isinstance(prechecks, list) or len(prechecks) > 100:
            self.fail("MISSING_OR_INVALID_PRECHECKS", "/prechecks", "Supply a list of at most 100 check observations.")
            prechecks = []
        for index, item in enumerate(prechecks):
            path = f"/prechecks/{index}"
            row = self.object(item, path, ["check_id", "kind", "passed", "checked_at", "evidence_ref", "order_id", "observation_id"])
            check_id, kind = self.text(row, "check_id", path), self.text(row, "kind", path)
            self.text(row, "evidence_ref", path)
            self.same(self.text(row, "order_id", path), o["order_id"], path + "/order_id", "order order_id")
            self.same(self.text(row, "observation_id", path), obs["observation_id"], path + "/observation_id", "current observation_id")
            checked_at = self.time(row, "checked_at", path)
            self.fresh(checked_at, None, age[ages[4]], path)
            if checked_at is not None and observed_at is not None and checked_at < observed_at:
                self.fail("PRECHECK_PREDATES_OBSERVATION", path + "/checked_at", "Check predates the current observation.")
            if row.get("passed") is not True:
                self.fail("PRECHECK_NOT_PASSED", path + "/passed", "An explicit JSON true is required for this fictional check.")
            if check_id is not None:
                if check_id in seen:
                    self.fail("DUPLICATE_PRECHECK", path + "/check_id", "Check ID occurs more than once.")
                seen.add(check_id)
                if check_id not in expected:
                    self.fail("UNDECLARED_PRECHECK", path + "/check_id", "Check is absent from the supplied required checklist.")
                else:
                    self.same(kind, expected[check_id], path + "/kind", "required check kind")
        for missing in sorted(set(expected) - seen):
            self.fail("MISSING_PRECHECK", "/prechecks", f"Required check is absent: {missing}")

        findings = sorted(self.findings, key=lambda item: (item["code"], item["path"], item["message"]))
        state = "HOLD" if findings else "READY_FOR_SUPERVISED_PILOT"
        return {"schema": SCHEMA, "evidence_class": EVIDENCE_CLASS, "scenario_id": scenario_id,
                "evaluated_at": evaluated_at, "state": state, "simulated_dispatch_inhibited": bool(findings),
                "live_control": False, "live_dispatch_authorized": False, "source_authenticity_verified": False,
                "findings_count": len(findings), "findings": findings,
                "context": {"plan_id": p["plan_id"], "plan_revision": p["revision"], "order_id": o["order_id"],
                            "aircraft_id": o["aircraft_id"], "flight_id": o["flight_id"], "stand_id": o["stand_id"],
                            "equipment_id": o["equipment_id"], "fuel_product": o["fuel_product"],
                            "uplift_litres": str(quantity) if quantity is not None else None}}


def markdown(report, input_hash):
    def escaped(value):
        # Render imported strings literally inside a Markdown table, including
        # arbitrary unknown-field names and their RFC 6901 pointer escapes.
        special = "&<>|\\[]()*_~!#`\r\n"
        return "".join(f"&#{ord(c)};" if c in special else c for c in str(value))

    lines = ["# Fictional misfueling scenario", "", f"**State: {report['state']}**", "",
             "Local simulation only. This report cannot enable or authorize fueling, dispatch, or a pilot.", "",
             f"Evaluated at: {report['evaluated_at']}", "", f"Original input SHA-256: {input_hash}", "",
             "## Supplied context", "", "| Field | Value |", "| --- | --- |"]
    lines.extend(f"| {key} | {escaped(value)} |" for key, value in report["context"].items())
    lines.extend(["", "## Local findings", ""])
    if report["findings"]:
        lines.extend(["| Code | Input path | Reason |", "| --- | --- | --- |"])
        lines.extend(f"| {x['code']} | {escaped(x['path'])} | {escaped(x['message'])} |" for x in report["findings"])
    else:
        lines.append("All supplied fictional conditions are consistent at this assessment time.")
    lines.extend(["", "Source references and passed flags are supplied claims, not authenticated observations.",
                  "Replay establishes retained-byte and calculation consistency, not source truth or operational readiness.", ""])
    return "\n".join(lines).encode("utf-8")


def build_handoff(raw, evaluated_at):
    report = Scenario(strict_json(raw), evaluated_at).assess(evaluated_at)
    source_hash = sha256(raw)
    files = {"input.json": raw, "assessment.json": json_bytes(report),
             "assessment.md": markdown(report, source_hash)}
    manifest = {"schema": SCHEMA, "evidence_class": EVIDENCE_CLASS, "evaluated_at": evaluated_at,
                "implementation_sha256": sha256(Path(__file__).read_bytes()),
                "files": {name: {"sha256": sha256(body), "bytes": len(body)} for name, body in sorted(files.items())}}
    manifest["receipt_sha256"] = sha256(json_bytes(manifest))
    files["manifest.json"] = json_bytes(manifest)
    return files, report, manifest


def write_new_file(path, body):
    created = False
    try:
        with Path(path).open("xb") as stream:
            created = True
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        if created:
            Path(path).unlink(missing_ok=True)
        raise


def write_handoff(path, files):
    destination = Path(path)
    destination.mkdir()
    created = []
    try:
        for name, raw in sorted(files.items()):
            target = destination / name
            write_new_file(target, raw)
            created.append(target)
    except BaseException:
        for target in reversed(created):
            target.unlink(missing_ok=True)
        destination.rmdir()
        raise


def verify_handoff(path):
    root = Path(path)
    if {p.name for p in root.iterdir()} != MEMBERS:
        raise InputError("handoff must contain exactly input.json, assessment.json, assessment.md and manifest.json")
    actual = {}
    for name in sorted(MEMBERS):
        member = root / name
        if member.is_symlink() or not member.is_file():
            raise InputError(f"handoff member must be a regular file: {name}")
        actual[name] = read_bytes(member)
    manifest = strict_json(actual["manifest.json"])
    if not isinstance(manifest, dict):
        raise InputError("manifest must be an object")
    expected, report, rebuilt = build_handoff(actual["input.json"], manifest.get("evaluated_at"))
    for name in sorted(MEMBERS):
        if actual[name] != expected[name]:
            raise InputError(f"replay mismatch: {name}; keep the original input, receipt and barrier.py together")
    return report, rebuilt


def starter(evaluated_at):
    now = timestamp(evaluated_at)
    issued = utc_text(now - timedelta(seconds=60))
    observed = utc_text(now - timedelta(seconds=30))
    expires = utc_text(now + timedelta(minutes=30))
    context = {"aircraft_id": "FICTIONAL-AIRCRAFT-1", "flight_id": "FICTIONAL-FLIGHT-1", "stand_id": "FICTIONAL-STAND-1", "fuel_product": "FICTIONAL-PRODUCT-A"}
    record = {"issued_at": issued, "expires_at": expires, "evidence_ref": "FICTIONAL-SOURCE-REPLACE-ME"}
    return {"schema": SCHEMA, "evidence_class": EVIDENCE_CLASS, "scenario_id": "FICTIONAL-SCENARIO-1",
            "policy": {"max_plan_age_seconds": 600, "max_order_age_seconds": 600, "max_asset_age_seconds": 600,
                       "max_observation_age_seconds": 120, "max_precheck_age_seconds": 120,
                       "required_prechecks": [{"check_id": "FICTIONAL-OPERATOR-CHECK", "kind": "operator"},
                                              {"check_id": "FICTIONAL-EQUIPMENT-CHECK", "kind": "equipment"}]},
            "plan": {**record, **context, "plan_id": "FICTIONAL-PLAN-1", "revision": 1, "min_uplift_litres": "10", "max_uplift_litres": "100"},
            "order": {**record, **context, "order_id": "FICTIONAL-ORDER-1", "plan_id": "FICTIONAL-PLAN-1", "plan_revision": 1,
                      "equipment_id": "FICTIONAL-EQUIPMENT-1", "uplift_litres": "50"},
            "aircraft": {**record, "aircraft_id": context["aircraft_id"], "allowed_fuel_products": [context["fuel_product"]], "max_uplift_litres": "100"},
            "equipment": {**record, "equipment_id": "FICTIONAL-EQUIPMENT-1", "fuel_product": context["fuel_product"]},
            "observation": {**context, "observation_id": "FICTIONAL-OBSERVATION-1", "order_id": "FICTIONAL-ORDER-1", "plan_id": "FICTIONAL-PLAN-1", "plan_revision": 1,
                            "equipment_id": "FICTIONAL-EQUIPMENT-1", "observed_at": observed, "evidence_ref": "FICTIONAL-OBSERVATION-REPLACE-ME"},
            "prechecks": [{"check_id": "FICTIONAL-OPERATOR-CHECK", "kind": "operator", "passed": False, "checked_at": observed,
                           "evidence_ref": "FICTIONAL-PENDING-CHECK", "order_id": "FICTIONAL-ORDER-1", "observation_id": "FICTIONAL-OBSERVATION-1"},
                          {"check_id": "FICTIONAL-EQUIPMENT-CHECK", "kind": "equipment", "passed": False, "checked_at": observed,
                           "evidence_ref": "FICTIONAL-PENDING-CHECK", "order_id": "FICTIONAL-ORDER-1", "observation_id": "FICTIONAL-OBSERVATION-1"}]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    template = commands.add_parser("template", help="write an editable fictional input with unpassed checks")
    template.add_argument("--at", help="UTC reference time; default is current UTC")
    template.add_argument("--out", required=True, type=Path)
    check = commands.add_parser("check", help="import a fictional scenario and write a new four-file handoff")
    check.add_argument("input", type=Path)
    check.add_argument("--at", help="UTC assessment time; default is current UTC")
    check.add_argument("--out", required=True, type=Path)
    verify = commands.add_parser("verify", help="reconstruct a saved handoff at its original assessment time")
    verify.add_argument("handoff", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "verify":
            report, manifest = verify_handoff(args.handoff)
            print(json.dumps({"replay": "VERIFIED", "state": report["state"],
                              "evidence_class": report["evidence_class"], "live_dispatch_authorized": False,
                              "live_control": False, "receipt_sha256": manifest["receipt_sha256"]}, sort_keys=True))
            return 0
        at = args.at or utc_text(datetime.now(timezone.utc))
        timestamp(at)
        if args.command == "template":
            write_new_file(args.out, json_bytes(starter(at)))
            print(json.dumps({"written": str(args.out), "evidence_class": EVIDENCE_CLASS, "prechecks_passed": False}, sort_keys=True))
            return 0
        files, report, manifest = build_handoff(read_bytes(args.input), at)
        write_handoff(args.out, files)
        print(json.dumps({"state": report["state"], "evidence_class": report["evidence_class"],
                          "live_dispatch_authorized": False, "live_control": False, "findings_count": report["findings_count"],
                          "alert_codes": sorted({x["code"] for x in report["findings"]}),
                          "receipt_sha256": manifest["receipt_sha256"], "handoff": str(args.out)}, sort_keys=True))
        return 1 if report["state"] == "HOLD" else 0
    except (OSError, InputError, TypeError, ValueError, OverflowError, RecursionError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
