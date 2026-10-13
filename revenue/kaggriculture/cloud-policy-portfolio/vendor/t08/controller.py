# SPDX-License-Identifier: MIT
"""T08 production composition. Exactly one authoritative Arlene act per turn.

Vendored policies retain their original licenses. This adapter is new design.
Carrot changes the feature surface of that same controller. Cap harvest uses
its actual selected route and changes only verified free unit slots; original
market order sequence is retained verbatim. No hidden state or future draws.
"""
import importlib.util
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent

def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

class Titan:
    def __init__(self, carrot=False, cap=False):
        self.base_module = load(HERE/'vendor/base/arlene.py', 'titan_arlene')
        if carrot:
            patch = HERE/'vendor/carrot/carrot_demand.py'
            exec(compile(patch.read_text(), str(patch), 'exec'), self.base_module.__dict__)
        if cap:
            sys.path.insert(0, str(HERE/'vendor/claude'))
            import arlene_plan
            import native_motifs
            self.policy = arlene_plan.PlanOverlay(
                self.base_module, arlene_plan.CapChooser(native_motifs.engine()),
                max_steps=arlene_plan.MAX_PLAN_STEPS, deposit=True,
                min_value=0.0, one_way=True)
            self.base = self.policy.agent
        else:
            self.policy = self.base = self.base_module.Agent()
        self.calls = 0

    def act(self, observation, configuration=None):
        self.calls += 1
        return self.policy.act(observation)

def entrypoint(carrot=False, cap=False):
    policy = None
    def agent(observation, configuration=None):
        nonlocal policy
        if policy is None or observation.get('step', -1) == 0:
            policy = Titan(carrot, cap)
        return policy.act(observation, configuration)
    return agent

agent = entrypoint(carrot=True, cap=True)
