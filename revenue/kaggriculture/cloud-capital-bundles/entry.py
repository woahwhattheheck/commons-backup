# SPDX-License-Identifier: Apache-2.0
"""Optional complete-route development candidate; frozen selected SELL is unchanged."""
from pathlib import Path
import sys
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / 'cloud-titan-composition' / 'vendor' / 'sell'))
import scheduler
from capital_routes import choose_before_action

class CapitalBundleAgent:
    def __init__(self):
        self.scheduler = scheduler.SellScheduler()
        self.selection = None

    def act(self, observation, configuration=None):
        config = configuration or {}
        if int(observation.get('step', -1)) == 226:
            self.selection = choose_before_action(self.scheduler.controller, observation, config, scheduler.m)
        return self.scheduler.act(observation, config)

_INSTANCE = None

def make_agent():
    return CapitalBundleAgent()

def agent(observation, configuration=None):
    global _INSTANCE
    if _INSTANCE is None or int(observation.get('step', -1)) == 0:
        _INSTANCE = make_agent()
    return _INSTANCE.act(observation, configuration)
