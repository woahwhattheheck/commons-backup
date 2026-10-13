from __future__ import annotations
import argparse, json, os, stat, sys
from pathlib import Path
from .compiler import GrantPacketError, MAX_BYTES, compile_packet, verify

def read(path):
    fd = os.open(path, os.O_RDONLY | getattr(os,'O_CLOEXEC',0) | getattr(os,'O_NOFOLLOW',0) | getattr(os,'O_NONBLOCK',0))
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode): raise GrantPacketError(f"{path}: regular file required")
        chunks=[]; total=0
        while True:
            b=os.read(fd,1024*1024)
            if not b: break
            total += len(b)
            if total > MAX_BYTES: raise GrantPacketError(f"{path}: too large")
            chunks.append(b)
        return b''.join(chunks)
    finally: os.close(fd)

def write(path, payload):
    fd=os.open(path, os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_CLOEXEC',0)|getattr(os,'O_NOFOLLOW',0), 0o644)
    try:
        view=memoryview(payload)
        while view: view=view[os.write(fd,view):]
        os.fsync(fd)
    finally: os.close(fd)

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__); sub=p.add_subparsers(dest='cmd',required=True)
    c=sub.add_parser('compile'); c.add_argument('--programs',required=True); c.add_argument('--input',required=True); c.add_argument('--out-dir',required=True)
    v=sub.add_parser('verify'); v.add_argument('--programs',required=True); v.add_argument('--input',required=True); v.add_argument('--packet',required=True); v.add_argument('--markdown',required=True); v.add_argument('--receipt',required=True)
    a=p.parse_args(argv)
    try:
        if a.cmd=='compile':
            packet,md,receipt=compile_packet(read(a.programs),read(a.input)); out=Path(a.out_dir); out.mkdir(parents=True,exist_ok=True)
            write(str(out/'packet.json'),packet); write(str(out/'packet.md'),md); write(str(out/'receipt.json'),receipt)
            print(json.dumps({'status':json.loads(packet)['status'],'packet_sha256':__import__('hashlib').sha256(packet).hexdigest()},sort_keys=True)); return 0
        result=verify(read(a.programs),read(a.input),read(a.packet),read(a.markdown),read(a.receipt)); print(json.dumps(result,sort_keys=True)); return 0
    except (GrantPacketError,OSError,FileExistsError) as exc:
        print(f"HOLD: {exc}",file=sys.stderr); return 2
if __name__=='__main__': raise SystemExit(main())
