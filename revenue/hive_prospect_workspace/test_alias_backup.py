"""Exercise merged-domain identities through the existing SQLite HTTP backup service.

No changes to the backup server, no browser storage substitutes, no provider calls.
A temporary private database is created and destroyed by this test.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import time
from urllib.request import Request, urlopen


def load_server(path: Path):
    spec = importlib.util.spec_from_file_location('fieldnote_existing_backup_server', path)
    if spec is None or spec.loader is None:
        raise ValueError(f'Cannot load the existing server: {path}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@contextmanager
def running(module, database: Path, assets: Path):
    server = module.Server(('127.0.0.1', 0), module.Store(database), assets)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}/api/state'
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        if thread.is_alive():
            raise RuntimeError('Test server did not terminate')


def request(url: str, body=None):
    data = json.dumps(body, ensure_ascii=False).encode('utf-8') if body is not None else None
    req = Request(url, data=data, headers={'Content-Type':'application/json'} if data else {})
    with urlopen(req, timeout=5) as response:
        if response.status != 200:
            raise AssertionError(f'Unexpected HTTP status {response.status}')
        return json.load(response)


def node(model: Path, script: str, stdin: str = '') -> str:
    return subprocess.run(['node','-e',script,str(model)],input=stdin,text=True,
                          capture_output=True,check=True,timeout=10).stdout


def check(condition: bool, message: str, steps: list[str]):
    if not condition:
        raise AssertionError(message)
    steps.append(message)


def run(server_path: Path, model_path: Path) -> dict:
    started = time.perf_counter()
    steps: list[str] = []
    module = load_server(server_path)
    payload = node(model_path, r"""
const F=require(process.argv[1]);
const csv='Company,Website,Email,Notes\nAlpha,alpha.example,a@alpha.example,First source\nBeta,beta.example,b@beta.example,Second source\n';
let s=F.commitImport(F.previewImport(F.empty(),csv,{filename:'alias-fixture.csv'}),'2026-09-08T10:00:00.000Z');
s=F.mergeDuplicates(s,s.accounts.map(a=>a.id)).state;
s=F.updateAccount(s,s.accounts[0].id,{notes:'Owner note – kept across backup'});
F.validateState(s);process.stdout.write(JSON.stringify(s,null,2)+'\n');
""")
    parsed = json.loads(payload)
    check(set(parsed['accounts'][0]['domainAliases']) == {'alpha.example','beta.example'}, 'Merged aliases present in model output', steps)
    digest = hashlib.sha256(payload.encode('utf-8')).hexdigest()
    with tempfile.TemporaryDirectory(prefix='fieldnote-alias-backup-') as tmp:
        db = Path(tmp)/'workspace.sqlite3'
        with running(module, db, model_path.parent) as url:
            initial = request(url)
            check(initial['revision'] == 0 and initial['payload'] is None, 'Fresh private SQLite database starts empty', steps)
            saved = request(url, {'payload':payload,'expected_revision':0,'operation_id':'quill-alias-backup-v1'})
            check(saved['revision'] == 1 and saved['sha256'] == digest, 'Actual HTTP save records revision and payload SHA256', steps)
            readback = request(url)
            check(readback['payload'] == payload, 'HTTP readback preserves exact JSON text', steps)
        # A new Store and HTTP server reopen the same actual database file.
        with running(module, db, model_path.parent) as url:
            recovered = request(url)
            check(recovered['payload'] == payload and recovered['revision'] == 1, 'New server instance recovers exact backup from SQLite', steps)
            after = json.loads(node(model_path, r"""
const fs=require('node:fs'),F=require(process.argv[1]),s=JSON.parse(fs.readFileSync(0,'utf8'));
F.validateState(s);
const r=F.previewImport(s,'Company,Website,Email\nBeta,beta.example,b@beta.example\n',{filename:'reimport.csv'});
process.stdout.write(JSON.stringify({created:r.report.created,errors:r.report.errors.length,
 accounts:r.state.accounts.length,contacts:r.state.accounts[0].contacts.length,
 notes:r.state.accounts[0].notes,aliases:r.state.accounts[0].domainAliases}));
""", recovered['payload']))
            check(after['created'] == 0 and after['errors'] == 0 and after['accounts'] == 1, 'Restored model reimport does not recreate the merged-away company', steps)
            check(after['contacts'] == 2 and 'Owner note – kept across backup' in after['notes'], 'Contact cardinality and owner note survive the complete roundtrip', steps)
    return {'status':'PASS','scope':'real loopback HTTP + SQLite reopen + actual model import',
            'checks':steps,'elapsed_seconds':round(time.perf_counter()-started,6),
            'completed_utc':datetime.now(timezone.utc).isoformat(),
            'payload_bytes':len(payload.encode('utf-8')),'payload_sha256':digest,
            'model_sha256':hashlib.sha256(model_path.read_bytes()).hexdigest(),
            'server_sha256':hashlib.sha256(server_path.read_bytes()).hexdigest(),
            'browser_native_storage_tested':False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model',type=Path,default=Path(__file__).with_name('model.js'))
    parser.add_argument('--server',type=Path,default=Path(__file__).resolve().parent.parent/'hive/prospect-workspace/server.py')
    parser.add_argument('--report',type=Path)
    args = parser.parse_args()
    for path in (args.model,args.server):
        if not path.is_file():
            parser.error(f'Missing source file: {path}')
    result = run(args.server.resolve(),args.model.resolve())
    output = json.dumps(result,ensure_ascii=False,indent=2)+'\n'
    if args.report:
        args.report.write_text(output,encoding='utf-8')
    print(output,end='')


if __name__ == '__main__':
    main()
