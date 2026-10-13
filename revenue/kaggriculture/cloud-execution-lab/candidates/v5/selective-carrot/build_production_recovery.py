# SPDX-License-Identifier: Apache-2.0
"""Build the frozen V3.1 production / V4 economics composition for evaluation."""
import argparse
import ast
import json
import os
from pathlib import Path
import shutil
import stat

from build_delivery import archive_bytes, digest, members
from publication_custody import publish_exclusive

V31_SHA = '5db3921f85efbc7596e5a1e7e198fc5f4644ceea43d8e8323c74ded7b4ba4361'
DELIVERY_SHA = '0d42ee5fabb089745fa0064207654bfdf5df9466ba6499d91b6e685d4880cab1'
LEGACY_SHA = '0aded66a2c393cc60f4f45d10f11c384a7e788182bf5430863829a02b66daf02'
CANDIDATE_SHA = '20f201161b14af7755146b08207593f9fa5df641d2f31e680792ea62c0e24239'
VENDOR = 'reference/next-panel/vendor/arlene.py'
DEPENDENCIES = (
    'b11_mirror_horizon.py', 'b5_fertilize.py', 'b9_terminal_fertilizer.py',
    'h3c_goose_eod_cap_rescue.py', 'jit_pass_fertilize.py', 'r01_tapes.py',
    'r04_dribble_dump.py', 'r04_fert_hand.py', 'r04_full_router.py',
    'r04_h4_strawberry.py', 'r04_kill_late_water.py',
    'r04_no_late_sale_advance.py', 'r04_strawberry_endgame.py',
)


def dependency_closure(v31):
    seen, todo = set(), ['r04_full_router.py']
    while todo:
        name = todo.pop()
        if name in seen:
            continue
        if name not in v31:
            raise ValueError('Missing donor dependency: ' + name)
        seen.add(name)
        for node in ast.walk(ast.parse(v31[name])):
            imports = ([alias.name.split('.')[0] for alias in node.names]
                       if isinstance(node, ast.Import) else
                       [node.module.split('.')[0]]
                       if isinstance(node, ast.ImportFrom) and node.module else [])
            todo.extend(x + '.py' for x in imports if x + '.py' in v31 and x + '.py' not in seen)
    if seen != set(DEPENDENCIES):
        raise ValueError('Expected the exact 13-file donor dependency closure')
    return seen


def compose(v31, delivery, overlay, version='v3'):
    dependency_closure(v31)
    files = dict(delivery)
    for name in DEPENDENCIES:
        if name in files and files[name] != v31[name]:
            raise ValueError('Incompatible existing dependency: ' + name)
        files[name] = v31[name]
    original = files[VENDOR].replace(b'\r\n', b'\n')
    anchor = b'\n_A = None\n'
    if original.count(anchor) != 1:
        raise ValueError('Expected one vendor class insertion seam')
    overlay = overlay.replace(b'\r\n', b'\n')
    files[VENDOR] = original.replace(anchor, b'\n' + overlay + b'\n_A = None\n')
    # Preserve the exact tested context member, including its original line end.
    files['full_production_context.py'] = b'configuration = {}\r\n'
    entry = files['main.py'].replace(b'\r\n', b'\n')
    needle = b'    returned = baseline.agent(observation, configuration)'
    if entry.count(needle) != 1:
        raise ValueError('Expected one outer delivery call seam')
    files['main.py'] = entry.replace(needle,
        b'    import full_production_context\n'
        b'    full_production_context.configuration = dict(configuration or {})\n' + needle)
    if digest(archive_bytes(files)) != LEGACY_SHA:
        raise ValueError('Composition differs from the tested production archive')
    if version == 'v3':
        # The pinned raw-file loader exposes the payload root only while exec
        # loads this entry. Capture the shipped context then; its first use in
        # agent() precedes baseline.agent() restoring the root on sys.path.
        anchor = b'import baseline_main as baseline\n'
        if files['main.py'].count(anchor) != 1:
            raise ValueError('Expected one entry import seam')
        files['main.py'] = files['main.py'].replace(
            anchor, anchor + b'import full_production_context\n', 1)
        if digest(archive_bytes(files)) != CANDIDATE_SHA:
            raise ValueError('Composition differs from the tested import-safe archive')
    elif version != 'v2':
        raise ValueError('Expected v2 or v3')
    return files


def _resolved(path):
    return Path(path).resolve(strict=False)


def _validate_publication_paths(out, tar_path, receipt_path):
    resolved = [_resolved(path) for path in (out, tar_path, receipt_path)]
    if len(set(resolved)) != len(resolved):
        raise ValueError('output directory, archive, and manifest paths must be distinct')
    out_resolved, tar_resolved, receipt_resolved = resolved
    if out_resolved in tar_resolved.parents or out_resolved in receipt_resolved.parents:
        raise ValueError('archive and manifest must not be inside the output directory')


def _rmtree_if_owned(path, identity):
    path = Path(path)
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return
    if (st.st_dev, st.st_ino) == identity and stat.S_ISDIR(st.st_mode):
        shutil.rmtree(path)


def _publish(files, packed, receipt, out, tar_path, receipt_path):
    """Publish extracted files plus an audited create-exclusive archive/manifest pair."""
    out = Path(out)
    tar_path = Path(tar_path)
    receipt_path = Path(receipt_path)
    _validate_publication_paths(out, tar_path, receipt_path)
    if out.exists():
        raise FileExistsError('output directory already exists')

    receipt_bytes = (json.dumps(receipt, indent=2) + '\n').encode('utf-8')
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

        # Keep only extracted-tree ownership local. The related final files use
        # the single shared V5 reserve/write/verify/fsync/rollback authority.
        publish_exclusive([(tar_path, packed), (receipt_path, receipt_bytes)])
    except BaseException:
        if out_identity is not None:
            _rmtree_if_owned(out, out_identity)
        raise
    finally:
        if out_fd is not None:
            os.close(out_fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--v31', type=Path, required=True)
    parser.add_argument('--delivery', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--tar', type=Path, required=True)
    parser.add_argument('--version', choices=('v2', 'v3'), default='v3')
    args = parser.parse_args()
    receipt_path = args.out.parent / (args.out.name + '-manifest.json')
    v31 = members(args.v31, V31_SHA)
    delivery = members(args.delivery, DELIVERY_SHA)
    overlay = Path(__file__).with_name('production_recovery_overlay.txt').read_bytes()
    files = compose(v31, delivery, overlay, args.version)
    packed = archive_bytes(files)
    receipt = {'schema': 'titan-production-recovery-build/v3', 'version': args.version,
        'v31_archive_sha256': V31_SHA, 'delivery_archive_sha256': DELIVERY_SHA,
        'candidate_archive_sha256': digest(packed), 'donor_dependencies': list(DEPENDENCIES),
        'files': {name: digest(body) for name, body in sorted(files.items())},
        'kaggle_submission_hold': True}
    try:
        _publish(files, packed, receipt, args.out, args.tar, receipt_path)
    except (FileExistsError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps({'out': str(args.out), 'members': len(files),
                      'candidate_archive_sha256': digest(packed)}))


if __name__ == '__main__':
    main()
