# SPDX-License-Identifier: Apache-2.0
"""Build the telemetry-only P01 V219 arm on the exact production-v3 family."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat

BASE_SHA = '20f201161b14af7755146b08207593f9fa5df641d2f31e680792ea62c0e24239'
V31_SHA = '5db3921f85efbc7596e5a1e7e198fc5f4644ceea43d8e8323c74ded7b4ba4361'
DELIVERY_SHA = '0d42ee5fabb089745fa0064207654bfdf5df9466ba6499d91b6e685d4880cab1'
ROUTER = 'r04_full_router.py'
ROUTER_SHA = '41ea55c5f20c43cd58c5099fbadb212de62ec95a95dfc2e6e1e19c3d4d55b39a'
GATE = 'p01_productive_expansion_gate.py'
ANCHOR = b'\n\ndef _v219_walk(pos, target):\n'
WRAPPER = b'''\n\n# P01 / TITAN-V5-PRODUCTIVE-EXPANSION-WIDE: default-off experiment carrier.\n# Keep the original V219 identity/land/worker checks and collect only public-\n# evidence payback telemetry. Full execution of the ten-seed purchase is not\n# authenticated, so P01 has no authority to accept or reject the parent.\n_V219_QUALIFIES_PARENT = _v219_qualifies\nfor _key in ('p01_gate_checks', 'p01_payback_rejects',\n             'p01_gate_passthroughs', 'p01_visible_rival_field_projection',\n             'p01_modeled_gross_visible_field', 'p01_gross_upper_bound',\n             'p01_unavoidable_cost_floor', 'p01_labor_cost_floor'):\n    _V219_REPORT.setdefault(_key, 0)\n\ndef _v219_qualifies(obs, native):\n    if not _V219_QUALIFIES_PARENT(obs, native):\n        return False\n    import p01_productive_expansion_gate as _p01\n    record = _p01.evaluate(obs, native, _v219_native_day, _v219_fib, _ro_price)\n    _V219_REPORT['p01_gate_checks'] += 1\n    if 'visible_rival_field_projection' in record:\n        _V219_REPORT['p01_visible_rival_field_projection'] = int(record['visible_rival_field_projection'])\n    if record.get('modeled_gross_visible_field') is not None:\n        _V219_REPORT['p01_modeled_gross_visible_field'] = int(record['modeled_gross_visible_field'])\n    if 'gross_revenue_upper_bound' in record:\n        _V219_REPORT['p01_gross_upper_bound'] = int(record['gross_revenue_upper_bound'])\n    if 'unavoidable_cost_floor' in record:\n        _V219_REPORT['p01_unavoidable_cost_floor'] = int(record['unavoidable_cost_floor'])\n    if 'labor_cost_floor' in record:\n        _V219_REPORT['p01_labor_cost_floor'] = int(record['labor_cost_floor'])\n    if record['decision'] is not None:\n        raise RuntimeError('P01 telemetry gate returned decision authority')\n    _V219_REPORT['p01_gate_passthroughs'] += 1\n    return True\n'''


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def inject(base_files, gate_source):
    """Return a copy with only the exact submitted R04 router plus one gate module changed."""
    from build_delivery import archive_bytes

    if _sha(archive_bytes(base_files)) != BASE_SHA:
        raise ValueError('P01 requires the exact production-v3 base archive')
    files = dict(base_files)
    router = files.get(ROUTER)
    if router is None or _sha(router) != ROUTER_SHA:
        raise ValueError('P01 requires the exact submitted V3.1 R04 router')
    if GATE in files:
        raise ValueError('P01 gate module already exists')
    if router.count(ANCHOR) != 1:
        raise ValueError('Expected one V219 qualification insertion seam')
    files[ROUTER] = router.replace(ANCHOR, WRAPPER + ANCHOR, 1)
    files[GATE] = gate_source.replace(b'\r\n', b'\n')
    return files


def _resolved(path):
    return Path(path).resolve(strict=False)


def _validate_publication_paths(out, tar_path, receipt_path):
    resolved = [_resolved(path) for path in (out, tar_path, receipt_path)]
    if len(set(resolved)) != len(resolved):
        raise ValueError('output directory, archive, and receipt paths must be distinct')
    out_resolved, tar_resolved, receipt_resolved = resolved
    if out_resolved in tar_resolved.parents or out_resolved in receipt_resolved.parents:
        raise ValueError('archive and receipt must not be inside the output directory')


def _rmtree_if_owned(path, identity):
    path = Path(path)
    try:
        stat_result = os.lstat(path)
    except FileNotFoundError:
        return
    if ((stat_result.st_dev, stat_result.st_ino) == identity
            and stat.S_ISDIR(stat_result.st_mode)):
        shutil.rmtree(path)


def _publish(files, packed, receipt, out, tar_path, receipt_path):
    """Publish the output tree plus an archive/receipt pair using shared custody."""
    from publication_custody import publish_exclusive

    out, tar_path, receipt_path = map(Path, (out, tar_path, receipt_path))
    _validate_publication_paths(out, tar_path, receipt_path)
    if out.exists():
        raise FileExistsError('output directory already exists')

    out_fd = None
    out_identity = None
    try:
        out.mkdir(parents=True)
        flags = os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0) | getattr(os, 'O_NOFOLLOW', 0)
        out_fd = os.open(out, flags)
        out_stat = os.fstat(out_fd)
        if not stat.S_ISDIR(out_stat.st_mode):
            raise OSError('output path is not a directory')
        out_identity = (out_stat.st_dev, out_stat.st_ino)
        for name, body in files.items():
            path = out / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)

        receipt_bytes = (json.dumps(receipt, indent=2) + '\n').encode('utf-8')
        publish_exclusive([
            (tar_path, packed),
            (receipt_path, receipt_bytes),
        ])
    except BaseException:
        if out_identity is not None:
            _rmtree_if_owned(out, out_identity)
        raise
    finally:
        if out_fd is not None:
            os.close(out_fd)


def main():
    from build_delivery import archive_bytes, members
    from build_production_recovery import compose

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--v31', type=Path, required=True)
    parser.add_argument('--delivery', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--tar', type=Path, required=True)
    args = parser.parse_args()
    receipt_path = args.out.parent / (args.out.name + '-manifest.json')

    v31 = members(args.v31, V31_SHA)
    delivery = members(args.delivery, DELIVERY_SHA)
    overlay = Path(__file__).with_name('production_recovery_overlay.txt').read_bytes()
    base_files = compose(v31, delivery, overlay, 'v3')
    gate_source = Path(__file__).with_name(GATE).read_bytes()
    files = inject(base_files, gate_source)
    packed = archive_bytes(files)
    receipt = {
        'schema': 'titan-v5-p01-productive-expansion/v3',
        'base_candidate_sha256': BASE_SHA,
        'candidate_archive_sha256': _sha(packed),
        'v31_archive_sha256': V31_SHA,
        'delivery_archive_sha256': DELIVERY_SHA,
        'changed_members': [ROUTER, GATE],
        'decision_contract': 'telemetry-only-until-full-seed-purchase-authenticated',
        'labor_model': 'day18-commitment-hires-only-lower-bound',
        'seed_cost_model': 'at-least-one-executed-unit-lower-bound',
        'rival_supply_scope': 'visible-field-telemetry-only',
        'default_activation': False,
        'kaggle_submission_hold': True,
        'files': {name: _sha(body) for name, body in sorted(files.items())},
    }
    try:
        _publish(files, packed, receipt, args.out, args.tar, receipt_path)
    except (FileExistsError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps({'out': str(args.out), 'members': len(files),
                      'candidate_archive_sha256': _sha(packed)}))


if __name__ == '__main__':
    main()
