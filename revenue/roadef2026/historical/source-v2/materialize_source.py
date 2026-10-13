#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Materialize and verify the exact historical temporal V2 source archive."""
from __future__ import annotations
import argparse,base64,gzip,hashlib,io,json,tarfile
from pathlib import Path,PurePosixPath

ARCHIVE_SHA256='53217562eeeeff53a200de5374105643fac6e9efd3de5a3eeebb288a974ecdb7'
FILES={
 'main.cpp':(39290,'4e0c328d28e053d335328ac520cb21825601d9cabd9d0bba8015634d5919393d'),
 'temporal_dp.hpp':(8995,'a9db8fc26acc6f4127640f306dd12ff61a2726e5b5edc5b4c53d1fb6225fca8b'),
}

def sha(data:bytes)->str:return hashlib.sha256(data).hexdigest()

def main()->int:
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--encoded',type=Path,default=Path(__file__).with_name('source-v2.tar.gz.b64'))
 p.add_argument('--output',type=Path,required=True)
 args=p.parse_args()
 try: encoded=args.encoded.read_text(encoding='ascii')
 except OSError as exc:p.error(str(exc))
 try: archive=base64.b64decode(encoded,validate=False)
 except ValueError as exc:p.error(f'invalid base64: {exc}')
 if sha(archive)!=ARCHIVE_SHA256:p.error('source archive digest mismatch')
 if args.output.exists():p.error('output directory already exists')
 rows=[]
 try:
  with tarfile.open(fileobj=io.BytesIO(archive),mode='r:gz') as tf:
   members=tf.getmembers()
   if len(members)!=2 or {m.name for m in members}!=set(FILES):
    p.error('unexpected archive member set')
   args.output.mkdir(parents=True)
   for member in members:
    pure=PurePosixPath(member.name)
    if pure.is_absolute() or '..' in pure.parts or not member.isfile():p.error('unsafe source archive member')
    stream=tf.extractfile(member)
    if stream is None:p.error(f'cannot read {member.name}')
    data=stream.read(); expected_size,expected_sha=FILES[member.name]
    if len(data)!=expected_size or sha(data)!=expected_sha:p.error(f'identity mismatch: {member.name}')
    path=args.output/member.name;path.write_bytes(data)
    rows.append({'path':member.name,'bytes':len(data),'sha256':sha(data)})
 except (OSError,tarfile.TarError) as exc:p.error(str(exc))
 print(json.dumps({'schema':'roadef.historical.temporal-v2.materialization.v1','status':'PASS',
                   'archive_sha256':ARCHIVE_SHA256,'output':str(args.output),'files':sorted(rows,key=lambda r:r['path']),
                   'compiled':False,'solver_runs':0,'checker_runs':0},indent=2,sort_keys=True))
 return 0
if __name__=='__main__':raise SystemExit(main())
