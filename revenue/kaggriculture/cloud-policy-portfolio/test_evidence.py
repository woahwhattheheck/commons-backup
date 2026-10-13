# SPDX-License-Identifier: Apache-2.0
import copy
import gzip
import json
from pathlib import Path
import tempfile
import unittest
from evidence import apply, changes, pack, unpack


class EvidenceTests(unittest.TestCase):
    def test_nested_deletion_types_and_arrays(self):
        before = {'removed': 7, 'items': [1, {'x': True}], 'a': []}
        after = {'items': [None, {'x': 1}], 'a': [3], 'new': {}}
        self.assertEqual(apply(copy.deepcopy(before), changes(before, after)), after)
        self.assertIs(type(apply(True, changes(True, 1))), int)

    def test_round_trip_and_identical_stream_deduplication(self):
        rows = [{'step': 0, 'private': {'seeds': {'WHEAT': 1}}},
                {'step': 1, 'private': {'seeds': {}}, 'action': []}]
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            inputs = root / 'input'
            inputs.mkdir()
            for name in ('a', 'b'):
                with gzip.open(inputs / (name + '.jsonl.gz'), 'wt') as f:
                    for row in rows:
                        f.write(json.dumps(row) + '\n')
            receipt = pack(inputs, root / 'evidence.xz')
            self.assertEqual((receipt['files'], receipt['unique_streams']), (2, 1))
            self.assertEqual(unpack(root / 'evidence.xz', root / 'output'), 2)
            for name in ('a', 'b'):
                self.assertEqual([json.loads(x) for x in (root / 'output' / (name + '.jsonl')).read_text().splitlines()], rows)
            with self.assertRaises(ValueError):
                unpack(root / 'evidence.xz', root / 'output')


if __name__ == '__main__':
    unittest.main()
