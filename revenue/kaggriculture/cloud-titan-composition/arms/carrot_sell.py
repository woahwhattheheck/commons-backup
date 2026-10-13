from pathlib import Path
import sys
HERE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(HERE))
sys.path.insert(0,str(HERE/'vendor/sell'))
from controller import Titan
from scheduler import SellScheduler
_POLICY=None
def agent(obs,cfg=None):
 global _POLICY
 if _POLICY is None or obs.get('step',-1)==0:
  _POLICY=SellScheduler()
  _POLICY.controller=Titan(carrot=True).base
 return _POLICY.act(obs,cfg)
