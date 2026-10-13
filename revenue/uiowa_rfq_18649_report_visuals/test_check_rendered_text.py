#!/usr/bin/env python3
"""Tests for the mid-word truncation detector."""
import importlib.util
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))


def load():
    spec = importlib.util.spec_from_file_location(
        "checker", os.path.join(HERE, "check_rendered_text.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def svg(desc, *texts):
    body = "".join(f"<text x='0' y='0'>{t}</text>" for t in texts)
    return f"<svg><desc>{desc}</desc>{body}</svg>"


class TruncationDetector(unittest.TestCase):
    def setUp(self):
        self.c = load()

    def test_detects_a_label_cut_mid_word(self):
        doc = svg("The practice is applied consistently across the group.",
                  "The practice is applied consist")
        self.assertEqual(self.c.truncated_texts(doc),
                         ["The practice is applied consist"])

    def test_complete_label_is_not_flagged(self):
        doc = svg("The practice is applied consistently across the group.",
                  "The practice is applied consistently across the group.")
        self.assertEqual(self.c.truncated_texts(doc), [])

    def test_break_on_a_word_boundary_is_not_flagged(self):
        # Stopping at a space is an editorial choice, not a clipped word.
        doc = svg("The practice is applied consistently across the group.",
                  "The practice is applied")
        self.assertEqual(self.c.truncated_texts(doc), [])

    def test_short_runs_are_ignored(self):
        # Axis ticks and marks are legitimately terse.
        doc = svg("Strength means evidence from two sources.", "Stren")
        self.assertEqual(self.c.truncated_texts(doc), [])

    def test_text_absent_from_desc_is_not_flagged(self):
        # Nothing to compare against is unknown, not a finding.
        doc = svg("Completely unrelated description text here.",
                  "Some label that appears nowhere in the desc")
        self.assertEqual(self.c.truncated_texts(doc), [])

    def test_nested_markup_is_stripped_before_comparison(self):
        doc = ("<svg><desc>The practice is applied consistently.</desc>"
               "<text><tspan>The practice is applied consist</tspan></text></svg>")
        self.assertEqual(self.c.truncated_texts(doc),
                         ["The practice is applied consist"])

    def test_several_truncations_in_one_figure_are_all_reported(self):
        doc = svg("Alpha beta gamma delta. Epsilon zeta eta theta.",
                  "Alpha beta gam", "Epsilon zeta et")
        self.assertEqual(len(self.c.truncated_texts(doc)), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
