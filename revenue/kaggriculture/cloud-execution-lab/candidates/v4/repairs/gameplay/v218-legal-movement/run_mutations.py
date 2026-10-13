import io,json,unittest
import test_v218_movement_parity as tests
import v218_movement_parity as repair
original=repair.transform
mutants=[
('restored_locked_transit',repair.PATH_NEW,repair.PATH_OLD,'test_exact_locked_start_witness_and_final_callback_drop'),
('removed_board_bounds',repair.PATH_NEW,'if False:','test_out_of_bounds_remains_rejected'),
('removed_terminal_drop',"final=commands+home+[['DROP']]",'final=commands+home','test_exact_locked_start_witness_and_final_callback_drop'),
('relaxed_capacity', '_v218_capacity_bound(view)>100','_v218_capacity_bound(view)>101','test_unchanged_plan_price_time_stock_and_parent_guards'),
('lost_collection',"route=commands+walk+[['COLLECT_FERTILIZER']]","route=commands+walk+[['PASS']]",'test_exact_locked_start_witness_and_final_callback_drop')]
rows=[]
for name,old,new,check in mutants:
    def mutant(source,*,enabled=False,old=old,new=new):
        post=original(source,enabled=enabled)
        if enabled:
            if post.count(old)!=1:raise RuntimeError('mutation anchor drift')
            post=post.replace(old,new)
        return post
    repair.transform=mutant
    result=unittest.TextTestRunner(stream=io.StringIO()).run(unittest.TestSuite([tests.MovementParityTests(check)]))
    rows.append(dict(name=name,rejected=not result.wasSuccessful(),failures=len(result.failures),errors=len(result.errors)))
repair.transform=original
print(json.dumps({'optimized':not __debug__,'mutants':rows},sort_keys=True,indent=2))
raise SystemExit(0 if all(r['rejected'] for r in rows) else 1)
