#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Independent native data-custody/ordering controls; this does not run games."""
from __future__ import annotations
import argparse
import csv
import hashlib
import importlib.util
import json
import random
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

import mine_top_mechanics as m
import native_mechanics_audit as audit
from sequence_contract import sequence_windows


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def check(archive: Path, donor_path: Path) -> bool:
    b = donor_path.read_bytes()
    if hashlib.sha1(b'blob ' + str(len(b)).encode() + b'\0' + b).hexdigest() != '0aa78703f26ee647bd5af5c0fbfd207ea3dd15f8':
        raise ValueError('original miner identity mismatch')
    donor = load(donor_path, 'independent_donor')
    routes, pins = audit.authenticated_routes(archive)
    events = {r: audit.events_from_tape(r, tape) for r, tape in routes.items()}

    class NativeDataControls(unittest.TestCase):
        def test_static_decoder_equals_real_native_decoder(self):
            with tempfile.TemporaryDirectory() as td:
                path = Path(td)/'vendor.py'
                with tarfile.open(archive) as tar:
                    path.write_bytes(tar.extractfile(audit.VENDOR_PATH).read())
                native = load(path, 'independent_native_routes')
                self.assertEqual(routes, native.routes())

        def test_legacy_oracle_matches_exact_original_miner(self):
            for route, rows in events.items():
                with self.subTest(route=route):
                    original = donor.features_by_team(rows)[0]['TITAN_AUTHORED']
                    self.assertEqual({f for f in original if f.startswith('seq')},
                                     {f for f, _ in audit.legacy_windows(rows)})
                    # All original non-sequence features stay byte-identical.
                    updated = m.features_by_team(rows)[0]['TITAN_AUTHORED']
                    self.assertEqual({f for f in original if not f.startswith('seq')},
                                     {f for f in updated if not f.startswith(('seq', 'actor_seq'))})

        def test_real_windows_have_the_declared_identity(self):
            count = 0
            for rows in events.values():
                for feature, witness in sequence_windows(rows, m.token):
                    count += 1
                    self.assertEqual(len({(e.team,e.match,e.player,e.source) for e in witness}), 1)
                    if feature.startswith('actor_seq'):
                        self.assertEqual(len({e.actor for e in witness}), 1)
                        self.assertIsNotNone(witness[0].actor)
                        self.assertTrue(all(a.step < b.step for a,b in zip(witness,witness[1:])))
                    else:
                        self.assertTrue(all(a.step < b.step or (a.source == 'market' and
                                        a.step == b.step and a.slot < b.slot)
                                        for a,b in zip(witness,witness[1:])))
            self.assertGreater(count, 50000)

        def test_all_raw_rows_survive(self):
            for route, tape in routes.items():
                rows = events[route]
                self.assertEqual(len(rows), sum(1+len(a.get('hands',[]))+len(a.get('market',[])) for a in tape))
                for e in rows:
                    action = tape[e.step]
                    raw = ([action.get('farmer',[]), *action.get('hands',[])][int(e.actor)]
                           if e.source == 'unit' else action['market'][e.slot])
                    self.assertEqual(e.verb, raw[0].upper() if raw else 'EMPTY')

        def test_full_native_shuffle_is_feature_invariant(self):
            for route, rows in events.items():
                shuffled = list(rows)
                random.Random(9600912).shuffle(shuffled)
                self.assertEqual(m.features_by_team(rows), m.features_by_team(shuffled))

        def test_real_csv_actor_slot_roundtrip(self):
            for route, rows in events.items():
                with tempfile.TemporaryDirectory() as td:
                    for source in ('unit','market'):
                        selected = [e for e in rows if e.source == source]
                        p=Path(td)/(source+'.csv')
                        with p.open('w',newline='') as f:
                            writer=csv.writer(f)
                            writer.writerow(['match_id','team','player','step','action_verb','target','qty','actor','raw_slot'])
                            for e in selected:
                                writer.writerow([e.match,e.team,e.player,e.step,e.verb,e.target,e.qty,e.actor,e.slot])
                        loaded=m.read_events(p,source)
                        signature=lambda e:(e.match,e.team,e.player,e.step,e.source,e.verb,e.target,e.qty,e.actor,e.slot)
                        self.assertEqual(list(map(signature,selected)), list(map(signature,loaded)))

        def test_modified_archive_fails_closed(self):
            with tempfile.TemporaryDirectory() as td:
                p=Path(td)/'bad.tar.gz'
                p.write_bytes(archive.read_bytes()+b'\0')
                with self.assertRaisesRegex(ValueError,'archive hash mismatch'):
                    audit.authenticated_routes(p)

    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(NativeDataControls))
    return result.wasSuccessful()


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive',type=Path,required=True)
    parser.add_argument('--donor',type=Path,required=True)
    args=parser.parse_args()
    raise SystemExit(0 if check(args.archive,args.donor) else 1)
