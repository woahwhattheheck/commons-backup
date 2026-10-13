#!/usr/bin/env python3
"""Export the existing report/deck contract to editable PowerPoint."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from zipfile import ZipFile, ZIP_DEFLATED

HERE = Path(__file__).resolve().parent
P = 'http://schemas.openxmlformats.org/presentationml/2006/main'
A = 'http://schemas.openxmlformats.org/drawingml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
PKG = 'http://schemas.openxmlformats.org/package/2006/relationships'


def add_navigation(source, destination, deck):
    """Use native slide-jump relationships rather than external file links."""
    numbers = {slide['id']: index + 1 for index, slide in enumerate(deck['slides'])}
    with ZipFile(source) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    count = 0
    for index, _ in enumerate(deck['slides'], 1):
        filename = f'ppt/slides/slide{index}.xml'
        relname = f'ppt/slides/_rels/slide{index}.xml.rels'
        slide = ET.fromstring(parts[filename])
        relations = ET.fromstring(parts[relname])
        ids = {row.get('Id') for row in relations}
        for shape in slide.iter(f'{{{P}}}cNvPr'):
            name = shape.get('name', '')
            if not name.startswith('jump-'):
                continue
            target = name.removeprefix('jump-')
            if target not in numbers:
                raise ValueError(f'unknown navigation target {target}')
            rid = 'rIdReadout' + str(count + 1)
            while rid in ids:
                rid += 'x'
            ids.add(rid)
            ET.SubElement(shape, f'{{{A}}}hlinkClick', {
                f'{{{R}}}id': rid, 'action': 'ppaction://hlinksldjump'})
            ET.SubElement(relations, f'{{{PKG}}}Relationship', {
                'Id': rid, 'Type': R + '/slide', 'Target': f'slide{numbers[target]}.xml'})
            count += 1
        parts[filename] = ET.tostring(slide, encoding='utf-8', xml_declaration=True)
        parts[relname] = ET.tostring(relations, encoding='utf-8', xml_declaration=True)
    with ZipFile(destination, 'w', compression=ZIP_DEFLATED) as archive:
        for name, content in parts.items():
            archive.writestr(name, content)
    return count


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--deck', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--node', default=os.environ.get('CODEX_PRIMARY_RUNTIME_NODE', 'node'))
    parser.add_argument('--font', default='Arial')
    parser.add_argument('--parent-engine', type=Path,
        default=HERE.parent / 'uiowa_rfq_18649_readout_deck/deck_architecture.py')
    args = parser.parse_args(argv)
    try:
        if args.out.exists():
            raise ValueError('output exists; choose a new PPTX path')
        spec = importlib.util.spec_from_file_location('uiowa_readout_architecture', args.parent_engine)
        engine = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = engine
        spec.loader.exec_module(engine)
        report, deck = engine.load_report(str(args.report)), engine.load_deck(str(args.deck))
        issues = engine.check(report, deck)
        if engine.errors(issues):
            print(engine.render_agreement_report(report, deck, issues), file=sys.stderr)
            return 1
        for slide in deck['slides']:
            if len(slide.get('bullets', [])) > 3 or len(slide.get('claims', [])) > 4:
                raise ValueError(f"{slide['id']}: layout supports three bullets and four claims; move detail to an appendix")
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='readout-pptx-') as temporary:
            raw = Path(temporary) / 'editable.pptx'
            result = subprocess.run([args.node, str(HERE / 'build.mjs'), str(args.deck.resolve()), str(raw), args.font],
                                    check=False)
            if result.returncode:
                return result.returncode
            links = add_navigation(raw, args.out, deck)
        print(f'WROTE {args.out}; {len(deck["slides"])} slides; {links} internal jump/return links')
        return 0
    except (OSError, ValueError, TypeError, KeyError, ImportError) as exc:
        print(f'export error: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
