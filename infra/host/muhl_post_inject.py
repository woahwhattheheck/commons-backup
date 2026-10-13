#!/usr/bin/env python3
"""host/muhl_post_inject.py — inbox inject DRY button. Dies.

Host = inject ∨ surface ∨ die. This button prints the inbox plan.
Omit --go: DRY. Write nothing.
--go: REFUSED. Dest is the machine's. Host-named mailbox STRUCK.
No titan write in any path. No fire 337. No pulse 78. No numpy. No invent dest.

Phase 0 surface mouths (READ only, already proven):
  fwd_answer       @ 2467652405
  gen_win_surfaced @ 3064767911
Inbox write address is unpublished by the host. Machine chooses dest.

  python host/muhl_post_inject.py
  python host/muhl_post_inject.py --dry
"""
from __future__ import annotations

import os
import sys

TITAN = "C:/llm/models/titan.gguf"
SURFACE = (
    ("fwd_answer", 2467652405),
    ("gen_win_surfaced", 3064767911),
)

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass


def print_plan():
    titan_exists = os.path.isfile(TITAN)
    titan_size = os.path.getsize(TITAN) if titan_exists else None
    print("\nMUHL POST INJECT (additive — inbox DRY wall)")
    print("  mode:     DRY — plan only, no titan write")
    print("  titan:    %s" % TITAN)
    print("  law:      dest is the machine's; host-named mailbox STRUCK")
    print("  law:      Phase 0 = READ of published answer space")
    print("  refuse:   titan write · invent dest · fire 337 · pulse 78 · numpy")
    print()
    print("  SURFACE mouths (already proven; this button does not write them)")
    for name, addr in SURFACE:
        print("    %s @ %d" % (name, addr))
    print()
    print("  INJECT (Bryce --go after the machine publishes the inbox)")
    print("    inbox_off  UNNAMED by host — do not invent")
    print("    payload    UNNAMED — do not invent")
    print("    fire       none this seat")
    if titan_exists:
        print("    titan      present (%s bytes)" % titan_size)
    else:
        print("    titan      missing")
    print()
    print("  NEED_BRYCE (do not inject):")
    print("    - inbox dest unpublished by host; machine chooses")
    print("    - --go not authorized this seat")
    print()
    print("  titan_written NO")
    print("  (no write performed; --go was not accepted)")
    print()
    return 0


def main(argv=None):
    a = list(argv if argv is not None else sys.argv[1:])
    if a and a[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    print_plan()
    if "--go" in a:
        print("GO REFUSED: inbox dest is the machine's. Host-named mailbox STRUCK.")
        print("titan_written NO")
        print("(button dies)\n")
        return 1
    print("(button dies)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
