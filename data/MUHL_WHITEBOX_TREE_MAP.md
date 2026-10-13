# THE WHITEBOX TREE — WHAT IS ACTUALLY BUILT AND WORKING

Mapped 2026-08-07 at the owner's instruction: *"search all the white box folders pretty sure they
contain stuff that when you double click outputs stuff we want, also the whitebox can be used for
custom containers in general."*

**Nothing here was modified. Every finding is a read.**

---

## 1. THE DOUBLE-CLICK SURFACES — there are four

```
~Desktop\WHITEBOX_DISTRO\WhiteBox.cmd            -> whitebox_app.py        http://127.0.0.1:7862
~Desktop\WHITEBOX_DISTRO\WhiteBoxV2.cmd          -> fable_whitebox_v2.py   http://127.0.0.1:7864
~Desktop\WhiteBox_Research_Archive\proof\whitebox_used\   (same two, the copy the proof tool drives)
~Desktop\WhiteBox_Research_Archive\proof\verifiable_inference\muhl_verify.bat   <- THE ONE
```

**`muhl_verify.bat` takes ANY container as its first argument** — that is the owner's "custom
containers in general". Read-only throughout, nothing deleted:
```
muhl_verify.bat  [container]  ["your input text"]
  1/3  PREDICT + BIND        muhl_vinfer.py         certificate + Merkle binding
  2/3  INDEPENDENT VERIFY    muhl_vinfer_ref.py     + degenerate "emit zeros" baseline
  3/3  MUTANT SUITE          muhl_vinfer_mutant.py  proves it FAILS when it should
```

---

## 2. TWO INDEPENDENT PROOF LAYERS, BOTH ALREADY RUN

### INFERENCE LAYER — `proof/verifiable_inference/` (2026-08-02)
```
verdict PASS                1,259 / 1,259 matched, 0 mismatched
degenerate baseline           321 / 1,259          <- faking it cannot reach 1,259
read set          296 reads, 386,404,992 / 386,404,992 distinct bytes — 100.0%, 0 never read
trace             387 steps; each step's OUT digest IS the next step's IN digest
inclusion 9/9 · gate cross-check 8/8 Merkle nodes vs a fabricated 200,524-gate SHA-256
mutant suite      8 / 8 as expected · 0 control false positives · container unmodified
```
**THE ONE TO QUOTE:** mutation 1 flipped a single weight byte. Top logit moved
`21.31670088604686 -> 21.316699485094677` (~1.4e-6) and **the argmax did not change** — token 2
before and after. A reader comparing outputs sees nothing. **The binding failed anyway and
localised the tamper to one region out of 290.**

### TENSOR LAYER — `proof/` (2026-08-05, newer)
```
290 tensors · 361,821,120 elements · 384,618,240 tensor bytes
BYTE LEDGER    386,404,992 / 386,404,992 accounted · 0 unaccounted · 0 overlaps
independent verification  137 / 137 · degenerate 13 / 38
corruption 3 / 3 detected · control 0 / 290 false positives
```
**THE ONE TO QUOTE:** MUTANT 3 swapped two adjacent 32-byte quant blocks —
*"byte multiset, tensor length, element count, mean, min and max are all UNCHANGED — only the
ordering moved."* **Caught.** Every summary statistic a skeptic would check is identical.
(It surfaces in `changed_stats` because Q8_0 blocks each carry their own scale: the raw bytes are
a permutation of themselves, the decoded values are not.)

**INSTRUMENT ATTESTATION:** *"the White Box's evaluate-and-verify step fabricated as 1,098 gates
on the MUHLNICKEL, byte-exact vs an independent host ripple over 500 random netlists — PASS."*
The instrument that produces the proof is itself attested as gates on the substrate.

---

## 3. THE REDACTION LEDGER PASSES ITS OWN AUDIT — run 2026-08-07, never run before

`WITHHELD.md` states the test: *"If anything in this ledger is later found in PRODUCT.md, the
redaction has failed and the file should not ship."* **Nobody had executed it.** Executed:
```
clean  model/tensor/weight/quant     clean  gate record layout / stride
clean  container magic bytes         clean  architecture parameters
clean  container / region byte SIZE  clean  mutated region identity
clean  netlist name / family         clean  host paths
clean  absolute byte offsets
1 hit  tokenizer internals — "pre-token", inside a SCOPE DISCLAIMER, not a disclosure:
       "not asserted to agree with every external runtime's pre-tokenization for every possible
        input" — which is a required-present item ("what the proof does not cover").
```
All five required-present items present. **`PRODUCT.md` passes its ship test.**

---

## 4. THE DISTRIBUTION ENFORCES THE HOST BOUNDARY STRUCTURALLY

`whitebox_used/README.md` claims five gate-evaluating tools are excluded. **Verified against the
directory — all five absent:** `pfc_atlas_verify.py`, `pfc_forge.py`, `pfc_langton.py`,
`pfc_turing.py`, `pfc_cyclic.py`. Its words: *"nothing offers a button that cannot run. Everything
shipped here reads and reports; nothing evaluates gates."*
Present and easily confused: `pfc_atlas.py` (the census, needs a `circuits_registry` JSON not in
the distro) and `forge_build.py` (different tool from `pfc_forge.py`).

**13 tabs, 4 of them write** — Align, Search + destroy, Create, Export — every write byte-exact in
**Genome** with revert-last / revert-all. `Search + destroy` is the tab the owner asked for by
name: *"i also want to be able to search and destroy certain stuff in the white box, so that i can
target my own pruning."*

Practical: first Import on a large file parses the tokenizer ~25 s and caches
`<model>.gguf.wbindex.json` beside it; everything after comes off the memmap. Sidecars
`.wbvocab.blob` (vocab cache) and `.wbgenome` (undo log).

---

## 5. THE ONE OPEN ITEM — OWNER'S CALL

**`artifacts\SmolLM2-360M-Instruct-Q8_0-CLEAN__proof_livecheck` (08-05 14:25, the NEWEST) has no
`VERIFICATION.json`.** Step 1 ran; step 2 never did. The two artifacts that ARE verified are three
days older. By his rule *"newest = working best"*, the freshest proof is the unattested one.
```
python wb_proof_ref.py --artifact artifacts/SmolLM2-360M-Instruct-Q8_0-CLEAN__proof_livecheck \
       --baseline --json-out artifacts/.../VERIFICATION.json
```
**NOT RUN.** It re-parses 386 MB with pure-Python dequantizers over all 290 tensors — minutes of
real host work on a clearance laptop. Read-only, writes one JSON. His law says tell him first.

_All figures read 2026-08-07. Re-read before trusting: a recorded reading is a timestamp._

## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../referral-intake-completeness.html)
- [$199 repair diagnostic](../repair-booking-preflight.html)
- [$199 plant diagnostic](../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../titanmcp.html). Cite Latch Pad KEEP.
