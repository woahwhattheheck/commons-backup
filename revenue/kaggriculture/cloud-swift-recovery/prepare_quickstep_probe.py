# SPDX-License-Identifier: Apache-2.0
"""Compose QUICKSTEP's published helper and declared callsites in a new test copy.

This is not a canonical package builder. The exact original root is untouched;
the prospective directory is private test material, not a release or promotion.
"""
from __future__ import annotations
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import shutil

HELPER_BLOB = '58ac31dada1c35b6dbaaaeef29fd83a0e52481ab'
BASE_FROZEN_SHA = 'fdf54ec963e93c831fc4c8459bb9095935a64be604b08b3bbcd6c44c2e45cdb5'
SOURCE_COMMIT = 'cbcb6b2ea15d8f3e98e2a2f4db376937a39c8ae9'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--helper', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    helper = args.helper.read_bytes()
    blob = hashlib.sha1(b'blob '+str(len(helper)).encode()+b'\0'+helper).hexdigest()
    if blob != HELPER_BLOB:
        raise ValueError('Helper differs from the published QUICKSTEP Git blob')
    original = (args.root/'frozen_selected.py').read_bytes()
    if hashlib.sha256(original).hexdigest() != BASE_FROZEN_SHA:
        raise ValueError('Probe requires the exact frozen820ed source, not a newer candidate')
    before = original.decode()
    if before.count('from scheduler import *\n') != 1 or before.count('self.previous=copy.deepcopy(obs)') != 2:
        raise ValueError('Unexpected callsite shape')
    after = before.replace('from scheduler import *\n',
                           'from scheduler import *\nfrom selected_sell_core import optimize_lot\nfrom seller_snapshot import seller_public_observation\n')
    after = after.replace('self.previous=copy.deepcopy(obs)',
                          'self.previous=seller_public_observation(obs)')
    shutil.copytree(args.root, args.output, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    (args.output/'seller_snapshot.py').write_bytes(helper)
    (args.output/'frozen_selected.py').write_text(after)
    changes = ''.join(difflib.unified_diff(before.splitlines(keepends=True),after.splitlines(keepends=True),
                                         fromfile='frozen_selected.py.frozen820ed',tofile='frozen_selected.py.quickstep-probe'))
    (args.output/'QUICKSTEP-PROBE.diff').write_text(changes)
    receipt = {'schema': 1, 'kind': 'private_declared_callsite_probe_not_canonical_archive',
               'source_commit': SOURCE_COMMIT, 'helper_git_blob': blob,
               'helper_sha256': hashlib.sha256(helper).hexdigest(),
               'original_frozen_selected_sha256': BASE_FROZEN_SHA,
               'probe_frozen_selected_sha256': hashlib.sha256(after.encode()).hexdigest(),
               'author_callsite_contract_slack_ts': '1788865228.759069',
               'changes': ['import existing selected_sell_core.optimize_lot',
                           'import exact published seller_public_observation',
                           'replace two previous-observation snapshots'],
               'original_root_modified': False, 'release_archive_built': False,
               'new_games': 0}
    (args.output/'QUICKSTEP-PROBE.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt,indent=2))


if __name__ == '__main__':
    main()
