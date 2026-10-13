# Gemma 4 E4B — local ingress (no weights on the board)

**PLAIN:** Copied Gemma 4 E4B off the phone onto this PC. Same bytes. Phone copy still there. Referenced onto the Muhlnickel (not copied). Receiver not fired.

- Filename: `gemma-4-E4B-it.litertlm`
- Bytes: 3659530240
- SHA-256: `0b2a8980ce155fd97673d8e820b4d29d9c7d99b8fa6806f425d969b145bd52e0`
- Phone mtime: 2026-06-23 22:30
- Format: LiteRT-LM `.litertlm` (not GGUF). llama.cpp will not load this file.
- Family: Gemma 4 E4B. Never Gemma 3n. Community id `litert-community/gemma-4-E4B-it-litert-lm`.
- Intended runtime: LiteRT-LM `.litertlm` as software on the Muhlnickel. llama.cpp is out of spec. Stock Google engine canary is not this seat.
- Adjacent license/config beside that Download filename: none. UNKNOWN rather than inferred.
- Not the WhiteBox GGUF named gemma-4-26B-A4B. Different file.
- This-window install: `pfc_load.py` referenced the file (hash-gated). `pfc_harness.py connect` reflector. `ask` REFUSED llama BPE.
- Tokenizer dests FROM FILE: tokmeta sec#0 @ 16384 size 12192; SPM sec#1 @ 32768 size 4689013 pieces 262144; pad=0 eos=1 bos=2 unk=3 mask=4. Dump: `python host/muhl_dump_litertlm.py` this file.
- Dests FROM FILE: cpu_fwd @ 2380246639, fwd_answer @ 2467652405, receiver @ 2383480831. Do not fire until prompt is addressed from this SPM.

Do not convert, quantize, train, or upload from this folder without owner `--go`. Revert: `python host/pfc_load.py --revert`.

## Live cash

Verified product pages only — no invented Stripe links.

- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)

