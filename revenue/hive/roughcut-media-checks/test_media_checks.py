"""Real FFmpeg fixtures and renders. No mocks or external network."""
import json
import tempfile
import unittest
from pathlib import Path

import media_checks as m


def render_reference(source, destination, keep):
    filters, inputs = [], []
    for i, (start, end) in enumerate(keep):
        filters.append(f'[0:v]trim=start={start}:end={end},setpts=PTS-{start}/TB[v{i}]')
        filters.append(f'[0:a]atrim=start={start}:end={end},asetpts=PTS-{start}/TB[a{i}]')
        inputs.append(f'[v{i}][a{i}]')
    filters.append(''.join(inputs) + f'concat=n={len(keep)}:v=1:a=1[v][a]')
    m.command(['ffmpeg','-nostdin','-v','error','-y','-i',str(source),'-filter_complex_threads','1','-filter_complex',';'.join(filters),'-map','[v]','-map','[a]','-c:v','libx264','-threads','1','-c:a','aac',str(destination)])


class MediaChecksTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.source = cls.root / 'source.mp4'
        cls.manifest = m.generate(cls.source, seconds=6, fps=25, first=1, period=2, pulse=.12)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_original_pulses_measured_from_pixels_and_audio(self):
        result = m.verify(self.source, self.source, self.manifest, [[0, 6]])
        self.assertTrue(result['passed'], result)
        self.assertEqual(result['expected']['expected_markers'], [1, 3, 5])
        self.assertEqual(len(result['observed_markers']['video']), 3)
        self.assertEqual(len(result['observed_markers']['audio']), 3)

    def test_cut_maps_later_pulses_and_preserves_source(self):
        output = self.root / 'edited.mp4'
        keep = [[0, 1.5], [2.5, 6]]
        render_reference(self.source, output, keep)
        result = m.verify(self.source, output, self.manifest, keep)
        self.assertTrue(result['passed'], result)
        self.assertEqual(result['expected']['expected_markers'], [1, 2, 4])
        self.assertEqual(m.sha256(self.source), self.manifest['source_sha256'])

    def test_restored_render_measures_original_marker_times(self):
        output = self.root / 'restored.mp4'
        render_reference(self.source, output, [[0, 6]])
        self.assertTrue(m.verify(self.source, output, self.manifest, [[0, 6]])['passed'])

    def test_real_audio_delay_is_detected(self):
        output = self.root / 'delayed.mp4'
        m.command(['ffmpeg','-nostdin','-v','error','-y','-i',str(self.source),'-af','adelay=300:all=1','-c:v','copy','-c:a','aac','-t','6',str(output)])
        result = m.verify(self.source, output, self.manifest, [[0, 6]])
        self.assertFalse(result['passed'])
        self.assertTrue(result['checks']['marker_counts_match'])
        self.assertFalse(result['checks']['av_alignment'])
        self.assertTrue(all(.25 < delta < .35 for delta in result['audio_minus_video_seconds']))

    def test_wrong_render_cannot_pass_on_duration_only(self):
        output = self.root / 'wrong-cut.mp4'
        render_reference(self.source, output, [[0, 1.5], [2.5, 6]])
        # Same 5s duration, but the declared cut is after the second marker.
        result = m.verify(self.source, output, self.manifest, [[0, 3.5], [4.5, 6]])
        self.assertTrue(result['checks']['duration'])
        self.assertTrue(result['checks']['marker_counts_match'])
        self.assertFalse(result['passed'])
        self.assertFalse(result['checks']['video_timing'])

    def test_source_change_cannot_pass(self):
        bad = self.root / 'changed.mp4'
        bad.write_bytes(self.source.read_bytes() + b'changed')
        result = m.verify(bad, self.source, self.manifest, [[0, 6]])
        self.assertFalse(result['passed'])
        self.assertFalse(result['source_unchanged'])

    def test_generator_omits_incomplete_final_pulse(self):
        source = self.root / 'partial-end.mp4'
        manifest = m.generate(source, seconds=3.05, fps=25, first=1, period=2, pulse=.12)
        self.assertEqual(manifest['source_markers'], [1])
        self.assertTrue(m.verify(source, source, manifest, [[0, 3.05]])['passed'])

    def test_source_and_manifest_are_not_overwritten(self):
        before = self.source.read_bytes()
        with self.assertRaises(m.MediaCheckError):
            m.generate(self.source, seconds=6, first=1, period=2, pulse=.12)
        self.assertEqual(self.source.read_bytes(), before)

    def test_invalid_ranges_and_types(self):
        for keep in [[], [[0, 7]], [[3, 2]], [[0, True]], [[0, float('inf')]], [[0, 2], [1, 3]], [None], '0:6']:
            with self.subTest(keep=keep), self.assertRaises(m.MediaCheckError):
                m.plan(self.manifest, keep)

    def test_partial_marker_is_unsuitable_test_plan(self):
        for keep in [[[0, 1.05], [2, 6]], [[1.05, 6]], [[0, .5]]]:
            with self.subTest(keep=keep), self.assertRaises(m.MediaCheckError):
                m.plan(self.manifest, keep)

    def test_malformed_manifest(self):
        for key, value in [('schema', 'unknown'), ('synthetic', False), ('fps', 0), ('duration', float('nan')), ('source_markers', [3, 1]), ('source_markers', [True])]:
            manifest = {**self.manifest, key:value}
            with self.subTest(key=key), self.assertRaises(m.MediaCheckError):
                m.plan(manifest, [[0, 6]])

    def test_cli_writes_actual_report_and_failure_exit(self):
        keep_path = self.root / 'keep.json'
        keep_path.write_text('[[0, 6]]')
        report_path = self.root / 'report.json'
        manifest_path = self.source.with_suffix('.mp4.fixture.json')
        args = ['verify', str(self.source), str(self.source), '--manifest', str(manifest_path), '--keep', str(keep_path), '--report', str(report_path)]
        self.assertEqual(m.main(args), 0)
        self.assertTrue(json.loads(report_path.read_text())['passed'])
        keep_path.write_text('[[0, 1.5], [2.5, 6]]')
        self.assertEqual(m.main(args), 1)
        self.assertFalse(json.loads(report_path.read_text())['passed'])
        keep_path.write_text('not json')
        self.assertEqual(m.main(args), 2)


if __name__ == '__main__':
    unittest.main()
