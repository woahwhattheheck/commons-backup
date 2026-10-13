"""Native fixture regressions: visible text, layout and assessment meaning.

Uses the real package model, palette, alt-text functions and retained fixture.
No substitute implementation or fake data-model module is installed.
"""
import copy
import json
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

import alt_text
import check_rendered_text
import figures
import model
import palette

HERE = Path(__file__).resolve().parent
NS = "{http://www.w3.org/2000/svg}"


def build():
    return model.Matrix.from_json_file(str(HERE / "fixtures" / "synthetic_assessment.json"))


def blocks(figure):
    root = ET.fromstring(figure.render())
    return root, [node for node in root.iter() if node.get("data-text-layout") == "full"]


class NativeFigureLayoutTests(unittest.TestCase):
    def assertVisible(self, figure, source):
        root, groups = blocks(figure)
        matches = [node for node in groups if node.get("data-source-text") == source]
        self.assertTrue(matches, f"no complete visible block for {source!r}")
        for node in matches:
            visible = "".join("".join(child.itertext()) for child in node.findall(NS + "text"))
            self.assertEqual(visible, source.replace("\r\n", "\n").replace("\r", "\n").replace("\n", ""))

    def assertLayout(self, figure):
        root, groups = blocks(figure)
        self.assertGreater(len(groups), 0)
        rectangles = []
        for node in groups:
            x, y, width, height = (float(node.get("data-layout-" + key))
                                    for key in ("x", "y", "width", "height"))
            self.assertGreaterEqual(x, 0)
            self.assertGreaterEqual(y, 0)
            self.assertLessEqual(x + width, figure.width + 0.01)
            self.assertLessEqual(y + height, figure.height + 0.01)
            rectangles.append((x, y, width, height, node.get("data-source-text")))
        for index, a in enumerate(rectangles):
            for b in rectangles[index + 1:]:
                overlap_x = min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])
                overlap_y = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
                self.assertFalse(overlap_x > 0.01 and overlap_y > 0.01,
                                 f"text layout overlap: {a[4]!r} / {b[4]!r}")

    def test_every_original_figure_and_theme_has_complete_visible_blocks(self):
        matrix = build()
        for theme in palette.THEMES:
            for name, make in figures.FIGURES.items():
                with self.subTest(theme=theme, figure=name):
                    figure = make(matrix, theme)
                    root, groups = blocks(figure)
                    for node in groups:
                        self.assertVisible(figure, node.get("data-source-text"))
                    self.assertLayout(figure)

    def test_full_group_context_and_label_survive_matrix(self):
        matrix = build()
        matrix.groups[0]["label"] = "Enterprise Shared Services with a deliberately complete organizational label"
        matrix.groups[0]["context"] = "Central team, approximately forty staff, shared services and independently funded delivery obligations."
        figure = figures.matrix_figure(matrix)
        self.assertVisible(figure, matrix.groups[0]["label"])
        self.assertVisible(figure, matrix.groups[0]["context"])
        self.assertLayout(figure)

    def test_all_three_conflict_readings_survive_without_reconciliation(self):
        matrix = build()
        cell = next(cell for cell in matrix.cells.values() if cell.conflict)
        cell.conflict = [
            {"source": "Long written record from the service owner", "says": "The approval procedure is documented but its most recent execution remains unverified."},
            {"source": "Independent interview with the operational team", "says": "The current procedure differs from the retained documentation and requires a follow-up."},
            {"source": "Third retained observation", "says": "This additional reading must remain on the page rather than being silently discarded."},
        ]
        before = copy.deepcopy(matrix.totals())
        figure = figures.matrix_figure(matrix)
        for reading in cell.conflict:
            self.assertVisible(figure, f"{reading['source']}: {reading['says']}")
        self.assertEqual(matrix.totals(), before)
        self.assertLayout(figure)

    def test_roadmap_retains_title_beyond_eighty_characters(self):
        matrix = build()
        title = "Rehearse the complete recovery sequence with the service owner, independent evidence review, explicit rollback responsibilities, and unresolved access prerequisites."
        matrix.roadmap[0]["title"] = title
        figure = figures.roadmap_figure(matrix)
        self.assertVisible(figure, title)
        self.assertLayout(figure)

    def test_long_recommendation_effort_and_dependencies_have_separate_rows(self):
        matrix = build()
        item = next(item for item in matrix.roadmap if item.get("depends_on"))
        item["recommendation"] = "REC-LONG-REFERENCE-RETAINED-WITHOUT-SILENT-TRUNCATION"
        item["effort"] = "Unknown until the service owner reviews access, timing, and dependencies"
        figure = figures.roadmap_figure(matrix)
        self.assertVisible(figure, "from " + item["recommendation"])
        self.assertVisible(figure, "Effort: " + item["effort"])
        self.assertVisible(figure, "after " + ", ".join(item["depends_on"]))
        self.assertLayout(figure)

    def test_state_meanings_and_not_a_rating_qualifiers_are_complete(self):
        figure = figures.states_figure()
        for band in palette.BANDS.values():
            self.assertVisible(figure, band.meaning + (" Not a rating." if not band.on_scale else ""))
        self.assertLayout(figure)

    def test_long_headers_and_subtitles_grow_the_canvas(self):
        matrix = build()
        matrix.title = "Synthetic report covering a deliberately long title and every retained scope qualification " * 3
        matrix.subtitle = "Evidence is fictional and the actual University situation is unknown. " * 4
        for name, make in figures.FIGURES.items():
            with self.subTest(figure=name):
                figure = make(matrix)
                self.assertLayout(figure)

    def test_non_ratings_remain_excluded_from_ratings(self):
        matrix = build()
        before = copy.deepcopy(matrix.totals())
        for make in figures.FIGURES.values():
            make(matrix).render()
        self.assertEqual(matrix.totals(), before)
        self.assertEqual(before["rated"], 7)
        self.assertEqual(before["cells_expected"], 12)

    def test_all_text_alternatives_are_the_original_generators(self):
        matrix = build()
        pairs = ((figures.matrix_figure, alt_text.matrix_alt),
                 (figures.cross_group_figure, alt_text.cross_group_alt),
                 (figures.evidence_coverage_figure, alt_text.evidence_alt),
                 (figures.roadmap_figure, alt_text.roadmap_alt))
        for make, describe in pairs:
            self.assertEqual(make(matrix).description, describe(matrix))
        self.assertEqual(figures.states_figure().description, alt_text.states_alt())

    def test_native_fixture_rerenders_byte_identically(self):
        matrix = build()
        for theme in palette.THEMES:
            for make in figures.FIGURES.values():
                self.assertEqual(make(matrix, theme).render(), make(matrix, theme).render())

    def test_semantic_detector_reports_no_native_truncation(self):
        matrix = build()
        for theme in palette.THEMES:
            for name, make in figures.FIGURES.items():
                with self.subTest(theme=theme, figure=name):
                    self.assertEqual(check_rendered_text.truncated_texts(make(matrix, theme).render()), [])

    def test_empty_roadmap_is_an_explicit_empty_plan(self):
        matrix = build()
        matrix.roadmap = []
        figure = figures.roadmap_figure(matrix)
        self.assertLayout(figure)
        self.assertEqual(matrix.roadmap, [])


if __name__ == "__main__":
    unittest.main()
