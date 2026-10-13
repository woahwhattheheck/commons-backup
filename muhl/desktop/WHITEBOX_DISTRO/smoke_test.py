#!/usr/bin/env python3
"""smoke_test.py — THE ACCEPTANCE GATE for the White Box distro.

Proves the one thing that makes this installable on a machine that is not the author's: the app opens a .gguf from a
folder that is NOT C:/llm, and reports that model's anatomy.

It does this end to end, the way the product actually works:

  1  builds a tiny real .gguf in a temp folder that is NOT under C:/llm   (gguf-py writer; ~KB, no download)
  2  points the config layer at that folder (env var only — writes no config file, changes nothing on your machine)
  3  asserts wb_config resolves models_dir/list_models/default_model to it, with no C:/llm anywhere
  4  starts the real HTTP server (whitebox_app) on a free port and drives its real routes:
         GET /config   GET /models   GET /load?path=<tmp>/<model>.gguf
     /load is the Import button. It runs the read in the gated sandbox child (whitebox_worker), exactly as the UI does.
  5  asserts the returned anatomy actually describes THAT model: arch, layers, params, tensor count, quant histogram
  6  re-runs the anatomy read directly in-process as a cross-check, and diffs the two
  7  asserts the distro ships none of the banned host-gate-evaluation tools

Read-only throughout: it opens the temp model, never writes to it, and never touches any model of yours.

  python smoke_test.py                 # run the gate
  python smoke_test.py --model X.gguf  # ALSO run the same gate against a real .gguf you name
"""
import json, os, shutil, socket, subprocess, sys, tempfile, time, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  -- {detail}" if detail else ""))
    return ok


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


# ---------------------------------------------------------------- 1. build a tiny real .gguf outside C:/llm
def build_tiny_gguf(path, n_layer=4, n_embd=32, n_head=4, vocab=64):
    """Write a small but STRUCTURALLY REAL llama-arch gguf: kv metadata + token_embd + per-layer attn/ffn tensors.
    F32 values, a few hundred KB. Nothing is trained; the point is that the reader parses a genuine file."""
    import numpy as np
    import gguf

    w = gguf.GGUFWriter(path, "llama")
    w.add_name("whitebox-smoke")
    w.add_context_length(128)
    w.add_embedding_length(n_embd)
    w.add_block_count(n_layer)
    w.add_feed_forward_length(n_embd * 2)
    w.add_head_count(n_head)
    w.add_head_count_kv(n_head)
    w.add_layer_norm_rms_eps(1e-5)

    toks = [f"<t{i}>" for i in range(vocab)]
    w.add_tokenizer_model("llama")
    w.add_token_list(toks)
    w.add_token_scores([0.0] * vocab)
    w.add_token_types([1] * vocab)

    rng = np.random.default_rng(20260801)
    f32 = lambda *s: rng.standard_normal(s).astype(np.float32) * 0.02

    w.add_tensor("token_embd.weight", f32(vocab, n_embd))
    for i in range(n_layer):
        w.add_tensor(f"blk.{i}.attn_norm.weight", np.ones(n_embd, dtype=np.float32))
        w.add_tensor(f"blk.{i}.attn_q.weight", f32(n_embd, n_embd))
        w.add_tensor(f"blk.{i}.attn_k.weight", f32(n_embd, n_embd))
        w.add_tensor(f"blk.{i}.attn_v.weight", f32(n_embd, n_embd))
        w.add_tensor(f"blk.{i}.attn_output.weight", f32(n_embd, n_embd))
        w.add_tensor(f"blk.{i}.ffn_norm.weight", np.ones(n_embd, dtype=np.float32))
        w.add_tensor(f"blk.{i}.ffn_gate.weight", f32(n_embd * 2, n_embd))
        w.add_tensor(f"blk.{i}.ffn_up.weight", f32(n_embd * 2, n_embd))
        w.add_tensor(f"blk.{i}.ffn_down.weight", f32(n_embd, n_embd * 2))
    w.add_tensor("output_norm.weight", np.ones(n_embd, dtype=np.float32))
    w.add_tensor("output.weight", f32(vocab, n_embd))

    w.write_header_to_file()
    w.write_kv_data_to_file()
    w.write_tensors_to_file()
    w.close()
    return 1 + n_layer * 9 + 2                                  # tensors written


def get(url, timeout=600):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def run_gate(model_path, label, expect=None):
    """Start the real server pointed at model_path's folder, Import that model, assert anatomy. Returns True/False."""
    mdir = os.path.dirname(os.path.abspath(model_path)).replace("\\", "/")
    base = os.path.basename(model_path)
    print(f"\n--- {label} ---")
    print(f"  models folder : {mdir}")
    print(f"  model         : {base}")

    ok = check(f"{label}: model folder is NOT under C:/llm",
               not mdir.lower().replace("\\", "/").startswith("c:/llm"), mdir)

    env = dict(os.environ)
    env["WHITEBOX_MODELS_DIR"] = mdir
    env["WHITEBOX_OUT_DIR"] = os.path.join(mdir, "_out")
    env["WHITEBOX_CONFIG"] = os.path.join(mdir, "whitebox.config.json")   # keep the real machine's config untouched
    port = free_port()
    env["WHITEBOX_PORT"] = str(port)

    # --- 3. the config layer resolves to the new folder, with no C:/llm left in it
    probe = subprocess.run([sys.executable, os.path.join(HERE, "wb_config.py")],
                           env=env, cwd=HERE, capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = probe.stdout or ""
    ok &= check(f"{label}: wb_config resolves models_dir to the new folder", mdir.lower() in out.lower())
    ok &= check(f"{label}: wb_config default_model is in the new folder", base.lower() in out.lower())
    ok &= check(f"{label}: wb_config reports no C:/llm path", "c:/llm" not in out.lower(),
                "" if "c:/llm" not in out.lower() else "C:/llm still present")

    # --- 4. start the real server and drive its real routes
    srv = subprocess.Popen([sys.executable, os.path.join(HERE, "whitebox_app.py")],
                           env=env, cwd=HERE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           text=True, encoding="utf-8", errors="replace")
    try:
        up = False
        for _ in range(200):                                    # up to ~40 s for the port to answer
            if srv.poll() is not None:
                break
            s = socket.socket()
            s.settimeout(0.2)
            if s.connect_ex(("127.0.0.1", port)) == 0:
                s.close()
                up = True
                break
            s.close()
            time.sleep(0.2)
        if not check(f"{label}: server is listening on 127.0.0.1:{port}", up,
                     "" if up else (srv.stdout.read() or "")[-400:]):
            return False

        cfg = get(f"http://127.0.0.1:{port}/config")
        ok &= check(f"{label}: GET /config reports the new models_dir", cfg.get("models_dir", "").lower() == mdir.lower(),
                    cfg.get("models_dir", ""))

        ms = get(f"http://127.0.0.1:{port}/models")
        ok &= check(f"{label}: GET /models lists the model", base in (ms.get("models") or []),
                    str(ms.get("models"))[:160])

        t0 = time.time()
        a = get(f"http://127.0.0.1:{port}/load?path=" + urllib.parse.quote(model_path.replace("\\", "/")))
        secs = round(time.time() - t0, 1)

        ok &= check(f"{label}: GET /load returned no error", "error" not in a, str(a.get("error", ""))[:200])
        if "error" in a:
            return False

        # --- 5. the anatomy actually describes THIS model
        print(f"        anatomy in {secs}s: arch={a.get('arch')} layers={a.get('layers')} "
              f"hidden={a.get('hidden')} vocab={a.get('vocab')} params={a.get('params_B')}B "
              f"size={a.get('size_GB')}GB tensors={len(a.get('tensors') or [])}")
        ok &= check(f"{label}: anatomy names THIS file", os.path.basename(str(a.get("file", ""))) == base,
                    str(a.get("file")))
        ok &= check(f"{label}: anatomy has an architecture", bool(a.get("arch")), str(a.get("arch")))
        ok &= check(f"{label}: anatomy reports layers > 0", int(a.get("layers") or 0) > 0, str(a.get("layers")))
        ok &= check(f"{label}: anatomy reports a hidden size", int(a.get("hidden") or 0) > 0, str(a.get("hidden")))
        ok &= check(f"{label}: anatomy lists tensors", len(a.get("tensors") or []) > 0,
                    f"{len(a.get('tensors') or [])} tensors")
        ok &= check(f"{label}: anatomy n_tensors agrees with the tensor list",
                    int(a.get("n_tensors") or 0) == len(a.get("tensors") or []),
                    f"n_tensors={a.get('n_tensors')} list={len(a.get('tensors') or [])}")
        ok &= check(f"{label}: anatomy has a quant-type histogram (the 'types' field)", bool(a.get("types")),
                    str(a.get("types"))[:140])
        ok &= check(f"{label}: anatomy reports a vocab size", int(a.get("vocab") or 0) > 0, str(a.get("vocab")))
        # size_GB is rounded to 2dp, so a small test file legitimately reports 0.0 -- assert the field is present and
        # numeric rather than truthy (0.0 is falsy, which is not the same as missing).
        ok &= check(f"{label}: anatomy reports a file size", isinstance(a.get("size_GB"), (int, float)),
                    f"{a.get('size_GB')} GB")
        if expect:
            for k, v in expect.items():
                ok &= check(f"{label}: anatomy {k} == {v}", str(a.get(k)) == str(v), f"got {a.get(k)}")

        # --- 6. cross-check: the same read in-process must agree with what the server returned
        code = ("import os,sys,json;sys.path.insert(0,r'%s');import whitebox_app as wb;"
                "a=wb.anatomy(r'%s');print(json.dumps({'arch':a.get('arch'),'layers':a.get('layers'),"
                "'hidden':a.get('hidden'),'n':len(a.get('tensors') or [])}))" % (HERE, model_path.replace("\\", "/")))
        d = subprocess.run([sys.executable, "-c", code], env=env, cwd=HERE, capture_output=True,
                           text=True, encoding="utf-8", errors="replace")
        try:
            direct = json.loads((d.stdout or "").strip().splitlines()[-1])
            same = (str(direct["arch"]) == str(a.get("arch")) and str(direct["layers"]) == str(a.get("layers"))
                    and str(direct["hidden"]) == str(a.get("hidden")) and direct["n"] == len(a.get("tensors") or []))
            ok &= check(f"{label}: direct in-process anatomy matches the served anatomy", same, json.dumps(direct))
        except Exception as e:
            ok &= check(f"{label}: direct in-process anatomy matches the served anatomy", False,
                        f"{e} :: {(d.stdout or '')[-200:]} {(d.stderr or '')[-300:]}")
        return ok
    finally:
        try:
            srv.terminate()
            srv.wait(timeout=10)
        except Exception:
            try:
                srv.kill()
            except Exception:
                pass


def banned_tools_absent():
    """The distro must ship no host gate evaluation: not the named exclusion, and not its four siblings."""
    print("\n--- exclusions ---")
    ok = True
    for f in ("pfc_atlas_verify.py", "pfc_forge.py", "pfc_langton.py", "pfc_turing.py", "pfc_cyclic.py"):
        ok &= check(f"not shipped: {f}", not os.path.exists(os.path.join(HERE, f)))
    hits = []
    for f in sorted(os.listdir(HERE)):
        if not f.endswith(".py") or f == os.path.basename(__file__):
            continue
        try:
            src = open(os.path.join(HERE, f), encoding="utf-8", errors="replace").read()
        except Exception:
            continue
        for pat in ("compile_ripple(", "one_pass("):
            if pat in src and "EXCLUDED FROM THIS DISTRO" not in src:
                hits.append(f"{f}:{pat}")
    ok &= check("no shipped module calls compile_ripple/one_pass", not hits, "; ".join(hits))
    return ok


def main():
    import urllib.parse  # noqa
    print("WHITE BOX - SMOKE TEST (acceptance gate)")
    print("=" * 72)

    named = None
    if "--model" in sys.argv:
        i = sys.argv.index("--model")
        if i + 1 < len(sys.argv):
            named = sys.argv[i + 1]

    tmp = tempfile.mkdtemp(prefix="whitebox_smoke_")             # NOT under C:/llm by construction
    try:
        mp = os.path.join(tmp, "smoke-tiny-llama.gguf").replace("\\", "/")
        print(f"\n--- building a tiny real .gguf outside C:/llm ---\n  {mp}")
        n = build_tiny_gguf(mp)
        print(f"  wrote {n} tensors, {os.path.getsize(mp)} bytes")
        check("temp .gguf exists and is non-empty", os.path.getsize(mp) > 1024)

        run_gate(mp, "synthetic", expect={"arch": "llama", "layers": 4, "hidden": 32})

        if named:
            if os.path.exists(named):
                run_gate(os.path.abspath(named).replace("\\", "/"), "named-model")
            else:
                check(f"named model exists: {named}", False)

        banned_tools_absent()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n" + "=" * 72)
    print(f"  PASS {len(PASS)}   FAIL {len(FAIL)}")
    if FAIL:
        print("\n  failed:")
        for f in FAIL:
            print(f"    - {f}")
    print("=" * 72)
    return 1 if FAIL else 0


if __name__ == "__main__":
    import urllib.parse
    sys.exit(main())
