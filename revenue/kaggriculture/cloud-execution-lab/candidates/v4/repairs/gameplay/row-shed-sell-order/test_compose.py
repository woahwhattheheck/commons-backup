# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import compose

RUNTIME_ROOT = (Path(os.environ['TITAN_V4_TEST_RUNTIME']) if 'TITAN_V4_TEST_RUNTIME' in os.environ else HERE.parents[4])
BASE = RUNTIME_ROOT / 'frozen_selected.py'
BASE_BLOB = 'fc7baf5c179818a55037f6a61d92984d81d1a21c'


def blob(data: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


class ComposeTests(unittest.TestCase):
    def test_source_pin_matches_canonical_donor(self):
        data=(HERE/'row_shed_sell_order.py').read_bytes()
        self.assertEqual(blob(data), compose.ROW_SHED_SOURCE_BLOB)
        self.assertEqual(hashlib.sha256(data).hexdigest(), compose.ROW_SHED_SOURCE_SHA256)

    def test_current_method_pin_and_rewrite_order(self):
        source=BASE.read_text()
        start,end,method=compose._method_span(source)
        self.assertEqual(hashlib.sha256(method.encode()).hexdigest(), compose.METHOD_BEFORE_SHA256)
        changed=compose.compose_frozen(source)
        _,_,out_method=compose._method_span(changed)
        self.assertEqual(hashlib.sha256(out_method.encode()).hexdigest(), compose.METHOD_AFTER_SHA256)
        self.assertEqual(changed.count(compose.IMPORT_LINE), 1)
        self.assertLess(out_method.index('farm,private=post_units(obs,base,config)'),
                        out_method.index('row_shed.transform('))
        self.assertLess(out_method.index('row_shed.transform('),
                        out_method.index("baseline_q={}"))
        compile(changed, 'frozen_selected.py', 'exec')

    def test_rewrite_preserves_bytes_outside_import_and_transform(self):
        source=BASE.read_text()
        changed=compose.compose_frozen(source)
        before=source.replace(compose.IMPORT_ANCHOR, '', 1)
        after=changed.replace(compose.IMPORT_ANCHOR + compose.IMPORT_LINE, '', 1)
        bs,be,bm=compose._method_span(before)
        aas,aae,am=compose._method_span(after)
        self.assertEqual(before[:bs], after[:aas])
        self.assertEqual(before[be:], after[aae:])
        self.assertNotEqual(bm, am)

    def test_partial_or_method_drift_fails_closed(self):
        source=BASE.read_text()
        with self.assertRaises(ValueError):
            compose.compose_frozen(source.replace(
                compose.IMPORT_ANCHOR, compose.IMPORT_ANCHOR + compose.IMPORT_LINE, 1))
        with self.assertRaises(ValueError):
            compose.compose_frozen(source.replace('        self.observe(obs)\n',
                                                  '        self.observe(obs)  # drift\n',1))

    def test_cli_default_rejects_uncomposed_foundation(self):
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)/'out'
            proc=subprocess.run([
                sys.executable, str(HERE/'compose.py'), '--package', str(RUNTIME_ROOT),
                '--output', str(out)], text=True, capture_output=True)
            self.assertNotEqual(proc.returncode,0)
            self.assertFalse(out.exists())
            self.assertIn(compose.GRAPH_PREDECESSOR_FROZEN_BLOB, proc.stderr+proc.stdout)

    def test_cli_explicit_reproduction_binds_actual_noncanonical_input(self):
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)/'out'
            subprocess.run([
                sys.executable, str(HERE/'compose.py'), '--package', str(RUNTIME_ROOT),
                '--output', str(out), '--frozen-blob', BASE_BLOB], check=True,
                text=True, capture_output=True)
            self.assertEqual((out/'row_shed_sell_order.py').read_bytes(),
                             (HERE/'row_shed_sell_order.py').read_bytes())
            receipt=json.loads((out/'ROW-SHED-COMPOSITION.json').read_text())
            base_bytes=BASE.read_bytes()
            self.assertFalse(receipt['release_authorized'])
            self.assertFalse(receipt['production_activated'])
            self.assertTrue(receipt['source_copied_verbatim'])
            self.assertEqual(receipt['graph_predecessor']['git_blob'], BASE_BLOB)
            self.assertEqual(receipt['graph_predecessor']['sha256'],
                             hashlib.sha256(base_bytes).hexdigest())
            self.assertEqual(receipt['materialization']['input_git_blob'], BASE_BLOB)
            self.assertEqual(receipt['canonical_graph_predecessor']['git_blob'],
                             compose.GRAPH_PREDECESSOR_FROZEN_BLOB)
            self.assertEqual(receipt['canonical_graph_predecessor']['sha256'],
                             compose.GRAPH_PREDECESSOR_FROZEN_SHA256)
            self.assertFalse(receipt['canonical_graph_predecessor']['matches_input'])
            self.assertEqual(receipt['materialization']['method_after_sha256'],
                             compose.METHOD_AFTER_SHA256)
            self.assertEqual(blob((out/'frozen_selected.py').read_bytes()),
                             receipt['materialization']['output_git_blob'])

    def test_no_second_controller_scheduler_or_feature_key(self):
        text=(HERE/'compose.py').read_text()
        tree=ast.parse(text)
        self.assertNotIn('TITAN-CONFIG', text)
        self.assertNotIn('Features(', text)
        self.assertNotIn('TitanAgent(', text)
        self.assertNotIn('scheduler.py', text)
        self.assertTrue(any(isinstance(n, ast.FunctionDef) and n.name=='compose_frozen'
                            for n in ast.walk(tree)))


if __name__ == '__main__':
    unittest.main()
