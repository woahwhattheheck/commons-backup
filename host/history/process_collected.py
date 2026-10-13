"""Process all saved full-body batches, resuming through JEV receipts.

Independent source files run concurrently. ``--follow`` rescans for batches
atomically added by a live collector; it never marks a source complete until
``read_history.py`` has written its full-body completion receipt.
"""
import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

parser=argparse.ArgumentParser()
parser.add_argument('directory')
parser.add_argument('--pattern',default='mail-*.json')
parser.add_argument('--workers',type=int,default=4)
parser.add_argument('--follow',action='store_true')
parser.add_argument('--poll-seconds',type=int,default=15)
args=parser.parse_args()
if args.workers < 1 or args.poll_seconds < 1:
    parser.error('workers and poll-seconds must be positive')
root=Path(args.directory)
if not root.is_dir():
    parser.error('directory must be an existing directory')
source_digests={}

def complete(source):
    receipt=source.parent/'jev-results'/(source.stem+'-complete.json')
    try:
        report=json.loads(receipt.read_text(encoding='utf-8'))
        if not isinstance(report,dict) or report.get('source_file')!=source.name or not report.get('source_sha256'):
            return False
        stat=source.stat()
        fingerprint=(stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns)
        prior=source_digests.get(source)
        if prior and prior[0]==fingerprint:
            digest=prior[1]
        else:
            hasher=hashlib.sha256()
            with source.open('rb') as handle:
                for block in iter(lambda:handle.read(1024*1024),b''):hasher.update(block)
            after=source.stat()
            if fingerprint!=(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns):
                return False
            digest=hasher.hexdigest()
            source_digests[source]=(fingerprint,digest)
        return report['source_sha256']==digest
    except (OSError,UnicodeError,ValueError):
        return False

def process(source):
    if complete(source):
        return None
    result=subprocess.run([sys.executable,str(Path(__file__).with_name('read_history.py')),str(source)],capture_output=True,text=True)
    if result.returncode:
        raise RuntimeError(json.dumps({'source_file':source.name,'status':'failed','code':result.returncode,
                                       'stderr_tail':result.stderr[-500:]}))
    if not complete(source):
        raise RuntimeError(f'missing or stale completion receipt: {source.name}')
    return result.stdout.strip()

with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
    while True:
        pending=[source for source in sorted(root.glob(args.pattern))
                 if not complete(source)]
        if pending:
            print(json.dumps({'status':'processing','pending_files':len(pending),'workers':args.workers}),flush=True)
            futures={pool.submit(process,source):source for source in pending}
            for future in concurrent.futures.as_completed(futures):
                try:
                    report=future.result()
                except Exception as error:
                    print(str(error),flush=True)
                    raise SystemExit(1)
                if report:
                    print(report,flush=True)
        else:
            print(json.dumps({'status':'all_current_files_processed'}),flush=True)
        if not args.follow:
            break
        time.sleep(args.poll_seconds)
