"""Reject deliberately corrupted fill receipts, with assertion-only test failures.

These mutate observer OUTPUT semantics, not the engine or a candidate gameplay
policy. Positive control must pass first; errors/skips are never kill credit.
"""
from copy import deepcopy
import io
import json
import unittest
from unittest.mock import patch
import market_fill_ledger as ledger
import test_market_fill_ledger as checks


def corrupt(report, defect):
    result = deepcopy(report)
    if result['status'] != 'complete': return result
    for row in result['rows']:
        if defect == 'requests_are_fills' and row['parsed']:
            row['filled_units'] = row['requested_units']
        elif defect == 'floor_sales_need_market_delta' and row['verb'] == 'SELL':
            row['filled_units'] = sum(row['delta']['market_inventory'].values())
        elif defect == 'net_day_hires' and row['verb'] == 'HIRE' and result['step'] % 24 == 23:
            row['filled_units'] = 0
        elif defect == 'raw_slot_compaction':
            row['raw_slot'] = 0
        elif defect == 'seat_zero_attribution':
            row['seat'] = 0
        elif defect == 'dropped_rows_executed' and not row['in_cap']:
            row['filled_units'] = 1
        elif defect == 'quotes_are_receipts' and row['verb'] in ('BUY_PRODUCT','SELL'):
            sign = 1 if row['verb'] == 'SELL' else -1
            row['delta']['money'] = sign*sum(float(p)*n for p,n in row['quote_counts'].items())
        elif defect == 'gross_fills_are_net_stock' and row['verb'] in ('BUY_PRODUCT','SELL'):
            row['filled_units'] = abs(result['market_delta'][row['seat']]['shed'].get(row['item'],0))
        elif defect == 'town_flow_is_own_trade' and row['verb'] == 'SELL':
            item = row['item']
            value = row['delta']['market_inventory'].get(item,0)
            value += sum(p['delta'][row['seat']]['market_inventory'].get(item,0) for p in result['phases'])
            row['delta']['market_inventory'][item] = value
    return result


def suite(): return unittest.defaultTestLoader.loadTestsFromTestCase(checks.FillTests)

def run():
    records = []
    control = unittest.TextTestRunner(stream=io.StringIO()).run(suite())
    if not control.wasSuccessful() or control.testsRun != 27 or control.skipped:
        raise RuntimeError('positive control failed')
    original = ledger.MarketFillLedger.run
    defects = ('requests_are_fills','floor_sales_need_market_delta','net_day_hires',
               'raw_slot_compaction','seat_zero_attribution','dropped_rows_executed',
               'quotes_are_receipts','gross_fills_are_net_stock','town_flow_is_own_trade')
    for defect in defects:
        def changed(self, state, env, defect=defect):
            return corrupt(original(self,state,env), defect)
        with patch.object(ledger.MarketFillLedger, 'run', changed):
            outcome = unittest.TextTestRunner(stream=io.StringIO()).run(suite())
        if not outcome.failures or outcome.errors or outcome.skipped or outcome.testsRun != 27:
            raise RuntimeError('defect not assertion-rejected: '+defect)
        records.append({'defect':defect,'tests':outcome.testsRun,
                        'assertion_failures':len(outcome.failures),'errors':len(outcome.errors),
                        'failed_test_ids':[test.id() for test,_ in outcome.failures]})
    return {'positive_control_tests':control.testsRun,'kind':'observer-output fault controls, not engine mutants',
            'rejected':records}

if __name__=='__main__':print(json.dumps(run(),indent=2,sort_keys=True))
