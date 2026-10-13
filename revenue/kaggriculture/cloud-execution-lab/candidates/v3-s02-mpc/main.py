# SPDX-License-Identifier: Apache-2.0
"""MPC wrapper around the unchanged canonical TITAN agent.

Disable with TITAN_MPC=0. Horizon via TITAN_MPC_H (default 12).
Planning budget TITAN_MPC_BUDGET (default 0.6 s).
"""
import os
from canonical_main import agent as _canonical_agent
from planner_mpc import Planner

_H = int(os.environ.get("TITAN_MPC_H", "12"))
_BUDGET = float(os.environ.get("TITAN_MPC_BUDGET", "0.6"))
_PLANNER = Planner(_canonical_agent, horizon=_H, budget_s=_BUDGET)


def agent(observation, configuration=None):
    return _PLANNER.act(observation, configuration)
