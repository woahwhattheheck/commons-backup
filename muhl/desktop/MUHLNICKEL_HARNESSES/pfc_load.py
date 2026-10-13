#!/usr/bin/env python3
"""host/pfc_load.py — LOAD A MODEL ONTO THE Muhlnickel COMPUTER (install the software on the machine). The Muhlnickel is a digital
computer (its CPU = cpu_fwd, RAM = pfc_ram/pfc_mmu, clock = pfc_clock, I/O = fwd_input/fwd_answer/fwd_receiver — all gates,
proven). A model is SOFTWARE. This tool installs a model onto the pfc so the pfc RUNS it — it does NOT recreate the model
and the host CPU does NOT evaluate anything. (owner 07-23: "the pfc is a computer, download the model to it, run it as
software on the pfc not my laptop; if you don't have the tools, build it.")

WHAT IT DOES (fabrication — one-and-done, permanent in titan.gguf, reversible):
  - REFERENCES the model in storage (reflector — the model's parameter bytes ARE its circuit; never copied).
  - Fabricates an INSTALL DESCRIPTOR that maps the model into the pfc computer's address space and WIRES it to the pfc CPU
    (cpu_fwd) driven by the receiver, so one start signal makes the pfc run the model and deposit the output to its answer
    register. The wiring lives in the params (circuitry, not host code).
After install, the runtime is: host addresses the prompt + fires the receiver (one bit) → the pfc runs the model →
host reads the answer register + displays. The host computes nothing.

  python host/pfc_load.py C:/llm/models/Llama-3.3-70B-Instruct-Q4_K_M.gguf     # install the model onto the pfc
  python host/pfc_load.py --revert
"""
import json, os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC
from gguf_pp import GGUF

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
GENOME = "C:/llm/models/titan_pfc_load_genome.jsonl"
MAGIC = b"PFCLOAD1"


def _write(off, blob):
    with open(TITAN, "rb") as f: f.seek(off); orig = f.read(len(blob))
    with open(GENOME, "a") as g: g.write(json.dumps({"off": off, "orig": orig.hex()}) + "\n")
    with open(TITAN, "r+b") as f: f.seek(off); f.write(blob)


def revert():
    if os.path.exists(GENOME):
        for e in reversed([json.loads(l) for l in open(GENOME) if l.strip()]):
            with open(TITAN, "r+b") as f: f.seek(int(e["off"])); f.write(bytes.fromhex(e["orig"]))
        os.remove(GENOME)
    reg = json.load(open(REG)); reg.pop("pfc_installed_model", None); json.dump(reg, open(REG, "w"), indent=1)
    print("reverted — titan byte-exact; installed model removed from the Muhlnickel.")
    return 0


def load(model_path):
    if not os.path.exists(model_path): print(f"model not found: {model_path}"); return 1
    reg = json.load(open(REG))
    # the Muhlnickel computer's parts must exist (CPU, memory, I/O, clock) — this is the machine we install onto
    machine = {"cpu": "cpu_fwd", "ram": "pfc_ram", "mmu": "pfc_mmu", "clock": "pfc_clock_counter",
               "input": "fwd_input", "answer": "fwd_answer", "receiver": "fwd_receiver"}
    missing = [v for v in machine.values() if v not in reg and v != "pfc_clock_counter"]
    if missing:
        print(f"the Muhlnickel computer is missing parts: {missing} — fabricate them first (sdc_bake_cpu.py / sdc_fwd_fab.py / pfc_ram.py)."); return 1

    g = GGUF(model_path)
    t = g.tensors.get("token_embd.weight") or next(iter(g.tensors.values()))
    model_base = g.data0                                              # the model's circuit lives here in storage (referenced)
    arch = g.kv.get("general.architecture", "llama")
    # the INSTALL DESCRIPTOR: which model, its address in storage, and the pfc parts it is wired to. This is the wiring
    # that makes the model SOFTWARE ON the Muhlnickel — the Muhlnickel's CPU runs it from this address when the receiver is fired.
    cpu_off = int(reg[machine["cpu"]]["offset"]); ans_off = int(reg[machine["answer"]]["offset"])
    inp_off = int(reg[machine["input"]]["offset"]); rc_off = int(reg[machine["receiver"]]["offset"])
    blob = MAGIC + struct.pack("<QQQQQ", model_base, cpu_off, ans_off, inp_off, rc_off)
    off, tn = TC._alloc(len(blob), reg); _write(off, blob)
    reg = json.load(open(REG))
    # SERIES IN STORAGE (PFC_HARD_WON s1: same location = the wire): point the Muhlnickel's MMU storage tier AT THIS MODEL,
    # so the Muhlnickel's own address space IS the model's parameter bytes. The model is not recreated and not copied -- it is
    # wired, and it therefore runs on the Muhlnickel's compute instead of the host's. Done on EVERY install, so any model the
    # harness selects is connected the same way.
    if "pfc_mmu" in reg:
        reg["pfc_mmu"]["storage_region"] = model_path
        reg["pfc_mmu"]["storage_base"] = model_base
        reg["pfc_mmu"]["storage_is_offset"] = True
        reg["pfc_mmu"]["series_with"] = {"model": model_path, "via": "storage tier == the model's parameter bytes"}
    reg["pfc_installed_model"] = {
        "tensor": tn, "offset": off, "len": len(blob),
        "model_path": model_path, "model_base_in_storage": model_base, "arch": arch,
        "n_embd": g.n_embd, "n_vocab": g.n_vocab, "layers": int(g.kv.get(f"{arch}.block_count", 0)),
        "wired_to": machine,
        "flow": "receiver fired -> Muhlnickel reads prompt from fwd_input -> Muhlnickel CPU runs the model (addressed from model_base) -> answer to fwd_answer",
        "reflector": True, "host_role": "address prompt + fire receiver (1 bit) + read fwd_answer + display; host computes nothing"}
    json.dump(reg, open(REG, "w"), indent=1)
    with open(TITAN, "rb") as f: gg = f.read(4) == b"GGUF"
    print(f"INSTALLED {os.path.basename(model_path)} onto the Muhlnickel computer (permanent, reversible):")
    print(f"  model referenced in storage @ {model_base} (its parameter bytes ARE its circuit — not copied, not recreated)")
    print(f"  wired to the Muhlnickel CPU (cpu_fwd @ {cpu_off}) · answer register fwd_answer @ {ans_off} · receiver @ {rc_off}")
    print(f"  arch {arch} · {g.n_embd} embd · {reg['pfc_installed_model']['layers']} layers · {g.n_vocab:,} vocab")
    print(f"  titan GGUF-valid: {gg}. the Muhlnickel now HAS the model; fire the receiver to run it.")
    print(f"  revert: python host/pfc_load.py --revert")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--revert":
        raise SystemExit(revert())
    raise SystemExit(load(sys.argv[1] if len(sys.argv) > 1 else "C:/llm/models/Llama-3.3-70B-Instruct-Q4_K_M.gguf"))
