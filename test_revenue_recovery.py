import importlib.util
import contextlib
import hashlib
import io
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from urllib.parse import quote


ROOT = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("revenue_recovery", ROOT / "host/revenue_recovery.py")
rr = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(rr)


class RevenueRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.pack = json.loads((ROOT / rr.PACK_PATH).read_text(encoding="utf-8"))
        self.recovery = json.loads((ROOT / rr.RECOVERY_PATH).read_text(encoding="utf-8"))

    def make_root(self, post=None):
        temp = tempfile.TemporaryDirectory()
        container = Path(temp.name)
        root = container / "commons"
        evidence_root = container / "private-evidence"
        (root / "revenue/payment_ready").mkdir(parents=True)
        (root / "p").mkdir()
        evidence_root.mkdir()
        for relative in (rr.PACK_PATH, rr.RECOVERY_PATH):
            shutil.copyfile(ROOT / relative, root / relative)
        if post is not None:
            (root / "p/buyer-signal.md").write_text(post, encoding="utf-8")
        return temp, root

    def evidence_root(self, root):
        return root.parent / "private-evidence"

    def valid_post(self, extra=""):
        return "\n".join([
            "---",
            "from: public-prospect",
            "to: OFFER",
            "board: OFFER",
            f"subject: {rr.SUBJECT}",
            "---",
            "PLAIN: Public, non-confidential GGUF diagnostic purchase intent.",
            f"OFFER_ID: {rr.OFFER_ID}",
            f"TERMS_SHA256: {rr.EXPECTED_TERMS_SHA256}",
            "PURCHASE_INTENT: YES",
            "GGUF_CONTROL: YES",
            "HARNESS_READY: YES",
            "PUBLIC_CONTACT_URL: https://example.com/contact",
            "START_WINDOW: public",
            "PUBLIC_OBJECTIVE: reproducibility",
            extra,
        ])

    def artifact(self, root, kind, reference, relative, content):
        path = self.evidence_root(root) / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return {
            "kind": kind,
            "reference": reference,
            "path": relative,
            "sha256": rr.sha256_bytes(content),
        }

    def advance(self, root, stage, previous_receipt_path, evidence_path):
        return rr.advance_receipt(
            root, self.evidence_root(root), stage, previous_receipt_path, evidence_path
        )

    def write_json(self, root, relative, value):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")

    def seed_chain(self, root, through="PURCHASE_INTENT"):
        (root / "receipts").mkdir(exist_ok=True)
        (root / "evidence").mkdir(exist_ok=True)
        (root / "p/buyer-signal.md").write_text(self.valid_post(), encoding="utf-8")
        result = {}
        intent = rr.purchase_intent_receipt(root, "buyer-signal")
        self.write_json(root, "receipts/intent.json", intent)
        result["PURCHASE_INTENT"] = intent
        if through == "PURCHASE_INTENT":
            return result
        quote_manifest = {
            "schema_version": "revenue-recovery-evidence/v1",
            "stage": "QUOTE",
            "artifact": self.artifact(
                root, "QUOTE_ARTIFACT", "owner-private:quote-seed", "owner-private/quote-seed.bin", b"quote seed\n"
            ),
        }
        self.write_json(root, "evidence/quote.json", quote_manifest)
        quote = self.advance(root, "QUOTE", "receipts/intent.json", "evidence/quote.json")
        self.write_json(root, "receipts/quote.json", quote)
        result["QUOTE"] = quote
        if through == "QUOTE":
            return result
        acceptance_manifest = {
            "schema_version": "revenue-recovery-evidence/v1",
            "stage": "ACCEPTANCE",
            "nda": {**self.artifact(root, "SIGNED_NDA", "owner-private:nda-seed", "owner-private/nda-seed.bin", b"nda seed\n"), "signed_at": "2026-08-25T14:00:00Z"},
            "sow": {**self.artifact(root, "SIGNED_SOW", "owner-private:sow-seed", "owner-private/sow-seed.bin", b"sow seed\n"), "signed_at": "2026-08-25T14:01:00Z"},
            "m1": {**self.artifact(root, "M1_PAYMENT_REFERENCE", "owner-private:m1-seed", "owner-private/m1-seed.bin", b"m1 seed\n"), "reference_at": "2026-08-25T14:02:00Z"},
        }
        self.write_json(root, "evidence/acceptance.json", acceptance_manifest)
        acceptance = self.advance(root, "ACCEPTANCE", "receipts/quote.json", "evidence/acceptance.json")
        self.write_json(root, "receipts/acceptance.json", acceptance)
        result["ACCEPTANCE"] = acceptance
        if through == "ACCEPTANCE":
            return result
        delivery_manifest = {"schema_version": "revenue-recovery-evidence/v1", "stage": "DELIVERY", "acceptance_tests": []}
        for i in range(1, 7):
            artifact = self.artifact(
                root, "ACCEPTANCE_TEST", f"owner-private:seed-at{i}", f"owner-private/seed-at{i}.bin", f"seed AT{i}\n".encode()
            )
            artifact.update({"id": f"AT{i}", "status": "PASS"})
            artifact.pop("kind")
            delivery_manifest["acceptance_tests"].append(artifact)
        self.write_json(root, "evidence/delivery.json", delivery_manifest)
        delivery = self.advance(root, "DELIVERY", "receipts/acceptance.json", "evidence/delivery.json")
        self.write_json(root, "receipts/delivery.json", delivery)
        result["DELIVERY"] = delivery
        return result

    def test_contract_hashes_are_exact(self):
        _, _, pack_hash, term_hash = rr.validate_contract(ROOT)
        self.assertEqual(pack_hash, self.recovery["offer"]["source_sha256"])
        self.assertEqual(term_hash, rr.EXPECTED_TERMS_SHA256)
        self.assertEqual(term_hash, self.recovery["offer"]["terms_sha256"])
        self.assertNotIn("titan", self.pack)
        self.assertIn("computer, titan, foundry, or hide-list material transferred", self.pack["offer"]["falsifier"])

    def test_pack_hash_is_canonical_across_lf_and_crlf(self):
        source = (ROOT / rr.PACK_PATH).read_text(encoding="utf-8")
        normalized = source.replace("\r\n", "\n").replace("\r", "\n")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lf_path = root / "pack-lf.json"
            crlf_path = root / "pack-crlf.json"
            lf_path.write_bytes(normalized.encode("utf-8"))
            crlf_path.write_bytes(normalized.replace("\n", "\r\n").encode("utf-8"))
            self.assertEqual(rr.sha256_canonical_text_file(lf_path), self.recovery["offer"]["source_sha256"])
            self.assertEqual(rr.sha256_canonical_text_file(crlf_path), self.recovery["offer"]["source_sha256"])

    def test_safe_path_rejects_escape(self):
        for value in ("../escape", "..\\escape", "a/b", ".", "..", ""):
            with self.subTest(value=value), self.assertRaises(ValueError):
                rr.safe_inbound_path(ROOT, value)

    def test_evidence_paths_are_cross_platform_posix_only(self):
        for value in ("..\\escape", "owner-private\\quote.bin", "../escape"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                rr.safe_repo_file(ROOT, value)

    def test_external_evidence_root_must_be_disjoint_and_paths_cannot_escape(self):
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        inside = root / "private-evidence"
        inside.mkdir()
        for candidate in (root, inside, root.parent):
            with self.subTest(candidate=candidate), self.assertRaisesRegex(ValueError, "evidence root"):
                rr.validate_evidence_root(root, candidate)
        for relative in ("../escape.bin", "nested\\escape.bin", str((root / "absolute.bin").resolve())):
            with self.subTest(relative=relative), self.assertRaises(ValueError):
                rr.safe_external_evidence_file(root, self.evidence_root(root), relative)

        outside = root.parent / "outside.bin"
        outside.write_bytes(b"outside")
        link = self.evidence_root(root) / "link.bin"
        try:
            link.symlink_to(outside)
        except OSError:
            pass
        else:
            with self.assertRaisesRegex(ValueError, "escaped the external evidence root"):
                rr.safe_external_evidence_file(root, self.evidence_root(root), "link.bin")

    def test_advance_cli_requires_explicit_evidence_root(self):
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = rr.main([
                "advance", "--root", str(root), "--stage", "QUOTE",
                "--previous-receipt", "receipts/intent.json",
                "--evidence-json", "evidence/quote.json",
            ])
        self.assertEqual(code, 2)
        self.assertIn("--evidence-root", output.getvalue())

    def test_missing_signal_is_needs_buyer_not_demand(self):
        receipt = rr.purchase_intent_receipt(ROOT, None)
        self.assertEqual(receipt["state"], "NEEDS_BUYER")
        self.assertEqual(receipt["facts"]["purchase_intent"], "UNKNOWN")
        self.assertEqual(receipt["facts"]["collected_cash_usd"], 0)
        self.assertFalse(receipt["cash_claimed"])

    def test_valid_signal_is_deterministic_and_redacted(self):
        temp, root = self.make_root(self.valid_post())
        self.addCleanup(temp.cleanup)
        one = rr.purchase_intent_receipt(root, "buyer-signal")
        two = rr.purchase_intent_receipt(root, "buyer-signal")
        rendered = json.dumps(one, sort_keys=True)
        self.assertEqual(one, two)
        self.assertEqual(one["state"], "RECORDED")
        self.assertEqual(one["next_stage"], "QUOTE")
        self.assertEqual(one["facts"]["legal_acceptance"], "NOT_LANDED")
        self.assertEqual(one["facts"]["processor_payment"], "NOT_LANDED")
        self.assertEqual(one["facts"]["collected_cash_usd"], 0)
        self.assertNotIn("example.com", rendered)

    def test_invalid_or_sensitive_signal_is_incomplete(self):
        cases = (
            self.valid_post().replace("HARNESS_READY: YES", "HARNESS_READY: NO"),
            self.valid_post().replace(rr.EXPECTED_TERMS_SHA256, "0" * 64),
            self.valid_post("ROUTING NUMBER: 123456789"),
            self.valid_post("CARD: 4242 4242 4242 4242"),
        )
        for index, post in enumerate(cases):
            with self.subTest(index=index):
                temp, root = self.make_root(post)
                try:
                    receipt = rr.purchase_intent_receipt(root, "buyer-signal")
                    self.assertEqual(receipt["state"], "INCOMPLETE")
                    self.assertFalse(receipt["cash_claimed"])
                finally:
                    temp.cleanup()

    def assert_sensitive_signal_is_incomplete(self, extra):
        temp, root = self.make_root(self.valid_post(extra))
        try:
            receipt = rr.purchase_intent_receipt(root, "buyer-signal")
            self.assertEqual(receipt["state"], "INCOMPLETE")
            self.assertFalse(receipt["cash_claimed"])
        finally:
            temp.cleanup()

    def test_x_url_embedded_secret_is_incomplete(self):
        self.assert_sensitive_signal_is_incomplete(
            "PUBLIC_CONTACT_URL: https://example.com/contact?token=sk_live_ABC123"
        )

    def test_y_plain_password_is_incomplete(self):
        self.assert_sensitive_signal_is_incomplete("PASSWORD: hunter2")

    def test_z_model_bytes_are_incomplete(self):
        self.assert_sensitive_signal_is_incomplete("MODEL_BYTES: payload")

    def test_adversarial_dlp_matrix_rejects_all_named_secret_classes(self):
        cases = (
            "TAX_ID: 12-3456789",
            "EIN: 12-3456789",
            "TOKEN: generic-secret-value",
            "AUTH: ghp_1234567890abcdef",
            "AUTHORIZATION: Bearer owner-secret-token",
            "AWS_ACCESS_KEY_ID: AKIAABCDEFGHIJKLMNOP",
            "AWS: AKIAABCDEFGHIJKLMNOP",
            "PRIVATE_BUYER: Acme",
            "PRIVATE_CUSTOMER: Acme",
            "BUYER_PRIVATE: Acme",
            "WEIGHTS: hidden-data",
            "MODEL_WEIGHTS: hidden-data",
            "MODEL: hidden-data",
            "GGUF: hidden-data",
            "GGUF_FILE: private.gguf",
            "BASE64: QUJDREVGR0hJSktMTU5PUA==",
            "PAYLOAD: data:application/octet-stream;base64,QUJDREVGRw==",
            '{"password":"hidden"}',
            '{"private_buyer":"Acme"}',
            '{"model_bytes":"QUJDREVGRw=="}',
            "A" * 100,
        )
        for value in cases:
            with self.subTest(value=value[:32]):
                self.assert_sensitive_signal_is_incomplete(value)

    def test_sensitive_field_names_are_canonical_and_value_independent(self):
        expected = {
            "authorization", "aws_access_key_id", "password", "passwd", "passphrase",
            "api_key", "access_token", "auth_token", "client_secret", "secret", "token",
            "private_buyer", "private_customer", "buyer_private", "model_bytes",
            "model_weights", "gguf_bytes", "gguf_file", "weights", "base64", "b64",
            "tax_id", "taxpayer_id", "taxpayer_identification", "ein", "tin",
            "email", "email_address", "customer_email", "private_email", "contact_email",
            "buyer_email", "work_email", "contact", "private_contact", "customer_contact",
            "buyer_contact", "phone", "phone_number", "telephone", "mobile", "mobile_phone",
            "customer_phone", "private_phone", "contact_phone", "buyer_phone", "name",
            "full_name", "first_name", "last_name", "legal_name", "customer_name",
            "private_name", "contact_name", "buyer_name", "address", "street_address",
            "address_line_1", "address_line_2", "mailing_address", "postal_address",
            "customer_address", "private_address", "contact_address", "postal_code",
            "zip_code", "postcode", "routing_number", "account_number", "bank_account",
            "bank_account_number", "bank_routing_number", "aba_routing_number", "iban",
            "swift", "swift_code", "bic", "sort_code",
        }
        self.assertEqual(rr.SENSITIVE_FIELD_NAMES, expected)
        for name in expected | {"AWS_SECRET_ACCESS_KEY"}:
            with self.subTest(name=name):
                self.assertTrue(rr.is_sensitive_field_name(name))
        self.assertFalse(rr.is_sensitive_field_name("PUBLIC_OBJECTIVE"))

    def test_server_rejects_every_sensitive_field_in_top_level_and_nested_json(self):
        for name in rr.SENSITIVE_FIELD_NAMES | {"aws_secret_access_key"}:
            with self.subTest(name=name):
                self.assertTrue(rr.contains_sensitive_value(json.dumps({name: "hidden"})))
                self.assertTrue(rr.contains_sensitive_value(json.dumps({"safe": {name: "hidden"}})))

    def test_server_rejects_raw_private_contact_values_but_keeps_public_https_url(self):
        for value in (
            "alice.customer@example.com", "555-123-4567", "+1 (555) 123-4567",
            "5551234567", "123 Main Street",
        ):
            with self.subTest(value=value):
                self.assertTrue(rr.contains_sensitive_value(value))
        self.assertFalse(rr.contains_sensitive_value("PUBLIC_CONTACT_URL: https://example.com/contact"))

    def test_server_rejects_camel_case_and_percent_encoded_full_posts(self):
        camel_names = {
            "routingNumber": "routing_number",
            "accountNumber": "account_number",
            "bankAccount": "bank_account",
            "customerEmail": "customer_email",
            "phoneNumber": "phone_number",
            "fullName": "full_name",
        }
        for supplied, expected in camel_names.items():
            with self.subTest(name=supplied):
                self.assertEqual(rr.canonical_field_name(supplied), expected)
                self.assertTrue(rr.is_sensitive_field_name(supplied))
                self.assertTrue(rr.contains_sensitive_value(json.dumps({supplied: "hidden"})))
                self.assert_sensitive_signal_is_incomplete(f"{supplied}=hidden")

        over_depth = json.dumps({"privateEmail": "alice@example.com"}, separators=(",", ":"))
        for _ in range(rr.PERCENT_DECODE_LAYERS + 1):
            over_depth = quote(over_depth, safe="")
        encoded = (
            "alice%40example.com",
            "%7B%22token%22%3A%22hidden%22%7D",
            "%7B%22privateEmail%22%3A%22alice%40example.com%22%7D",
            "%257B%2522privateEmail%2522%253A%2522alice%2540example.com%2522%257D",
            "customerEmail%3Dalice%2540example.com",
            over_depth,
        )
        for value in encoded:
            with self.subTest(value=value):
                self.assertTrue(rr.contains_sensitive_value(value))
                self.assert_sensitive_signal_is_incomplete(value)

        safe_url = "PUBLIC_CONTACT_URL: https://example.com/contact?next=%2Fpublic"
        self.assertFalse(rr.contains_sensitive_value(safe_url))
        temp, root = self.make_root(self.valid_post().replace(
            "PUBLIC_CONTACT_URL: https://example.com/contact", safe_url
        ))
        try:
            self.assertEqual(rr.purchase_intent_receipt(root, "buyer-signal")["state"], "RECORDED")
        finally:
            temp.cleanup()

    def test_server_rejects_short_bracket_unicode_and_overbudget_assignments(self):
        hostile = (
            'x["token"]="hidden"',
            "x['token']='hidden'",
            r'root["to\u006ben"]="hidden"',
            'root["topic]=reproducibility',
            r'root["to\ken"]="hidden"',
            "paßword=hidden",
            "paſſword=hidden",
            "ſecret=hidden",
            'x="{\\"token\\":\\"hidden\\"}"',
            'payload={"paſſword":"hidden"}',
            'payload={"paßword":"hidden"}',
            'payload={"ſecret":"hidden"}',
            "PUBLIC_CONTACT_URL: "
            "https://example.com/contact?payload=%7B%22pa%5Cu017f%5Cu017fword%22%3A%22hidden%22%7D",
            "PUBLIC_CONTACT_URL: https://alice%3Ahidden%0A%40example.com",
            "PUBLIC_CONTACT_URL: https://exa%7Fmple.com/contact",
            "PUBLIC_CONTACT_URL: https://exa%C2%85mple.com/contact",
            "PUBLIC_CONTACT_URL: https://alice%3Ahidden%C2%A0%40example.com",
            "x=[" + ",".join(["null"] * rr.JSON_SCAN_MAX_NODES) + "]",
        )
        for value in hostile:
            with self.subTest(value=value[:96]):
                self.assertTrue(rr.contains_sensitive_value(value))
                self.assert_sensitive_signal_is_incomplete(value)

        self.assertEqual(rr.canonical_field_name("paſſword"), "password")
        self.assertEqual(rr.canonical_field_name("paßword"), "password")
        self.assertEqual(rr.canonical_field_name("ſecret"), "secret")
        for value in (
            'x="reproducibility"',
            'x["topic"]="reproducibility"',
            r'root["to\u0070ic"]="reproducibility"',
            "paßage=public",
            "ſtatus=ready",
            "topic=straße",
        ):
            with self.subTest(safe_short_binding=value):
                self.assertFalse(rr.contains_sensitive_value(value))
                temp, root = self.make_root(self.valid_post(value))
                try:
                    self.assertEqual(
                        rr.purchase_intent_receipt(root, "buyer-signal")["state"],
                        "RECORDED",
                    )
                finally:
                    temp.cleanup()

    def test_server_rejects_glued_assignment_after_quoted_value(self):
        blocked = (
            'privateEmail=""customerEmail=hidden',
            'publicObjective=""customerEmail=hidden',
            "privateEmail=''customerEmail=hidden",
            "publicObjective=''customerEmail=hidden",
        )
        for value in blocked:
            with self.subTest(blocked=value):
                self.assertTrue(rr.contains_sensitive_value(value))
                self.assert_sensitive_signal_is_incomplete(value)

        safe = (
            'privateEmail=""',
            "privateEmail=''",
        )
        for value in safe:
            with self.subTest(safe=value):
                self.assertFalse(rr.contains_sensitive_value(value))
                temp, root = self.make_root(self.valid_post(value))
                try:
                    self.assertEqual(
                        rr.purchase_intent_receipt(root, "buyer-signal")["state"],
                        "RECORDED",
                    )
                finally:
                    temp.cleanup()

    def test_server_recursively_scans_public_contact_url_query_components(self):
        over_depth = "privateEmail=hidden"
        for _ in range(rr.PERCENT_DECODE_LAYERS + 1):
            over_depth = quote(over_depth, safe="")
        sensitive_urls = (
            "https://example.com/contact?private+email%3Dhidden",
            "https://example.com/contact?privateEmail%3Dhidden",
            "https://example.com/contact?priv%FFateEmail=hidden",
            "https://example.com/contact?tok%FFen=hidden",
            "https://example.com/contact?pass%FFword=hidden",
            "https://example.com/contact?accountNum%FFber=hidden",
            "https://example.com/contact?topic=%FF",
            "https://example.com/contact?topic=%C3%28",
            "https://example.com/contact?payload=private%252Bemail%253Dhidden",
            "https://example.com/contact?payload=%257B%2522privateEmail%2522%253A%2522hidden%2522%257D",
            "https://example.com/contact?next=https%3A%2F%2Fpublic.example%2Fcontact%3FprivateEmail%253Dhidden",
            "https://example.com/contact#private_email=hidden",
            "https://example.com/contact#private%5Femail%3Dhidden",
            "https://example.com/contact#privateEmail=hidden",
            "https://example.com/contact#accountNumber=hidden",
            "https://example.com/contact#safe=1&privateEmail=hidden",
            f"https://example.com/contact?payload={over_depth}",
            "https://alice@example.com",
            "https://alice@127.0.0.1",
            "https://alice%40example.com",
            "https://alice%40127.0.0.1",
            "https://alice:secret@example.com",
            "https://alice:secret@127.0.0.1",
            "https://alice%3Asecret%40example.com",
            "https://alice%3Asecret%40127.0.0.1",
            "https://alice%2F@127.0.0.1/contact",
            "https://alice%3F@127.0.0.1/contact",
            "https://alice%23@127.0.0.1/contact",
            "https://alice%0A@example.com/contact",
            "https://alice%252F@127.0.0.1/contact",
            "https://@example.com",
            "https://:@example.com",
            "https://%40example.com",
        )
        for url in sensitive_urls:
            with self.subTest(url=url):
                line = f"PUBLIC_CONTACT_URL: {url}"
                self.assertTrue(rr.contains_sensitive_value(line))
                temp, root = self.make_root(self.valid_post().replace(
                    "PUBLIC_CONTACT_URL: https://example.com/contact", line
                ))
                try:
                    receipt = rr.purchase_intent_receipt(root, "buyer-signal")
                    self.assertEqual(receipt["state"], "INCOMPLETE")
                    self.assertFalse(receipt["cash_claimed"])
                finally:
                    temp.cleanup()

    def test_server_scans_bare_query_fragment_and_wrapper_values(self):
        nested_json = json.dumps({"privateEmail": "hidden"}, separators=(",", ":"))
        once_nested_json = quote(nested_json, safe="")
        twice_nested_json = quote(once_nested_json, safe="")
        sensitive_values = (
            "?privateEmail[0]=hidden",
            "?user.privateEmail=hidden",
            "?user[privateEmail]=hidden",
            "?PrIvAtEeMaIl=hidden",
            "?privateEmail=hidden",
            "?privateEmail%3Dhidden",
            "?private_email=hidden",
            "?customerEmail=hidden",
            "#privateEmail=hidden",
            "#privateEmail%3Dhidden",
            "#customerEmail=hidden",
            "?payload=privateEmail=hidden",
            "?payload=privateEmail%3Dhidden",
            "#payload=privateEmail%3Dhidden",
            "payload=privateEmail%3Dhidden",
            f"?payload={nested_json}",
            f"?payload={once_nested_json}",
            f"?payload={twice_nested_json}",
            f"payload={once_nested_json}",
            "%C0%AF",
            "%ED%A0%80",
            "%F4%90%80%80",
        )
        for value in sensitive_values:
            with self.subTest(value=value):
                self.assertTrue(rr.contains_sensitive_value(value))

        for value in sensitive_values[:-3]:
            with self.subTest(full_post=value):
                self.assert_sensitive_signal_is_incomplete(value)

        safe_values = (
            "?topic=reproducibility",
            "?progress=100%",
            "?progress=100%25",
            "?topic=C%2B%2B",
            "?topic[0]=reproducibility",
            "?user.progress=steady",
            "?domain=docs.example.com",
            "?ToPiC[0]=reproducibility",
            "?UsEr.PrOgReSs=steady",
            "?note=%2",
            "?note=%GG",
            "#section-2",
            "#topic=C%2B%2B",
            "#progress=100%25",
            "payload=topic%3Dreproducibility",
            "payload=progress%3D100%2525",
        )
        for value in safe_values:
            with self.subTest(value=value):
                self.assertFalse(rr.contains_sensitive_value(value))

        for value in safe_values:
            with self.subTest(full_post=value):
                temp, root = self.make_root(self.valid_post().replace(
                    "PUBLIC_OBJECTIVE: reproducibility", f"PUBLIC_OBJECTIVE: {value}"
                ))
                try:
                    self.assertEqual(rr.purchase_intent_receipt(root, "buyer-signal")["state"], "RECORDED")
                finally:
                    temp.cleanup()

        for supplied in (
            "privateEmail[0]", "user.privateEmail", "user[privateEmail]", "PrIvAtEeMaIl",
        ):
            with self.subTest(sensitive_path_name=supplied):
                self.assertTrue(rr.is_sensitive_field_name(supplied))
        self.assertEqual(rr.canonical_field_name("PrIvAtEeMaIl"), "private_email")
        for supplied in (
            "topic[0]", "user.progress", "docs.example.com",
            "ToPiC[0]", "UsEr.PrOgReSs", "DoCs.ExAmPlE.CoM",
        ):
            with self.subTest(safe_path_name=supplied):
                self.assertFalse(rr.is_sensitive_field_name(supplied))

        below_safe_json = json.dumps("topic=reproducibility")
        below_sensitive_json = json.dumps("privateEmail=hidden")
        for _ in range(rr.JSON_SCAN_MAX_DEPTH // 2):
            below_safe_json = "[" + below_safe_json + "]"
            below_sensitive_json = "[" + below_sensitive_json + "]"
        self.assertFalse(rr.contains_sensitive_value(below_safe_json))
        self.assertTrue(rr.contains_sensitive_value(below_sensitive_json))
        self.assert_sensitive_signal_is_incomplete(
            "PUBLIC_OBJECTIVE: " + below_sensitive_json
        )

        over_depth_json = json.dumps("topic=reproducibility")
        for _ in range(rr.JSON_SCAN_MAX_DEPTH + 1):
            over_depth_json = "[" + over_depth_json + "]"
        self.assertTrue(rr.contains_sensitive_value(over_depth_json))
        self.assert_sensitive_signal_is_incomplete("PUBLIC_OBJECTIVE: " + over_depth_json)

        hostile_depth_json = json.dumps("topic=reproducibility")
        for _ in range(2200):
            hostile_depth_json = "[" + hostile_depth_json + "]"
        self.assertTrue(rr.contains_sensitive_value(hostile_depth_json))
        self.assert_sensitive_signal_is_incomplete(
            "PUBLIC_OBJECTIVE: " + hostile_depth_json
        )

        safe_boundary_json = json.dumps(
            [None] * (rr.JSON_SCAN_MAX_NODES - 1), separators=(",", ":")
        )
        hostile_over_node_json = json.dumps(
            [None] * (rr.JSON_SCAN_MAX_NODES + 1), separators=(",", ":")
        )
        safe_boundary_assignment = "payload=" + safe_boundary_json
        hostile_over_node_assignment = "payload=" + hostile_over_node_json
        self.assertFalse(rr.contains_sensitive_value(safe_boundary_assignment))
        safe_temp, safe_root = self.make_root(self.valid_post(safe_boundary_assignment))
        try:
            self.assertEqual(
                rr.purchase_intent_receipt(safe_root, "buyer-signal")["state"], "RECORDED"
            )
        finally:
            safe_temp.cleanup()
        self.assertTrue(rr.contains_sensitive_value(hostile_over_node_assignment))
        self.assert_sensitive_signal_is_incomplete(hostile_over_node_assignment)

        malformed_assignments = (
            "payload=[null,null",
            'payload={"topic":"reproducibility",}',
        )
        for assignment in malformed_assignments:
            with self.subTest(malformed_json_assignment=assignment):
                self.assertTrue(rr.contains_sensitive_value(assignment))
                self.assert_sensitive_signal_is_incomplete(assignment)

        safe_comma_assignments = (
            "payload=alpha,beta",
            'payload={"topics":["reproducibility","diagnostics"]}',
        )
        for assignment in safe_comma_assignments:
            with self.subTest(safe_comma_assignment=assignment):
                self.assertFalse(rr.contains_sensitive_value(assignment))
                temp, root = self.make_root(self.valid_post(assignment))
                try:
                    self.assertEqual(
                        rr.purchase_intent_receipt(root, "buyer-signal")["state"], "RECORDED"
                    )
                finally:
                    temp.cleanup()

        sensitive_comma_assignment = (
            'payload={"topic":"reproducibility","privateEmail":"hidden"}'
        )
        self.assertTrue(rr.contains_sensitive_value(sensitive_comma_assignment))
        self.assert_sensitive_signal_is_incomplete(sensitive_comma_assignment)

        for field in ("privateEmail", "token"):
            assignment = "payload=" + json.dumps(json.dumps(
                {field: "hidden"}, separators=(",", ":")
            ))
            with self.subTest(quoted_sensitive_json_assignment=field):
                self.assertTrue(rr.contains_sensitive_value(assignment))
                self.assert_sensitive_signal_is_incomplete(assignment)

        safe_quoted_assignments = (
            "payload=" + json.dumps("alpha,beta"),
            "payload=" + json.dumps(json.dumps(
                {"topics": ["reproducibility", "diagnostics"]}, separators=(",", ":")
            )),
        )
        for assignment in safe_quoted_assignments:
            with self.subTest(safe_quoted_comma_or_json_assignment=assignment):
                self.assertFalse(rr.contains_sensitive_value(assignment))
                temp, root = self.make_root(self.valid_post(assignment))
                try:
                    self.assertEqual(
                        rr.purchase_intent_receipt(root, "buyer-signal")["state"], "RECORDED"
                    )
                finally:
                    temp.cleanup()

        malformed_quoted_assignments = (
            "payload=" + json.dumps("[null,null"),
            "payload=" + json.dumps('{"topic":"reproducibility",}'),
            'payload="[null,null',
        )
        for assignment in malformed_quoted_assignments:
            with self.subTest(malformed_quoted_json_assignment=assignment):
                self.assertTrue(rr.contains_sensitive_value(assignment))
                self.assert_sensitive_signal_is_incomplete(assignment)

        overbudget_quoted_assignments = (
            "payload=" + json.dumps(over_depth_json),
            "payload=" + json.dumps(hostile_depth_json),
            "payload=" + json.dumps(hostile_over_node_json),
        )
        for assignment in overbudget_quoted_assignments:
            with self.subTest(overbudget_quoted_json_assignment=len(assignment)):
                self.assertTrue(rr.contains_sensitive_value(assignment))
                self.assert_sensitive_signal_is_incomplete(assignment)

        encoded_percent = "%"
        for layer in range(1, rr.PERCENT_DECODE_LAYERS + 2):
            encoded_percent = quote(encoded_percent, safe="")
            candidate = f"PUBLIC_OBJECTIVE: {encoded_percent}"
            with self.subTest(percent_layer=layer):
                self.assertEqual(
                    rr.contains_sensitive_value(candidate),
                    layer > rr.PERCENT_DECODE_LAYERS,
                )

        safe_urls = (
            "https://example.com/contact?next=%2Fpublic",
            "https://example.com/contact?topic=C%2B%2B",
            "https://example.com/contact?progress=100%",
            "https://example.com/contact?progress=100%25",
            "https://example.com/contact?note=%2",
            "https://example.com/contact?note=%GG",
            "https://example.com/contact?next=https%3A%2F%2Fpublic.example%2Fdocs%3Ftopic%3Dreproducibility",
            "https://example.com/contact#section-2",
            "https://example.com/contact#topic=C%2B%2B",
            "https://example.com/contact#progress=100%25",
        )
        for url in safe_urls:
            with self.subTest(url=url):
                line = f"PUBLIC_CONTACT_URL: {url}"
                self.assertFalse(rr.contains_sensitive_value(line))
                temp, root = self.make_root(self.valid_post().replace(
                    "PUBLIC_CONTACT_URL: https://example.com/contact", line
                ))
                try:
                    self.assertEqual(
                        rr.purchase_intent_receipt(root, "buyer-signal")["state"],
                        "RECORDED",
                    )
                finally:
                    temp.cleanup()

        safe_public_texts = (
            "PUBLIC_OBJECTIVE: improve by 100% reproducibly",
            "PUBLIC_OBJECTIVE: improve by 100%25 reproducibly",
            "PUBLIC_OBJECTIVE: literal %2 and %GG",
        )
        for line in safe_public_texts:
            with self.subTest(line=line):
                self.assertFalse(rr.contains_sensitive_value(line))
                temp, root = self.make_root(self.valid_post().replace(
                    "PUBLIC_OBJECTIVE: reproducibility", line
                ))
                try:
                    self.assertEqual(
                        rr.purchase_intent_receipt(root, "buyer-signal")["state"],
                        "RECORDED",
                    )
                finally:
                    temp.cleanup()

    def test_public_surface_is_open_and_exact(self):
        page = (ROOT / "diagnostic.html").read_text(encoding="utf-8")
        self.assertIn('id="say"', page)
        self.assertIn('data-no-from-memory="true"', page)
        self.assertIn('src="./carrier.js?', page)
        self.assertIn('name="to" value="OFFER"', page)
        self.assertIn('name="board" value="OFFER"', page)
        self.assertIn(f'name="subject" value="{rr.SUBJECT}"', page)
        self.assertIn(f"TERMS_SHA256: {rr.EXPECTED_TERMS_SHA256}", page)
        exact_m1 = "$6,000 before customer file exchange; after NDA and SOW signing; $6,000 on AT1–AT6 acceptance"
        self.assertIn(exact_m1, page)
        self.assertIn("event.stopImmediatePropagation()", page)
        self.assertIn("forbiddenFieldName", page)
        self.assertIn("canonicalFieldName", page)
        self.assertIn("jsonHasForbiddenField", page)
        self.assertIn("containsForbiddenAssignment", page)
        self.assertIn("authorization", page)
        self.assertIn("aws_access_key_id", page)
        self.assertIn('form.addEventListener("submit"', page)
        self.assertIn("}, true);", page)
        self.assertLess(page.index("event.stopImmediatePropagation()"), page.index('src="./carrier.js?'))
        self.assertLess(page.index('form.addEventListener("submit"'), page.index('src="./carrier.js?'))
        self.assertIn("No login or approval gate", page)
        self.assertIn("UNSEATED", page)
        self.assertNotIn('name="from"', page)
        carrier = (ROOT / "carrier.js").read_text(encoding="utf-8")
        self.assertIn('form.getAttribute("data-no-from-memory") === "true"', carrier)
        self.assertIn('el.form.getAttribute("data-no-from-memory") === "true"', carrier)
        lower = page.lower()
        self.assertNotIn('type="password"', lower)
        self.assertNotIn("allowlist", lower)
        self.assertNotIn("user tier", lower)

    def test_index_door_and_runtime_catalog_match(self):
        index = (ROOT / "index.html").read_text(encoding="utf-8")
        catalog = (ROOT / "door.js").read_text(encoding="utf-8")
        self.assertIn('href="./diagnostic.html">GGUF diagnostic</a>', index)
        self.assertIn('["diagnostic.html", "GGUF diagnostic"]', catalog)

    def test_actions_include_every_revenue_surface(self):
        workflow = (ROOT / ".github/workflows/tests.yml").read_text(encoding="utf-8")
        for path in (".gitattributes", "commercial.html", "diagnostic.html", "door.js", "revenue/payment_ready/**", "test_*.js"):
            self.assertEqual(workflow.count(f"- '{path}'"), 2)
        focused = (ROOT / ".github/workflows/revenue-hardening.yml").read_text(encoding="utf-8")
        for path in (
            "p/jojo-revenue-recovery-pipeline-20260825-01.md",
            "test_carrier_from_memory.js",
            ".gitignore",
        ):
            self.assertEqual(focused.count(f"- '{path}'"), 2)
        self.assertIn("node test_carrier_from_memory.js", focused)
        for command in (
            "test_revenue_recovery.py test_payment_ready.py test_dio_revenue_contract.py test_dio_crlf.py",
            "node test_diagnostic_dlp.js",
            "python host/revenue_recovery.py --self-test",
            "python host/revenue_recovery.py measure",
            "open_door_guard.py --diff-file -",
            "git diff --check HEAD^",
        ):
            self.assertIn(command, focused)
        self.assertEqual(focused.count("'test_diagnostic_dlp.js'"), 2)

    def test_gitignore_has_no_extra_blank_line_at_eof(self):
        data = (ROOT / ".gitignore").read_bytes()
        self.assertTrue(data.endswith(b"\n"), "POSIX text files end with one newline")
        self.assertFalse(
            data.endswith(b"\n\n"),
            "extra blank line at EOF fails git diff --check (revenue-hardening whitespace guard)",
        )
        self.assertNotIn(b"\r", data)
        text = data.decode("utf-8")
        self.assertIn("*.vault\n", text)
        self.assertIn("**/.commons/*.vault\n", text)
        self.assertTrue(text.rstrip("\n").endswith("**/.commons/*.vault"))

    def test_extra_blank_line_at_eof_fails_git_diff_check(self):
        """Regression for revenue-hardening run 33187123387 (.gitignore:21 new blank line at EOF)."""
        good = (ROOT / ".gitignore").read_bytes()
        self.assertFalse(good.endswith(b"\n\n"))
        bad = good.rstrip(b"\n") + b"\n\n"
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)

            def git(*args, check=True):
                return subprocess.run(
                    ["git", "-C", str(repo), *args],
                    check=check,
                    capture_output=True,
                    text=True,
                )

            git("init")
            git("config", "user.email", "rivet@example.invalid")
            git("config", "user.name", "RIVET")
            (repo / ".gitignore").write_bytes(good)
            git("add", ".gitignore")
            git("commit", "-m", "good")
            (repo / ".gitignore").write_bytes(bad)
            git("add", ".gitignore")
            git("commit", "-m", "bad")
            result = git("diff", "--check", "HEAD^", check=False)
            self.assertNotEqual(result.returncode, 0)
            combined = result.stdout + result.stderr
            self.assertIn("new blank line at EOF", combined)

    def test_append_only_canonical_post_and_new_correction_receipt(self):
        canonical_path = ROOT / "p/jojo-revenue-recovery-pipeline-20260825-01.md"
        canonical = canonical_path.read_bytes()
        blob = hashlib.sha1(f"blob {len(canonical)}\0".encode("ascii") + canonical).hexdigest()
        self.assertEqual(blob, "2e9b395e919e860134c6ffe70d29e3d8514127d3")

        receipt = (ROOT / "p/demon-revenue-hardening-correction-20260825-01.md").read_text(encoding="utf-8")
        self.assertIn("f2cdb0bd43123888e794999d9580f5c394fef969", receipt)
        self.assertIn("Correction base: the candidate commit's first parent", receipt)
        self.assertIn("cd132df7790940db230d7703ba49d6f95e2e00cc2a8893f0e29b5010453ecb36", receipt)
        self.assertIn("72 PASS", receipt)
        self.assertIn("test_diagnostic_dlp.js", receipt)
        self.assertIn("test_carrier_from_memory.js", receipt)
        self.assertIn("buyer: `UNKNOWN`", receipt)
        self.assertIn("demand: `UNKNOWN`", receipt)
        self.assertIn("contact sent: `false`", receipt)
        self.assertIn("collected cash: `USD 0 / NOT_LANDED`", receipt)
        self.assertNotIn("914eb20d333ebbe0b4452640b89204491207470b", receipt)

    def test_pipeline_truth_and_prospects_are_calibrated(self):
        self.assertTrue(self.recovery["public_surface"]["no_login"])
        self.assertTrue(self.recovery["public_surface"]["no_auth"])
        self.assertTrue(self.recovery["public_surface"]["no_gate"])
        self.assertEqual(self.recovery["truth"]["buyer"], "UNKNOWN")
        self.assertEqual(self.recovery["truth"]["demand"], "UNKNOWN")
        self.assertTrue(self.recovery["truth"]["contact_sent"])
        self.assertEqual(self.recovery["truth"]["distinct_contacts_sent"], 7)
        self.assertEqual(self.recovery["truth"]["provider_transports_observed"], 12)
        self.assertEqual(self.recovery["truth"]["replies_observed"], 0)
        self.assertEqual(self.recovery["truth"]["collected_cash_usd"], 0)
        self.assertFalse(self.recovery["resource_recovery"]["cursor_used_for_this_pipeline"])
        prospects = json.loads((ROOT / "revenue/payment_ready/prospects.json").read_text(encoding="utf-8"))
        self.assertEqual(prospects["measured_at"], "2026-08-27")
        self.assertEqual(len(prospects["prospects"]), 4)
        for row in prospects["prospects"]:
            self.assertEqual(row["state"], "CONTACTED_NO_RESPONSE")
            self.assertTrue(row["buyer_channel_url"].startswith("https://"))
            self.assertTrue(row["disqualifier"])
        self.assertTrue(prospects["contact_sent"])
        self.assertEqual(prospects["distinct_contacts_sent"], 7)
        self.assertEqual(prospects["provider_transports_observed"], 12)
        self.assertEqual(prospects["replies_observed"], 0)
        self.assertTrue(prospects["do_not_resend_all"])
        transports = prospects["canonical_transports"]
        self.assertEqual(len(transports), 7)
        self.assertEqual(len({row["provider_reference"] for row in transports}), 7)
        self.assertEqual(len({row["receipt"] for row in transports}), 7)
        receipt_paths = list((ROOT / "revenue/payment_ready/outreach_receipts").glob("*.json"))
        receipt_names = {path.name for path in receipt_paths}
        canonical_contact_keys = set()
        observed_provider_refs = {row["provider_reference"] for row in transports}
        for row in transports:
            self.assertEqual(row["state"], "SENT_COMPLETED_NO_RESPONSE")
            self.assertTrue(row["do_not_resend"])
            receipt_path = ROOT / "revenue/payment_ready" / row["receipt"]
            self.assertTrue(receipt_path.is_file())
            self.assertIn(Path(row["receipt"]).name, receipt_names)
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            campaign_id = receipt.get("campaign_id", "")
            self.assertFalse(campaign_id.startswith("same-day-agent-survival-proof-"))
            self.assertTrue(
                campaign_id == "owner-seven-outreach-20260826-01"
                or receipt.get("offer_id") == prospects["offer_id"]
            )
            self.assertEqual(receipt["provider_reference"], row["provider_reference"])
            provider_state = receipt.get("provider_state", receipt.get("transport_state"))
            self.assertIn(provider_state, {"COMPLETED", "DELIVERED"})
            if "dedupe" in receipt:
                self.assertTrue(receipt["dedupe"]["do_not_resend"])
            self.assertEqual(receipt["facts"]["buyer_authorization"], "UNKNOWN")
            self.assertEqual(receipt["facts"]["legal_acceptance"], "NOT_LANDED")
            self.assertFalse(receipt["facts"]["cash_claimed"])
            self.assertEqual(receipt["facts"]["collected_cash_usd"], 0)
            canonical_contact_keys.add(
                receipt.get("dedupe", {}).get("distinct_contact_key", receipt["recipient_email"]).casefold()
            )
        self.assertEqual(len(canonical_contact_keys), prospects["distinct_contacts_sent"])

        # The receipt directory is append-only and can contain unrelated campaigns.
        # Bind this funnel only to its declared routes and duplicate corrections.
        related_duplicate_receipts = []
        for path in receipt_paths:
            if "-duplicate-" not in path.name:
                continue
            duplicate = json.loads(path.read_text(encoding="utf-8"))
            duplicate_contact_key = duplicate.get("dedupe", {}).get("distinct_contact_key")
            if duplicate_contact_key is None:
                duplicate_contact_key = duplicate["recipient_email"]
            if duplicate_contact_key.casefold() not in canonical_contact_keys:
                continue
            related_duplicate_receipts.append(path)
            self.assertTrue(duplicate["dedupe"]["do_not_resend"])
            duplicate_state = duplicate.get("provider_state", duplicate.get("transport_state"))
            self.assertIn(duplicate_state, {"COMPLETED", "DELIVERED"})
            self.assertNotIn(duplicate["provider_reference"], observed_provider_refs)
            observed_provider_refs.add(duplicate["provider_reference"])
            self.assertEqual(duplicate["facts"]["buyer_authorization"], "UNKNOWN")
            self.assertEqual(duplicate["facts"]["legal_acceptance"], "NOT_LANDED")
            self.assertFalse(duplicate["facts"]["cash_claimed"])
            self.assertEqual(duplicate["facts"]["collected_cash_usd"], 0)
        self.assertEqual(
            len(related_duplicate_receipts),
            prospects["provider_transports_observed"] - prospects["distinct_contacts_sent"],
        )
        self.assertEqual(len(observed_provider_refs), prospects["provider_transports_observed"])
        self.assertEqual(prospects["truth"]["collected_cash_usd"], 0)

    def test_processor_is_hosted_handoff_not_mock_checkout(self):
        text = (ROOT / "revenue/payment_ready/processor_handoff.md").read_text(encoding="utf-8")
        self.assertIn("https://dashboard.stripe.com/account/payouts", text)
        self.assertIn("https://dashboard.stripe.com/invoices", text)
        self.assertIn("https://www.paypal.com/myaccount/money/", text)
        self.assertIn("never paste", text.lower())
        self.assertIn("enter the payout destination there only", text.lower())
        self.assertEqual(self.recovery["processor_handoff"]["values_never_enter_commons"], True)

    def test_public_artifacts_do_not_contain_secret_values(self):
        for relative in (
            "revenue/payment_ready/recovery.json",
            "revenue/payment_ready/prospects.json",
            "revenue/payment_ready/processor_handoff.md",
            "revenue/payment_ready/current_receipt.json",
            "revenue/payment_ready/integration_inventory.json",
            "revenue/payment_ready/evidence_contract.md",
        ):
            with self.subTest(relative=relative):
                self.assertFalse(rr.contains_sensitive_value((ROOT / relative).read_text(encoding="utf-8")))

    def test_receipt_schema_never_claims_cash(self):
        schema = json.loads((ROOT / "revenue/payment_ready/receipt.schema.json").read_text(encoding="utf-8"))
        self.assertIs(schema["properties"]["cash_claimed"]["const"], False)
        self.assertEqual(schema["properties"]["facts"]["properties"]["collected_cash_usd"]["const"], 0)
        for field in ("processor_payment", "payout", "bank_available", "cash_evidence"):
            self.assertEqual(schema["properties"]["facts"]["properties"][field]["const"], "NOT_LANDED")

    def test_receipt_schema_binds_later_stage_state_next_and_facts(self):
        schema = json.loads((ROOT / "revenue/payment_ready/receipt.schema.json").read_text(encoding="utf-8"))
        rules = {row["if"]["properties"]["stage"]["const"]: row["then"] for row in schema["allOf"]}
        expected = {
            "QUOTE": ("OFFERED", "ACCEPTANCE", "NOT_LANDED", "NOT_LANDED"),
            "ACCEPTANCE": ("ACCEPTED", "DELIVERY", "OWNER_REPORTED", "NOT_LANDED"),
            "DELIVERY": ("DELIVERED", "PROCESSOR_REFERENCE", "OWNER_REPORTED", "OWNER_REPORTED"),
            "PROCESSOR_REFERENCE": ("REFERENCE_RECORDED", "OWNER_PRIVATE_CASH_EVIDENCE", "OWNER_REPORTED", "OWNER_REPORTED"),
        }
        self.assertEqual(set(rules), set(expected))
        for stage, (state, next_stage, legal, delivery) in expected.items():
            with self.subTest(stage=stage):
                then = rules[stage]["properties"]
                self.assertEqual(then["state"]["const"], state)
                self.assertEqual(then["next_stage"]["const"], next_stage)
                self.assertEqual(then["facts"]["properties"]["legal_acceptance"]["const"], legal)
                self.assertEqual(then["facts"]["properties"]["delivery"]["const"], delivery)

    def test_false_cash_claim_rejects_positive_previous_cash(self):
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        prior = self.seed_chain(root)["PURCHASE_INTENT"]
        prior["facts"]["collected_cash_usd"] = 1
        self.write_json(root, "receipts/intent.json", prior)
        manifest = {
            "schema_version": "revenue-recovery-evidence/v1",
            "stage": "QUOTE",
            "artifact": self.artifact(root, "QUOTE_ARTIFACT", "owner-private:quote-example", "owner-private/quote.bin", b"quote"),
        }
        self.write_json(root, "evidence/quote.json", manifest)
        with self.assertRaisesRegex(ValueError, "stage-specific facts"):
            self.advance(root, "QUOTE", "receipts/intent.json", "evidence/quote.json")

    def test_false_cash_lineage_rejects_bank_or_payout_claim(self):
        for field in ("processor_payment", "payout", "bank_available", "cash_evidence"):
            temp, root = self.make_root()
            try:
                prior = self.seed_chain(root)["PURCHASE_INTENT"]
                prior["facts"][field] = "OWNER_REPORTED"
                self.write_json(root, "receipts/intent.json", prior)
                manifest = {
                    "schema_version": "revenue-recovery-evidence/v1", "stage": "QUOTE",
                    "artifact": self.artifact(root, "QUOTE_ARTIFACT", "owner-private:quote", "owner-private/quote.bin", b"quote"),
                }
                self.write_json(root, "evidence/quote.json", manifest)
                with self.subTest(field=field), self.assertRaisesRegex(ValueError, "stage-specific facts"):
                    self.advance(root, "QUOTE", "receipts/intent.json", "evidence/quote.json")
            finally:
                temp.cleanup()

    def test_predecessor_rejects_mutated_immutable_envelope_and_injected_facts(self):
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        original = self.seed_chain(root)["PURCHASE_INTENT"]
        manifest = {
            "schema_version": "revenue-recovery-evidence/v1",
            "stage": "QUOTE",
            "artifact": self.artifact(root, "QUOTE_ARTIFACT", "owner-private:quote", "owner-private/quote.bin", b"quote"),
        }
        self.write_json(root, "evidence/quote.json", manifest)
        mutations = (
            ("schema_version", "forged/v1"),
            ("kind", "FORGED_RECEIPT"),
            ("offer_id", "forged-offer"),
            ("stage", "QUOTE"),
            ("state", "OFFERED"),
            ("next_stage", "DELIVERY"),
        )
        for field, value in mutations:
            with self.subTest(field=field):
                forged = json.loads(json.dumps(original))
                forged[field] = value
                self.write_json(root, "receipts/intent.json", forged)
                with self.assertRaisesRegex(ValueError, f"immutable {field} mismatch"):
                    self.advance(root, "QUOTE", "receipts/intent.json", "evidence/quote.json")
        forged = json.loads(json.dumps(original))
        forged["unexpected"] = True
        self.write_json(root, "receipts/intent.json", forged)
        with self.assertRaisesRegex(ValueError, "envelope fields mismatch"):
            self.advance(root, "QUOTE", "receipts/intent.json", "evidence/quote.json")
        fact_mutations = {
            "purchase_intent": "UNKNOWN",
            "legal_acceptance": "OWNER_REPORTED",
            "delivery": "OWNER_REPORTED",
            "processor_reference": "REFERENCE_RECORDED",
        }
        for field, value in fact_mutations.items():
            with self.subTest(fact=field):
                forged = json.loads(json.dumps(original))
                forged["facts"][field] = value
                self.write_json(root, "receipts/intent.json", forged)
                with self.assertRaisesRegex(ValueError, "stage-specific facts mismatch"):
                    self.advance(root, "QUOTE", "receipts/intent.json", "evidence/quote.json")

    def test_predecessor_rejects_forged_shape_correct_source_and_lineage(self):
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        chain = self.seed_chain(root, "QUOTE")
        quote_manifest = json.loads((root / "evidence/quote.json").read_text(encoding="utf-8"))

        forged_intent = json.loads(json.dumps(chain["PURCHASE_INTENT"]))
        (root / "p/buyer-signal.md").write_text(self.valid_post("PUBLIC_OBJECTIVE: changed"), encoding="utf-8")
        new_hash = rr.sha256_file(root / "p/buyer-signal.md")
        forged_intent["source"]["sha256"] = new_hash
        forged_intent["evidence"][1]["sha256"] = new_hash
        self.write_json(root, "receipts/intent.json", forged_intent)
        with self.assertRaisesRegex(ValueError, "deterministic source replay"):
            self.advance(root, "QUOTE", "receipts/intent.json", "evidence/quote.json")

        (root / "p/buyer-signal.md").write_text(self.valid_post(), encoding="utf-8")
        self.write_json(root, "receipts/intent.json", chain["PURCHASE_INTENT"])
        forged_quote = json.loads(json.dumps(chain["QUOTE"]))
        forged_quote["evidence"][0]["sha256"] = "a" * 64
        self.write_json(root, "receipts/quote.json", forged_quote)
        acceptance_manifest = {
            "schema_version": "revenue-recovery-evidence/v1",
            "stage": "ACCEPTANCE",
            "nda": {**self.artifact(root, "SIGNED_NDA", "owner-private:nda", "owner-private/nda.bin", b"nda"), "signed_at": "2026-08-25T14:00:00Z"},
            "sow": {**self.artifact(root, "SIGNED_SOW", "owner-private:sow", "owner-private/sow.bin", b"sow"), "signed_at": "2026-08-25T14:01:00Z"},
            "m1": {**self.artifact(root, "M1_PAYMENT_REFERENCE", "owner-private:m1", "owner-private/m1.bin", b"m1"), "reference_at": "2026-08-25T14:02:00Z"},
        }
        self.write_json(root, "evidence/acceptance-forged.json", acceptance_manifest)
        with self.assertRaisesRegex(ValueError, "lineage sha256 does not match prior bytes"):
            self.advance(root, "ACCEPTANCE", "receipts/quote.json", "evidence/acceptance-forged.json")

        exact_quote = self.advance(root, "QUOTE", "receipts/intent.json", "evidence/quote.json")
        exact_quote["evidence"].append({
            "kind": "FORGED_BUT_SHAPED", "reference": "owner-private:forged",
            "sha256": "b" * 64, "status": "VERIFIED",
        })
        self.write_json(root, "receipts/quote.json", exact_quote)
        with self.assertRaisesRegex(ValueError, "deterministic source replay"):
            self.advance(root, "ACCEPTANCE", "receipts/quote.json", "evidence/acceptance-forged.json")

    def test_acceptance_orders_owner_reported_timestamps_without_overclaim(self):
        cases = (
            ("2026-08-25T14:00:00", "2026-08-25T14:01:00Z", "2026-08-25T14:02:00Z", "timezone"),
            ("2026-08-25T14:03:00Z", "2026-08-25T14:01:00Z", "2026-08-25T14:02:00Z", "must precede"),
            ("2026-08-25T14:00:00Z", "2026-08-25T14:02:00Z", "2026-08-25T14:02:00Z", "must precede"),
        )
        for nda_at, sow_at, m1_at, message in cases:
            temp, root = self.make_root()
            try:
                self.seed_chain(root, "QUOTE")
                manifest = {
                    "schema_version": "revenue-recovery-evidence/v1", "stage": "ACCEPTANCE",
                    "nda": {**self.artifact(root, "SIGNED_NDA", "owner-private:nda", "owner-private/nda.bin", b"nda"), "signed_at": nda_at},
                    "sow": {**self.artifact(root, "SIGNED_SOW", "owner-private:sow", "owner-private/sow.bin", b"sow"), "signed_at": sow_at},
                    "m1": {**self.artifact(root, "M1_PAYMENT_REFERENCE", "owner-private:m1", "owner-private/m1.bin", b"m1"), "reference_at": m1_at},
                }
                self.write_json(root, "evidence/acceptance-order.json", manifest)
                with self.subTest(nda_at=nda_at, sow_at=sow_at), self.assertRaisesRegex(ValueError, message):
                    self.advance(root, "ACCEPTANCE", "receipts/quote.json", "evidence/acceptance-order.json")
            finally:
                temp.cleanup()

        contract = (ROOT / "revenue/payment_ready/evidence_contract.md").read_text(encoding="utf-8")
        normalized_contract = " ".join(contract.split())
        self.assertIn("owner-reported timestamp metadata", normalized_contract)
        self.assertIn("does not independently prove legal signature or payment chronology", normalized_contract)

    def test_fractional_owner_reported_timestamps_remain_distinct_and_ordered(self):
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        self.seed_chain(root, "QUOTE")
        manifest = {
            "schema_version": "revenue-recovery-evidence/v1", "stage": "ACCEPTANCE",
            "nda": {**self.artifact(root, "SIGNED_NDA", "owner-private:nda-fraction", "nda-fraction.bin", b"nda"), "signed_at": "2026-08-25T14:00:00.100Z"},
            "sow": {**self.artifact(root, "SIGNED_SOW", "owner-private:sow-fraction", "sow-fraction.bin", b"sow"), "signed_at": "2026-08-25T14:00:00.200Z"},
            "m1": {**self.artifact(root, "M1_PAYMENT_REFERENCE", "owner-private:m1-fraction", "m1-fraction.bin", b"m1"), "reference_at": "2026-08-25T14:00:00.300Z"},
        }
        self.write_json(root, "evidence/acceptance-fraction.json", manifest)
        receipt = self.advance(root, "ACCEPTANCE", "receipts/quote.json", "evidence/acceptance-fraction.json")
        reported = [row["owner_reported_at"] for row in receipt["evidence"][1:]]
        self.assertEqual(reported, [
            "2026-08-25T14:00:00.100000Z",
            "2026-08-25T14:00:00.200000Z",
            "2026-08-25T14:00:00.300000Z",
        ])
        self.assertEqual(reported, sorted(reported))

    def test_public_current_receipt_is_deterministic(self):
        committed = json.loads((ROOT / "revenue/payment_ready/current_receipt.json").read_text(encoding="utf-8"))
        self.assertEqual(committed, rr.purchase_intent_receipt(ROOT, None))

    def test_integration_inventory_has_no_fake_checkout(self):
        inventory = json.loads((ROOT / "revenue/payment_ready/integration_inventory.json").read_text(encoding="utf-8"))
        self.assertTrue(inventory["zero_cursor"])
        stripe = next(row for row in inventory["missing_or_pending"] if row["provider"] == "Stripe")
        self.assertEqual(stripe["state"], "NOT_PROVISIONED")
        self.assertTrue(stripe["private_values_never_enter_commons"])
        apollo = next(row for row in inventory["connected"] if row["provider"] == "Apollo.io")
        self.assertEqual(apollo["state"], "CONNECTED")
        self.assertEqual(apollo["distinct_contacts_sent"], 7)
        self.assertEqual(apollo["provider_transports_observed"], 12)
        self.assertEqual(apollo["replies_observed"], 0)
        github = next(row for row in inventory["connected"] if row["provider"] == "GitHub")
        self.assertEqual(github["diagnostic_surface_state"], "LIVE_PUBLIC_NO_LOGIN")
        self.assertEqual(inventory["first_revenue_result"]["buyer"], "UNKNOWN")
        self.assertTrue(inventory["first_revenue_result"]["contact_sent"])
        self.assertEqual(inventory["first_revenue_result"]["distinct_contacts_sent"], 7)
        self.assertEqual(inventory["first_revenue_result"]["replies_observed"], 0)
        self.assertEqual(inventory["first_revenue_result"]["collected_cash_usd"], 0)

    def test_full_stage_chain_is_deterministic_and_stops_before_cash(self):
        temp, root = self.make_root(self.valid_post())
        self.addCleanup(temp.cleanup)
        (root / "receipts").mkdir()
        (root / "evidence").mkdir()

        def write_json(relative, value):
            (root / relative).write_text(json.dumps(value, sort_keys=True), encoding="utf-8")

        intent = rr.purchase_intent_receipt(root, "buyer-signal")
        write_json("receipts/intent.json", intent)
        quote_artifact = self.artifact(
            root, "QUOTE_ARTIFACT", "owner-private:quote-example", "owner-private/quote.bin", b"quote bytes\n"
        )
        quote_manifest = {
            "schema_version": "revenue-recovery-evidence/v1",
            "stage": "QUOTE",
            "artifact": quote_artifact,
        }
        write_json("evidence/quote.json", quote_manifest)
        quote = self.advance(root, "QUOTE", "receipts/intent.json", "evidence/quote.json")
        self.assertEqual(quote, self.advance(root, "QUOTE", "receipts/intent.json", "evidence/quote.json"))
        write_json("receipts/quote.json", quote)

        acceptance_manifest = {
            "schema_version": "revenue-recovery-evidence/v1",
            "stage": "ACCEPTANCE",
            "nda": {**self.artifact(root, "SIGNED_NDA", "owner-private:nda-example", "owner-private/nda.bin", b"nda bytes\n"), "signed_at": "2026-08-25T14:00:00Z"},
            "sow": {**self.artifact(root, "SIGNED_SOW", "owner-private:sow-example", "owner-private/sow.bin", b"sow bytes\n"), "signed_at": "2026-08-25T14:01:00Z"},
            "m1": {**self.artifact(root, "M1_PAYMENT_REFERENCE", "owner-private:m1-example", "owner-private/m1.bin", b"m1 reference bytes\n"), "reference_at": "2026-08-25T14:02:00Z"},
        }
        write_json("evidence/acceptance.json", acceptance_manifest)
        acceptance = self.advance(root, "ACCEPTANCE", "receipts/quote.json", "evidence/acceptance.json")
        self.assertEqual(acceptance["facts"]["legal_acceptance"], "OWNER_REPORTED")
        self.assertEqual([row["kind"] for row in acceptance["evidence"][1:]], ["SIGNED_NDA", "SIGNED_SOW", "M1_PAYMENT_REFERENCE"])
        self.assertEqual(
            [row["owner_reported_at"] for row in acceptance["evidence"][1:]],
            ["2026-08-25T14:00:00Z", "2026-08-25T14:01:00Z", "2026-08-25T14:02:00Z"],
        )
        self.assertNotIn("owner-private/nda.bin", json.dumps(acceptance))
        write_json("receipts/acceptance.json", acceptance)

        delivery_manifest = {
            "schema_version": "revenue-recovery-evidence/v1",
            "stage": "DELIVERY",
            "acceptance_tests": [],
        }
        for i in range(1, 7):
            artifact = self.artifact(
                root, "ACCEPTANCE_TEST", f"owner-private:at{i}-evidence", f"owner-private/at{i}.bin", f"AT{i} bytes\n".encode()
            )
            artifact.update({"id": f"AT{i}", "status": "PASS"})
            artifact.pop("kind")
            delivery_manifest["acceptance_tests"].append(artifact)
        write_json("evidence/delivery.json", delivery_manifest)
        delivery = self.advance(root, "DELIVERY", "receipts/acceptance.json", "evidence/delivery.json")
        self.assertEqual(delivery["facts"]["delivery"], "OWNER_REPORTED")
        self.assertEqual([row["kind"] for row in delivery["evidence"][1:]], [f"AT{i}" for i in range(1, 7)])
        write_json("receipts/delivery.json", delivery)

        processor_payload = b"stripe reference payload\n"
        (self.evidence_root(root) / "processor.bin").write_bytes(processor_payload)
        processor_manifest = {
            "schema_version": "revenue-recovery-evidence/v1",
            "stage": "PROCESSOR_REFERENCE",
            "provider": "Stripe",
            "opaque_reference": "stripe:event-example",
            "payload_path": "processor.bin",
            "payload_sha256": rr.sha256_bytes(processor_payload),
        }
        write_json("evidence/processor.json", processor_manifest)
        processor = self.advance(root, "PROCESSOR_REFERENCE", "receipts/delivery.json", "evidence/processor.json")
        self.assertEqual(processor["state"], "REFERENCE_RECORDED")
        self.assertEqual(processor["next_stage"], "OWNER_PRIVATE_CASH_EVIDENCE")
        self.assertEqual(processor["facts"]["processor_reference"], "REFERENCE_RECORDED")
        self.assertEqual(processor["facts"]["processor_payment"], "NOT_LANDED")
        self.assertEqual(processor["facts"]["payout"], "NOT_LANDED")
        self.assertEqual(processor["facts"]["bank_available"], "NOT_LANDED")
        self.assertEqual(processor["facts"]["cash_evidence"], "NOT_LANDED")
        self.assertEqual(processor["facts"]["collected_cash_usd"], 0)
        self.assertFalse(processor["cash_claimed"])
        rendered_chain = json.dumps([quote, acceptance, delivery, processor], sort_keys=True)
        self.assertNotIn(str(self.evidence_root(root)), rendered_chain)
        for private_path in (
            quote_artifact["path"], acceptance_manifest["nda"]["path"],
            acceptance_manifest["sow"]["path"], acceptance_manifest["m1"]["path"],
            "processor.bin",
        ):
            self.assertNotIn(private_path, rendered_chain)

    def test_artifact_digest_binds_exact_bytes_not_canonical_text(self):
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        self.seed_chain(root)
        lf = b"quote\nline\n"
        crlf = b"quote\r\nline\r\n"
        self.assertNotEqual(rr.sha256_bytes(lf), rr.sha256_bytes(crlf))
        artifact = self.artifact(root, "QUOTE_ARTIFACT", "owner-private:quote-exact", "owner-private/quote.bin", crlf)
        artifact["sha256"] = rr.sha256_bytes(lf)
        manifest = {"schema_version": "revenue-recovery-evidence/v1", "stage": "QUOTE", "artifact": artifact}
        (root / "evidence/quote.json").write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "does not match artifact bytes"):
            self.advance(root, "QUOTE", "receipts/intent.json", "evidence/quote.json")

    def test_opaque_references_are_namespace_ids_and_never_paths(self):
        bad_references = (
            "/tmp/private.bin", "C:/private/private.bin", "C:\\private\\private.bin",
            "file:///tmp/private.bin", "../private.bin", "owner-private:folder/file.bin",
            "owner-private:folder\\file.bin", "owner-private:..", "stripe:event:extra",
        )

        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        self.seed_chain(root)
        artifact = self.artifact(
            root, "QUOTE_ARTIFACT", "owner-private:quote-valid", "quote-private.bin", b"quote"
        )
        for reference in bad_references:
            artifact["reference"] = reference
            self.write_json(root, "evidence/quote-path-ref.json", {
                "schema_version": "revenue-recovery-evidence/v1",
                "stage": "QUOTE",
                "artifact": artifact,
            })
            with self.subTest(stage="QUOTE", reference=reference), self.assertRaisesRegex(ValueError, "opaque"):
                self.advance(root, "QUOTE", "receipts/intent.json", "evidence/quote-path-ref.json")

        chain = self.seed_chain(root, "DELIVERY")
        payload = self.evidence_root(root) / "processor-private.bin"
        payload.write_bytes(b"processor")
        manifest = {
            "schema_version": "revenue-recovery-evidence/v1",
            "stage": "PROCESSOR_REFERENCE",
            "provider": "Stripe",
            "opaque_reference": "stripe:event-valid",
            "payload_path": payload.name,
            "payload_sha256": rr.sha256_file(payload),
        }
        for reference in bad_references:
            manifest["opaque_reference"] = reference
            self.write_json(root, "evidence/processor-path-ref.json", manifest)
            with self.subTest(stage="PROCESSOR_REFERENCE", reference=reference), self.assertRaisesRegex(ValueError, "opaque"):
                self.advance(
                    root, "PROCESSOR_REFERENCE", "receipts/delivery.json",
                    "evidence/processor-path-ref.json",
                )

        manifest["opaque_reference"] = "stripe:event-valid"
        self.write_json(root, "evidence/processor-path-ref.json", manifest)
        receipt = self.advance(
            root, "PROCESSOR_REFERENCE", "receipts/delivery.json", "evidence/processor-path-ref.json"
        )
        rendered = json.dumps({"chain": chain, "receipt": receipt}, sort_keys=True)
        self.assertNotIn(str(payload), rendered)
        self.assertNotIn(payload.name, rendered)

    def test_acceptance_rejects_missing_or_reused_nda_sow_m1_evidence(self):
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        self.seed_chain(root, "QUOTE")
        shared = self.artifact(root, "SIGNED_NDA", "owner-private:shared", "owner-private/shared.bin", b"shared")
        manifest = {
            "schema_version": "revenue-recovery-evidence/v1",
            "stage": "ACCEPTANCE",
            "nda": {**shared, "signed_at": "2026-08-25T14:00:00Z"},
            "sow": {**shared, "kind": "SIGNED_SOW", "signed_at": "2026-08-25T14:01:00Z"},
            "m1": {**shared, "kind": "M1_PAYMENT_REFERENCE", "reference_at": "2026-08-25T14:02:00Z"},
        }
        (root / "evidence/acceptance.json").write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "must be distinct"):
            self.advance(root, "ACCEPTANCE", "receipts/quote.json", "evidence/acceptance.json")

    def test_event_order_rejects_delivery_before_acceptance(self):
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        self.seed_chain(root, "QUOTE")
        (root / "evidence/delivery.json").write_text(json.dumps({
            "schema_version": "revenue-recovery-evidence/v1", "stage": "DELIVERY", "acceptance_tests": []
        }), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "immutable stage mismatch"):
            self.advance(root, "DELIVERY", "receipts/quote.json", "evidence/delivery.json")

    def test_delivery_rejects_incomplete_acceptance_tests(self):
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        self.seed_chain(root, "ACCEPTANCE")
        manifest = {
            "schema_version": "revenue-recovery-evidence/v1",
            "stage": "DELIVERY",
            "acceptance_tests": [],
        }
        (root / "evidence/delivery.json").write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "AT1-AT6"):
            self.advance(root, "DELIVERY", "receipts/acceptance.json", "evidence/delivery.json")


if __name__ == "__main__":
    unittest.main()
