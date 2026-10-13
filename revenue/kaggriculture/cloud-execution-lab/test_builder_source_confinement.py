# SPDX-License-Identifier: Apache-2.0
"""Predecessor killers for canonical release source confinement."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent


def _load_builder():
    path = ROOT / 'build_integrated.py'
    spec = importlib.util.spec_from_file_location('_titan_builder_source_confinement', path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'cannot load canonical builder: {path}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _install_fixture(root: Path) -> None:
    (root / 'runtime/integrated-selected').mkdir(parents=True)
    (root / 'TITAN-CONFIG.json').write_text('{}\n', encoding='utf-8')
    (root / 'runtime/integrated-selected/RELEASE.json').write_text('{}\n', encoding='utf-8')


class BuilderSourceConfinementTests(unittest.TestCase):
    def test_render_allows_attributed_sibling_inside_kaggriculture(self):
        builder = _load_builder()
        original_root = builder.ROOT
        original_source_files = builder.source_files
        try:
            with tempfile.TemporaryDirectory(prefix='titan-builder-source-ok-') as raw:
                kaggriculture = Path(raw) / 'revenue/kaggriculture'
                root = kaggriculture / 'cloud-execution-lab'
                sibling = kaggriculture / 'cloud-sibling'
                root.mkdir(parents=True)
                sibling.mkdir()
                _install_fixture(root)
                (sibling / 'sibling.py').write_text('VALUE = 1\n', encoding='utf-8')
                mapping = {
                    'TITAN-CONFIG.json': 'TITAN-CONFIG.json',
                    'sibling.py': '../cloud-sibling/sibling.py',
                }
                builder.ROOT = root
                builder.source_files = lambda: mapping

                data, source_bytes, receipt = builder.render()

                self.assertTrue(data)
                self.assertEqual(receipt['runtime_files'], 2)
                manifest = json.loads(source_bytes)
                self.assertEqual(
                    manifest['runtime']['sibling.py']['source_path'],
                    '../cloud-sibling/sibling.py',
                )
        finally:
            builder.ROOT = original_root
            builder.source_files = original_source_files

    def test_render_rejects_symlink_escape(self):
        builder = _load_builder()
        original_root = builder.ROOT
        original_source_files = builder.source_files
        try:
            with tempfile.TemporaryDirectory(prefix='titan-builder-source-escape-') as raw:
                kaggriculture = Path(raw) / 'revenue/kaggriculture'
                root = kaggriculture / 'cloud-execution-lab'
                root.mkdir(parents=True)
                outside = Path(raw) / 'outside.py'
                outside.write_text('SENTINEL = True\n', encoding='utf-8')
                link = root / 'escape.py'
                try:
                    link.symlink_to(outside)
                except (NotImplementedError, OSError) as exc:
                    self.skipTest(f'symlinks unavailable: {exc}')
                builder.ROOT = root
                builder.source_files = lambda: {'escape.py': 'escape.py'}

                with self.assertRaisesRegex(ValueError, 'escapes Kaggriculture tree'):
                    builder.render()
        finally:
            builder.ROOT = original_root
            builder.source_files = original_source_files

    def test_render_rejects_parent_traversal_escape(self):
        builder = _load_builder()
        original_root = builder.ROOT
        original_source_files = builder.source_files
        try:
            with tempfile.TemporaryDirectory(prefix='titan-builder-source-parent-') as raw:
                kaggriculture = Path(raw) / 'revenue/kaggriculture'
                root = kaggriculture / 'cloud-execution-lab'
                root.mkdir(parents=True)
                outside = Path(raw) / 'outside.py'
                outside.write_text('SENTINEL = True\n', encoding='utf-8')
                builder.ROOT = root
                builder.source_files = lambda: {'escape.py': '../../../outside.py'}

                with self.assertRaisesRegex(ValueError, 'escapes Kaggriculture tree'):
                    builder.render()
        finally:
            builder.ROOT = original_root
            builder.source_files = original_source_files


if __name__ == '__main__':
    unittest.main(verbosity=2)
