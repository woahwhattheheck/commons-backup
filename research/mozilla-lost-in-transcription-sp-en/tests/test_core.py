import math
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import ConsensusConfig, Hypothesis, NgramPrior, choose_consensus, corpus_wer, edit_distance, normalize_for_score


class CoreTests(unittest.TestCase):
    def test_normalization_contract_edges(self):
        self.assertEqual(normalize_for_score('¿Hola! NASA va. Ándale—sí, pues... [noise] (?)'), ' hola NASA va ándale sí pues... ')
        self.assertEqual(normalize_for_score("(hello) #x27;test#x27;"), "hello 'test'")

    def test_edit_and_corpus_wer(self):
        self.assertEqual(edit_distance(("a", "b"), ("a", "c", "b")), 1)
        self.assertAlmostEqual(corpus_wer(["hola world"], ["hola word"]), 0.5)
        self.assertEqual(corpus_wer([""], [""]), 0.0)
        self.assertTrue(math.isinf(corpus_wer(["x"], [""])))

    def test_prior_is_deterministic_and_raw_text_free(self):
        lines = ["hola world", "hello mundo", "hola again"]
        a = NgramPrior.fit(lines, source_sha256="a" * 64)
        b = NgramPrior.fit(lines, source_sha256="a" * 64)
        self.assertEqual(a.to_json(), b.to_json())
        restored = NgramPrior.from_json(a.to_json())
        self.assertEqual(restored.source_sha256, "a" * 64)
        self.assertNotIn("hola world", a.to_json())

    def test_mbr_selects_supported_high_confidence_hypothesis(self):
        prior = NgramPrior.fit(["pues sí voy but i have to know la fecha", "okay entonces nos vemos after work"])
        hyps = [
            Hypothesis("pues sí voy but i have to no la fecha", "a", -8.0),
            Hypothesis("pues sí voy but i have to know la fecha", "b", -2.0),
            Hypothesis("pues sí voy but i have to know the date", "c", -9.0, 0.9),
        ]
        result = choose_consensus(hyps, prior=prior)
        self.assertEqual(result.chosen_source, "b")
        self.assertEqual(result.text, hyps[1].text)
        self.assertEqual(len(result.evidence_sha256), 64)

    def test_deterministic_tie_break_and_abstention(self):
        hyps = [Hypothesis("hola world", "a"), Hypothesis("hola word", "b")]
        result = choose_consensus(hyps, config=ConsensusConfig(acoustic_weight=0, prior_weight=0, margin_abstain=0.01))
        self.assertEqual(result.chosen_index, 0)
        self.assertTrue(result.abstain)

    def test_invalid_hypotheses_fail_closed(self):
        with self.assertRaises(ValueError):
            choose_consensus([Hypothesis("", "a"), Hypothesis("ok", "b")])
        with self.assertRaises(ValueError):
            choose_consensus([Hypothesis("ok", "a", float("nan")), Hypothesis("yes", "b")])
        with self.assertRaises(ValueError):
            choose_consensus([Hypothesis("ok", "a")])


if __name__ == "__main__":
    unittest.main()
