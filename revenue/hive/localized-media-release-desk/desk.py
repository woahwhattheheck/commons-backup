#!/usr/bin/env python3
"""Local-only localized-media variant/release operations desk."""
from __future__ import annotations
import argparse, hashlib, io, json, os, re, sqlite3, stat, sys, zipfile
from contextlib import closing
from datetime import datetime, timezone

KINDS={"subtitle","caption","dub_audio","localized_text"}; MAX=512*1024*1024
LOCALE=re.compile(r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$"); TERR=re.compile(r"^[A-Z0-9]{2,3}$"); SHA=re.compile(r"^[0-9a-f]{64}$")
class DeskError(Exception): pass
class InvalidState(DeskError): pass
class IdempotencyConflict(DeskError): pass
class HoldError(DeskError):
    def __init__(self,holds): self.holds=holds; super().__init__("; ".join(holds))

def now(): return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z")
def cj(v): return json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False)
def cb(v): return (cj(v)+"\n").encode()
def sha(b): return hashlib.sha256(b).hexdigest()
def sha256_bytes(b): return sha(b)
def _pairs(pairs):
    out={}
    for k,v in pairs:
        if k in out: raise InvalidState(f"duplicate JSON key: {k}")
        out[k]=v
    return out
def strict_json_loads(raw):
    if isinstance(raw,bytes):
        if len(raw)>1_000_000: raise InvalidState("JSON input exceeds size cap")
        try: raw=raw.decode()
        except UnicodeDecodeError as e: raise InvalidState("JSON input must be UTF-8") from e
    try: return json.loads(raw,object_pairs_hook=_pairs)
    except InvalidState: raise
    except Exception as e: raise InvalidState(f"invalid JSON: {e}") from e
def _id(name,v):
    if not isinstance(v,str) or not v or len(v)>128 or any(ord(c)<32 for c in v): raise InvalidState(f"invalid {name}")
    return v
def key(locale,territory,kind):
    if not isinstance(locale,str) or not LOCALE.fullmatch(locale): raise InvalidState(f"invalid locale: {locale!r}")
    ps=locale.split("-"); locale=ps[0].lower()+"".join("-"+(p.upper() if len(p)==2 else p) for p in ps[1:])
    if not isinstance(territory,str): raise InvalidState(f"invalid territory: {territory!r}")
    territory=territory.upper()
    if not TERR.fullmatch(territory): raise InvalidState(f"invalid territory: {territory!r}")
    if kind not in KINDS: raise InvalidState(f"invalid artifact kind: {kind!r}")
    return locale,territory,kind
def required(v):
    if not isinstance(v,list) or not v: raise InvalidState("required variants must be a non-empty array")
    out=[]; seen=set()
    for i,r in enumerate(v):
        if not isinstance(r,dict) or set(r)!={"locale","territory","kind"}: raise InvalidState(f"required[{i}] must contain exactly locale, territory, kind")
        k=key(r["locale"],r["territory"],r["kind"])
        if k in seen: raise InvalidState(f"duplicate required variant: {'/'.join(k)}")
        seen.add(k); out.append(dict(zip(("locale","territory","kind"),k)))
    return sorted(out,key=lambda r:(r["locale"],r["territory"],r["kind"]))
def read_file(path):
    """Read a bounded, producer-complete input; reject observed concurrent changes.

    Descriptor metadata and EOF checks are not an atomic filesystem snapshot.
    Callers must keep inputs quiescent for ingestion/verification.
    """
    nonblock=getattr(os,"O_NONBLOCK",0)
    if not nonblock: raise InvalidState("nonblocking input acquisition unsupported on this host")
    path=os.fspath(path)
    flags=os.O_RDONLY|nonblock|getattr(os,"O_NOFOLLOW",0)|getattr(os,"O_CLOEXEC",0)
    fd=os.open(path,flags)
    try:
        st=os.fstat(fd)
        if not stat.S_ISREG(st.st_mode): raise InvalidState("not a regular file")
        if st.st_size<0 or st.st_size>MAX: raise InvalidState("artifact exceeds size cap")
        def identity(s):
            return (s.st_dev,s.st_ino,s.st_mode,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
        before=identity(st); chunks=[]; read=0
        while read<st.st_size:
            x=os.read(fd,min(1024*1024,st.st_size-read))
            if not x: raise InvalidState("file changed/truncated while reading")
            chunks.append(x); read+=len(x)
        # Probe even an initially empty file, but never chase a growing producer.
        if os.read(fd,1): raise InvalidState("file grew while reading")
        if identity(os.fstat(fd))!=before: raise InvalidState("file changed while reading")
        data=b"".join(chunks)
        return data,sha(data),len(data),os.path.basename(path)
    finally: os.close(fd)
def _open_dir_nofollow(path):
    """Open an absolute directory by walking every component without symlink traversal."""
    nofollow=getattr(os,"O_NOFOLLOW",0); odir=getattr(os,"O_DIRECTORY",0)
    if not nofollow or os.open not in getattr(os,"supports_dir_fd",()):
        raise InvalidState("safe no-follow directory traversal unsupported on this host")
    full=os.path.abspath(os.fspath(path)); drive,tail=os.path.splitdrive(full)
    if drive:
        raise InvalidState("safe no-follow directory traversal unsupported for drive paths")
    flags=os.O_RDONLY|odir|nofollow|getattr(os,"O_CLOEXEC",0)
    fd=os.open(os.sep,os.O_RDONLY|odir|getattr(os,"O_CLOEXEC",0))
    try:
        for part in (p for p in tail.split(os.sep) if p and p!="."):
            if part=="..": raise InvalidState("parent traversal is not allowed")
            nxt=os.open(part,flags,dir_fd=fd)
            st=os.fstat(nxt)
            if not stat.S_ISDIR(st.st_mode): os.close(nxt); raise InvalidState("output parent component is not a directory")
            os.close(fd); fd=nxt
        return fd
    except Exception:
        os.close(fd); raise

_DESK_SCHEMA = (
"CREATE TABLE IF NOT EXISTS titles(title_id TEXT PRIMARY KEY,source_name TEXT NOT NULL,source_sha256 TEXT NOT NULL,source_size INTEGER NOT NULL CHECK(source_size>=0),required_json TEXT NOT NULL,rights_ready INTEGER NOT NULL DEFAULT 0 CHECK(rights_ready IN(0,1)),created_at TEXT NOT NULL,updated_at TEXT NOT NULL)",
"CREATE TABLE IF NOT EXISTS variants(title_id TEXT NOT NULL REFERENCES titles(title_id) ON DELETE CASCADE,locale TEXT NOT NULL,territory TEXT NOT NULL,kind TEXT NOT NULL,revision INTEGER NOT NULL CHECK(revision>=1),artifact_name TEXT NOT NULL,content_sha256 TEXT NOT NULL,content_size INTEGER NOT NULL CHECK(content_size>=0),source_sha256 TEXT NOT NULL,updated_at TEXT NOT NULL,PRIMARY KEY(title_id,locale,territory,kind))",
"CREATE TABLE IF NOT EXISTS approvals(id INTEGER PRIMARY KEY,title_id TEXT NOT NULL,locale TEXT NOT NULL,territory TEXT NOT NULL,kind TEXT NOT NULL,revision INTEGER NOT NULL,content_sha256 TEXT NOT NULL,reviewer_id TEXT NOT NULL,approved_at TEXT NOT NULL,UNIQUE(title_id,locale,territory,kind,revision,content_sha256,reviewer_id),FOREIGN KEY(title_id,locale,territory,kind) REFERENCES variants(title_id,locale,territory,kind) ON DELETE CASCADE)",
"CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY,title_id TEXT NOT NULL REFERENCES titles(title_id) ON DELETE CASCADE,event_kind TEXT NOT NULL,detail_json TEXT NOT NULL,at_utc TEXT NOT NULL)",
"CREATE TABLE IF NOT EXISTS requests(request_id TEXT PRIMARY KEY,op TEXT NOT NULL,payload_sha256 TEXT NOT NULL,result_json TEXT NOT NULL)",
)

def _canonical_desk_tables():
    """Stored SQL for the ordinary desk, including keys and constraints."""
    mem=sqlite3.connect(":memory:")
    try:
        for stmt in _DESK_SCHEMA: mem.execute(stmt)
        return {name: sql for name, sql in mem.execute("SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
    finally: mem.close()

_CANONICAL_DESK_TABLES=None
def _expected_desk_tables():
    global _CANONICAL_DESK_TABLES
    if _CANONICAL_DESK_TABLES is None: _CANONICAL_DESK_TABLES=_canonical_desk_tables()
    return _CANONICAL_DESK_TABLES

class ReleaseDesk:
    def __init__(self,db_path): self.db_path=os.fspath(db_path); self._init()
    def conn(self):
        c=sqlite3.connect(self.db_path,timeout=30,isolation_level=None); c.row_factory=sqlite3.Row
        c.execute("PRAGMA foreign_keys=ON"); c.execute("PRAGMA busy_timeout=30000"); return c
    def _init(self):
        """Create a new desk, reopen a compatible one, or refuse anything else.

        A missing file or a database with no user schema objects is initialized
        inside one transaction. An existing desk is recognized from its tables,
        columns, keys and constraints on the reserved connection, not from its
        pathname. A foreign or incompatible database, including one whose only
        object is a view or trigger, is rolled back unchanged.
        """
        expected=_expected_desk_tables()
        with closing(self.conn()) as c:
            c.execute("BEGIN IMMEDIATE")
            try:
                found={name: sql for name, sql in c.execute("SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
                if not found:
                    if c.execute("SELECT 1 FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchone():
                        raise InvalidState("existing database is not a compatible localized-media release desk; schema and rows were not changed")
                    for stmt in _DESK_SCHEMA: c.execute(stmt)
                elif set(found)!=set(expected) or any(found[name]!=expected[name] for name in expected):
                    raise InvalidState("existing database is not a compatible localized-media release desk; schema and rows were not changed")
                elif c.execute("SELECT 1 FROM sqlite_master WHERE type IN ('view','trigger')").fetchone():
                    raise InvalidState("existing database has views or triggers the release desk does not own; schema and rows were not changed")
                c.execute("COMMIT")
            except Exception:
                if c.in_transaction: c.execute("ROLLBACK")
                raise
    def event(self,c,title,kind_,detail,t):
        c.execute("INSERT INTO events(title_id,event_kind,detail_json,at_utc) VALUES(?,?,?,?)",(title,kind_,cj(detail),t)); c.execute("UPDATE titles SET updated_at=? WHERE title_id=?",(t,title))
    def mutate(self,rid,op,payload,fn):
        _id("request_id",rid); ph=sha(cb({"op":op,"payload":payload})); t=now()
        with closing(self.conn()) as c:
            c.execute("BEGIN IMMEDIATE")
            try:
                old=c.execute("SELECT * FROM requests WHERE request_id=?",(rid,)).fetchone()
                if old:
                    if old["op"]!=op or old["payload_sha256"]!=ph: raise IdempotencyConflict(f"request_id {rid!r} reused with different semantics")
                    ans=strict_json_loads(old["result_json"]); c.execute("COMMIT"); return ans
                ans=fn(c,t); c.execute("INSERT INTO requests VALUES(?,?,?,?)",(rid,op,ph,cj(ans))); c.execute("COMMIT"); return ans
            except Exception: c.execute("ROLLBACK"); raise
    def create_title(self,rid,title,source_path,req):
        title=_id("title_id",title); req=required(req); _,h,n,name=read_file(source_path); p={"title_id":title,"source_sha256":h,"source_size":n,"source_name":name,"required":req}
        def f(c,t):
            if c.execute("SELECT 1 FROM titles WHERE title_id=?",(title,)).fetchone(): raise InvalidState(f"title already exists: {title}")
            c.execute("INSERT INTO titles VALUES(?,?,?,?,?,0,?,?)",(title,name,h,n,cj(req),t,t)); self.event(c,title,"TITLE_CREATED",{"source_sha256":h,"required":req},t); return {"title_id":title,"source_sha256":h,"required_count":len(req)}
        return self.mutate(rid,"create_title",p,f)
    def update_source(self,rid,title,path):
        title=_id("title_id",title); _,h,n,name=read_file(path); p={"title_id":title,"source_sha256":h,"source_size":n,"source_name":name}
        def f(c,t):
            r=c.execute("SELECT source_sha256 FROM titles WHERE title_id=?",(title,)).fetchone()
            if not r: raise InvalidState(f"unknown title: {title}")
            if r[0]==h: return {"title_id":title,"source_sha256":h,"changed":False}
            old=r[0]; c.execute("UPDATE titles SET source_name=?,source_sha256=?,source_size=? WHERE title_id=?",(name,h,n,title)); self.event(c,title,"SOURCE_UPDATED",{"old_sha256":old,"new_sha256":h},t); return {"title_id":title,"source_sha256":h,"changed":True}
        return self.mutate(rid,"update_source",p,f)
    def set_rights_ready(self,rid,title,ready):
        title=_id("title_id",title)
        if type(ready) is not bool: raise InvalidState("ready must be a boolean")
        def f(c,t):
            r=c.execute("SELECT rights_ready FROM titles WHERE title_id=?",(title,)).fetchone()
            if not r: raise InvalidState(f"unknown title: {title}")
            if bool(r[0])==ready: return {"title_id":title,"rights_ready":ready,"changed":False}
            c.execute("UPDATE titles SET rights_ready=? WHERE title_id=?",(int(ready),title)); self.event(c,title,"OWNER_RIGHTS_READY_SET",{"rights_ready":ready},t); return {"title_id":title,"rights_ready":ready,"changed":True}
        return self.mutate(rid,"set_rights_ready",{"title_id":title,"ready":ready},f)
    def add_variant(self,rid,title,locale,territory,kind_,path):
        title=_id("title_id",title); locale,territory,kind_=key(locale,territory,kind_); _,h,n,name=read_file(path); p={"title_id":title,"locale":locale,"territory":territory,"kind":kind_,"content_sha256":h,"content_size":n,"artifact_name":name}
        def f(c,t):
            tr=c.execute("SELECT source_sha256,required_json FROM titles WHERE title_id=?",(title,)).fetchone()
            if not tr: raise InvalidState(f"unknown title: {title}")
            if (locale,territory,kind_) not in {(x["locale"],x["territory"],x["kind"]) for x in strict_json_loads(tr[1])}: raise InvalidState("variant key is not owner-declared as required")
            r=c.execute("SELECT revision,content_sha256,source_sha256 FROM variants WHERE title_id=? AND locale=? AND territory=? AND kind=?",(title,locale,territory,kind_)).fetchone()
            if r and r[1]==h and r[2]==tr[0]: return {"title_id":title,"locale":locale,"territory":territory,"kind":kind_,"revision":r[0],"content_sha256":h,"changed":False}
            rev=1 if not r else r[0]+1
            c.execute("INSERT INTO variants VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(title_id,locale,territory,kind) DO UPDATE SET revision=excluded.revision,artifact_name=excluded.artifact_name,content_sha256=excluded.content_sha256,content_size=excluded.content_size,source_sha256=excluded.source_sha256,updated_at=excluded.updated_at",(title,locale,territory,kind_,rev,name,h,n,tr[0],t)); self.event(c,title,"VARIANT_REVISED",{"locale":locale,"territory":territory,"kind":kind_,"revision":rev,"content_sha256":h,"source_sha256":tr[0]},t); return {"title_id":title,"locale":locale,"territory":territory,"kind":kind_,"revision":rev,"content_sha256":h,"changed":True}
        return self.mutate(rid,"add_variant",p,f)
    def approve_variant(self,rid,title,locale,territory,kind_,reviewer,revision,content_sha256):
        title=_id("title_id",title); reviewer=_id("reviewer_id",reviewer); locale,territory,kind_=key(locale,territory,kind_)
        if type(revision) is not int or revision<1 or not isinstance(content_sha256,str) or not SHA.fullmatch(content_sha256): raise InvalidState("invalid revision/hash")
        p={"title_id":title,"locale":locale,"territory":territory,"kind":kind_,"reviewer_id":reviewer,"revision":revision,"content_sha256":content_sha256}
        def f(c,t):
            r=c.execute("SELECT v.revision,v.content_sha256,v.source_sha256,t.source_sha256 FROM variants v JOIN titles t USING(title_id) WHERE v.title_id=? AND v.locale=? AND v.territory=? AND v.kind=?",(title,locale,territory,kind_)).fetchone()
            if not r: raise InvalidState("cannot approve missing/cross-title variant")
            if r[2]!=r[3]: raise InvalidState("cannot approve variant bound to stale source generation")
            if r[0]!=revision or r[1]!=content_sha256: raise InvalidState("approval evidence does not match current variant revision/hash")
            cur=c.execute("INSERT OR IGNORE INTO approvals(title_id,locale,territory,kind,revision,content_sha256,reviewer_id,approved_at) VALUES(?,?,?,?,?,?,?,?)",(title,locale,territory,kind_,revision,content_sha256,reviewer,t)); changed=cur.rowcount==1
            if changed: self.event(c,title,"VARIANT_APPROVED",p,t)
            return {**p,"changed":changed}
        return self.mutate(rid,"approve_variant",p,f)
    def status(self,title):
        """Project one committed generation, not a continuously valid release grant.

        BEGIN retains the first SELECT's snapshot across variants, approvals and
        audit reads. closing() rolls back any failed read before releasing the
        connection; successful reads COMMIT before rendering/exporting bytes.
        """
        title=_id("title_id",title)
        with closing(self.conn()) as c:
            c.execute("BEGIN")
            tr=c.execute("SELECT * FROM titles WHERE title_id=?",(title,)).fetchone()
            if not tr: raise InvalidState(f"unknown title: {title}")
            req=strict_json_loads(tr["required_json"]); holds=[] if tr["rights_ready"] else ["OWNER_RIGHTS_NOT_READY"]; vs=[]
            for q in req:
                k=(q["locale"],q["territory"],q["kind"]); kt="/".join(k); r=c.execute("SELECT * FROM variants WHERE title_id=? AND locale=? AND territory=? AND kind=?",(title,*k)).fetchone()
                if not r: holds.append("MISSING_VARIANT:"+kt); vs.append({**q,"status":"MISSING"}); continue
                aps=[dict(a) for a in c.execute("SELECT reviewer_id,approved_at FROM approvals WHERE title_id=? AND locale=? AND territory=? AND kind=? AND revision=? AND content_sha256=? ORDER BY reviewer_id,approved_at",(title,*k,r["revision"],r["content_sha256"])).fetchall()]; cur=r["source_sha256"]==tr["source_sha256"]
                if not cur: holds.append("STALE_SOURCE_BINDING:"+kt)
                if not aps: holds.append("MISSING_CURRENT_APPROVAL:"+kt)
                vs.append({**q,"revision":r["revision"],"artifact_name":r["artifact_name"],"content_sha256":r["content_sha256"],"content_size":r["content_size"],"source_sha256":r["source_sha256"],"source_current":cur,"approvals":aps,"status":"CURRENT_APPROVED" if cur and aps else "HOLD"})
            ev=[{"seq":r[0],"event_kind":r[1],"detail":strict_json_loads(r[2]),"at_utc":r[3]} for r in c.execute("SELECT seq,event_kind,detail_json,at_utc FROM events WHERE title_id=? ORDER BY seq",(title,))]
            c.execute("COMMIT")
        holds=sorted(set(holds)); return {"schema_version":1,"title_id":title,"source":{"name":tr["source_name"],"sha256":tr["source_sha256"],"size":tr["source_size"]},"required_variants":req,"variants":vs,"owner_supplied_rights_ready":bool(tr["rights_ready"]),"external_publish_authorized":False,"created_at":tr["created_at"],"updated_at":tr["updated_at"],"holds":holds,"release_status":"READY_FOR_LOCAL_HANDOFF" if not holds else "HOLD","events":ev}
    def build_package(self,title):
        st=self.status(title)
        if st["holds"]: raise HoldError(st["holds"])
        j=cb(st); lines=[f"# Localized Media Release Packet — {title}","",f"Status: **{st['release_status']}**",f"Source SHA-256: `{st['source']['sha256']}`",f"Owner-supplied rights ready: `{str(st['owner_supplied_rights_ready']).lower()}`","External publish authorized: `false`","","## Required variants",""]
        for x in st["variants"]: lines.append(f"- `{x['locale']}/{x['territory']}/{x['kind']}` — {x['status']} · rev {x['revision']} · `{x['content_sha256']}` · reviewers: {', '.join(a['reviewer_id'] for a in x['approvals'])}")
        lines += ["","## Holds","","- none","","## Authority ceiling","","This packet records owner-supplied facts and exact artifact identities. It does not interpret contracts or rights, assess translation quality, authorize external publication, contact third parties, or mutate provider/payment systems.",""]; m="\n".join(lines).encode(); rec={"schema_version":1,"title_id":title,"state_sha256":sha(j),"markdown_sha256":sha(m)}
        buf=io.BytesIO()
        with zipfile.ZipFile(buf,"w",compression=zipfile.ZIP_STORED) as z:
            for name,data in (("release.json",j),("release.md",m),("receipt.json",cb(rec))):
                info=zipfile.ZipInfo(name,(1980,1,1,0,0,0)); info.compress_type=zipfile.ZIP_STORED; info.external_attr=0o100600<<16; info.create_system=3; z.writestr(info,data)
        out=buf.getvalue(); return out,{**rec,"package_sha256":sha(out)}
    def export_package(self,title,out_path):
        data,rec=self.build_package(title); out=os.path.abspath(os.fspath(out_path)); parent,leaf=os.path.split(out)
        if not leaf or leaf in {".",".."}: raise InvalidState("output must name a file")
        pfd=_open_dir_nofollow(parent or "."); fd=None
        try:
            ps=os.fstat(pfd)
            if not stat.S_ISDIR(ps.st_mode): raise InvalidState("output parent is not a directory")
            fd=os.open(leaf,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,"O_NOFOLLOW",0),0o600,dir_fd=pfd); fs=os.fstat(fd); identity=(fs.st_dev,fs.st_ino)
            if not stat.S_ISREG(fs.st_mode): raise InvalidState("created output is not regular")
            view=memoryview(data)
            while view:
                n=os.write(fd,view)
                if n<=0: raise OSError("short write")
                view=view[n:]
            os.fsync(fd)
            ls=os.stat(leaf,dir_fd=pfd,follow_symlinks=False)
            if not stat.S_ISREG(ls.st_mode) or (ls.st_dev,ls.st_ino)!=identity: raise InvalidState("output leaf identity changed during publication")
            visible=_open_dir_nofollow(parent or ".")
            try:
                vp=os.fstat(visible)
                if (vp.st_dev,vp.st_ino)!=(ps.st_dev,ps.st_ino): raise InvalidState("output parent identity changed during publication")
            finally: os.close(visible)
            os.fsync(pfd); os.close(fd); fd=None
            return {"path":out,**rec,"bytes":len(data)}
        except Exception:
            if fd is not None:
                try:
                    os.ftruncate(fd,0); os.fsync(fd)
                except OSError:
                    pass
                os.close(fd)
            raise
        finally: os.close(pfd)
    def verify_package(self,title,path):
        actual,h,n,_=read_file(path); expected,rec=self.build_package(title); return {"title_id":title,"valid":actual==expected,"actual_sha256":h,"expected_sha256":rec["package_sha256"],"bytes":n}

def parser():
    p=argparse.ArgumentParser(); p.add_argument("--db",required=True); s=p.add_subparsers(dest="cmd",required=True)
    def a(name,*args):
        q=s.add_parser(name)
        for x in args: q.add_argument("--"+x,required=True)
        return q
    a("create-title","request-id","title-id","source","required"); a("update-source","request-id","title-id","source"); q=a("set-rights-ready","request-id","title-id"); q.add_argument("--ready",choices=("true","false"),required=True)
    q=a("add-variant","request-id","title-id","locale","territory","kind","artifact"); q=a("approve","request-id","title-id","locale","territory","kind","reviewer","revision","sha256"); q._option_string_actions["--revision"].type=int
    a("status","title-id"); a("export","title-id","out"); a("verify","title-id","package"); return p
def main(argv=None):
    x=parser().parse_args(argv)
    try:
        d=ReleaseDesk(x.db)
        if x.cmd=="create-title": r=d.create_title(x.request_id,x.title_id,x.source,strict_json_loads(read_file(x.required)[0]))
        elif x.cmd=="update-source": r=d.update_source(x.request_id,x.title_id,x.source)
        elif x.cmd=="set-rights-ready": r=d.set_rights_ready(x.request_id,x.title_id,x.ready=="true")
        elif x.cmd=="add-variant": r=d.add_variant(x.request_id,x.title_id,x.locale,x.territory,x.kind,x.artifact)
        elif x.cmd=="approve": r=d.approve_variant(x.request_id,x.title_id,x.locale,x.territory,x.kind,x.reviewer,x.revision,x.sha256)
        elif x.cmd=="status": r=d.status(x.title_id)
        elif x.cmd=="export": r=d.export_package(x.title_id,x.out)
        else:
            r=d.verify_package(x.title_id,x.package)
            if not r["valid"]: print(json.dumps(r,indent=2,sort_keys=True)); return 1
        print(json.dumps(r,indent=2,sort_keys=True)); return 0
    except HoldError as e: print(json.dumps({"error":"HOLD","holds":e.holds},indent=2)); return 2
    except (DeskError,OSError,sqlite3.Error) as e: print(json.dumps({"error":"INVALID","detail":str(e)},indent=2)); return 1
if __name__=="__main__": raise SystemExit(main())
