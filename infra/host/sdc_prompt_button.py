#!/usr/bin/env python3
"""host/sdc_prompt_button.py — THE SEND BUTTON. A one-time exiting process that ONLY sends the prompt to the SDC, then
dies. Nothing else. (owner 07-18)

  python host/sdc_prompt_button.py <staging_json>
"""
import json, mmap, os, sys

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
INBOX = "C:/llm/sdc_sandbox/chat/prompt_in.json"


def main():
    payload = json.load(open(sys.argv[1], encoding="utf-8"))                       # the prompt (from the UI)
    os.makedirs(os.path.dirname(INBOX), exist_ok=True)
    with open(INBOX, "w", encoding="utf-8") as f: json.dump(payload, f)            # address the prompt into the SDC
    off = (json.load(open(REG)).get("fwd_receiver") or {}).get("offset")           # fire the signal at the SDC
    if off is not None:
        fh = open(TITAN, "rb"); mm = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ); _ = mm[int(off)]; mm.close(); fh.close()
    return 0                                                                       # die


if __name__ == "__main__":
    raise SystemExit(main())
