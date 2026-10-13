"""Verify the exact attributed upstream Git blobs; optionally normalize copy EOF."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def blob_id(raw):
    return hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--normalize-copy-eof', action='store_true')
    args = parser.parse_args()
    manifest = json.loads((ROOT / 'SOURCE_MANIFEST.json').read_text(encoding='utf-8'))
    for item in manifest['upstream_files']:
        path = ROOT / item['local_path']
        raw = original = path.read_bytes()
        if args.normalize_copy_eof:
            while blob_id(raw) != item['git_blob'] and raw.endswith(b'\n'):
                raw = raw[:-1]
            if blob_id(raw) == item['git_blob'] and raw != original:
                path.write_bytes(raw)
        if blob_id(path.read_bytes()) != item['git_blob']:
            raise SystemExit('Upstream source mismatch: ' + item['local_path'])
    print(json.dumps({'verified_upstream_files': len(manifest['upstream_files']),
                      'commit': manifest['commons_commit']}))

if __name__ == '__main__':
    main()
