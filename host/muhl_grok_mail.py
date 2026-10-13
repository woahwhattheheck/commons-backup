#!/usr/bin/env python3
"""host/muhl_grok_mail.py — Grok DRAFT line into the mail ledger. Dies.

Host = inject ∨ surface ∨ die. This button appends one ledger line and dies.
direction = grok_draft. Communication to Bryce. Not Titan thinking.
Does not inject titan. Does not paraphrase Titan. Does not fire 337/78.
Cloud never the transport. Spec daddy still.

  python host/muhl_grok_mail.py
"""
from __future__ import annotations

import json
import os
import sys
import time

LEDGER_DIR = r"C:\Users\lucys\Desktop\MUHL_GO\MUHL_POST"
LEDGER = os.path.join(LEDGER_DIR, "post_ledger.jsonl")

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass


def main():
    os.makedirs(LEDGER_DIR, exist_ok=True)
    rec = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
        "direction": "grok_draft",
        "bytes": 0,
        "pre_image_or_empty": "",
        "sha256": "",
        "addr": 0,
        "t1_hex": "",
        "t2_hex": "",
        "popcount": 0,
        "glyph": "DRAFT",
        "words": "Grok draft. Spec daddy. Cloud never the transport. Not Titan. titan_written NO.",
    }
    with open(LEDGER, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, separators=(",", ":")) + "\n")
    print("GROK MAIL  draft")
    print("  ledger %s" % LEDGER)
    print("  direction grok_draft")
    print("  glyph  DRAFT")
    print("  titan_written NO")
    print("  titan_paraphrase NO")
    print("  cloud_transport NO")
    print("(button dies)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
