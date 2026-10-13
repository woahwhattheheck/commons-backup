"""Tests for the accessible report visuals.

The suite is organised around the claims this package makes. Each claim that
would otherwise be marketing is an assertion here:

  * "WCAG compliant"            -> reference ratios + a full palette audit
  * "readable without colour"   -> grayscale conversion, then re-measure
  * "unassessed is not a low
     rating"                    -> data-layer, figure-layer and grayscale tests
  * "text alternative matches
     the picture"               -> the <desc> is compared to the generator
  * "reproducible"              -> render twice, compare bytes

Run:  python3 -m unittest -v test_report_visuals
"""

from __future__ import annotations

import copy
import json
import os
import tempfile
import unittest
import xml.etree.ElementTree as ET

import alt_text
import contrast
import figures
import model
import monochrome
import palette
import render_report_visuals as cli
import svg

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURE = os.path.join(HERE, "fixtures", "synthetic_assessment.json")
SVG_NS = "{http://www.w3.org/2000/svg}"


def load_raw() -> dict:
    with open(FIXTURE, "r", encoding="utf-8") as fh:
        return json.load(fh)


def build() -> model.Matrix:
    return model.Matrix.from_json_file(FIXTURE)


class TestContrastMath(unittest.TestCase):
    """The measuring instrument itself, against published reference values."""

    def test_extremes(self):
        self.assertAlmostEqual(contrast.contrast_ratio("#FFFFFF", "#000000"), 21.0, places=2)
        self.assertAlmostEqual(contrast.contrast_ratio("#FFFFFF", "#FFFFFF"), 1.0, places=6)

    def test_known_boundary_grey(self):
        # #767676 on white is the documented WCAG 4.5:1 boundary for body text.
        ratio = contrast.contrast_ratio("#767676", "#FFFFFF")
        self.assertGreaterEqual(round(ratio, 2), 4.5)
        self.assertLess(ratio, 4.6)

    def test_luminance_endpoints(self):
        self.assertAlmostEqual(contrast.relative_luminance("#000000"), 0.0, places=6)
        self.assertAlmostEqual(contrast.relative_luminance("#FFFFFF"), 1.0, places=6)

    def test_symmetry(self):
        self.assertAlmostEqual(contrast.contrast_ratio("#10505E", "#FFFFFF"),
                               contrast.contrast_ratio("#FFFFFF", "#10505E"), places=9)

    def test_grayscale_lands_on_the_nearest_representable_gray(self):
        """The grayscale transform preserves luminance exactly, up to rounding.

        A tolerance here would be a guess. The exact property is that the
        result is the CLOSEST gray an 8-bit channel can represent: no
        neighbouring gray level is nearer the source luminance. That catches a
        wrong luminance coefficient or a missing gamma step (both move the
        result many levels) while accepting the one unavoidable rounding.
        """
        for colour in ("#10505E", "#9C3016", "#8F6510", "#EFEFEC", "#2F6A93",
                       "#D8D8D4", "#FFFFFF", "#000000", "#7A3E8F", "#1F6B4B"):
            with self.subTest(colour=colour):
                target = contrast.relative_luminance(colour)
                produced = contrast.to_grayscale(colour)
                level = contrast.parse_hex(produced)[0]
                self.assertEqual(contrast.parse_hex(produced), (level, level, level))
                best = abs(contrast.relative_luminance(produced) - target)
                for neighbour in (level - 1, level + 1):
                    if 0 <= neighbour <= 255:
                        alt = contrast.to_hex((neighbour, neighbour, neighbour))
                        self.assertLessEqual(
                            best, abs(contrast.relative_luminance(alt) - target) + 1e-12,
                            f"{colour}: gray {produced} is not the closest level")

    def test_shorthand_and_rejection(self):
        self.assertEqual(contrast.parse_hex("#abc"), (0xAA, 0xBB, 0xCC))
        for bad in ("FFFFFF", "#GGGGGG", "#12345", "", None, 17):
            with self.assertRaises(contrast.ColorError):
                contrast.parse_hex(bad)

    def test_readable_ink_picks_the_better_one(self):
        self.assertEqual(contrast.readable_ink("#10505E"), "#FFFFFF")
        self.assertEqual(contrast.readable_ink("#EFEFEC"), "#000000")


class TestPaletteAudit(unittest.TestCase):
    """Every colour this package ships is measured, on every theme."""

    def test_no_failures_in_any_theme(self):
        for theme in palette.THEMES:
            with self.subTest(theme=theme):
                results = palette.audit_palette(theme)
                self.assertGreater(len(results), 30)
                bad = [r.as_dict() for r in results if not r.ok]
                self.assertEqual(bad, [], f"{theme}: {len(bad)} contrast failures")

    def test_audit_actually_detects_a_bad_colour(self):
        """A checker that cannot fail proves nothing. Prove it can fail."""
        original = palette.BANDS["STRENGTH"].ink
        try:
            palette.BANDS["STRENGTH"].ink = "#6E8D96"  # low contrast on its own fill
            self.assertTrue(palette.failures("print"),
                            "audit passed a deliberately unreadable colour")
        finally:
            palette.BANDS["STRENGTH"].ink = original
        self.assertEqual(palette.failures("print"), [])

    def test_text_meets_45_and_graphics_meet_3(self):
        for theme in palette.THEMES:
            for r in palette.audit_palette(theme):
                if r.kind == "text":
                    self.assertGreaterEqual(round(r.ratio, 2), 4.5, r.name)
                elif r.kind == "graphical":
                    self.assertGreaterEqual(round(r.ratio, 2), 3.0, r.name)


class TestUnassessedIsNotALowRating(unittest.TestCase):
    """The completion condition of this work order, as assertions."""

    def test_survives_grayscale_against_every_rating(self):
        """Strip the colour out, then measure again."""
        for nr in palette.NON_RATING_KEYS:
            for rating in palette.ORDINAL_KEYS:
                with self.subTest(pair=f"{nr}/{rating}"):
                    ratio = contrast.grayscale_contrast(palette.BANDS[nr].fill,
                                                        palette.BANDS[rating].fill)
                    self.assertGreaterEqual(
                        round(ratio, 2), contrast.DISTINCT_MIN,
                        f"{nr} and {rating} are only {ratio:.2f}:1 apart in grayscale; "
                        f"a black-and-white print could not tell them apart")

    def test_the_named_risk_pair_specifically(self):
        """'Not assessed' vs 'Gap' is the confusion this order names."""
        una = palette.BANDS["UNASSESSED"]
        gap = palette.BANDS["GAP"]
        self.assertGreaterEqual(round(contrast.grayscale_contrast(una.fill, gap.fill), 2), 3.0)
        self.assertNotEqual(una.shape, gap.shape)
        self.assertNotEqual(una.texture, gap.texture)
        self.assertNotEqual(una.border, gap.border)
        self.assertNotEqual(una.label, gap.label)
        self.assertNotEqual(una.glyph, gap.glyph)

    def test_non_ratings_carry_no_rank(self):
        """rank is None, so nothing can sort them onto the bottom of the scale."""
        for key in palette.NON_RATING_KEYS:
            self.assertIsNone(palette.BANDS[key].rank)
            self.assertFalse(palette.BANDS[key].on_scale)
        for key in palette.ORDINAL_KEYS:
            self.assertIsInstance(palette.BANDS[key].rank, int)
            self.assertTrue(palette.BANDS[key].on_scale)

    def test_excluded_from_rating_counts_not_counted_as_zero(self):
        m = build()
        totals = m.totals()
        self.assertEqual(totals["cells_expected"], 12)
        self.assertEqual(totals["rated"], 7)
        self.assertEqual(totals["not_assessed"], 1)
        self.assertEqual(totals["insufficient_evidence"], 2)
        self.assertEqual(totals["not_applicable"], 1)
        self.assertEqual(totals["contradictory"], 1)
        # Every unrated cell is absent from `rated`, not folded in as a low.
        self.assertEqual(totals["rated"] + totals["not_assessed"]
                         + totals["insufficient_evidence"] + totals["not_applicable"]
                         + totals["contradictory"], 12)
        ess = m.summarize_group("ESS")
        self.assertEqual(ess.rated, 3)
        self.assertEqual(ess.unassessed, 1)
        self.assertEqual(ess.band_counts["GAP"], 0,
                         "an unassessed area leaked into the Gap count")

    def test_no_average_band_is_exposed(self):
        """There is deliberately no mean-rating API to misuse."""
        m = build()
        for forbidden in ("average", "mean_band", "score", "overall_rating", "maturity"):
            self.assertFalse(hasattr(m, forbidden), f"Matrix exposes {forbidden}")
            self.assertFalse(hasattr(m.summarize_group("ESS"), forbidden))

    def test_figure_draws_unassessed_with_its_own_vocabulary(self):
        m = build()
        payload = figures.matrix_figure(m, "print").render()
        self.assertIn("Not assessed", payload)
        self.assertIn("no evidence collected", payload)
        # dashed border = the not-a-rating signal, present in the markup
        self.assertIn('stroke-dasharray="5 3"', payload)
        # its texture is a real pattern def, not a colour-only difference
        self.assertIn("matrix-tex-UNASSESSED", payload)
        self.assertIn("matrix-tex-INSUFFICIENT_EVIDENCE", payload)

    def test_cross_group_separates_the_off_scale_lanes(self):
        payload = figures.cross_group_figure(build(), "print").render()
        self.assertIn("Off the rating scale", payload)
        self.assertIn("not lower ratings", payload)


class TestRedundantEncoding(unittest.TestCase):
    """No single channel may be load-bearing on its own."""

    def test_contract_holds(self):
        self.assertEqual(cli.check_encoding_contract(), [])

    def test_every_channel_is_unique_per_band(self):
        for attr in ("label", "glyph", "shape", "texture", "fill"):
            values = [getattr(palette.BANDS[k], attr) for k in palette.BAND_ORDER]
            self.assertEqual(len(set(values)), len(values), f"duplicate {attr}")

    def test_contract_check_detects_a_collapsed_channel(self):
        """If two bands ever share a shape, the checker must say so."""
        original = palette.BANDS["GAP"].shape
        try:
            palette.BANDS["GAP"].shape = palette.BANDS["UNASSESSED"].shape
            problems = cli.check_encoding_contract()
            self.assertTrue(any("shape" in p for p in problems), problems)
        finally:
            palette.BANDS["GAP"].shape = original
        self.assertEqual(cli.check_encoding_contract(), [])

    def test_all_shapes_and_textures_are_drawable(self):
        for key in palette.BAND_ORDER:
            b = palette.BANDS[key]
            self.assertIn(b.shape, svg.KNOWN_SHAPES)
            self.assertIn(b.texture, svg.KNOWN_TEXTURES)
            self.assertTrue(svg.mark(b.shape, 10, 10, 12, "#000000").startswith("<"))

    def test_group_identity_never_rides_on_colour(self):
        """Measured: the group colours are indistinguishable in grayscale.

        That is exactly why every group mark is also captioned with its code.
        """
        worst = max(
            contrast.grayscale_contrast(a, b)
            for i, a in enumerate(palette.GROUP_COLOURS)
            for b in palette.GROUP_COLOURS[i + 1:]
        )
        self.assertLess(worst, 3.0,
                        "group colours look separable in grayscale; if that ever "
                        "becomes true, revisit this test -- but never rely on it")
        m = build()
        root = ET.fromstring(figures.cross_group_figure(m, "print").render())
        texts = [el.text for el in root.iter(SVG_NS + "text") if el.text]
        for gid in m.group_ids:
            plotted = sum(1 for aid in m.area_ids if m.cell(gid, aid) is not None)
            self.assertGreaterEqual(
                texts.count(gid), plotted,
                f"{gid}: fewer printed codes than plotted marks, so some marks are "
                f"identified by colour alone")

    def test_group_shapes_are_distinct_from_each_other(self):
        self.assertEqual(len(set(palette.GROUP_SHAPES)), len(palette.GROUP_SHAPES))


class TestSvgAccessibilityStructure(unittest.TestCase):
    def test_every_figure_is_wellformed_labelled_and_described(self):
        m = build()
        for name, builder in figures.FIGURES.items():
            for theme in palette.THEMES:
                with self.subTest(figure=name, theme=theme):
                    payload = builder(m, theme).render()
                    root = ET.fromstring(payload)  # raises if malformed
                    self.assertEqual(root.get("role"), "img")
                    labelled = root.get("aria-labelledby")
                    self.assertTrue(labelled)
                    title = root.find(SVG_NS + "title")
                    desc = root.find(SVG_NS + "desc")
                    self.assertIsNotNone(title)
                    self.assertIsNotNone(desc)
                    self.assertIn(title.get("id"), labelled)
                    self.assertIn(desc.get("id"), labelled)
                    self.assertGreater(len(desc.text), 200)

    def test_desc_is_generated_not_hand_written(self):
        """The text alternative and the picture come from one source."""
        m = build()
        for key, builder in figures.FIGURES.items():
            with self.subTest(figure=key):
                root = ET.fromstring(builder(m, "print").render())
                desc = root.find(SVG_NS + "desc").text
                self.assertEqual(desc, alt_text.ALT_BUILDERS[key](m))

    def test_special_characters_are_escaped(self):
        raw = load_raw()
        raw["title"] = 'Risk & "scope" <draft>'
        m = model.Matrix(raw)
        payload = figures.matrix_figure(m, "print").render()
        ET.fromstring(payload)  # would raise on a raw & or <
        self.assertIn("&amp;", payload)
        self.assertIn("&lt;draft&gt;", payload)

    def test_nothing_is_drawn_outside_the_canvas(self):
        """A clipped label is an unreadable label."""
        m = build()
        for name, builder in figures.FIGURES.items():
            for theme in palette.THEMES:
                with self.subTest(figure=name, theme=theme):
                    root = ET.fromstring(builder(m, theme).render())
                    w = float(root.get("width"))
                    h = float(root.get("height"))
                    for el in root.iter(SVG_NS + "text"):
                        x = float(el.get("x", 0))
                        y = float(el.get("y", 0))
                        self.assertTrue(0 <= x <= w and 0 <= y <= h,
                                        f"{name}/{theme}: text at ({x},{y}) outside {w}x{h}")


class TestTextAlternatives(unittest.TestCase):
    def test_mentions_every_group_area_and_band(self):
        m = build()
        text = alt_text.matrix_alt(m)
        for gid in m.group_ids:
            self.assertIn(gid, text)
        for aid in m.area_ids:
            self.assertIn(m.area_label(aid), text)
        self.assertIn("not assessed", text.lower())
        self.assertIn("insufficient evidence", text.lower())

    def test_phrasing_protects_the_unassessed_cells(self):
        m = build()
        text = alt_text.matrix_alt(m)
        self.assertIn("outside the agreed scope", text)
        self.assertIn("not the performance of the group", text)

    def test_counts_in_text_match_the_data(self):
        m = build()
        t = m.totals()
        text = alt_text.matrix_alt(m)
        self.assertIn(f"{t['rated']} cells carry a rating", text)
        self.assertIn(f"{t['not_assessed']} were not assessed", text)

    def test_tables_carry_glyph_and_label_never_colour_alone(self):
        m = build()
        table = alt_text.matrix_markdown(m)
        for key in palette.BAND_ORDER:
            b = palette.BANDS[key]
            if any(c.band_key == key for c in m.cells.values()):
                self.assertIn(b.glyph, table)
                self.assertIn(b.label, table)
        # no hex colour should ever be the carrier of meaning in a table
        self.assertNotIn("#", table.replace("### ", "").replace("## ", ""))

    def test_no_invented_precision_anywhere(self):
        m = build()
        blob = alt_text.alt_text_bundle(m)
        for forbidden in ("out of 5", "out of 10", "score of", "maturity level",
                          "percentile", "/5", "/10"):
            self.assertNotIn(forbidden, blob.lower(), f"invented precision: {forbidden}")

    def test_unknown_effort_is_named_never_guessed(self):
        m = build()
        table = alt_text.roadmap_markdown(m)
        self.assertIn("_not estimated_", table)
        svg_payload = figures.roadmap_figure(m, "print").render()
        self.assertIn("Effort not estimated", svg_payload)
        r4 = [i for i in m.roadmap if i["id"] == "R4"][0]
        self.assertIsNone(r4.get("effort"))
        self.assertIn("effort not estimated", alt_text.roadmap_alt(m).lower())

    def test_fiction_is_labelled_as_fiction_in_every_output(self):
        m = build()
        self.assertIn("SYNTHETIC", m.disclaimer)
        for builder in alt_text.ALT_BUILDERS.values():
            self.assertIn("SYNTHETIC", builder(m))
        for fig_builder in figures.FIGURES.values():
            self.assertIn("SYNTHETIC", fig_builder(m, "print").render())


class TestHostileAndMissingData(unittest.TestCase):
    """Bad input is rejected with a reason. It is never quietly repaired."""

    def _expect_error(self, mutate, fragment):
        raw = copy.deepcopy(load_raw())
        mutate(raw)
        with self.assertRaises(model.DataError) as ctx:
            model.Matrix(raw)
        self.assertIn(fragment, str(ctx.exception))

    def test_rating_without_evidence_is_refused(self):
        def mutate(raw):
            raw["cells"][3]["band"] = "GAP"  # an UNASSESSED cell with no evidence
        self._expect_error(mutate, "is a rating but no evidence was collected")

    def test_unknown_band_is_refused_not_defaulted(self):
        """An invented band name must stop the run, not pick a nearby band."""
        raw = copy.deepcopy(load_raw())
        raw["cells"][0]["band"] = "PARTIALLY_MATURE"
        with self.assertRaises(KeyError) as ctx:
            model.Matrix(raw)
        self.assertIn("PARTIALLY_MATURE", str(ctx.exception))

    def test_blank_band_is_refused(self):
        self._expect_error(lambda raw: raw["cells"][0].update(band="   "),
                           "is empty")

    def test_missing_evidence_collected_flag_is_refused(self):
        def mutate(raw):
            del raw["cells"][0]["evidence_collected"]
        self._expect_error(mutate, "must be true or false")

    def test_collected_false_with_items_is_refused(self):
        def mutate(raw):
            raw["cells"][3]["evidence"] = {"documents": 2}
        self._expect_error(mutate, "One of the two is wrong")

    def test_collected_true_with_no_items_is_refused(self):
        def mutate(raw):
            raw["cells"][0]["evidence"] = {}
        self._expect_error(mutate, "Use evidence_collected=false")

    def test_negative_and_non_integer_evidence_refused(self):
        self._expect_error(lambda raw: raw["cells"][0]["evidence"].update(documents=-1),
                           "cannot be negative")
        self._expect_error(lambda raw: raw["cells"][0]["evidence"].update(documents="four"),
                           "must be a whole number")
        self._expect_error(lambda raw: raw["cells"][0]["evidence"].update(documents=True),
                           "must be a whole number")

    def test_unknown_evidence_kind_refused(self):
        self._expect_error(lambda raw: raw["cells"][0]["evidence"].update(vibes=3),
                           "unknown evidence kind")

    def test_duplicate_cell_refused(self):
        def mutate(raw):
            raw["cells"].append(copy.deepcopy(raw["cells"][0]))
        self._expect_error(mutate, "duplicate cell")

    def test_cell_for_unknown_group_refused(self):
        self._expect_error(lambda raw: raw["cells"][0].update(group="GHOST"),
                           "unknown group")

    def test_dangling_roadmap_dependency_refused(self):
        self._expect_error(lambda raw: raw["roadmap"][2].update(depends_on=["R99"]),
                           "not in this roadmap")

    def test_backwards_roadmap_dependency_refused(self):
        def mutate(raw):
            raw["roadmap"][0]["depends_on"] = ["R5"]  # P1 depending on P3
        self._expect_error(mutate, "scheduled later")

    def test_self_dependency_refused(self):
        self._expect_error(lambda raw: raw["roadmap"][0].update(depends_on=["R1"]),
                           "depends on itself")

    def test_unknown_phase_refused(self):
        with self.assertRaises(KeyError):
            raw = copy.deepcopy(load_raw())
            raw["roadmap"][0]["phase"] = "P9"
            model.Matrix(raw)

    def test_missing_cell_is_reported_never_backfilled(self):
        raw = copy.deepcopy(load_raw())
        # Remove the one real GAP, by lookup rather than by index, so this test
        # keeps testing the same thing when the fixture is edited.
        idx = next(i for i, c in enumerate(raw["cells"])
                   if c["group"] == "RIS" and c["area"] == "SDLC")
        removed = raw["cells"].pop(idx)
        m = model.Matrix(raw)
        self.assertIn((removed["group"], removed["area"]), m.missing)
        self.assertEqual(m.totals()["cells_missing"], 1)
        self.assertEqual(m.totals()["rated"], 6)
        self.assertIsNone(m.cell("RIS", "SDLC"))
        payload = figures.matrix_figure(m, "print").render()
        self.assertIn("no record supplied", payload)
        self.assertIn("no record supplied", alt_text.matrix_alt(m))
        # crucially: it did not become a Gap, a zero, or a pass
        self.assertEqual(m.summarize_group("RIS").band_counts["GAP"], 0)

    def test_group_with_no_cells_renders_without_inventing_any(self):
        raw = copy.deepcopy(load_raw())
        raw["cells"] = [c for c in raw["cells"] if c["group"] != "IAM"]
        m = model.Matrix(raw)
        s = m.summarize_group("IAM")
        self.assertEqual(s.rated, 0)
        self.assertEqual(s.evidence_total, 0)
        payload = figures.evidence_coverage_figure(m, "print").render()
        self.assertIn("no evidence collected", payload)
        ET.fromstring(payload)

    def test_empty_roadmap_is_handled(self):
        raw = copy.deepcopy(load_raw())
        raw["roadmap"] = []
        m = model.Matrix(raw)
        payload = figures.roadmap_figure(m, "print").render()
        ET.fromstring(payload)
        self.assertIn("No roadmap items supplied", alt_text.roadmap_alt(m))

    def test_malformed_json_is_rejected_with_the_path(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                         encoding="utf-8") as fh:
            fh.write("{ not json at all ")
            path = fh.name
        try:
            with self.assertRaises(model.DataError) as ctx:
                model.Matrix.from_json_file(path)
            self.assertIn("not valid JSON", str(ctx.exception))
        finally:
            os.unlink(path)

    def test_unknown_band_lookup_names_the_valid_options(self):
        with self.assertRaises(KeyError) as ctx:
            palette.band("MOSTLY_FINE")
        self.assertIn("STRENGTH", str(ctx.exception))


class TestCliAndReproducibility(unittest.TestCase):
    def test_render_is_byte_identical_across_runs(self):
        """A second operator must get the same files, or a diff means nothing."""
        m = build()
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            a = cli.render_all(m, d1, ["print", "screen"])
            b = cli.render_all(build(), d2, ["print", "screen"])
            self.assertEqual(a, b)
            self.assertGreaterEqual(len(a), 13)
            for name, _ in a:
                with open(os.path.join(d1, name), "rb") as f1, \
                     open(os.path.join(d2, name), "rb") as f2:
                    self.assertEqual(f1.read(), f2.read(), name)

    def test_cli_audit_exits_clean(self):
        self.assertEqual(cli.main(["--audit"]), 0)

    def test_cli_encoding_check_exits_clean(self):
        self.assertEqual(cli.main(["--check-encoding"]), 0)

    def test_cli_rejects_bad_data_with_exit_code_2(self):
        with tempfile.TemporaryDirectory() as d:
            bad = os.path.join(d, "bad.json")
            with open(bad, "w", encoding="utf-8") as fh:
                json.dump({"title": "x"}, fh)
            self.assertEqual(cli.main(["--data", bad, "--out", d]), 2)

    def test_cli_reports_missing_file(self):
        self.assertEqual(cli.main(["--data", "/nonexistent/nope.json", "--out", "/tmp"]), 2)

    def test_full_render_produces_every_artifact(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(cli.main(["--data", FIXTURE, "--out", d]), 0)
            for expected in ("matrix.print.svg", "matrix.screen.svg",
                             "cross-group.print.svg", "evidence-coverage.print.svg",
                             "roadmap.print.svg", "text-alternatives.md",
                             "matrix-table.md", "contrast-audit.txt", "manifest.json"):
                self.assertTrue(os.path.exists(os.path.join(d, expected)), expected)
            with open(os.path.join(d, "manifest.json"), encoding="utf-8") as fh:
                manifest = json.load(fh)
            self.assertIn("SYNTHETIC", manifest["disclaimer"])
            self.assertEqual(manifest["totals"]["not_assessed"], 1)
            self.assertEqual(manifest["totals"]["contradictory"], 1)

    def test_unknown_theme_is_refused(self):
        with self.assertRaises(KeyError):
            figures.matrix_figure(build(), "neon")


class TestZeroIsNotMissing(unittest.TestCase):
    """UIOWA-126: a measured zero is a value; an omission is not.

    The failure this guards against: a count of zero drawn as an empty bar is
    indistinguishable from "we never recorded this", so a real finding ("zero
    unresolved items") is filed as a hole in the evidence.
    """

    def test_omitted_and_zero_parse_to_different_things(self):
        raw = copy.deepcopy(load_raw())
        cell = next(c for c in raw["cells"] if c["group"] == "ESS" and c["area"] == "SEC")
        cell["evidence"] = {"documents": 3, "interviews": 2, "system_records": 0}
        m = model.Matrix(raw)
        c = m.cell("ESS", "SEC")
        self.assertEqual(c.evidence["system_records"], 0)
        self.assertEqual(c.evidence["observed"], palette.NOT_RECORDED)
        self.assertIn("system_records", c.measured_zero_kinds)
        self.assertIn("observed", c.not_recorded_kinds)
        self.assertNotIn("observed", c.measured_zero_kinds)

    def test_not_recorded_never_becomes_a_zero_in_a_total(self):
        """Two groups, same evidence kind, same total of 0 -- different facts.

        RIS never recorded observed artifacts. IAM did the walkthrough and
        found none. Both totals are 0; only one of them is a measurement.
        """
        m = build()
        ris = m.summarize_group("RIS")
        iam = m.summarize_group("IAM")
        self.assertEqual(ris.evidence["observed"], 0)
        self.assertEqual(iam.evidence["observed"], 0)
        self.assertFalse(ris.recorded["observed"], "an omission was treated as recorded")
        self.assertTrue(iam.recorded["observed"], "a measurement was treated as missing")
        # The omission is excluded from the total; the measured zero adds zero.
        self.assertEqual(ris.evidence_total, sum(
            v for cell in m.cells.values() if cell.group == "RIS"
            for v in cell.evidence.values() if isinstance(v, int)))

    def test_partial_recording_is_stated_not_hidden(self):
        """A group total built from only some areas says so."""
        ess = build().summarize_group("ESS")
        self.assertTrue(ess.recorded["observed"])
        self.assertEqual(ess.missing_counts["observed"], 1)
        self.assertIn("counts incomplete for observed artifacts", ess.coverage_sentence)

    def test_the_two_states_use_different_borders(self):
        zero = palette.VALUE_STATES["MEASURED_ZERO"]
        missing = palette.VALUE_STATES["NOT_RECORDED"]
        self.assertNotEqual(zero["border"], missing["border"])
        self.assertEqual(zero["border"], "solid", "a value we have wears the solid border")
        self.assertEqual(missing["border"], "dashed")

    def test_coverage_chart_draws_both_states_instead_of_nothing(self):
        payload = figures.evidence_coverage_figure(build(), "print").render()
        self.assertIn("not recorded", payload, "an omission vanished from the chart")
        self.assertIn("Obs 0", payload, "a measured zero vanished from the chart")
        # and they are not drawn the same way
        self.assertIn('stroke-dasharray="5 3"', payload)

    def test_tables_and_alt_text_say_not_recorded_in_words(self):
        m = build()
        self.assertIn("_not recorded_", alt_text.coverage_markdown(m))
        text = alt_text.evidence_alt(m)
        self.assertIn("observed artifacts not recorded", text)   # RIS
        self.assertIn("observed artifacts 0", text)              # IAM, a measured zero

    def test_negative_still_refused_but_zero_accepted(self):
        raw = copy.deepcopy(load_raw())
        cell = next(c for c in raw["cells"] if c["group"] == "ESS" and c["area"] == "SDLC")
        cell["evidence"] = {"documents": 0, "interviews": 3}
        model.Matrix(raw)  # zero is legal
        cell["evidence"] = {"documents": -1, "interviews": 3}
        with self.assertRaises(model.DataError):
            model.Matrix(raw)


class TestNotApplicableIsNotNotAssessed(unittest.TestCase):
    """A fact about the group's context vs a fact about our evidence."""

    def test_they_are_different_bands_with_different_channels(self):
        na = palette.BANDS["NOT_APPLICABLE"]
        ua = palette.BANDS["UNASSESSED"]
        for attr in ("label", "glyph", "shape", "texture", "fill", "meaning"):
            self.assertNotEqual(getattr(na, attr), getattr(ua, attr), attr)

    def test_neither_is_a_rating(self):
        for key in ("NOT_APPLICABLE", "UNASSESSED"):
            self.assertIsNone(palette.BANDS[key].rank)
            self.assertFalse(palette.BANDS[key].on_scale)

    def test_not_applicable_with_evidence_is_refused(self):
        raw = copy.deepcopy(load_raw())
        cell = next(c for c in raw["cells"] if c["band"] == "NOT_APPLICABLE")
        cell["evidence_collected"] = True
        cell["evidence"] = {"documents": 2}
        with self.assertRaises(model.DataError) as ctx:
            model.Matrix(raw)
        self.assertIn("nothing to collect", str(ctx.exception))

    def test_wording_never_implies_a_shortfall(self):
        m = build()
        text = alt_text.matrix_alt(m)
        self.assertIn("does not apply to how this group operates", text)
        self.assertIn("nothing is missing", text.lower())

    def test_counted_separately_from_not_assessed(self):
        t = build().totals()
        self.assertEqual(t["not_applicable"], 1)
        self.assertEqual(t["not_assessed"], 1)
        iam = build().summarize_group("IAM")
        self.assertEqual(iam.not_applicable, 1)
        self.assertEqual(iam.unassessed, 0)


class TestContradictoryEvidence(unittest.TestCase):
    """Two sources disagreeing is information, not an absence."""

    def test_both_readings_are_retained(self):
        m = build()
        cell = m.cell("RIS", "SEC")
        self.assertEqual(cell.band_key, "CONTRADICTORY")
        self.assertEqual(len(cell.conflict), 2)
        payload = figures.matrix_figure(m, "print").render()
        for reading in cell.conflict:
            self.assertIn(reading["source"][:20], payload,
                          "a reading was dropped from the figure")
        text = alt_text.matrix_alt(m)
        for reading in cell.conflict:
            self.assertIn(reading["says"][:24], text)

    def test_it_is_not_averaged_into_a_middle_rating(self):
        m = build()
        self.assertIsNone(palette.BANDS["CONTRADICTORY"].rank)
        self.assertEqual(m.summarize_group("RIS").band_counts["DEVELOPING"], 0)
        self.assertEqual(m.summarize_group("RIS").contradictory, 1)
        self.assertNotIn("CONTRADICTORY", palette.ORDINAL_KEYS)

    def test_a_single_reading_is_not_a_conflict(self):
        raw = copy.deepcopy(load_raw())
        cell = next(c for c in raw["cells"] if c["band"] == "CONTRADICTORY")
        cell["conflict"] = [cell["conflict"][0]]
        with self.assertRaises(model.DataError) as ctx:
            model.Matrix(raw)
        self.assertIn("at least two readings", str(ctx.exception))

    def test_a_reading_without_a_source_is_refused(self):
        raw = copy.deepcopy(load_raw())
        cell = next(c for c in raw["cells"] if c["band"] == "CONTRADICTORY")
        del cell["conflict"][0]["source"]
        with self.assertRaises(model.DataError) as ctx:
            model.Matrix(raw)
        self.assertIn("source", str(ctx.exception))

    def test_a_conflict_cannot_be_hidden_under_a_rating(self):
        """Attaching a conflict to a rating would resolve it silently."""
        raw = copy.deepcopy(load_raw())
        target = next(c for c in raw["cells"] if c["band"] == "ESTABLISHED")
        target["conflict"] = [{"source": "A", "says": "x"}, {"source": "B", "says": "y"}]
        with self.assertRaises(model.DataError) as ctx:
            model.Matrix(raw)
        self.assertIn("both readings stay on the page", str(ctx.exception))

    def test_it_gets_the_only_double_border(self):
        doubles = [k for k in palette.BAND_ORDER if palette.BANDS[k].border == "double"]
        self.assertEqual(doubles, ["CONTRADICTORY"])

    def test_the_conflict_stripe_survives_monochrome(self):
        b = palette.BANDS["CONTRADICTORY"]
        self.assertGreaterEqual(
            round(contrast.grayscale_contrast(b.texture_ink, b.fill), 2), 3.0,
            "the conflict texture disappears in black and white")


class TestMonochromeExport(unittest.TestCase):
    """'Works in monochrome' is proved by removing the colour, not asserted."""

    def test_conversion_actually_removes_all_hue(self):
        m = build()
        for key, builder in figures.FIGURES.items():
            with self.subTest(figure=key):
                colour = builder(m, "print").render()
                mono = monochrome.to_monochrome(colour)
                self.assertFalse(monochrome.is_monochrome(colour),
                                 "the colour version had no colour to begin with")
                self.assertTrue(monochrome.is_monochrome(mono))
                ET.fromstring(mono)  # still a valid document afterwards

    def test_monochrome_keeps_every_word(self):
        """Colour goes, content stays."""
        m = build()
        colour = figures.matrix_figure(m, "print").render()
        mono = monochrome.to_monochrome(colour)
        c_text = [el.text for el in ET.fromstring(colour).iter(SVG_NS + "text")]
        m_text = [el.text for el in ET.fromstring(mono).iter(SVG_NS + "text")]
        self.assertEqual(c_text, m_text)

    def test_texture_and_border_survive_the_conversion(self):
        mono = monochrome.to_monochrome(figures.matrix_figure(build(), "print").render())
        self.assertIn("matrix-tex-UNASSESSED", mono)
        self.assertIn("matrix-tex-CONTRADICTORY", mono)
        self.assertIn("stroke-dasharray", mono)

    def test_every_unrated_state_stays_apart_from_every_rating_in_mono(self):
        fills = {k: palette.BANDS[k].fill for k in palette.BAND_ORDER}
        for nr in palette.NON_RATING_KEYS:
            for rating in palette.ORDINAL_KEYS:
                with self.subTest(pair=f"{nr}/{rating}"):
                    self.assertGreaterEqual(
                        round(contrast.grayscale_contrast(fills[nr], fills[rating]), 2), 3.0)

    def test_no_rating_is_ever_the_closest_thing_to_an_unrated_state(self):
        """Eight fills cannot all sit 3:1 apart -- the luminance range does not
        contain that many steps. So the question is not "is every pair far
        apart" (it cannot be) but "is any RATING confusable with a NON-RATING".
        That one must never happen, and it is what this asserts.
        """
        fills = {k: palette.BANDS[k].fill for k in palette.BAND_ORDER}
        close = [(a, b, r) for a, b, r in monochrome.separation_report(fills) if r < 3.0]
        self.assertTrue(close, "expected some pairs to be close; see the docstring")
        for a, b, ratio in close:
            mixed = (a in palette.ORDINAL_KEYS) != (b in palette.ORDINAL_KEYS)
            self.assertFalse(mixed,
                             f"{a} and {b} are only {ratio:.2f}:1 apart in monochrome and one "
                             f"of them is a rating -- an unrated cell could be read as a score")

    def test_every_close_pair_is_separated_by_three_other_channels(self):
        """Where fill luminance cannot separate two states, everything else must."""
        fills = {k: palette.BANDS[k].fill for k in palette.BAND_ORDER}
        for a, b, ratio in monochrome.separation_report(fills):
            if ratio >= 3.0:
                continue
            ba, bb = palette.BANDS[a], palette.BANDS[b]
            for channel in ("texture", "shape", "label", "glyph"):
                self.assertNotEqual(
                    getattr(ba, channel), getattr(bb, channel),
                    f"{a} and {b} are {ratio:.2f}:1 apart in monochrome and share "
                    f"their {channel}; nothing would tell them apart in print")


class TestStatesComparisonFixture(unittest.TestCase):
    """The compact comparison fixture UIOWA-126 asks for."""

    def test_it_shows_every_state(self):
        payload = figures.states_figure(None, "print").render()
        for key in palette.BAND_ORDER:
            self.assertIn(palette.BANDS[key].label, payload, key)
        for state in palette.VALUE_STATES.values():
            self.assertIn(state["long_label"], payload)
        self.assertIn("No record supplied", payload)

    def test_it_says_how_each_state_is_counted(self):
        payload = figures.states_figure(None, "print").render()
        self.assertIn("counted as a rating", payload)
        self.assertIn("excluded from every rating count", payload)
        self.assertIn("counted as the value 0", payload)
        self.assertIn("never summed as 0", payload)

    def test_it_needs_no_data_and_carries_no_university_claim(self):
        payload = figures.states_figure().render()
        self.assertIn("No University data appears in this figure", payload)
        self.assertIn("SYNTHETIC", payload)

    def test_its_row_count_matches_the_vocabulary(self):
        """If a band is added and the fixture is not updated, this fails."""
        band_rows = [r for r in figures.STATE_ROWS if r[0] == "band"]
        self.assertEqual([r[1] for r in band_rows], list(palette.BAND_ORDER))
        value_rows = [r for r in figures.STATE_ROWS if r[0] == "value"]
        self.assertEqual([r[1] for r in value_rows], list(palette.VALUE_STATES))

    def test_alt_text_covers_the_whole_vocabulary(self):
        text = alt_text.states_alt()
        for key in palette.BAND_ORDER:
            self.assertIn(palette.BANDS[key].label, text)
        self.assertIn("never summed", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
