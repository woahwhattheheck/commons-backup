# SPDX-License-Identifier: Apache-2.0
# Exact methods extracted from titan_runtime.py blob b952c9c228ecbde592bf3d2df01638677abb0d24.
# This is an isolated method fixture, NOT a complete runtime or runnable agent.
from copy import deepcopy

class TitanAgent:
    def _finish_production(self, obs, returned, cfg=None):
        if self.spatial is not None:
            self.spatial.observe_crop_receipts(obs,
                None if self.history is None else self.history.fill_result,self.controller.cur)
        if self.spatial is not None:
            returned = self.spatial.guard_returned(obs, returned,
                repair_fallback=self.diagnostics.get('status')=='deadline_fallback')
        post = self._selected_snapshot(obs, returned) if self.history is not None else None
        if self.spatial is not None:
            returned=self.spatial.guard_crop_returned(obs,returned,post)
        # This small stock/position calculation is the final market guard, so
        # crop/idle composition and a completed selected fallback cannot undo
        # its same-slot reservation. It never executes a producer or game.
        returned = self._feed_stock_selected(obs, cfg or {}, returned)
        returned = self._early_capital_selected(obs, cfg or {}, returned)
        if self.quadrant is not None:
            self.quadrant.finish(obs, returned)
            self.diagnostics['fourth_quadrant_events'] = list(self.quadrant.events)
            if self._quadrant_admission is not None:
                self.diagnostics['fourth_quadrant_admission'] = deepcopy(
                    self._quadrant_admission.last_report)
        if self.spatial is not None:
            self.spatial.finish(obs, returned, post)
            self.spatial.finish_crop(obs,returned,post,self.controller.cur,
                                     seller_completed=self.diagnostics.get('status')=='completed')
            self.diagnostics['route_events'] = list(self.spatial.events)
            self.diagnostics['idle_fertilizer_receipts'] = list(self.spatial.receipt_events)
            self.diagnostics['idle_fertilizer_obligation'] = deepcopy(self.spatial.sale_obligation)
            if self.features.crop_release:
                self.diagnostics['crop_release']=deepcopy(self.spatial.crop_intent)
                self.diagnostics['crop_release_action']=deepcopy(self.spatial.crop_report)
        if self.history is not None:
            needed = (self.features.terminal_history or
                      (self.spatial is not None and (self.spatial.sale_obligation is not None
                                                     or self.spatial.crop_intent is not None)))
            self.history.remember(obs,cfg or {},returned,
                                  post if needed else None)
            self.diagnostics['history'] = self.history.diagnostics
        return returned

    def _selected_snapshot(self, obs, returned=None):
        if self.features.consumer == 'ordered':
            packet = self.consumer.last_packet
            return None if packet is None else packet['post_unit_observation']
        pair = getattr(self.consumer, 'selected_post_units', None)
        if pair is None:
            if (returned is not None and returned['farmer']==['PASS']
                    and all(a==['PASS'] for a in returned.get('hands',[]))):
                return obs  # PASS has no unit-stage stock mutation; EOD is later.
            return None
        binding = getattr(self.consumer, 'selected_post_units_binding', None)
        if binding is None or binding[:2] != (int(obs['step']),int(obs['player'])):
            return None
        if returned is not None and binding[2:] != (returned['farmer'],returned.get('hands',[])):
            return None
        post = deepcopy(obs)
        post['farms'][int(obs['player'])], post['private'] = pair
        return post
