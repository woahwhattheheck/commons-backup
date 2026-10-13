from pathlib import Path
import importlib.util
import json
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("reach", HERE / "check_current_native_reachability.py")
reach = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reach)

BASE_MAIN = '''from titan_runtime import TitanAgent, Features, load\ndef _new_instance(root, feature_data):\n    class FinalPressureAgent(TitanAgent):\n        pass\n    return FinalPressureAgent(Features(**feature_data))\ndef agent(o,c):\n    instance=_new_instance(None,{})\n    return instance.act(o,c)\n'''
BASE_RUNTIME = '''class TitanAgent:\n    def act(self,o,c): return {}\nclass Features:\n    pass\ndef load(*a, **k): return None\nfrom frozen_selected import FrozenSelected\ndef make():\n    self=type("X",(),{})()\n    self.consumer = FrozenSelected()\n    return self\n'''
BASE_FROZEN = 'class FrozenSelected: pass\n'


def make_root(extra=None, config=None):
    td = tempfile.TemporaryDirectory()
    root = Path(td.name)
    (root / 'main.py').write_text(BASE_MAIN)
    (root / 'titan_runtime.py').write_text(BASE_RUNTIME)
    (root / 'frozen_selected.py').write_text(BASE_FROZEN)
    (root / 'TITAN-CONFIG.json').write_text(json.dumps({'consumer':'frozen'} if config is None else config))
    for name, text in (extra or {}).items():
        p = root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    return td, root


class ReachabilityTests(unittest.TestCase):
    def test_baseline_is_blocked(self):
        td, root = make_root()
        try:
            r = reach.audit(root)
            self.assertEqual(r['disposition'], 'BLOCKED_AT_NATIVE_ASSEMBLY')
            self.assertEqual(r['reachable'], {'f3_v217': False, 'night_feed': False, 'opening_book': False})
        finally: td.cleanup()

    def test_comments_and_strings_do_not_bind(self):
        extra = {'helper.py': '# r04_full_router _v217_plan night_feed_frontier\nX="opening_book_rebound OpeningBookRebound prepare apply"\n'}
        td, root = make_root(extra)
        try: self.assertEqual(reach.audit(root)['disposition'], 'BLOCKED_AT_NATIVE_ASSEMBLY')
        finally: td.cleanup()

    def test_candidate_source_cannot_self_bind(self):
        extra = {'candidates/v4/fake.py': 'from r04_full_router import _v217_plan\ndef x(): return _v217_plan(None)\n'}
        td, root = make_root(extra)
        try: self.assertFalse(reach.audit(root)['reachable']['f3_v217'])
        finally: td.cleanup()

    def test_direct_v217_call_binds(self):
        extra = {'f3_entry.py': 'from r04_full_router import _v217_plan\ndef x(): return _v217_plan(None)\n'}
        td, root = make_root(extra)
        try:
            r=reach.audit(root)
            self.assertTrue(r['reachable']['f3_v217'])
            self.assertEqual(r['disposition'],'BOUND_REQUIRES_RUNTIME_GATE')
        finally: td.cleanup()

    def test_dynamic_v217_loader_and_call_binds(self):
        extra = {'f3_entry.py': 'def x(root):\n    m=load("f3", root/"r04_full_router.py")\n    return m._v217_plan(None)\n'}
        td, root = make_root(extra)
        try: self.assertTrue(reach.audit(root)['reachable']['f3_v217'])
        finally: td.cleanup()

    def test_night_feed_call_binds(self):
        extra = {'night.py': 'from night_feed_frontier import propose_feed_tails\ndef x(): return propose_feed_tails({}, {}, [], {}, enabled=True)\n'}
        td, root = make_root(extra)
        try: self.assertTrue(reach.audit(root)['reachable']['night_feed'])
        finally: td.cleanup()

    def test_opening_book_requires_constructor_and_lifecycle(self):
        extra = {'open.py': 'from opening_book_rebound import OpeningBookRebound\ndef x():\n    o=OpeningBookRebound(None)\n    o.prepare({}, {}, {})\n    return o.apply({})\n'}
        td, root = make_root(extra)
        try: self.assertTrue(reach.audit(root)['reachable']['opening_book'])
        finally: td.cleanup()

    def test_opening_import_only_is_not_binding(self):
        extra = {'open.py': 'from opening_book_rebound import OpeningBookRebound\n'}
        td, root = make_root(extra)
        try: self.assertFalse(reach.audit(root)['reachable']['opening_book'])
        finally: td.cleanup()

    def test_generic_seed_budget_is_explicitly_ignored(self):
        extra = {'budget.py': 'from seed_budget import SeedBudget\ndef x(): return SeedBudget(None)\n'}
        td, root = make_root(extra)
        try:
            r=reach.audit(root)
            self.assertFalse(r['reachable']['opening_book'])
            self.assertTrue(r['generic_seed_budget_signals_ignored_for_opening_book'])
        finally: td.cleanup()

    def test_target_config_key_alone_is_not_binding(self):
        td, root = make_root(config={'consumer':'frozen','opening_book_rebound':True})
        try:
            r=reach.audit(root)
            self.assertFalse(r['reachable']['opening_book'])
            self.assertEqual(r['family']['config_target_keys'], ['opening_book_rebound'])
        finally: td.cleanup()

    def test_missing_core_fails_closed(self):
        td, root = make_root()
        try:
            (root/'main.py').unlink()
            with self.assertRaises(ValueError): reach.audit(root)
        finally: td.cleanup()

    def test_syntax_error_fails_closed(self):
        td, root = make_root({'bad.py':'def nope(:\n'})
        try:
            with self.assertRaises(SyntaxError): reach.audit(root)
        finally: td.cleanup()

    def test_unrecognized_call_chain_is_separate_blocker(self):
        td, root = make_root({'main.py':'def agent(o,c): return {}\n'})
        try: self.assertEqual(reach.audit(root)['disposition'],'BLOCKED_UNRECOGNIZED_NATIVE_CHAIN')
        finally: td.cleanup()


if __name__ == '__main__':
    unittest.main()
