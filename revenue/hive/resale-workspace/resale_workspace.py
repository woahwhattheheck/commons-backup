#!/usr/bin/env python3
"""Local resale workspace. No marketplace network calls."""
import argparse, hashlib, json, sqlite3
from pathlib import Path
from urllib.parse import urlparse

class WorkspaceError(RuntimeError): pass
class RequestConflict(WorkspaceError): pass
class ImmutablePhotoError(WorkspaceError): pass
class InvalidReference(WorkspaceError): pass

def _json(x): return json.dumps(x,sort_keys=True,separators=(",",":"))
def _hash(x): return hashlib.sha256(_json(x).encode()).hexdigest()
def _url(x):
    p=urlparse(x)
    if p.scheme not in ("http","https") or not p.netloc: raise InvalidReference("http(s) URL required")

class ResaleWorkspace:
    def __init__(self,path):
        self.path=Path(path); self.path.parent.mkdir(parents=True,exist_ok=True); c=self._c()
        try: c.executescript("""CREATE TABLE IF NOT EXISTS s(id INTEGER PRIMARY KEY,doc TEXT);
CREATE TABLE IF NOT EXISTS r(id TEXT PRIMARY KEY,op TEXT,h TEXT,out TEXT);
INSERT OR IGNORE INTO s VALUES(1,'{"items":{},"next":1}');""")
        finally: c.close()
    def _c(self):
        c=sqlite3.connect(self.path,timeout=10,isolation_level=None); c.row_factory=sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL"); c.execute("PRAGMA busy_timeout=10000"); return c
    def _read(self):
        c=self._c()
        try: return json.loads(c.execute("SELECT doc FROM s WHERE id=1").fetchone()[0])
        finally: c.close()
    def _write(self,rid,op,payload,fn):
        if not isinstance(rid,str) or not rid.strip(): raise WorkspaceError("request_id required")
        h=_hash(payload); c=self._c()
        try:
            c.execute("BEGIN IMMEDIATE"); old=c.execute("SELECT * FROM r WHERE id=?",(rid,)).fetchone()
            if old:
                if old["op"]!=op or old["h"]!=h: raise RequestConflict("request payload changed")
                c.execute("COMMIT"); return json.loads(old["out"])
            d=json.loads(c.execute("SELECT doc FROM s WHERE id=1").fetchone()[0]); out=fn(d)
            c.execute("UPDATE s SET doc=? WHERE id=1",(_json(d),)); c.execute("INSERT INTO r VALUES(?,?,?,?)",(rid,op,h,_json(out)))
            c.execute("COMMIT"); return out
        except Exception:
            try: c.execute("ROLLBACK")
            except sqlite3.OperationalError: pass
            raise
        finally: c.close()
    @staticmethod
    def _item(d,item_id):
        i=d["items"].get(item_id)
        if not i: raise WorkspaceError("unknown item")
        return i

    def add_item(self,*,item_id,sku,title,photo_ref,photo_sha256,condition_notes="",request_id):
        p={"item_id":item_id,"sku":sku,"title":title,"photo_ref":photo_ref,"photo_sha256":photo_sha256,"condition_notes":condition_notes}
        def f(d):
            if item_id in d["items"]:
                if d["items"][item_id]["photo"]!={"ref":photo_ref,"sha256":photo_sha256}: raise ImmutablePhotoError("photo immutable")
                raise WorkspaceError("item exists; retry original request")
            d["items"][item_id]={"sku":sku,"title":title,"condition_notes":condition_notes,"state":"FOR_SALE","sold_at":None,
              "photo":{"ref":photo_ref,"sha256":photo_sha256},"attributes":{},"price_references":[],"drafts":{},"listings":[],"close_tasks":[]}
            return {"item_id":item_id,"state":"FOR_SALE","photo_sha256":photo_sha256}
        return self._write(request_id,"add",p,f)

    def edit_item(self,*,item_id,title,condition_notes,attributes,uncertain_attributes=(),request_id):
        a=dict(attributes); u=sorted(set(uncertain_attributes))
        if set(u)-set(a): raise WorkspaceError("uncertain attribute missing")
        p={"item_id":item_id,"title":title,"condition_notes":condition_notes,"attributes":a,"uncertain_attributes":u}
        def f(d):
            i=self._item(d,item_id); i["title"]=title; i["condition_notes"]=condition_notes
            i["attributes"]={k:{"value":v,"uncertain":k in u} for k,v in sorted(a.items())}
            return {"item_id":item_id,"attribute_count":len(a),"uncertain":u}
        return self._write(request_id,"edit",p,f)

    def add_price_reference(self,*,item_id,source_url,note,request_id):
        _url(source_url); p={"item_id":item_id,"source_url":source_url,"note":note}
        def f(d):
            i=self._item(d,item_id); x={"source_url":source_url,"note":note}
            if x not in i["price_references"]: i["price_references"].append(x)
            return {"item_id":item_id,"source_url":source_url}
        return self._write(request_id,"price",p,f)

    def save_draft(self,*,item_id,channel,title,body,request_id):
        p={"item_id":item_id,"channel":channel,"title":title,"body":body}
        def f(d):
            self._item(d,item_id)["drafts"][channel]={"title":title,"body":body}
            return {"item_id":item_id,"channel":channel,"draft_state":"EDITABLE_LOCAL"}
        return self._write(request_id,"draft",p,f)

    def record_listing(self,*,item_id,channel,remote_url,request_id):
        _url(remote_url); p={"item_id":item_id,"channel":channel,"remote_url":remote_url}
        def f(d):
            i=self._item(d,item_id)
            if i["state"]=="SOLD": raise WorkspaceError("sold item cannot reactivate")
            for x in i["listings"]:
                if (x["channel"],x["remote_url"])==(channel,remote_url): x["local_active"]=True; break
            else: i["listings"].append({"channel":channel,"remote_url":remote_url,"local_active":True})
            return {"item_id":item_id,"channel":channel,"remote_url":remote_url,"local_active":True,"remote_changed":False}
        return self._write(request_id,"listing",p,f)

    def mark_sold(self,*,item_id,sold_at,request_id):
        p={"item_id":item_id,"sold_at":sold_at}
        def f(d):
            i=self._item(d,item_id)
            if i["state"]!="SOLD": i["state"]="SOLD"; i["sold_at"]=sold_at
            for x in i["listings"]:
                x["local_active"]=False
                if not any((t["channel"],t["remote_url"])==(x["channel"],x["remote_url"]) for t in i["close_tasks"]):
                    i["close_tasks"].append({"task_id":d["next"],"channel":x["channel"],"remote_url":x["remote_url"],"status":"PENDING","confirmation_note":None}); d["next"]+=1
            tasks=[{k:t[k] for k in ("task_id","channel","remote_url","status")} for t in i["close_tasks"]]
            return {"item_id":item_id,"state":"SOLD","sold_at":i["sold_at"],"local_active_channels":0,"remote_changed":False,"close_tasks":tasks}
        return self._write(request_id,"sold",p,f)

    def confirm_remote_close(self,*,task_id,confirmation_note,request_id):
        if type(task_id) is not int or task_id<=0: raise WorkspaceError("valid task_id required")
        if not isinstance(confirmation_note,str) or not confirmation_note.strip(): raise WorkspaceError("confirmation required")
        p={"task_id":task_id,"confirmation_note":confirmation_note}
        def f(d):
            for item_id,i in d["items"].items():
                for t in i["close_tasks"]:
                    if t["task_id"]==task_id:
                        if t["status"]!="PENDING": raise WorkspaceError("close task already confirmed")
                        t["status"]="CONFIRMED"; t["confirmation_note"]=confirmation_note
                        return {"task_id":task_id,"item_id":item_id,"channel":t["channel"],"remote_url":t["remote_url"],
                          "status":"CONFIRMED","confirmation_note":confirmation_note,"remote_changed":"HUMAN_CONFIRMED"}
            raise WorkspaceError("unknown close task")
        return self._write(request_id,"confirm",p,f)

    def active_channel_export(self,channel):
        out=[]
        for item_id,i in sorted(self._read()["items"].items()):
            if i["state"]!="FOR_SALE": continue
            for x in i["listings"]:
                if x["channel"]==channel and x["local_active"]:
                    out.append({"item_id":item_id,"sku":i["sku"],"title":i["title"],"condition_notes":i["condition_notes"],
                      "photo_ref":i["photo"]["ref"],"photo_sha256":i["photo"]["sha256"],"remote_url":x["remote_url"],
                      "draft":i["drafts"].get(channel),"attributes":i["attributes"],
                      "uncertain_attributes":[k for k,v in i["attributes"].items() if v["uncertain"]]})
        return out
    def item_snapshot(self,item_id): return json.loads(_json(self._item(self._read(),item_id)))

def run_demo(fixture_path,db_path):
    f=json.loads(Path(fixture_path).read_text()); w=ResaleWorkspace(db_path); i=f["item"]; iid=i["item_id"]
    w.add_item(**i,request_id="add"); w.edit_item(item_id=iid,request_id="edit",**f["edited"])
    for n,x in enumerate(f["price_references"]): w.add_price_reference(item_id=iid,request_id=f"p{n}",**x)
    for n,x in enumerate(f["drafts"]): w.save_draft(item_id=iid,request_id=f"d{n}",**x)
    for n,x in enumerate(f["listings"]): w.record_listing(item_id=iid,request_id=f"l{n}",**x)
    before={x["channel"]:len(w.active_channel_export(x["channel"])) for x in f["listings"]}
    sold=w.mark_sold(item_id=iid,sold_at=f["sold_at"],request_id="sold")
    after={x["channel"]:len(w.active_channel_export(x["channel"])) for x in f["listings"]}; s=w.item_snapshot(iid)
    return {"item_id":iid,"before_active_counts":before,"after_active_counts":after,"close_task_count":len(sold["close_tasks"]),
      "close_task_statuses":[x["status"] for x in sold["close_tasks"]],"uncertain_attributes":[k for k,v in s["attributes"].items() if v["uncertain"]],
      "photo_sha256":s["photo"]["sha256"],"remote_changed":sold["remote_changed"]}

def main(argv=None):
    p=argparse.ArgumentParser(); q=p.add_subparsers(dest="cmd",required=True); d=q.add_parser("demo")
    d.add_argument("fixture"); d.add_argument("--db",required=True); a=p.parse_args(argv)
    if a.cmd=="demo": print(json.dumps(run_demo(a.fixture,a.db),indent=2,sort_keys=True)); return 0
    return 2
if __name__=="__main__": raise SystemExit(main())
