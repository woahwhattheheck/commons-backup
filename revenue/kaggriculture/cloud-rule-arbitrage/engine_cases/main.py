# SPDX-License-Identifier: Apache-2.0
"""Research entrypoint: exactly one frozen SELL call, then economic transform."""
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
VENDOR = HERE / 'vendor/sell'
if not VENDOR.is_dir():
    VENDOR = HERE.parents[1] / 'cloud-titan-composition/vendor/sell'
sys.path.insert(0, str(VENDOR))
from scheduler import agent as selected_agent
from liquidity_cycle import LiquidityCycle

_cycle = LiquidityCycle()


def agent(observation, configuration=None):
    global _cycle
    if observation.get('step', -1) == 0:
        _cycle = LiquidityCycle()
    base_action = selected_agent(observation, configuration)
    return _cycle.transform(observation, configuration, base_action)
