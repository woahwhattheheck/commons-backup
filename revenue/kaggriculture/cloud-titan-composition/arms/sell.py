from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'vendor/sell'))
from scheduler import agent as _scheduler_agent


def agent(obs, configuration=None):
    """Supply the public clock without changing the frozen SELL scheduler."""
    if obs.get('step') is None:
        config = {} if configuration is None else configuration
        step = int(obs['day']) * int(config.get('turnsPerDay', 24)) + int(obs['hour'])
        obs = dict(obs, step=step)
    return _scheduler_agent(obs, configuration)
