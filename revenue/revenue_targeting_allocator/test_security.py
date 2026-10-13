from .test_support import *


class SecurityTests(AllocatorBase):
    def test_zero_explicit_probability_is_preserved_not_invented(self):
        out, _, _ = compile_portfolio(document(candidate(probability_bps=0)))
        row = out["rows"][0]
        self.assertEqual(row["queue"], "EXPECTED_VALUE")
        self.assertEqual(row["expected_value_minor"], 0)

    def test_duplicate_pair_rejected(self):
        c = candidate()
        with self.assertRaisesRegex(AllocationError, "duplicate opportunity/offer"):
            validate_input(document(c, copy.deepcopy(c)))

    def test_offer_switch_same_opportunity_rejected(self):
        a = candidate(offer_id="offer-a", evidence_bundle_sha256=digest("a"))
        b = candidate(offer_id="offer-b", evidence_bundle_sha256=digest("b"))
        with self.assertRaisesRegex(AllocationError, "cannot switch offers"):
            validate_input(document(a, b))

    def test_unknown_candidate_key_rejected(self):
        c = candidate()
        c["sales_magic"] = True
        with self.assertRaisesRegex(AllocationError, "unknown keys"):
            validate_input(document(c))

    def test_bool_is_not_integer_money(self):
        with self.assertRaisesRegex(AllocationError, "integer minor units"):
            validate_input(document(candidate(commercial_value_minor=True)))

    def test_probability_bounds(self):
        with self.assertRaisesRegex(AllocationError, "0..10000"):
            validate_input(document(candidate(probability_bps=10001)))

    def test_receipt_verifies_exact_semantics(self):
        doc = document(candidate(probability_bps=4000))
        out, md, receipt = compile_portfolio(doc)
        verified = verify_bundle(doc, out, md, receipt)
        self.assertTrue(verified["valid"])
        self.assertFalse(verified["external_send_authorized"])

    def test_tampered_output_rejected(self):
        doc = document(candidate(probability_bps=4000))
        out, md, receipt = compile_portfolio(doc)
        out["rows"][0]["commercial_value_minor"] += 1
        with self.assertRaisesRegex(AllocationError, "output semantic"):
            verify_bundle(doc, out, md, receipt)

    def test_tampered_markdown_rejected(self):
        doc = document(candidate())
        out, md, receipt = compile_portfolio(doc)
        with self.assertRaisesRegex(AllocationError, "markdown semantic"):
            verify_bundle(doc, out, md + "tamper", receipt)

    def test_tampered_receipt_rejected(self):
        doc = document(candidate())
        out, md, receipt = compile_portfolio(doc)
        receipt["counts"]["total"] += 1
        with self.assertRaisesRegex(AllocationError, "receipt semantic"):
            verify_bundle(doc, out, md, receipt)

    def test_every_authority_flag_false(self):
        out, _, receipt = compile_portfolio(document(candidate()))
        for key in ("external_send_authorized", "provider_mutation_authorized", "payment_or_revenue_inferred"):
            self.assertIs(out[key], False)
            self.assertIs(receipt[key], False)
            self.assertIs(out["rows"][0][key], False)

    def test_cli_compile_verify_and_overwrite_refusal(self):
        with tempfile.TemporaryDirectory() as td:
            outdir = Path(td) / "out"
            env = dict(os.environ)
            repo_root = Path(__file__).resolve().parents[2]
            env["PYTHONPATH"] = str(repo_root)
            compile_run = subprocess.run(
                [sys.executable, "-m", "revenue.revenue_targeting_allocator.cli", "compile", str(FIXTURE), "--output-dir", str(outdir)],
                cwd=repo_root, env=env, capture_output=True, text=True, check=False,
            )
            self.assertEqual(compile_run.returncode, 0, compile_run.stderr)
            verify_run = subprocess.run(
                [sys.executable, "-m", "revenue.revenue_targeting_allocator.cli", "verify", str(FIXTURE), "--output-dir", str(outdir)],
                cwd=repo_root, env=env, capture_output=True, text=True, check=False,
            )
            self.assertEqual(verify_run.returncode, 0, verify_run.stderr)
            duplicate = subprocess.run(
                [sys.executable, "-m", "revenue.revenue_targeting_allocator.cli", "compile", str(FIXTURE), "--output-dir", str(outdir)],
                cwd=repo_root, env=env, capture_output=True, text=True, check=False,
            )
            self.assertEqual(duplicate.returncode, 2)
            self.assertIn("File exists", duplicate.stderr)

    def test_ordinary_policy_global_rebinding_does_not_retarget_compiler(self):
        originals = {
            "STAGE_POINTS": allocator_module.STAGE_POINTS,
            "ROUTE_STATES": allocator_module.ROUTE_STATES,
            "CURRENCY_RE": allocator_module.CURRENCY_RE,
            "AUTHORITY_FALSE": allocator_module.AUTHORITY_FALSE,
        }
        try:
            allocator_module.STAGE_POINTS = {"PUBLIC_FIT": 999999}
            allocator_module.ROUTE_STATES = {"UNKNOWN"}
            allocator_module.CURRENCY_RE = allocator_module.re.compile(r"XXX")
            allocator_module.AUTHORITY_FALSE = {
                "external_send_authorized": True,
                "provider_mutation_authorized": True,
                "payment_or_revenue_inferred": True,
            }
            out, _, receipt = compile_portfolio(document(candidate()))
            row = out["rows"][0]
            self.assertEqual(row["stage_points"], 100)
            self.assertEqual(row["queue"], "EVIDENCE_STRENGTH")
            self.assertFalse(row["external_send_authorized"])
            self.assertFalse(out["external_send_authorized"])
            self.assertFalse(receipt["external_send_authorized"])
        finally:
            for name, value in originals.items():
                setattr(allocator_module, name, value)

    def test_duplicate_json_key_cli_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            bad = Path(td) / "bad.json"
            bad.write_text('{"schema":"x","schema":"y"}', encoding="utf-8")
            env = dict(os.environ)
            repo_root = Path(__file__).resolve().parents[2]
            env["PYTHONPATH"] = str(repo_root)
            run = subprocess.run(
                [sys.executable, "-m", "revenue.revenue_targeting_allocator.cli", "compile", str(bad), "--output-dir", str(Path(td)/"out")],
                cwd=repo_root, env=env, capture_output=True, text=True, check=False,
            )
            self.assertEqual(run.returncode, 2)
            self.assertIn("duplicate JSON key", run.stderr)

