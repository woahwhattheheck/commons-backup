#!/usr/bin/env python3
"""Dependency-free contract tests for revenue/dio.

The small validator implements only the JSON Schema keywords used by this
packet.  Byte truth is checked separately against the named repository files.
"""
from __future__ import annotations

import copy
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

from revenue.dio import substrate_receipt


ROOT = Path(__file__).resolve().parent
DIO = ROOT / "revenue" / "dio"


class ContractError(AssertionError):
    pass


class MiniSchemaValidator:
    """Validate the deliberately small 2020-12 subset used in this packet."""

    def __init__(self, schema_dir: Path):
        self.schema_dir = schema_dir
        self.cache = {}

    def load(self, name: str):
        path = (self.schema_dir / name).resolve()
        if path not in self.cache:
            self.cache[path] = json.loads(path.read_text(encoding="utf-8"))
        return self.cache[path], path

    def validate_file(self, instance, name: str):
        schema, path = self.load(name)
        self._validate(instance, schema, schema, path, "$")

    def _resolve(self, ref: str, root, schema_path: Path):
        if "#" in ref:
            file_part, fragment = ref.split("#", 1)
        else:
            file_part, fragment = ref, ""
        if file_part:
            next_path = (schema_path.parent / file_part).resolve()
            if next_path not in self.cache:
                self.cache[next_path] = json.loads(next_path.read_text(encoding="utf-8"))
            next_root = self.cache[next_path]
        else:
            next_path, next_root = schema_path, root
        node = next_root
        if fragment:
            if not fragment.startswith("/"):
                raise ContractError("unsupported ref fragment %r" % fragment)
            for raw in fragment[1:].split("/"):
                key = raw.replace("~1", "/").replace("~0", "~")
                node = node[key]
        return node, next_root, next_path

    def _matches(self, value, schema, root, schema_path, at):
        try:
            self._validate(value, schema, root, schema_path, at)
            return True
        except ContractError:
            return False

    @staticmethod
    def _type_ok(value, wanted):
        if wanted == "null":
            return value is None
        if wanted == "object":
            return isinstance(value, dict)
        if wanted == "array":
            return isinstance(value, list)
        if wanted == "string":
            return isinstance(value, str)
        if wanted == "integer":
            return isinstance(value, int) and not isinstance(value, bool)
        if wanted == "number":
            return isinstance(value, (int, float)) and not isinstance(value, bool)
        if wanted == "boolean":
            return isinstance(value, bool)
        raise ContractError("validator does not implement type %r" % wanted)

    def _validate(self, value, schema, root, schema_path: Path, at: str):
        if schema is True:
            return
        if schema is False:
            raise ContractError("%s rejected by false schema" % at)
        if not isinstance(schema, dict):
            raise ContractError("%s has non-object schema" % at)

        if "$ref" in schema:
            node, next_root, next_path = self._resolve(schema["$ref"], root, schema_path)
            self._validate(value, node, next_root, next_path, at)
            return
        if "allOf" in schema:
            for part in schema["allOf"]:
                self._validate(value, part, root, schema_path, at)
        if "anyOf" in schema:
            if not any(self._matches(value, part, root, schema_path, at) for part in schema["anyOf"]):
                raise ContractError("%s matches no anyOf branch" % at)
        if "oneOf" in schema:
            hits = sum(self._matches(value, part, root, schema_path, at) for part in schema["oneOf"])
            if hits != 1:
                raise ContractError("%s matches %d oneOf branches" % (at, hits))
        if "if" in schema:
            branch = "then" if self._matches(value, schema["if"], root, schema_path, at) else "else"
            if branch in schema:
                self._validate(value, schema[branch], root, schema_path, at)
        if "const" in schema and value != schema["const"]:
            raise ContractError("%s is not const %r" % (at, schema["const"]))
        if "enum" in schema and value not in schema["enum"]:
            raise ContractError("%s is not in enum" % at)

        wanted = schema.get("type")
        if wanted is not None:
            choices = wanted if isinstance(wanted, list) else [wanted]
            if not any(self._type_ok(value, item) for item in choices):
                raise ContractError("%s has wrong type; need %r" % (at, wanted))

        if isinstance(value, str):
            if len(value) < schema.get("minLength", 0):
                raise ContractError("%s is too short" % at)
            if "maxLength" in schema and len(value) > schema["maxLength"]:
                raise ContractError("%s is too long" % at)
            if "pattern" in schema and re.search(schema["pattern"], value) is None:
                raise ContractError("%s does not match %s" % (at, schema["pattern"]))
            if schema.get("format") == "date-time":
                try:
                    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                except ValueError as exc:
                    raise ContractError("%s is not date-time" % at) from exc
                if parsed.tzinfo is None or parsed.utcoffset() is None:
                    raise ContractError("%s date-time has no timezone" % at)

        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if "minimum" in schema and value < schema["minimum"]:
                raise ContractError("%s is below minimum" % at)
            if "maximum" in schema and value > schema["maximum"]:
                raise ContractError("%s is above maximum" % at)

        if isinstance(value, list):
            if len(value) < schema.get("minItems", 0):
                raise ContractError("%s has too few items" % at)
            if schema.get("uniqueItems"):
                frozen = [json.dumps(item, sort_keys=True) for item in value]
                if len(frozen) != len(set(frozen)):
                    raise ContractError("%s has duplicate items" % at)
            if "items" in schema:
                for index, item in enumerate(value):
                    self._validate(item, schema["items"], root, schema_path, "%s[%d]" % (at, index))

        if isinstance(value, dict):
            for key in schema.get("required", []):
                if key not in value:
                    raise ContractError("%s missing %s" % (at, key))
            props = schema.get("properties", {})
            additional = schema.get("additionalProperties", True)
            extra = sorted(set(value) - set(props))
            if additional is False:
                if extra:
                    raise ContractError("%s has extra keys %r" % (at, extra))
            elif isinstance(additional, dict):
                for key in extra:
                    self._validate(
                        value[key], additional, root, schema_path, "%s.%s" % (at, key)
                    )
            for key, child_schema in props.items():
                if key in value:
                    self._validate(value[key], child_schema, root, schema_path, "%s.%s" % (at, key))


def load_json(relative: str):
    return json.loads((DIO / relative).read_text(encoding="utf-8"))


def sha256(raw: bytes):
    return hashlib.sha256(raw).hexdigest()


def iter_keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from iter_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_keys(child)


def iter_strings(value):
    if isinstance(value, dict):
        for child in value.values():
            yield from iter_strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_strings(child)
    elif isinstance(value, str):
        yield value


class DioRevenueContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.validator = MiniSchemaValidator(DIO)
        cls.foundation = load_json("foundation.json")
        cls.closed = load_json("examples/closed_room_model_edit.json")
        cls.repo = load_json("examples/repo_compute_job.json")
        cls.substrate_delivery = load_json("examples/substrate_delivery.json")

    def test_manifest_names_the_complete_lifecycle_and_packet(self):
        self.assertEqual(self.foundation["schema_version"], "dio-revenue/v1")
        self.assertEqual(
            [row["record"] for row in self.foundation["lifecycle"]],
            ["CUSTOMER_JOB", "QUOTE", "ACCEPTED_WORK", "DELIVERY_RECEIPT"],
        )
        for name in self.foundation["schemas"].values():
            self.assertTrue((DIO / name).is_file(), name)
        for name in self.foundation["examples"]:
            self.assertTrue((DIO / name).is_file(), name)
        self.assertEqual(
            self.foundation["delivery_receipt_fields"],
            [
                "schema_version", "kind", "receipt_id", "job_id", "quote_id", "status",
                "delivered_at", "result_address", "substrate", "artifacts", "acceptance",
                "bazaar", "payment",
            ],
        )

    def test_foundation_joins_the_canonical_public_offer(self):
        pointer = self.foundation["commercial_offer"]
        offer_path = (DIO / pointer["path"]).resolve()
        self.assertEqual(offer_path, ROOT / "commercial.json")
        commercial = json.loads(offer_path.read_text(encoding="utf-8"))
        self.assertEqual(commercial["offer"]["offer_id"], pointer["offer_id"])

    def test_examples_validate_without_external_jsonschema(self):
        for bundle in (self.closed, self.repo):
            self.validator.validate_file(bundle["job"], "customer_job.schema.json")
            self.validator.validate_file(bundle["quote"], "quote.schema.json")
            if bundle["delivery"] is not None:
                self.validator.validate_file(bundle["delivery"], "delivery_receipt.schema.json")
        self.validator.validate_file(
            self.substrate_delivery, "delivery_receipt.schema.json"
        )

    def test_every_stage_requires_substrate(self):
        specimens = (
            (self.repo["job"], "customer_job.schema.json"),
            (self.repo["quote"], "quote.schema.json"),
            (self.repo["delivery"], "delivery_receipt.schema.json"),
        )
        for value, schema in specimens:
            broken = copy.deepcopy(value)
            del broken["substrate"]
            with self.assertRaises(ContractError, msg=schema):
                self.validator.validate_file(broken, schema)

    def test_substrate_measurements_match_actual_mno_bytes(self):
        substrates = []
        for bundle in (self.closed, self.repo):
            substrates.extend([bundle["job"]["substrate"], bundle["quote"]["substrate"]])
            if bundle["delivery"] is not None:
                substrates.append(bundle["delivery"]["substrate"])
        substrates.append(self.substrate_delivery["substrate"])
        for substrate in substrates:
            path = ROOT / substrate["path"]
            self.assertEqual(path.suffix, ".mno")
            raw = path.read_bytes()
            self.assertEqual(len(raw), substrate["bytes"])
            self.assertEqual(sha256(raw), substrate["sha256"])

            header = substrate["header"]
            header_raw = raw[header["offset"]:header["offset"] + header["bytes"]]
            self.assertEqual(sha256(header_raw), header["sha256"])
            self.assertEqual(raw[:8].decode("ascii"), header["magic_ascii"])
            self.assertEqual(raw[:8].hex(), header["magic_hex"])
            self.assertEqual(substrate["format"], header["magic_ascii"])

            wire = substrate["wire_plane"]
            wire_raw = raw[wire["offset"]:wire["offset"] + wire["bytes"]]
            self.assertEqual(sha256(wire_raw), wire["sha256"])

            gates = substrate["gates"]
            region = raw[gates["region_offset"]:gates["region_offset"] + gates["region_bytes"]]
            body = raw[gates["body_offset"]:gates["body_offset"] + gates["body_bytes"]]
            self.assertEqual(sha256(region), gates["region_sha256"])
            self.assertEqual(sha256(body), gates["body_sha256"])
            self.assertEqual(gates["region_bytes"], gates["count"] * gates["record_bytes"])
            self.assertEqual(gates["body_offset"], header["bytes"])
            self.assertEqual(gates["body_offset"] + gates["body_bytes"], len(raw))

            for output in substrate["output_addresses"]:
                actual = raw[output["address"]]
                self.assertEqual(actual, output["value_uint"])
                self.assertEqual("%02x" % actual, output["value_hex"])

    def test_closed_room_example_stops_before_unmeasured_work(self):
        self.assertEqual(self.closed["quote"]["status"], "DRAFT")
        self.assertIsNone(self.closed["quote"]["price"]["amount_decimal"])
        self.assertIsNone(self.closed["accepted_work"])
        self.assertIsNone(self.closed["delivery"])
        self.assertIsNone(self.closed["job"]["inputs"][0]["sha256"])
        self.assertEqual(self.closed["job"]["payment"]["status"], "NOT_REQUESTED")
        for value in self.closed["job"]["bazaar"].values():
            if value != self.closed["job"]["bazaar"]["note"]:
                self.assertIsNone(value)

    def test_repo_example_links_job_quote_action_result_and_delivery(self):
        job, quote, delivery = self.repo["job"], self.repo["quote"], self.repo["delivery"]
        self.assertEqual(quote["job_id"], job["job_id"])
        self.assertEqual(delivery["job_id"], job["job_id"])
        self.assertEqual(delivery["quote_id"], quote["quote_id"])
        self.assertEqual(quote["status"], "ACCEPTED")
        self.assertNotIn("action_id", quote["accepted_work"])
        self.assertEqual(quote["bazaar"]["action_id"], delivery["bazaar"]["action_id"])
        self.assertEqual(job["bazaar"]["result_id"], delivery["bazaar"]["result_id"])
        self.assertEqual(delivery["status"], "DELIVERED")
        self.assertEqual(delivery["acceptance"]["status"], "PASS")

    def test_delivered_artifacts_and_acceptance_evidence_match_files(self):
        for delivery in (self.repo["delivery"], self.substrate_delivery):
            for artifact in delivery["artifacts"]:
                raw = (ROOT / artifact["path"]).read_bytes()
                self.assertEqual(len(raw), artifact["bytes"])
                self.assertEqual(sha256(raw), artifact["sha256"])
            for evidence in delivery["acceptance"]["evidence"]:
                if isinstance(evidence, dict) and "path" in evidence:
                    raw = (ROOT / evidence["path"]).read_bytes()
                    self.assertEqual(sha256(raw), evidence["sha256"])

    def test_generated_substrate_receipt_remeasures_cleanly(self):
        receipt_path = DIO / "examples" / "substrate_delivery.json"
        direct = substrate_receipt.check_receipt(receipt_path)
        self.assertEqual(direct["status"], "VALID")

        parsed = substrate_receipt.parse_mha(
            ROOT / self.substrate_delivery["substrate"]["path"]
        )
        recorded = self.substrate_delivery["substrate"]
        self.assertEqual(parsed["sha256"], recorded["sha256"])
        self.assertEqual(parsed["bytes"], recorded["bytes"])
        self.assertEqual(parsed["header"]["n_gate"], recorded["header"]["n_gate"])
        self.assertEqual(parsed["wire_plane"]["bytes"], recorded["wire_plane"]["bytes"])
        self.assertEqual(len(parsed["output_addresses"]), recorded["header"]["n_out"])

        completed = subprocess.run(
            [
                sys.executable,
                "revenue/dio/substrate_receipt.py",
                "check",
                "--receipt",
                "revenue/dio/examples/substrate_delivery.json",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(result["status"], "VALID")
        self.assertEqual(
            result["substrate_sha256"], self.substrate_delivery["substrate"]["sha256"]
        )

    def test_substrate_parser_rejects_corrupt_body_length(self):
        source = ROOT / self.substrate_delivery["substrate"]["path"]
        with tempfile.TemporaryDirectory() as directory:
            corrupt = Path(directory) / "corrupt.mno"
            corrupt.write_bytes(source.read_bytes() + b"\x00")
            with self.assertRaisesRegex(
                substrate_receipt.ReceiptError, "body length mismatch"
            ):
                substrate_receipt.parse_mha(corrupt)

    def test_quote_state_machine_rejects_adversarial_transitions(self):
        draft_with_work = copy.deepcopy(self.closed["quote"])
        draft_with_work["accepted_work"] = {
            "accepted_at": "2026-08-25T03:41:21Z",
            "acceptance_reference": "SHOULD-NOT-EXIST",
        }
        with self.assertRaises(ContractError):
            self.validator.validate_file(draft_with_work, "quote.schema.json")

        old_duplicate_action = copy.deepcopy(self.repo["quote"])
        old_duplicate_action["accepted_work"]["action_id"] = "conflicting-action-id"
        with self.assertRaises(ContractError):
            self.validator.validate_file(old_duplicate_action, "quote.schema.json")

        for path in ("accepted_work", "amount_decimal", "currency", "action_id"):
            broken = copy.deepcopy(self.repo["quote"])
            if path == "accepted_work":
                broken[path] = None
            elif path in ("amount_decimal", "currency"):
                broken["price"][path] = None
            else:
                broken["bazaar"][path] = None
            with self.subTest(required_for_accepted=path), self.assertRaises(ContractError):
                self.validator.validate_file(broken, "quote.schema.json")

    def test_delivered_state_requires_passed_accepted_lineage(self):
        mutations = (
            ("quote_id", lambda value: value.__setitem__("quote_id", None)),
            ("acceptance PASS", lambda value: value["acceptance"].__setitem__("status", "FAIL")),
            ("Bazaar action", lambda value: value["bazaar"].__setitem__("action_id", None)),
            ("Bazaar result", lambda value: value["bazaar"].__setitem__("result_id", None)),
            ("result address", lambda value: value.__setitem__("result_address", "")),
            ("artifact", lambda value: value.__setitem__("artifacts", [])),
        )
        for label, mutate in mutations:
            broken = copy.deepcopy(self.repo["delivery"])
            mutate(broken)
            with self.subTest(required=label), self.assertRaises(ContractError):
                self.validator.validate_file(broken, "delivery_receipt.schema.json")

        self.assertEqual(self.substrate_delivery["status"], "MEASURED")
        self.assertIsNone(self.substrate_delivery["quote_id"])
        self.assertIsNone(self.substrate_delivery["bazaar"]["action_id"])
        self.assertIsNone(self.substrate_delivery["bazaar"]["result_id"])

    def test_receipt_schema_and_full_check_reject_falsification(self):
        falsified = copy.deepcopy(self.substrate_delivery)
        falsified["status"] = "DELIVERED"
        falsified["acceptance"]["status"] = "FAIL"
        with self.assertRaises(ContractError):
            self.validator.validate_file(falsified, "delivery_receipt.schema.json")

        unknown = copy.deepcopy(self.substrate_delivery)
        unknown["unexpected_debug_field"] = True
        with self.assertRaises(ContractError):
            self.validator.validate_file(unknown, "delivery_receipt.schema.json")

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "falsified-receipt.json"
            for specimen in (falsified, unknown):
                path.write_text(json.dumps(specimen), encoding="utf-8")
                with self.assertRaises(substrate_receipt.ReceiptError):
                    substrate_receipt.check_receipt(path)

    def test_validator_rejects_bad_map_values_and_timezone_less_timestamps(self):
        bad_histogram = copy.deepcopy(self.substrate_delivery)
        bad_histogram["substrate"]["gates"]["opcode_histogram"]["NAND"] = "not-an-integer"
        with self.assertRaises(ContractError):
            self.validator.validate_file(bad_histogram, "delivery_receipt.schema.json")

        timezone_less = copy.deepcopy(self.repo["quote"])
        timezone_less["quoted_at"] = "2026-08-25T03:00:00"
        with self.assertRaises(ContractError):
            self.validator.validate_file(timezone_less, "quote.schema.json")

    def test_payment_is_honest_metadata_not_a_rail(self):
        allowed = set(self.foundation["payment_statuses"])
        for bundle in (self.closed, self.repo):
            records = [bundle["job"], bundle["quote"]]
            if bundle["delivery"] is not None:
                records.append(bundle["delivery"])
            for record in records:
                payment = record["payment"]
                self.assertEqual(set(payment), {"reference", "status"})
                self.assertIn(payment["status"], allowed)
                if payment["status"] == "NOT_REQUESTED":
                    self.assertIsNone(payment["reference"])

        substrate_payment = self.substrate_delivery["payment"]
        self.assertEqual(set(substrate_payment), {"reference", "status"})
        self.assertIn(substrate_payment["status"], allowed)
        self.assertIsNone(substrate_payment["reference"])

        self.assertNotIn("SETTLEMENT_EVIDENCE_PRESENT", allowed)
        for status in allowed - {"NOT_REQUESTED"}:
            broken = copy.deepcopy(self.repo["job"])
            broken["payment"] = {"reference": None, "status": status}
            with self.subTest(null_reference=status), self.assertRaises(ContractError):
                self.validator.validate_file(broken, "customer_job.schema.json")

            valid = copy.deepcopy(self.repo["job"])
            valid["payment"] = {"reference": "external-reference-01", "status": status}
            self.validator.validate_file(valid, "customer_job.schema.json")

        for status, reference in (
            ("NOT_REQUESTED", "must-be-null"),
            ("SETTLEMENT_EVIDENCE_PRESENT", None),
            ("PAID", "invented-state"),
        ):
            broken = copy.deepcopy(self.repo["job"])
            broken["payment"] = {"reference": reference, "status": status}
            with self.subTest(invalid_payment=status), self.assertRaises(ContractError):
                self.validator.validate_file(broken, "customer_job.schema.json")

    def test_contract_has_no_admission_or_secret_fields(self):
        blocked_keys = {
            "auth", "authentication", "authorization", "credential", "credentials",
            "identity", "login", "permission", "permissions", "token", "api_key", "rail",
        }
        for name in (
            "foundation.json", "customer_job.schema.json", "quote.schema.json",
            "delivery_receipt.schema.json", "examples/closed_room_model_edit.json",
            "examples/repo_compute_job.json", "examples/substrate_delivery.json",
        ):
            document = load_json(name)
            keys = {key.lower() for key in iter_keys(document)}
            self.assertFalse(keys & blocked_keys, "%s: %s" % (name, sorted(keys & blocked_keys)))
            for value in iter_strings(document):
                self.assertIsNone(
                    re.search(
                        r"-----BEGIN [A-Z ]*PRIVATE KEY-----|"
                        r"\bBearer\s+[A-Za-z0-9._~-]{8,}|"
                        r"\b(?:sk|ghp|github_pat)-[A-Za-z0-9_-]{16,}|"
                        r"\b(?:password|api[_-]?key|access[_-]?token)\s*[:=]\s*\S+|"
                        r"^(?:/root/|/home/|/Users/|[A-Za-z]:\\Users\\)",
                        value,
                        re.IGNORECASE,
                    ),
                    "%s contains a private value" % name,
                )


if __name__ == "__main__":
    unittest.main()
