"""Bounded local subprocess profiler for an already-prepared offline smoke command."""
from __future__ import annotations
import argparse, os, resource, subprocess, time
from hashlib import sha256
from pathlib import Path
from core import canonical_json


def profile(command: list[str], output: Path, *, timeout_s: float, max_wall_s: float, max_rss_mib: float) -> dict:
    if not command: raise ValueError('command required')
    if min(timeout_s,max_wall_s,max_rss_mib) <= 0: raise ValueError('limits must be > 0')
    env={k:v for k,v in os.environ.items() if k.lower() not in {'http_proxy','https_proxy','all_proxy'}}
    before=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    start=time.monotonic()
    try:
        proc=subprocess.run(command,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=timeout_s,env=env,check=False)
        timed_out=False
    except subprocess.TimeoutExpired as exc:
        elapsed=time.monotonic()-start
        receipt={'schema_version':1,'command':command,'timed_out':True,'returncode':None,'wall_seconds':elapsed,'max_rss_mib':None,
                 'wall_limit_seconds':max_wall_s,'rss_limit_mib':max_rss_mib,'accepted':False,
                 'stdout_sha256':sha256((exc.stdout or b'') if isinstance(exc.stdout,bytes) else str(exc.stdout or '').encode()).hexdigest(),
                 'stderr_sha256':sha256((exc.stderr or b'') if isinstance(exc.stderr,bytes) else str(exc.stderr or '').encode()).hexdigest()}
        output.write_text(canonical_json(receipt),encoding='utf-8'); return receipt
    elapsed=time.monotonic()-start
    after=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    rss_mib=max(before,after)/1024.0
    accepted=(proc.returncode==0 and elapsed<=max_wall_s and rss_mib<=max_rss_mib)
    receipt={'schema_version':1,'command':command,'timed_out':timed_out,'returncode':proc.returncode,'wall_seconds':elapsed,'max_rss_mib':rss_mib,
             'wall_limit_seconds':max_wall_s,'rss_limit_mib':max_rss_mib,'accepted':accepted,
             'stdout_sha256':sha256(proc.stdout.encode()).hexdigest(),'stderr_sha256':sha256(proc.stderr.encode()).hexdigest()}
    output.write_text(canonical_json(receipt),encoding='utf-8'); return receipt

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--output',required=True,type=Path); ap.add_argument('--timeout-s',type=float,required=True); ap.add_argument('--max-wall-s',type=float,required=True); ap.add_argument('--max-rss-mib',type=float,required=True); ap.add_argument('command',nargs=argparse.REMAINDER)
    a=ap.parse_args(); r=profile(a.command,a.output,timeout_s=a.timeout_s,max_wall_s=a.max_wall_s,max_rss_mib=a.max_rss_mib); raise SystemExit(0 if r['accepted'] else 2)
if __name__=='__main__': main()
