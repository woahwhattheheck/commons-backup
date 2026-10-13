#!/usr/bin/env python3
"""host/sdc_os_start.py — start the SDC OS (Phase 4, the one command). Brings up the two ISOLATED processes in the right
order and manages them as a pair:

  1) the checker  (sdc_os_checker.py, 7905) — resident, one job: read the safezone, feed the UI. Started FIRST so the
     browser always opens onto a live feed (no dead-endpoint retrying).
  2) the UI       (sdc_os_ui.py, 7904)      — text field + Send; Send fires the orchestrator run, which routes the prompt
     through a verified circuit on the SDC and deposits the result to the safezone, then dies.

Ctrl+C tears BOTH down together (no orphans). Type a request in the page (e.g. `9094 * 40496`, `is 31537 > 30968`) — an
exact/verifiable request is answered by a verified circuit computed CONTAINED on the SDC; anything ungrounded is refused.

  python host/sdc_os_start.py
"""
import os, subprocess, sys, time, webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
sys.stdout.reconfigure(encoding="utf-8")
PY = sys.executable
UI_URL = "http://127.0.0.1:7904/"


def main():
    checker = subprocess.Popen([PY, os.path.join(HERE, "sdc_os_checker.py")])
    time.sleep(0.8)                                           # let the feed bind before the page (browser) attaches
    ui = subprocess.Popen([PY, os.path.join(HERE, "sdc_os_ui.py"), "--no-open"])
    time.sleep(0.8)
    print(f"\nSDC OS up.  UI: {UI_URL}   checker feed: http://127.0.0.1:7905/")
    print("type a request in the page — grounded exact answers via verified circuits on the SDC; ungrounded -> refused.")
    print("Ctrl+C here tears both down.\n")
    try: webbrowser.open(UI_URL)
    except Exception: pass
    try:
        while True:
            if checker.poll() is not None or ui.poll() is not None:
                print("a server exited; shutting the other down."); break
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nstopping.")
    finally:
        for p in (ui, checker):
            if p.poll() is None:
                p.terminate()
                try: p.wait(timeout=5)
                except Exception: p.kill()
        print("both servers down (no orphans). close the browser tab to stop its reconnect.")


if __name__ == "__main__":
    raise SystemExit(main())
