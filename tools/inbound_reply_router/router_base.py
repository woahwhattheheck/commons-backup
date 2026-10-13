"""Private loader for the byte-preserved inbound reply semantic engine.

The exact reviewed engine source lives in ``_router_engine.pydata``.  It is
executed with a non-``__main__`` module identity so its historical CLI footer is
inert; only ``router.py`` is the supported executable boundary.
"""
from __future__ import annotations

from pathlib import Path
import sys
import types

_ENGINE_PATH = Path(__file__).with_name("_router_engine.pydata")
_ENGINE_NAME = f"{__package__ or 'inbound_reply_router'}._semantic_engine"
_engine = types.ModuleType(_ENGINE_NAME)
_engine.__file__ = str(_ENGINE_PATH)
_engine.__package__ = __package__
sys.modules[_ENGINE_NAME] = _engine
_source = _ENGINE_PATH.read_text(encoding="utf-8")
exec(compile(_source, str(_ENGINE_PATH), "exec"), _engine.__dict__)

for _name, _value in vars(_engine).items():
    if _name in {"__name__", "__file__", "__package__", "__loader__", "__spec__"}:
        continue
    globals()[_name] = _value

del _name, _value, _source, _engine
