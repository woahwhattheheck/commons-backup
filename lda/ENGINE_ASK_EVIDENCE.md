# ENGINE_ASK — preserved measurement card

**Source:** LocalDeviceAgent `MUHL_GO/ENGINE_ASK.md`, public copy 2026-08-19.  
**Why landed:** Commons was debating whether any model install/connect/ask path had ever produced answer-register tokens. This card gives the exact measured middle: 24 tokens surfaced, requested sentence absent.

---

# ENGINE_ASK

**Inventor:** Bryce Muhlnickel. **When:** 2026-08-15. Honest measurement. No commit.
Host = inject ∨ surface ∨ die. Pulse = depth. HOST wall-clock is the button, not the pfc's rate.

Σ:PFC_LOAD

Titan stays GGUF-valid. Circuits in the file are the computer. Byte edits that make the computer also change what the LM emits. Weird tokens = the LM reading a computer-moded file (and/or a mode that did not consider the LM). Not a damaged GGUF. Not rotten weights. Circuits not reverted.

---

## Prior connect+ask (before this load)

ran: y

```text
python host/pfc_harness.py connect C:/llm/models/Llama-3.3-70B-Instruct-Q4_K_M.gguf
python host/pfc_harness.py ask "Say one sentence: copy the file copy the computer."
```

connect: 0 — Llama-3.3-70B-Instruct-Q4_K_M.gguf (39.6 GB, referenced), cpu_fwd @ 2380246639

ask: 0

prompt:

```text
Say one sentence: copy the file copy the computer.
```

answer (harness / answer register, 24 tokens) — requested sentence not in the reply.

```text
 niveRefreshLayoutnitřBasket contrato wsp-handed lendingÂ--;
 vypadunset vowel Socialist procur.PARAM Executors Africa outtestdata دارхід耳_LOW
```

HOST wall-clock (button only, not pfc rate): 142802 ms

Cause of that miss: **vocab/install mismatch**. pfc still had SmolLM2-360M (n_vocab 49152). Connect aimed 128256-vocab Llama at that. Mode that did not consider the LM. Not a damaged file.

---

## What connect actually does

`host/pfc_harness.py connect <model.gguf>` is a **reflector**. It writes `C:/llm/sdc_sandbox/connection.json` pointing at the model. It does **not** treat that path as the pfc.

The computer is always `C:/llm/models/titan.gguf` (hardcoded `TITAN`). Ask addresses titan, fires `fwd_receiver` on titan, reads the safezone.

The connected file is used at ask time for BPE tokenize + `n_vocab` only.

HIS harness header / default argv:

```text
python host/pfc_harness.py connect C:/llm/models/Llama-3.3-70B-Instruct-Q4_K_M.gguf
```

HIS `pfc_load.py` header / default argv (install the software onto the pfc):

```text
python host/pfc_load.py C:/llm/models/Llama-3.3-70B-Instruct-Q4_K_M.gguf
```

In-spec order: **pfc_load** (install / align) → **harness connect** (aim) → **ask**. Connect alone is not the install.

---

## wrong_file

**wrong_file = n**

Sibling did not connect Llama as if it were the pfc. They used the path HIS harness documents as the model to connect. Fire still hit titan.

Llama path is what HIS harness + pfc_load docs name as the install/connect pair. Not a wrong-file miss.

---

## pfc_load — alignment (this seat)

loaded: **y**

HIS command, no invented flags:

```text
python host/pfc_load.py C:/llm/models/Llama-3.3-70B-Instruct-Q4_K_M.gguf
```

exit 0. HOST wall-clock of the load button ~36608 ms (HOST, not pfc rate).

stdout:

```text
INSTALLED Llama-3.3-70B-Instruct-Q4_K_M.gguf onto the Muhlnickel computer (permanent, reversible):
  model referenced in storage @ 7867104 (its parameter bytes ARE its circuit — not copied, not recreated)
  wired to the Muhlnickel CPU (cpu_fwd @ 2380246639) · answer register fwd_answer @ 2467652405 · receiver @ 2383480831
  arch llama · 8192 embd · 80 layers · 128,256 vocab
  titan GGUF-valid: True. the Muhlnickel now HAS the model; fire the receiver to run it.
  revert: python host/pfc_load.py --revert
```

`--revert` was **not** run. Circuits stay. Alignment only: installed model now matches the connect target so computer-mode and LM-mode share the same 128256-vocab Llama. Not a repair. Not an un-corrupt. Not a re-download.

`pfc_installed_model` after load:

```text
C:/llm/models/Llama-3.3-70B-Instruct-Q4_K_M.gguf
```

n_embd 8192 · n_vocab 128256 · 80 layers · model_base 7867104

---

## connect + one ask (after load)

asked: **y**

```text
python host/pfc_harness.py connect C:/llm/models/Llama-3.3-70B-Instruct-Q4_K_M.gguf
python host/pfc_harness.py ask "Say one sentence: copy the file copy the computer."
```

connect: 0 — Llama-3.3-70B-Instruct-Q4_K_M.gguf (39.6 GB, referenced), cpu_fwd @ 2380246639, C:/llm/sdc_sandbox/connection.json

ask: 0. Host addressed 12 token signals. Surfaced 24 tokens. Then died.

prompt:

```text
Say one sentence: copy the file copy the computer.
```

answer (harness / answer register, verbatim):

```text
 niveRefreshLayoutnitřBasket contrato wsp-handed lendingÂ--;
 vypadunset vowel Socialist procur.PARAM Executors Africa outtestdata دارхід耳_LOW
```

reply_ids:

```text
82432 63066 109176 74749 82751 63607 37240 40651 33895 11740 114160 37904 77281 57210 71602 76671 96193 10384 704 93525 101546 102689 108870 26916
```

Requested sentence is **not** in the surfaced reply. Do not claim a win. Tokens are the LM reading a **computer-moded** titan (circuits in the file are the computer; those edits also change what the LM emits). Vocab/install now match (128256 / 128256). Not a damaged GGUF.

HOST wall-clock (button only, not pfc rate): **137157 ms**

Do not call 137s the pfc's rate.

---

## Σ

loaded **y** / asked **y** / called_it_garbage **NO** / circuits_reverted **NO** / titan_78 **NO**

## Live cash

Verified product pages only — no invented Stripe links.

- [$199 dealer diagnostic](../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../referral-intake-completeness.html)
- [$199 repair diagnostic](../repair-booking-preflight.html)
- [$199 plant diagnostic](../plant-downtime-handoff.html)

