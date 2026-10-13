"""Aggregate the complete Water4All readiness hostile suite."""

import unittest

from .test_ready_sources import ReadyPathTests, SourceAuthorityTests
from .test_consortium import ConsortiumTests
from .test_evidence_cli import ApplicantAndEvidenceTests, ParsingAndCliTests
from .test_security_regressions import AuthorityBoundaryRegressionTests, ConsortiumAndPartnerRegressionTests


class PackagePublicApiTests(unittest.TestCase):
    def test_engine_reexports_source_sealing_helpers(self):
        import revenue.water4all_2026_swm as pkg
        from revenue.water4all_2026_swm import engine

        self.assertIs(pkg.seal_source, engine.seal_source)
        self.assertIs(pkg.source_fact_commitment, engine.source_fact_commitment)
        self.assertIs(pkg.strict_json_loads, engine.strict_json_loads)
        self.assertTrue(callable(engine.seal_source))
        self.assertTrue(callable(engine.source_fact_commitment))
        self.assertTrue(callable(engine.strict_json_loads))

    def test_compile_at_cannot_mint_current_packets(self):
        from .test_support import T0, ReadinessError, base_valid, compile_at

        with self.assertRaisesRegex(ReadinessError, "cannot mint CURRENT"):
            compile_at(base_valid(), T0, "CURRENT")

    def test_historical_compile_is_hold_only(self):
        from .test_support import T0, base_valid, compile_at, compile_historical

        historical = compile_at(base_valid(), T0, "HISTORICAL")
        self.assertEqual(historical["packet"]["decision"]["status"], "HISTORICAL_INTEGRITY_ONLY")
        self.assertEqual(historical["packet"]["decision"]["reason_count"], 0)
        alias = compile_historical(base_valid(), T0)
        self.assertEqual(alias["packet"]["decision"]["status"], "HISTORICAL_INTEGRITY_ONLY")

    def test_current_ready_requires_authority_root(self):
        from unittest.mock import patch

        from .test_support import T0, ReadinessError, base_valid, compile_current, verify_bundle

        value = base_valid()
        with self.assertRaisesRegex(ReadinessError, "independent authority is required"):
            compile_current(value, None)
        with patch("revenue.water4all_2026_swm.engine.utc_now", return_value=T0):
            bundle = compile_current(value, value)
        self.assertEqual(bundle["packet"]["decision"]["status"], "READY_FOR_OWNER_REVIEW")
        with self.assertRaisesRegex(ReadinessError, "independent authority is required"):
            verify_bundle(value, bundle, None)
        with patch("revenue.water4all_2026_swm.engine.utc_now", return_value=T0):
            result = verify_bundle(value, bundle, value)
        self.assertTrue(result["valid"])
        self.assertTrue(result["current_semantics"])

    def test_current_readiness_guard_is_clear_on_engine(self):
        from pathlib import Path

        from tools.current_readiness_guard.guard import scan_paths

        root = Path(__file__).resolve().parents[2]
        findings = scan_paths(["revenue/water4all_2026_swm/engine.py"], root=root)
        self.assertEqual([(item.rule, item.function) for item in findings], [])


__all__ = [
    "PackagePublicApiTests",
    "ReadyPathTests",
    "SourceAuthorityTests",
    "ConsortiumTests",
    "ApplicantAndEvidenceTests",
    "ParsingAndCliTests",
    "AuthorityBoundaryRegressionTests",
    "ConsortiumAndPartnerRegressionTests",
]

if __name__ == "__main__":
    unittest.main()
