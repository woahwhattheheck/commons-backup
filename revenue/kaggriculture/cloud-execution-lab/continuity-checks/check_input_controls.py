# SPDX-License-Identifier: Apache-2.0
"""Input-boundary controls for check_frozen_continuity; no actor execution."""
import copy
import gzip
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
import check_frozen_continuity as C

ARCHIVE = None


class Overlay:
    def __init__(self, changes):
        self.changes = changes

    def read(self, name):
        return self.changes[name] if name in self.changes else ARCHIVE.read(name)


def altered(suffix, edit):
    cell = C.CELLS[0]
    name = cell + suffix
    report = json.loads(ARCHIVE.read(cell + '.json'))
    rows = [json.loads(line) for line in gzip.decompress(ARCHIVE.read(name)).splitlines()]
    edit(rows)
    raw = gzip.compress(b'\n'.join(C.encode(row) for row in rows) + b'\n', mtime=0)
    report['files'][Path(name).name] = {'bytes': len(raw), 'sha256': C.sha(raw)}
    return Overlay({name: raw, cell + '.json': C.encode(report)})


class ContinuityInputTests(unittest.TestCase):
    def require_rejection(self, view, text):
        with self.assertRaisesRegex(ValueError, text):
            C.own_inputs(view, C.CELLS[0])

    def test_original_complete_stream(self):
        packets, result = C.own_inputs(ARCHIVE, C.CELLS[0])
        self.assertEqual(len(packets), 719)
        self.assertEqual(packets[0]['observation']['step'], 0)
        self.assertEqual(packets[-1]['observation']['step'], 718)
        self.assertEqual(result['candidate_seat'], 0)

    def test_digest_mismatch(self):
        name = C.CELLS[0] + '.frames.jsonl.gz'
        self.require_rejection(Overlay({name: ARCHIVE.read(name) + b'x'}), 'hash/size')

    def test_missing_row(self):
        self.require_rejection(altered('.frames.jsonl.gz', lambda rows: rows.pop()), 'complete 0..718')

    def test_reordered_frames(self):
        def edit(rows):
            rows[10], rows[11] = rows[11], rows[10]
        self.require_rejection(altered('.frames.jsonl.gz', edit), 'order mismatch')

    def test_wrong_telemetry_clock(self):
        self.require_rejection(altered('.telemetry.jsonl.gz', lambda rows: rows[10].update(step=11)), 'order mismatch')

    def test_changed_own_action(self):
        self.require_rejection(altered('.telemetry.jsonl.gz', lambda rows: rows[10]['action'].update(farmer=['WRONG'])), 'action mismatch')

    def test_wrong_player(self):
        self.require_rejection(altered('.frames.jsonl.gz', lambda rows: rows[10]['state'][0]['observation'].update(player=1)), 'player or clock')

    def test_wrong_public_clock(self):
        self.require_rejection(altered('.frames.jsonl.gz', lambda rows: rows[10]['state'][0]['observation'].update(hour=11)), 'player or clock')

    def test_wrong_terminal_identity(self):
        self.require_rejection(altered('.frames.jsonl.gz', lambda rows: rows[-1]['state'][0].update(reward=-1)), 'terminal identity')

    def test_uncompleted_result(self):
        name = C.CELLS[0] + '.json'
        report = json.loads(ARCHIVE.read(name)); report['status'] = 'interrupted'
        self.require_rejection(Overlay({name: C.encode(report)}), 'completed retained SELL')

    def test_rival_private_and_current_action_are_not_actor_inputs(self):
        def edit(rows):
            for row in rows:
                row['state'][1]['observation']['private'] = {'not_actor_input': True}
                row['state'][1]['action'] = {'not_actor_input': True}
        expected, _ = C.own_inputs(ARCHIVE, C.CELLS[0])
        actual, _ = C.own_inputs(altered('.frames.jsonl.gz', edit), C.CELLS[0])
        self.assertEqual(actual, expected)

    def test_source_pin_changes_fail(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); (root / 'a.py').write_bytes(b'original\n')
            pins = {'a.py': C.sha(b'original\n')}
            self.assertEqual(C.source_map(root, pins)['a.py']['bytes'], 9)
            (root / 'a.py').write_bytes(b'changed\n')
            with self.assertRaisesRegex(ValueError, 'source mismatch'):
                C.source_map(root, pins)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--delve-archive', type=Path, required=True)
    args = parser.parse_args()
    if C.sha(args.delve_archive.read_bytes()) != C.DELVE_SHA256:
        raise ValueError('wrong retained archive')
    with zipfile.ZipFile(args.delve_archive) as source:
        ARCHIVE = source
        result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ContinuityInputTests))
    raise SystemExit(not result.wasSuccessful())
