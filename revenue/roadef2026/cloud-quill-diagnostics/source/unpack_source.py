#!/usr/bin/env python3
"""Verify, reconstruct, and safely extract the retained QUILL source archive."""
from __future__ import annotations
import argparse, base64, hashlib, json, tarfile
from pathlib import Path


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--source-dir',type=Path,default=Path(__file__).resolve().parent)
    args=parser.parse_args()
    source=args.source_dir.resolve()
    manifest=json.loads((source/'archive-manifest.json').read_text(encoding='utf-8'))
    encoded=[]
    for row in manifest['parts']:
        path=source/Path(row['path']).name
        data=path.read_bytes()
        if len(data)!=row['bytes'] or digest(data)!=row['sha256']:
            raise SystemExit(f'part mismatch: {path.name}')
        encoded.append(data)
    archive=base64.b64decode(b''.join(encoded),validate=True)
    if len(archive)!=manifest['archive_bytes'] or digest(archive)!=manifest['archive_sha256']:
        raise SystemExit('archive mismatch')
    args.output.mkdir(parents=True,exist_ok=False)
    archive_path=args.output/manifest['archive_filename']
    archive_path.write_bytes(archive)
    extract=args.output/'extracted'
    extract.mkdir()
    with tarfile.open(archive_path,'r:gz') as tf:
        base=extract.resolve()
        for member in tf.getmembers():
            target=(base/member.name).resolve()
            if target!=base and base not in target.parents:
                raise SystemExit(f'unsafe archive member: {member.name}')
            if member.issym() or member.islnk():
                raise SystemExit(f'links not permitted: {member.name}')
        tf.extractall(extract,filter='data')
    print(json.dumps({'archive':str(archive_path),'sha256':digest(archive),
                      'extracted':str(extract/manifest['extracted_root']),
                      'parts':len(manifest['parts'])},sort_keys=True))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
