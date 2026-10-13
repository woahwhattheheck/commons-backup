#!/usr/bin/env python3
"""Direct isolated-CLI CURRENT authority for UArk RFP09112026.

Imported CURRENT APIs and CURRENT-looking rendering fail closed. Historical replay
remains explicit. Only direct ``python -I -S current_authority.py`` execution may
sample process UTC and emit a CURRENT packet or verification receipt.
"""
from __future__ import annotations

import importlib.util
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


def _load_adjacent(name: str, filename: str):
    path = Path(__file__).with_name(filename).resolve()
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:  # pragma: no cover
        raise ImportError(f"cannot load {name} from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_policy = _load_adjacent("uark_current_policy", "_current_policy.py")
_renderers = _load_adjacent("uark_current_render", "_current_render.py")
_entry = _load_adjacent("uark_current_entry", "_current_entry.py")
del _load_adjacent

InputError = _policy.InputError
canonical_json = _policy.canonical_json
sha256_obj = _policy.sha256_obj
read_json_file = _policy.read_json_file
compile_historical = _policy.compile_historical
verify_packet_historical = _policy.verify_packet_historical
CURRENT_VERIFICATION_SCHEMA = _policy.CURRENT_VERIFICATION_SCHEMA
CURRENT_AUTHORITY_MODE = _policy.CURRENT_AUTHORITY_MODE
_core = _policy._core  # historical compatibility only; CURRENT public APIs ignore it


def _clock_factory(
    time_ns: Callable[[], int],
    fromtimestamp: Callable[..., datetime],
    utc: timezone,
) -> Callable[[], datetime]:
    def sample() -> datetime:
        return fromtimestamp(time_ns() // 1_000_000_000, tz=utc).replace(microsecond=0)

    return sample


_PROCESS_NOW = _clock_factory(time.time_ns, datetime.fromtimestamp, timezone.utc)
del _clock_factory


def _make_fail_closed(error_type: type[Exception]):
    authority_message = (
        "CURRENT authority is CLI-only; invoke current_authority.py directly with "
        "python -I -S"
    )
    markdown_message = (
        "CURRENT markdown is CLI-only; invoke current_authority.py directly with "
        "python -I -S"
    )

    def compile_current(intake: Any) -> dict[str, Any]:
        del intake
        raise error_type(authority_message)

    def verify_packet_current(packet: Any) -> dict[str, Any]:
        del packet
        raise error_type(authority_message)

    def render_markdown(packet: dict[str, Any]) -> str:
        del packet
        raise error_type(markdown_message)

    return compile_current, verify_packet_current, render_markdown


compile_current, verify_packet_current, render_markdown = _make_fail_closed(InputError)
compile_production = compile_current
del _make_fail_closed


render_markdown_historical = _renderers.make_historical_renderer(
    verify_packet_historical
)
_render_current = _renderers.make_current_renderer(verify_packet_historical)
_REQUIRE_DIRECT_ISOLATED_ENTRY = _entry.make_entry_guard(
    InputError,
    __name__ == "__main__",
    bool(sys.flags.isolated),
    bool(sys.flags.no_site),
)
main = _entry.make_main(
    InputError,
    _REQUIRE_DIRECT_ISOLATED_ENTRY,
    _policy._compile_at_now,
    _policy._verify_at_now,
    _PROCESS_NOW,
    read_json_file,
    canonical_json,
    _core._write_exclusive,
    _render_current,
    sys.stdout,
    sys.stderr,
)


if __name__ == "__main__":
    raise SystemExit(main())
