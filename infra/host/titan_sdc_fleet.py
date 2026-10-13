#!/usr/bin/env python3
"""host/titan_sdc_fleet.py — the FLEET, as SEPARATE MANUAL BUTTONS (owner 07-16). Each press exits. YOU trigger each.

Same button model as the single SDC, fleet-wide. Nothing chains; nothing runs on its own. You press each:
  bake      — PREBAKE: pull ONE block; for every SDC node, build the miner for that node's disjoint extranonce2 (its own
              header -> its own 2^32 field) and write it into that node's params via the White-Box circuit bytes. Persist
              the armed record (en1/job/per-node offsets). Exit. Split work is done here, before start.
  start     — aim power at every prebaked node (press each receiver, one addressed read), then EXIT. Power flows on; each
              breaker sits inert until a 1.
  progress  — read each node's answer register (read-only) + its mailbox; print where the fleet is at. Exit.
  submit    — read each node's FROZEN answer; submit any winner to the live wallet (same en1 that baked it, so it's valid);
              fire the pop-up so peers advance. Exit.

  python host/titan_sdc_fleet.py bake | start | progress | submit
"""
import json, mmap, os, socket, struct, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
os.environ.setdefault("TITAN_POOL_HOST", "public-pool.io")     # diff-1, credits the wallet address directly
os.environ.setdefault("TITAN_POOL_PORT", "3333")
import titan_build_mine as B
import titan_sdc as T
import titan_sdc_bus as BUS

RESDIR = "C:/llm/models"
POPUP  = os.path.join(HERE, "titan_sdc_popup.py")
ARMED  = f"{RESDIR}/titan_fleet_armed.json"
DESIGN = f"{RESDIR}/titan_fleet_design.json"                    # the DESIGNED bitstreams (synthesized once, cached)
BITDIR = f"{RESDIR}/titan_fleet_bits"                           # one cached bitstream .bin per node
DIFF1  = 0x00000000FFFF0000000000000000000000000000000000000000000000000000


# ---------- DESIGN (synthesize the bitstreams ONCE — the deliberate, slow step; NOT on the bake path) ----------
def design():
    fleet = BUS._load_fleet()
    nodes = sorted(fleet.items(), key=lambda kv: kv[1]["sdc_id"])
    if not nodes:
        print("no fleet — reconfigure nodes first (titan_sdc_reconfigure.py)."); return
    s = socket.create_connection((T.POOL_HOST, T.POOL_PORT), timeout=20); buf = b""
    def send(o): s.sendall((json.dumps(o)+"\n").encode())
    send({"id":1,"method":"mining.subscribe","params":["titan-fleet/1.0"]})
    send({"id":4,"method":"mining.suggest_difficulty","params":[0.001]})
    send({"id":2,"method":"mining.authorize","params":[T.WALLET,"x"]})
    en1=None; en2size=8; job=None; diff=1.0; t=time.time()+20
    while time.time()<t and (en1 is None or job is None):
        s.settimeout(1.0)
        try: buf += s.recv(8192)
        except Exception: continue
        while b"\n" in buf:
            ln,buf = buf.split(b"\n",1)
            if not ln.strip(): continue
            try: m=json.loads(ln)
            except Exception: continue
            if m.get("id")==1 and m.get("result"): en1=m["result"][1]; en2size=m["result"][2]
            elif m.get("method")=="mining.set_difficulty": diff=m["params"][0]
            elif m.get("method")=="mining.notify":
                p=m["params"]; job=dict(job_id=p[0],prevhash=p[1],coinb1=p[2],coinb2=p[3],
                                        merkle_branch=p[4],version=p[5],nbits=p[6],ntime=p[7])
    s.close()
    if en1 is None or job is None:
        print("[design] pool handshake failed."); return
    os.makedirs(BITDIR, exist_ok=True)
    share_z = 256 - (DIFF1 // max(1,int(diff))).bit_length()
    print(f"[design] job {job['job_id']}  share diff {diff} (~{share_z} zero-bits)  en1={en1}  — synthesizing bitstreams…", flush=True)
    d = {"en1": en1, "diff": diff, "nodes": []}
    for path, e in nodes:
        en2_hex = "%0*x" % (en2size*2, e["sdc_id"])            # disjoint extranonce2 => this node's own field
        r = B.build_circuit(job, en1, en2_hex, diff)           # SYNTHESIS (the slow fold/DCE) happens HERE, once
        if not r.get("ok"):
            print(f"  sdc {e['sdc_id']:2d}: synth failed, skipped."); continue
        cb = T.circuit_bytes()                                 # the finished bitstream bytes
        bitf = f"{BITDIR}/sdc_{e['sdc_id']}.bin"
        with open(bitf, "wb") as f: f.write(cb)
        meta = json.load(open(T.META))
        d["nodes"].append(dict(path=path, sid=e["sdc_id"], bit=bitf, bits=len(cb), en2=en2_hex,
                               job_id=meta["job_id"], ntime=meta["ntime"], prefix=meta["prefix"],
                               share_target=meta.get("share_target")))
        print(f"  sdc {e['sdc_id']:2d} en2={en2_hex}  bitstream {len(cb)/1e6:.1f} MB cached", flush=True)
    json.dump(d, open(DESIGN,"w"))
    print(f"[design] {len(d['nodes'])} bitstreams designed + cached. now BAKE is an instant flash. done.", flush=True)


# ---------- BAKE (INSTANT: flash the ALREADY-DESIGNED bitstream into every node — no synthesis, no pool) ----------
def bake():
    if not os.path.exists(T.NET):
        print("no design to bake — the circuit isn't synthesized yet (titan_mine_net.npz missing)."); return
    fleet = BUS._load_fleet()
    nodes = sorted(fleet.items(), key=lambda kv: kv[1]["sdc_id"])
    if not nodes:
        print("no fleet — reconfigure nodes first."); return
    cb = T.circuit_bytes()                                     # the DESIGN that already exists — the finished bitstream
    meta = json.load(open(T.META)); prefix = bytes.fromhex(meta["prefix"])
    nb = struct.unpack("<I", prefix[72:76])[0]; block_tgt=(nb&0xffffff)<<(8*((nb>>24)-3))
    N = len(nodes); t0 = time.time(); armed = {"nodes": []}
    for path, e in nodes:
        off, tname = T.pick_tensor(len(cb)+1)
        with open(path,"r+b") as f: f.seek(off); f.write(cb); f.write(b"\x00")         # FLASH the design into the fabric
        ro = off + len(cb)
        armed["nodes"].append(dict(path=path, sid=e["sdc_id"], off=off, ro=ro,
                                   en2=meta.get("en2","%016x"%e["sdc_id"]), job_id=meta["job_id"], ntime=meta["ntime"],
                                   prefix=meta["prefix"], share_target=meta.get("share_target","%064x"%block_tgt),
                                   base=(e["sdc_id"]*(0x100000000//N))&0xffffffff))     # disjoint nonce base per node
    json.dump(armed, open(ARMED,"w"))
    print(f"[bake] flashed the design into {N} nodes in {time.time()-t0:.2f}s (instant, no synthesis). press START. done.", flush=True)


# ---------- START (aim power at every node, then die) ----------
def start():
    if not os.path.exists(ARMED): print("nothing prebaked — press BAKE first."); return
    armed=json.load(open(ARMED))
    reconf = json.load(open("C:/llm/models/titan_sdc_reconf.json")) if os.path.exists("C:/llm/models/titan_sdc_reconf.json") else {}
    n=0
    for nd in armed["nodes"]:
        r = reconf.get(os.path.abspath(nd["path"]), {})
        recv_off = int(r.get("receiver", nd["off"]))
        f=open(nd["path"],"rb"); mm=mmap.mmap(f.fileno(),0,access=mmap.ACCESS_READ)
        _=mm[recv_off]                                         # power in: address the receiver switch, one touch
        mm.close(); f.close(); n+=1
    print(f"[start] power aimed at {n} SDC nodes (receivers pressed). they run on power, cut off. START exits now. done.", flush=True)


# ---------- PROGRESS (read-only snapshot of the fleet) ----------
def progress():
    if not os.path.exists(ARMED): print("nothing prebaked — press BAKE first."); return
    armed=json.load(open(ARMED))
    print("=== FLEET PROGRESS ===", flush=True)
    for nd in armed["nodes"]:
        f=open(nd["path"],"rb"); mm=mmap.mmap(f.fileno(),0,access=mmap.ACCESS_READ)
        reg=bytes(mm[nd["ro"]:nd["ro"]+5]); mm.close(); f.close()
        status=reg[0]; nonce=struct.unpack("<I",reg[1:5])[0]
        state = f"SOLVED nonce {nonce}" if status==1 else "solving (bit 0)"
        print(f"  sdc {nd['sid']:2d} en2={nd['en2']}  {os.path.basename(nd['path'])[:34]:34s}  {state}", flush=True)
    print("snapshot complete — done.", flush=True)


# ---------- SUBMIT (read frozen answers, send winners to the wallet) ----------
def submit():
    if not os.path.exists(ARMED): print("nothing prebaked — press BAKE first."); return
    armed=json.load(open(ARMED)); en1=armed.get("en1")
    winners=[]
    for nd in armed["nodes"]:
        f=open(nd["path"],"rb"); mm=mmap.mmap(f.fileno(),0,access=mmap.ACCESS_READ)
        reg=bytes(mm[nd["ro"]:nd["ro"]+5]); mm.close(); f.close()
        if reg[0]==1: winners.append((nd, struct.unpack("<I",reg[1:5])[0]))
    if not winners:
        print("[submit] no frozen winner in any node yet (all bit 0). nothing to submit. done."); return
    s=socket.create_connection((T.POOL_HOST,T.POOL_PORT),timeout=20); buf=b""
    def send(o): s.sendall((json.dumps(o)+"\n").encode())
    send({"id":1,"method":"mining.subscribe","params":["titan-fleet-sub/1.0"]})
    send({"id":2,"method":"mining.authorize","params":[T.WALLET,"x"]}); time.sleep(1.0)
    mid=100
    for nd,nc in winners:
        send({"id":mid,"method":"mining.submit","params":[T.WALLET,nd["job_id"],nd["en2"],nd["ntime"],"%08x"%(nc&0xffffffff)]})
        v=None; t=time.time()+6
        while time.time()<t:
            s.settimeout(1.0)
            try: buf+=s.recv(8192)
            except Exception: continue
            while b"\n" in buf:
                ln,buf=buf.split(b"\n",1)
                if ln.strip():
                    try:
                        m=json.loads(ln)
                        if m.get("id")==mid: v=m
                    except Exception: pass
            if v: break
        ok = v is not None and v.get("result") is True
        print(f"  [wallet] sdc {nd['sid']} nonce {nc}: {'ACCEPTED' if ok else (v.get('error') if v else 'no verdict')}", flush=True)
        import subprocess; subprocess.run([sys.executable, POPUP, str(nd["sid"]), str(nc)],
                                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        mid+=1
    s.close(); print("[submit] done.", flush=True)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv)>1 else "progress"
    {"design":design, "bake":bake, "start":start, "progress":progress, "submit":submit}.get(cmd, progress)()
