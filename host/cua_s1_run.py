"""Run CUA-S1-FORMS against one existing Chrome tab via direct CDP.

The default is a read-only plan. ``--execute`` permits field and checkbox
mutations; ``--submit`` also permits a recognized Submit control.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from cua_s1.driver import DriverError
from cua_s1.schema import Entity

from host.cua_s1_browser import connect_cdp
from host.cua_s1_forms import run_with_driver


def _request(raw: Any) -> tuple[str, list[Entity]]:
    if not isinstance(raw, dict):
        raise ValueError("input must be a JSON object")
    title = raw.get("form_title")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("form_title must be a non-empty string")
    values = raw.get("entities")
    if not isinstance(values, list):
        raise ValueError("entities must be an array of labeled source values")
    entities: list[Entity] = []
    for index, item in enumerate(values):
        if not isinstance(item, dict):
            raise ValueError(f"entities[{index}] must be an object")
        label, value = item.get("label"), item.get("value")
        if not isinstance(label, str) or not label.strip() or not isinstance(value, str):
            raise ValueError(f"entities[{index}] needs a non-empty label and string value")
        entities.append(Entity(label=label.strip(), value=value))
    return title.strip(), entities


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="Exact URL of one already-open Chrome tab")
    parser.add_argument("--checkpoint", required=True, type=Path, help="Official .safetensors with matching .json sidecar")
    parser.add_argument("--input", type=Path, help="JSON with form_title and entities; stdin by default")
    parser.add_argument("--cdp-endpoint", default="http://127.0.0.1:9222", help="Direct Chrome debugging endpoint")
    parser.add_argument("--device", default="auto", help="PyTorch device")
    parser.add_argument("--min-confidence", type=float, default=0.5)
    parser.add_argument("--execute", action="store_true", help="Apply selected fills and checks after preflight")
    parser.add_argument("--submit", action="store_true", help="With --execute, also permit one recognized Submit click")
    args = parser.parse_args(argv)
    driver = None
    try:
        content = args.input.read_text(encoding="utf-8") if args.input else sys.stdin.read()
        form_title, entities = _request(json.loads(content))
        driver, target = connect_cdp(args.url, args.cdp_endpoint, allow_submit=args.submit)
        result = run_with_driver(
            checkpoint=args.checkpoint,
            driver=driver,
            target=target,
            form_title=form_title,
            entities=entities,
            device=args.device,
            min_confidence=args.min_confidence,
            execute=args.execute,
            submit=args.submit,
        )
    except DriverError as exc:
        result = {"ok": False, "error": exc.to_dict(), "execution_order": []}
    except (OSError, ValueError, RuntimeError, ImportError) as exc:
        result = {"ok": False, "error": {"code": "run_unavailable", "message": str(exc)}, "execution_order": []}
    finally:
        if driver is not None:
            driver.close()
    print(json.dumps(result, separators=(",", ":")))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
