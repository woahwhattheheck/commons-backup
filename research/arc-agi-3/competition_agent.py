"""Adapter for arcprize/ARC-AGI-3-Agents. Copy beside arc3_baseline.py under agents/."""
from __future__ import annotations
import os
from typing import Any
from arcengine import FrameData, GameAction, GameState
from .agent import Agent
from .arc3_baseline import NoveltyExplorer

class SolArc3(Agent):
    MAX_ACTIONS=int(os.environ.get('SOL_ARC3_MAX_ACTIONS','400'))
    def __init__(self,*args:Any,**kwargs:Any)->None:
        super().__init__(*args,**kwargs); self.policy=NoveltyExplorer()
    def is_done(self,frames:list[FrameData],latest_frame:FrameData)->bool:
        return latest_frame.state is GameState.WIN
    def choose_action(self,frames:list[FrameData],latest_frame:FrameData)->GameAction:
        if latest_frame.state in (GameState.NOT_PLAYED,GameState.GAME_OVER): return GameAction.RESET
        d=self.policy.choose(latest_frame.frame,latest_frame.available_actions,state=latest_frame.state,levels_completed=latest_frame.levels_completed)
        action=GameAction.from_id(d.action_id)
        if d.action_id==6: action.set_data(d.as_action_data())
        diag=self.policy.diagnostics(); action.reasoning={'policy':diag['policy'],'reason':d.reason,'unique_states':diag['unique_states'],'known_edges':diag['known_edges'],'frontier_routes':diag['frontier_routes'],'decisions':diag['total_decisions']}
        return action
