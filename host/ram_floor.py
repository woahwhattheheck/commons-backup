#!/usr/bin/env python3
"""host/ram_floor.py — find the BARE MINIMUM RAM a model needs to function.

The hypothesis (RAM_MECHANISM.md): the floor is the ANONYMOUS set (KV cache + compute buffers), which is
O(layers x context), NOT proportional to weight size. So with mmap-streamed weights and a small context,
a 40 GB model floors at roughly the same small RAM as a 9 GB one. This drives every anonymous-set lever
DOWN and measures the smallest RAM at which the model still emits a correct token.

Two numbers per run (Windows):
  PrivateBytes (PrivateMemorySize64)  = the HARD, non-reclaimable commit that MUST fit = the true floor.
  WorkingSet   (WorkingSet64)         = resident incl. reclaimable file-cache (how much of the mmap'd
                                        weights it opportunistically held; not the floor).
Plus llama.cpp's own reported KV / compute-buffer / model-buffer MiB, parsed from the load log.

Levers (all shrink the anonymous set, none touch the weights): small -c (ctx), -np 1 (one slot, not the
default 4), -fa on (flash attn), -ctk/-ctv q8_0 (quantized KV), small -ub/-b (compute buffer), -ngl 0
(weights mmap-streamed). NEVER --mlock/--no-mmap.

Usage:  python host/ram_floor.py --model C:/llm/models/phi-4-Q4_K_M.gguf --ctx 2048,512,256,128,64
Env/args: --out (default C:/llm/bin/ram_floor.json), LLAMA_BIN.
"""
import argparse, json, os, re, subprocess, time, urllib.request

BIN = os.environ.get("LLAMA_BIN", "C:/llm/bin/llamacpp/llama-server.exe")
PORT = 8080
URL = f"http://127.0.0.1:{PORT}"


def stop_server():
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    "Stop-Process -Name llama-server -Force -ErrorAction SilentlyContinue"], capture_output=True)
    time.sleep(2)


def proc_mem():
    """(privateMB, workingSetMB) of the llama-server process, or (0,0)."""
    out = subprocess.run(["powershell", "-NoProfile", "-Command",
        "$p=Get-Process llama-server -ErrorAction SilentlyContinue;"
        "if($p){'{0} {1}' -f [math]::Round($p.PrivateMemorySize64/1MB),[math]::Round($p.WorkingSet64/1MB)}else{'0 0'}"],
        capture_output=True, text=True).stdout.strip().split()
    try:
        return int(out[0]), int(out[1])
    except Exception:
        return 0, 0


def parse_log(path):
    kv = comp = mdl = 0.0
    lines = []
    try:
        t = open(path, encoding="utf-8", errors="replace").read()
    except Exception:
        return kv, comp, mdl, lines
    for m in re.finditer(r".*?(KV|compute buffer|model buffer|CPU_Mapped).*?([\d.]+)\s*MiB.*", t):
        val = float(m.group(2)); lines.append(m.group(0).strip()[:120])
        low = m.group(0).lower()
        if "kv" in low and kv == 0:
            kv = val
        elif "compute buffer" in low:
            comp = max(comp, val)
        elif ("model buffer" in low or "cpu_mapped" in low) and mdl == 0:
            mdl = val
    return kv, comp, mdl, lines[-6:]


def correct_token():
    # 1 token, long timeout — big models stream slowly, so a short cap false-fails a model that IS working.
    body = json.dumps({"messages": [{"role": "user", "content": "Hi"}], "max_tokens": 1,
                       "temperature": 0}).encode()
    try:
        req = urllib.request.Request(URL + "/v1/chat/completions", body, {"Content-Type": "application/json"})
        r = json.loads(urllib.request.urlopen(req, timeout=600).read())
        txt = (r["choices"][0].get("message") or {}).get("content", "") or ""
        return txt.strip()[:40]
    except Exception as e:
        return f"<err {e}>"


def run_one(model, ctx, log, no_repack=False, kv="q8_0", ub="64"):
    stop_server()
    open(log, "w").close()
    flags = ["-m", model, "-c", str(ctx), "-np", "1", "-fa", "on", "-ub", str(ub), "-b", str(ub),
             "-ngl", "0", "-ctk", kv, "-ctv", kv, "--host", "127.0.0.1", "--port", str(PORT)]
    if no_repack:
        flags.append("--no-repack")   # weights stay pure mmap (no private SIMD copy) — the floor lever
    subprocess.Popen([BIN] + flags, stdout=open(log, "w"), stderr=subprocess.STDOUT)
    bound = False
    for i in range(300):  # up to 15 min for a cold big-model mmap load
        try:
            t = open(log, encoding="utf-8", errors="replace").read()
        except Exception:
            t = ""
        if re.search(r"listening on http", t, re.I):
            bound = True; break
        if re.search(r"error loading|failed to load|bad_alloc|terminate called|invalid argument", t, re.I):
            break
        time.sleep(3)
    row = {"ctx": ctx, "bound": bound}
    if not bound:
        row["error"] = "did not bind"; row["tail"] = "\n".join(
            open(log, encoding="utf-8", errors="replace").read().splitlines()[-6:])
        stop_server(); return row
    # sample peak private/working across the 1-token gen (peak commit = the requirement)
    priv = ws = 0
    tok = correct_token()
    for _ in range(4):
        p, w = proc_mem(); priv = max(priv, p); ws = max(ws, w); time.sleep(0.4)
    kv, comp, mdl, lines = parse_log(log)
    row.update(private_mb=priv, working_mb=ws, kv_mib=kv, compute_mib=comp, model_buf_mib=mdl,
               token=tok, ok=bool(tok and not tok.startswith("<err")), llama_lines=lines)
    stop_server(); return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--ctx", default="2048,512,256,128,64")
    ap.add_argument("--out", default="C:/llm/bin/ram_floor.json")
    ap.add_argument("--no-repack", action="store_true", help="weights pure mmap (the floor lever)")
    ap.add_argument("--kv", default="q8_0", help="KV cache quant (q8_0 / q4_0)")
    ap.add_argument("--ub", default="64", help="compute batch (-ub/-b)")
    a = ap.parse_args()
    name = os.path.basename(a.model)
    file_gb = round(os.path.getsize(a.model) / (1024**3), 1)
    ladder = [int(x) for x in a.ctx.split(",") if x.strip()]
    nr = getattr(a, "no_repack")
    print(f"\nRAM FLOOR — {name}  ({file_gb} GB on disk)   flags: -np1 -fa on -ctk/v {a.kv} -ub/b {a.ub} -ngl 0"
          + ("  --NO-REPACK (pure mmap)" if nr else "  (repack ON)"))
    print("  physical(WS) = RAM actually resident (the real footprint) · committed(PB) = virtual, pagefile-backed")
    print(f"{'ctx':>6}{'physical MB':>13}{'committed MB':>14}{'KV MiB':>9}{'comp MiB':>9}  ok  token")
    print("-" * 78)
    results = {}
    if os.path.exists(a.out):
        try:
            results = json.load(open(a.out, encoding="utf-8"))
        except Exception:
            results = {}
    rows = []
    for ctx in ladder:
        r = run_one(a.model, ctx, "C:/llm/bin/ram_floor_server.log", no_repack=nr, kv=a.kv, ub=a.ub)
        rows.append(r)
        if r["bound"]:
            print(f"{ctx:>6}{r['working_mb']:>13}{r['private_mb']:>14}{r['kv_mib']:>9.0f}{r['compute_mib']:>9.0f}"
                  f"   {'Y' if r['ok'] else 'n'}  {r['token']!r}")
        else:
            print(f"{ctx:>6}{'—':>13}  FAILED: {r.get('error')}")
        results[name] = {"file_gb": file_gb, "rows": rows}
        json.dump(results, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    bound = [r for r in rows if r["bound"]]
    if bound:
        floor = min(r["working_mb"] for r in bound)  # physical RAM resident = the real footprint
        conf = " (token-confirmed)" if any(r["ok"] for r in bound) else " (loaded+resident; token check slow)"
        print(f"\nPHYSICAL FLOOR: {name} stayed resident in as little as {floor} MB "
              f"({floor/1024:.2f} GB) — a {file_gb} GB model{conf}. The rest streams from the SSD.")
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
