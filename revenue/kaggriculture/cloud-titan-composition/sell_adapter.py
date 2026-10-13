# SPDX-License-Identifier: MIT
"""Conservative T08 adapter over ASTRA's unchanged SELL optimizer.

New integration design, not the author's requested future generic interface.
The caller owns production and supplies its already selected action. A proxy
provides that action once and exposes the same owner's current route for market
reservations. Changed unit arrivals receive an explicit upper capacity reserve;
they are never asserted to follow the unchanged parent's deposit timing.
"""
import copy
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE/'vendor/sell'))
from scheduler import SellScheduler

class SelectedAction:
    def __init__(self, owner):
        self.owner = owner
        self.action = None
        self.used = False
    @property
    def R(self):
        return self.owner.R
    @property
    def cur(self):
        return self.owner.cur
    def act(self, observation):
        if self.used or self.action is None:
            raise RuntimeError('Selected action must be supplied exactly once')
        self.used = True
        return copy.deepcopy(self.action)

class SelectedActionSell(SellScheduler):
    def __init__(self, base_owner):
        # Explicit initialization avoids constructing an unused parent controller.
        self.controller = SelectedAction(base_owner)
        self.mode = 'candidate'
        self.pending = {}
        self.planned = {}
        self.previous = None
        self.observed_harvests = {}
        self.diagnostics = {}
        self.extra_capacity_reserve = 0

    def transform(self, observation, configuration, selected_action, *,
                  extra_capacity_reserve=0):
        """Transform SELL quantities while retaining ordered inherited expenses.

        extra_capacity_reserve is an upper bound on deposits that changed unit
        routes could deliver earlier/in addition to the parent's projected path.
        It is capacity protection, not guaranteed harvest, output or sale.
        Current unit execution still uses actual configured capacity. The reserve
        is applied only to future/post-market feasibility in receipt_profile.
        """
        if extra_capacity_reserve < 0:
            raise ValueError('Capacity reserve cannot be negative')
        self.extra_capacity_reserve = int(extra_capacity_reserve)
        self.controller.action = selected_action
        self.controller.used = False
        return super().act(observation, configuration)

    def receipt_profile(self, obs, base, farm, private, end, item, config):
        protected = dict(config)
        protected['shedCapacity'] = max(0, int(config.get('shedCapacity',100))
                                         - self.extra_capacity_reserve)
        return super().receipt_profile(obs,base,farm,private,end,item,protected)

def cap_arrival_reserve(observation):
    """Broad same-day upper envelope for cap-harvest route deviations.

    Cap only HARVESTs existing animals and never changes care/production/market.
    Before end-of-day animal production, all collectible animal yield is bounded
    by visible held yield. All current carried stock is added because a changed
    walk could deposit it earlier than the reference route. Double-counting is
    deliberate conservative capacity protection, not an output prediction.
    """
    farm = observation['farms'][int(observation['player'])]
    held = sum(max(0,int(tile.get('yield_units',0)))
               for row in farm['tiles'] for tile in row
               if isinstance(tile,dict) and tile.get('animal') is not None)
    carried = sum(max(0,int(n)) for inv in observation['private'].get('inventories',[])
                  for n in inv.values())
    return held + carried

class CapSell:
    def __init__(self, carrot=True):
        from controller import Titan
        self.production = Titan(carrot=carrot, cap=True)
        self.execution = SelectedActionSell(self.production.base)

    def act(self, obs, cfg=None):
        selected = self.production.act(obs,cfg)
        return self.execution.transform(obs,cfg,selected,
            extra_capacity_reserve=cap_arrival_reserve(obs))

_INSTANCE = None
def agent(obs,cfg=None):
    global _INSTANCE
    if _INSTANCE is None or obs.get('step',-1)==0:
        _INSTANCE = CapSell()
    return _INSTANCE.act(obs,cfg)
