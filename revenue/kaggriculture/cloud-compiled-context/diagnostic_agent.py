# SPDX-License-Identifier: MIT OR CC-BY-4.0
"""Development-only daily state trace. Not part of standalone candidate export."""
import json
import os
from pathlib import Path
import candidate

TRACE_PREFIX = None


def agent(obs, configuration=None):
    action = candidate.agent(obs, configuration)
    step = obs.get("step", 0)
    turns = candidate._get(configuration, "turnsPerDay", 24)
    terminal = candidate._get(configuration, "episodeSteps", 720)-2
    if candidate._PLAN and ((step+1)%turns == 0 or step == terminal):
        row = {k: candidate._PLAN[k] for k in ("day", "step", "phase", "status", "observed", "installation_target", "crop_target", "backlog", "completed_count", "expired_count", "cash_reserve", "animal_attempts", "budget_actions", "reserved_service_actions")}
        path = TRACE_PREFIX or os.environ.get("KAG_CONTEXT_TRACE")
        if path:
            with Path(path+"-seat"+str(obs["player"])+".jsonl").open("a") as f:
                f.write(json.dumps(row, sort_keys=True)+"\n")
    return action
