import main as _canonical
from s02_mpc import DECISION_STEPS, RecedingHorizonGate
_GATE=RecedingHorizonGate(24)
def agent(observation, configuration=None):
    cfg=dict(configuration or {}); step=int(observation.get('step',0))
    if step in DECISION_STEPS:
        inst=getattr(_canonical,'_INSTANCE',None); ctl=getattr(inst,'controller',None)
        _GATE.inspect(observation,cfg,routes=None if ctl is None else ctl.R,current=None if ctl is None else ctl.cur)
    return _canonical.agent(observation,cfg)
