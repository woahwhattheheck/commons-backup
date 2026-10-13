from __future__ import annotations

from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from engine import (
    ContractError, STATUS_HOLD, STATUS_READY, Trader, canonical_bytes, compile_result,
    loads_strict, run_continuous, validate_blackbox_action, validate_scenario, verify_result,
)

def load_fixture(name: str):
    return loads_strict((HERE / name).read_bytes())
