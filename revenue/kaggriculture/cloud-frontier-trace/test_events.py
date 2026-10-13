import unittest
import test_trace
from events import production_events, harvest_contract, liquidation_window, fertilizer_contract

class EventTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        test_trace.TraceTests.setUpClass()
        cls.engine=test_trace.TraceTests.engine
    def test_strawberry_events_match_engine(self):
        engine=self.engine
        tile=engine._new_plant('STRAWBERRY',0,24)
        planned=production_events(tile,0)
        self.assertEqual([e['available_step'] for e in planned],[240,288,336,384])
        farm={'tiles':[[tile]]};observed=[]
        for day in range(19):
            tile['watered_today']=True;tile['fertilized_until_day']=day
            before=tile['yield_units']
            engine._daily_refresh_plants(farm,day,24)
            if tile['yield_units']>before:
                observed.append((day+1)*24)
                tile['yield_units']=0 # recorded hypothetical harvest to free capacity
        self.assertEqual(observed,[e['available_step'] for e in planned])
        self.assertEqual(tile['max_lifespan_step'],408)
        self.assertEqual(planned[0]['fertilizer_application_days'],[7,9])
    def test_terminal_and_decay_deadlines(self):
        tile=self.engine._new_plant('STRAWBERRY',20,24)
        self.assertEqual(production_events(tile,480),[]) # day30 output cannot sell
        tile=self.engine._new_plant('WHEAT',0,24)
        tile['yield_units']=4
        contract=harvest_contract(tile,24)
        self.assertEqual(contract['harvest_release_step'],48)
        self.assertEqual(contract['harvest_before_first_decay_step'],120)
        self.assertTrue(contract['survival_action_due_today'])
        self.assertFalse(liquidation_window(718,0,0)['cash_before_terminal'])
        self.assertTrue(liquidation_window(717,0,0)['cash_before_terminal'])
        self.assertEqual(liquidation_window(23,0,20)['earliest_sale_step'],24)
    def test_fertilizer_coverage_uses_refresh_day(self):
        tile=self.engine._new_plant('STRAWBERRY',0,24)
        tile['fertilized_until_day']=9
        target=fertilizer_contract(tile,9*24)
        self.assertEqual(target['care_day'],11) # first day10 output is already covered
        self.assertTrue(target['apply_today_covers_event'])
        tile['fertilized_until_day']=99
        self.assertIsNone(fertilizer_contract(tile,9*24))

    def test_capacity_and_care(self):
        tile=self.engine._new_plant('TOMATO',0,24);tile['yield_units']=4
        self.assertEqual(harvest_contract(tile,180)['capacity_relief_step'],191)
        cow=self.engine._new_animal('COW',0)
        event=production_events(cow,0)[0]
        self.assertEqual(event['available_step'],192)
        self.assertTrue(event['same_day_care_applies_to_later_event'])
        self.assertFalse(liquidation_window(1,0,0,depot_has_capacity=False)['cash_before_terminal'])
if __name__=='__main__': unittest.main()
