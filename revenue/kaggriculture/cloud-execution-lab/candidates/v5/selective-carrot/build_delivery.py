# SPDX-License-Identifier: Apache-2.0
"""Reproduce the frozen delivery-carrot experiment from two exact archives."""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import tarfile

CAP12_SHA = '5bf8e90602e145b353b9ff421fc514f2cf8af77ec549557e5e0acc1bc6bd67aa'
RECOVERY_SHA = 'a44bf380cd79f967893ea90273be7dc92d6fd4f5e553aac0b02e457e85cf4ca8'
CANDIDATE_SHA = '0d42ee5fabb089745fa0064207654bfdf5df9466ba6499d91b6e685d4880cab1'
LEGACY_SHA = '4db8d176bd34b219eff62c65e584a0786889065a52467b68f79e01f24af8fb30'
DELIVERY_SHA = '4d3f9729d7fa52a9c221e9d9ffcc434dee55a7dcd22d92f15ad4728103e6c924'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def members(path, expected):
    raw = path.read_bytes()
    if digest(raw) != expected:
        raise ValueError('Archive identity mismatch: ' + str(path))
    result = {}
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as archive:
        for member in archive.getmembers():
            name = member.name
            rel = PurePosixPath(name)
            if (not member.isfile() or name in result or rel.is_absolute()
                    or '..' in rel.parts or '\\' in name or str(rel) != name):
                raise ValueError('Noncanonical archive member: ' + name)
            result[name] = archive.extractfile(member).read()
    return result


def normalize_callback(wrapper):
    old = b"    step = observation.get('step', observation.get('day', 0)*24+observation.get('hour', 0))\n"
    new = b"""    step = observation.get('step')
    if step is None:
        step = (int(observation.get('day', 0)) * int((configuration or {}).get('turnsPerDay', 24))
                + int(observation.get('hour', 0)))
    step = int(step)
    observation = dict(observation, step=step)
"""
    if wrapper.count(old) != 1:
        raise ValueError('Expected exact outer callback clock seam')
    return wrapper.replace(old, new)


def compose(cap12, recovery, delivery, version='v2'):
    """Replace only the parent entry and delivery wrapper/helper."""
    extras = {'main.py', 'baseline_main.py', 'selective_carrot.py'}
    cap_rest = {k: v for k, v in cap12.items() if k not in extras}
    recovery_rest = {k: v for k, v in recovery.items() if k != 'main.py'}
    if not extras <= cap12.keys() or 'main.py' not in recovery:
        raise ValueError('Missing required entry/helper')
    if cap_rest != recovery_rest:
        raise ValueError('Unrelated payload members differ between controls')
    if digest(delivery) != DELIVERY_SHA:
        raise ValueError('Delivery helper differs from tested source')
    wrapper = cap12['main.py'].replace(b'\r\n', b'\n')
    import_anchor = b'from selective_carrot import CropChoice'
    constructor = b'CropChoice(market_price, max_active=12)'
    if wrapper.count(import_anchor) != 1 or wrapper.count(constructor) != 1:
        raise ValueError('Exact cap12 wrapper seams changed')
    wrapper = wrapper.replace(import_anchor, b'from delivery_choice import DeliveryChoice')
    wrapper = wrapper.replace(constructor, b'DeliveryChoice(market_price, max_active=12)')
    if version == 'v2':
        wrapper = normalize_callback(wrapper)
    elif version != 'v1':
        raise ValueError('Expected v1 or v2')
    result = dict(cap12)
    result['baseline_main.py'] = recovery['main.py']
    result['main.py'] = wrapper
    result['delivery_choice.py'] = delivery
    return result


def archive_bytes(files):
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode='w') as archive:
        for name, body in sorted(files.items()):
            info = tarfile.TarInfo(name)
            info.size = len(body)
            info.mode = 0o644
            archive.addfile(info, io.BytesIO(body))
    packed = io.BytesIO()
    with gzip.GzipFile(filename='', mode='wb', fileobj=packed, mtime=0) as zipped:
        zipped.write(raw.getvalue())
    return packed.getvalue()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cap12', type=Path, required=True)
    parser.add_argument('--route-recovery', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--tar', type=Path, required=True)
    parser.add_argument('--version', choices=('v1', 'v2'), default='v2')
    args = parser.parse_args()
    receipt_path = args.out.parent / (args.out.name + '-manifest.json')
    if any(p.exists() for p in (args.out, args.tar, receipt_path)):
        parser.error('Use new output directory, archive and manifest paths')
    cap12 = members(args.cap12, CAP12_SHA)
    recovery = members(args.route_recovery, RECOVERY_SHA)
    delivery = Path(__file__).with_name('delivery_choice.py').read_bytes().replace(b'\r\n', b'\n')
    files = compose(cap12, recovery, delivery, args.version)
    packed = archive_bytes(files)
    candidate_sha = CANDIDATE_SHA if args.version == 'v2' else LEGACY_SHA
    if digest(packed) != candidate_sha:
        raise ValueError('Build did not reproduce the tested archive')
    # No output is created before both input snapshots and the result match.
    args.out.mkdir(parents=True)
    for name, body in files.items():
        path = args.out / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
    args.tar.parent.mkdir(parents=True, exist_ok=True)
    with args.tar.open('xb') as stream:
        stream.write(packed)
    receipt = {'schema': 'titan-delivery-carrot-build/v1',
               'cap12_archive_sha256': CAP12_SHA,
               'route_recovery_archive_sha256': RECOVERY_SHA,
               'candidate_archive_sha256': candidate_sha, 'version': args.version,
               'max_active': 12, 'kaggle_submission_hold': True,
               'files': {name: digest(body) for name, body in sorted(files.items())}}
    receipt_path.write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'out': str(args.out), 'members': len(files),
                      'candidate_archive_sha256': candidate_sha}))


if __name__ == '__main__':
    main()
