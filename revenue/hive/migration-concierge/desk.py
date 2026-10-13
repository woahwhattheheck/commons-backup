# SPDX-License-Identifier: Apache-2.0
"""Local customer/task workspace for a completed CSV migration."""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import tempfile
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, urlparse

from intake import MigrationError, digest
from migrate import edit_record, export_workspace, read_state

PAGE = r'''<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Migration Desk</title>
<style>
:root{font-family:system-ui,sans-serif;color:#192c3c;background:#f3f5f7}*{box-sizing:border-box}
body{margin:0}header{background:#142d3e;color:white;padding:24px 5vw;display:flex;justify-content:space-between;align-items:center}
h1{font-size:25px;margin:0}header p{margin:6px 0 0;color:#cad8e1}main{max-width:1250px;margin:auto;padding:28px}
nav{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:20px}button,.download{cursor:pointer;border:1px solid #9baebd;border-radius:6px;padding:10px 15px;background:white;color:#192c3c;font:inherit;text-decoration:none}button[aria-pressed=true],button.primary{background:#154e68;color:white}
input,select{padding:10px;border:1px solid #9baebd;border-radius:5px;font:inherit;width:100%}.layout{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(300px,1fr);gap:20px}
.card{background:white;border:1px solid #d9e1e6;border-radius:10px;padding:22px;overflow:auto}table{border-collapse:collapse;width:100%;font-size:14px}td,th{text-align:left;padding:12px 8px;border-bottom:1px solid #e1e6ea}th{font-size:12px;text-transform:uppercase;letter-spacing:.06em}label{display:block;margin:14px 0 5px}small,.muted{color:#586b79}#message{min-height:26px;margin:12px 0;white-space:pre-wrap}.bad{color:#a02222}.good{color:#15603a}h2{margin-top:0}h3{margin-bottom:8px}ul{padding-left:20px}li{margin:10px 0}.identity{overflow-wrap:anywhere;font-size:12px}footer{margin-top:22px;color:#586b79;font-size:13px}pre{white-space:pre-wrap;word-break:break-word}@media(max-width:800px){.layout{grid-template-columns:1fr}header{align-items:flex-start;gap:20px}main{padding:15px}}
</style>
<header><div><h1>Migration Desk</h1><p>Your customers, linked work and original files—in one place.</p></div><button id="export">Export workspace</button></header>
<main><nav id="tabs"><button data-kind="customers" aria-pressed="true">Customers</button><button data-kind="tasks">Tasks</button><button data-kind="runs">Import history</button></nav>
<label for="search">Find a record</label><input id="search" type="search" placeholder="Name, email, task or original source ID">
<div id="message" role="status" aria-live="polite"></div><div class="layout"><section class="card"><h2 id="list-title">Customers</h2><div id="list"></div></section><section class="card" id="detail"><h2>Ready for daily work</h2><p>Select a customer to see linked tasks and source files, or a task to update its status.</p><p>Import and rollback are explicit command-line actions. This desk never sends emails or changes an external CRM.</p></section></div>
<footer>Migration Desk • Local workspace • Source exports remain unchanged. Exported files contain the workspace's customer data.</footer></main>
<script>
let records=[],runs=[],kind='customers',selected=null;
const $=id=>document.getElementById(id);
function node(tag,text){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;}
function message(text,bad=false){$('message').textContent=text;$('message').className=bad?'bad':'good';}
async function api(path,body){const r=await fetch(path,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{});const data=await r.json();if(!r.ok)throw Error(data.error||'Request could not complete');return data;}
async function refresh(){records=await api('/api/records');runs=await api('/api/runs');render();}
function show(r){selected=r.id;const box=$('detail');box.replaceChildren(node('h2',r.data.name||r.data.title||r.data.name));box.append(node('p','Source: '+r.namespace+' / '+r.external_id));const origin=node('p',r.source.file+' · row '+r.source.row+' · revision '+r.revision);origin.className='identity';box.append(origin);
 const fields=r.kind==='customers'?['name','email','phone']:['title','status','due_date'];const form=node('form');
 for(const key of fields){const label=node('label',key.replaceAll('_',' '));label.htmlFor='edit-'+key;const input=key==='status'?node('select'):node('input');input.id='edit-'+key;input.name=key;if(key==='status'){for(const value of ['open','in_progress','done','cancelled']){const opt=node('option',value);opt.value=value;input.append(opt);}}else if(key==='due_date')input.type='date';input.value=r.data[key]||'';form.append(label,input);}
 const save=node('button','Save changes');save.className='primary';save.style.marginTop='18px';form.append(save);form.onsubmit=async e=>{e.preventDefault();try{const values=Object.fromEntries(new FormData(form));const updated=await api('/api/edit',{id:r.id,revision:r.revision,fields:values});await refresh();show(updated);message('Saved. Linked records and source files are unchanged.');}catch(err){message(err.message,true);}};box.append(form);
 if(r.kind==='customers'){box.append(node('h3','Linked tasks'));const tasks=records.filter(x=>x.kind==='tasks'&&x.data.customer_id===r.id);const ul=node('ul');for(const task of tasks){const li=node('li'),b=node('button',task.data.title+' · '+task.data.status);b.onclick=()=>show(task);li.append(b);ul.append(li);}box.append(tasks.length?ul:node('p','No imported tasks.'));
 box.append(node('h3','Original attachments'));const assets=records.filter(x=>x.kind==='attachments'&&x.data.customer_id===r.id);const list=node('ul');for(const asset of assets){const li=node('li'),a=node('a',asset.data.name+' ('+asset.data.bytes+' bytes)');a.href='/files/'+encodeURIComponent(asset.id);li.append(a);list.append(li);}box.append(assets.length?list:node('p','No imported attachments.'));}
 else{const customer=records.find(x=>x.id===r.data.customer_id);if(customer){const b=node('button','Open customer: '+customer.data.name);b.style.marginTop='18px';b.onclick=()=>show(customer);box.append(b);}}
}
function render(){const query=$('search').value.toLocaleLowerCase();$('list-title').textContent=kind==='runs'?'Import history':kind[0].toUpperCase()+kind.slice(1);const table=node('table');const head=node('tr');for(const label of kind==='runs'?['Operation','Status','Changed']:['Record','Details','Source ID'])head.append(node('th',label));table.append(head);let count=0;
 for(const r of (kind==='runs'?runs:records.filter(x=>x.kind===kind))){if(!JSON.stringify(r).toLocaleLowerCase().includes(query))continue;count++;const tr=node('tr');if(kind==='runs'){tr.append(node('td',r.operation),node('td',r.status),node('td',String(r.changed)));}else{const td=node('td'),button=node('button',r.data.name||r.data.title);button.onclick=()=>show(r);td.append(button);tr.append(td,node('td',r.data.email||r.data.status||''),node('td',r.external_id));}table.append(tr);}$('list').replaceChildren(count?table:node('p','No matching records.'));}
$('tabs').onclick=e=>{const chosen=e.target.dataset.kind;if(!chosen)return;kind=chosen;for(const b of $('tabs').children)b.setAttribute('aria-pressed',String(b.dataset.kind===kind));render();};$('search').oninput=render;
$('export').onclick=async()=>{try{const r=await fetch('/api/export',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});if(!r.ok){const error=await r.json();throw Error(error.error);}const blob=await r.blob(),url=URL.createObjectURL(blob),a=node('a');a.href=url;a.download='migration-workspace.zip';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);message('Exported records, relationships, original files and a hash manifest.');}catch(err){message(err.message,true);}};
refresh().catch(err=>message(err.message,true));
</script></html>'''


def server_for(database: Path, assets: Path, host: str = "127.0.0.1", port: int = 8080) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def respond(self, status: int, raw: bytes, content_type: str = "application/json", headers: dict | None = None) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(raw)

        def fail(self, exc: Exception, status: int = 409) -> None:
            self.respond(status, json.dumps({"error": str(exc)}).encode())

        def do_GET(self) -> None:
            path = urlparse(self.path).path
            try:
                if path == "/":
                    self.respond(200, PAGE.encode(), "text/html; charset=utf-8")
                elif path == "/api/records":
                    self.respond(200, json.dumps(list(read_state(database).values()), ensure_ascii=False).encode())
                elif path == "/api/runs":
                    db = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
                    try:
                        rows = [{"operation": op, "status": status, "changed": json.loads(report)["changed"]}
                                for op, status, report in db.execute("SELECT operation,status,report FROM runs ORDER BY created_at DESC")]
                    finally:
                        db.close()
                    self.respond(200, json.dumps(rows).encode())
                elif path.startswith("/files/"):
                    record = read_state(database).get(path.removeprefix("/files/"))
                    if record is None or record["kind"] != "attachments":
                        raise MigrationError("No such attachment")
                    data = record["data"]
                    if not re.fullmatch(r"[0-9a-f]{64}", data["sha256"]):
                        raise MigrationError("Attachment content address is malformed")
                    raw = (assets / data["sha256"]).read_bytes()
                    if digest(raw) != data["sha256"] or len(raw) != data["bytes"]:
                        raise MigrationError("Attachment differs from its imported content")
                    filename = quote(data["name"], safe="")
                    self.respond(200, raw, "application/octet-stream",
                                 {"Content-Disposition": "attachment; filename*=UTF-8''" + filename})
                else:
                    self.fail(MigrationError("Not found"), 404)
            except (MigrationError, OSError, sqlite3.Error, KeyError, ValueError) as exc:
                self.fail(exc)

        def do_POST(self) -> None:
            try:
                if self.headers.get_content_type() != "application/json":
                    self.fail(MigrationError("Use a JSON request body"), 415)
                    return
                length = int(self.headers.get("Content-Length", "0"))
                if length < 0 or length > 1_000_000:
                    raise MigrationError("JSON body must be at most 1 MB")
                data = json.loads(self.rfile.read(length))
                if not isinstance(data, dict):
                    raise MigrationError("JSON body must be an object")
                if self.path == "/api/edit":
                    revision = data["revision"]
                    if type(revision) is not int or not isinstance(data["fields"], dict):
                        raise MigrationError("Supply an integer revision and fields object")
                    updated = edit_record(database, data["id"], revision, data["fields"])
                    self.respond(200, json.dumps(updated, ensure_ascii=False).encode())
                elif self.path == "/api/export":
                    with tempfile.TemporaryDirectory() as folder:
                        output = Path(folder) / "workspace"
                        export_workspace(database, assets, output)
                        archive = Path(folder) / "workspace.zip"
                        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
                            for file in sorted(output.rglob("*")):
                                if file.is_file():
                                    bundle.write(file, str(file.relative_to(output)))
                        self.send_response(200)
                        self.send_header("Content-Type", "application/zip")
                        self.send_header("Content-Disposition", 'attachment; filename="migration-workspace.zip"')
                        self.send_header("Content-Length", str(archive.stat().st_size))
                        self.send_header("Cache-Control", "no-store")
                        self.end_headers()
                        with archive.open("rb") as source:
                            while chunk := source.read(64 * 1024):
                                self.wfile.write(chunk)
                else:
                    self.fail(MigrationError("Not found"), 404)
            except (MigrationError, OSError, sqlite3.Error, KeyError, ValueError, TypeError) as exc:
                self.fail(exc)

        def log_message(self, fmt: str, *args) -> None:
            # Keep request payloads and customer fields out of console logs.
            pass

    return ThreadingHTTPServer((host, port), Handler)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    if not args.database.is_file():
        parser.error("Apply a trial plan to create the workspace first")
    server = server_for(args.database, args.assets, args.host, args.port)
    print(f"Migration Desk: http://{args.host}:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
