import json, tempfile, unittest
from pathlib import Path
from unittest import mock
import check_current_native_binding as g


class TestGate(unittest.TestCase):
    def tree(self, td, main='def agent(o,c=None): return {}\n',
             runtime='class X: pass\n', cfg=None, extra=None):
        r=Path(td)
        (r/'main.py').write_text(main)
        (r/'titan_runtime.py').write_text(runtime)
        (r/'TITAN-CONFIG.json').write_text(
            json.dumps({"consumer":"frozen"} if cfg is None else cfg)
        )
        if extra:
            for name,text in extra.items():
                p=r/name
                p.parent.mkdir(parents=True,exist_ok=True)
                p.write_text(text)
        return r

    def semantic_tree(self, td, *, locked_bug=False, shed_bug=False):
        move_body = (
            "  if tile == 'LOCKED': return True\n"
            if locked_bug else ""
        )
        shed = (
            " return (x,y) in ((h-1,h-1),(h,h-1),(h-1,h))\n"
            if shed_bug else
            " return (x,y) in ((h-1,h-1),(h,h-1),(h-1,h),(h,h))\n"
        )
        arlene = (
            "BOARD=10\n"
            "MOVES={'NORTH':(0,-1),'SOUTH':(0,1),'EAST':(1,0),'WEST':(-1,0)}\n"
            "ANIMALS={}\n"
            "def _shed_adjacent(x,y,board=BOARD):\n"
            " h=board//2\n" + shed +
            "def _noop(act,tile,inv,seeds,x,y,board=BOARD):\n"
            " if not act:return True\n"
            " op=act[0]\n"
            " if op in MOVES:\n" +
            move_body +
            "  dx,dy=MOVES[op]\n"
            "  return not (0<=x+dx<board and 0<=y+dy<board)\n"
            " if op=='PASS':return True\n"
            " if tile=='LOCKED':return True\n"
            " return False\n"
        )
        spatial = (
            "MOVES={'NORTH':(0,-1),'SOUTH':(0,1),'EAST':(1,0),'WEST':(-1,0)}\n"
            "def move(pos,action,board):\n"
            " d=MOVES.get(action[0] if action else '')\n"
            " if d:\n"
            "  q=(pos[0]+d[0],pos[1]+d[1])\n"
            "  if 0<=q[0]<board and 0<=q[1]<board:return q\n"
            " return pos\n"
            "def path(a,b):\n"
            " return [[('EAST' if b[0]>a[0] else 'WEST')]]*abs(b[0]-a[0])+[[('SOUTH' if b[1]>a[1] else 'NORTH')]]*abs(b[1]-a[1])\n"
        )
        return self.tree(
            td,
            main=(
                "from titan_runtime import TitanAgent, Features, load\n"
                "def f(features):\n"
                " return FinalPressureAgent(features)\n"
            ),
            runtime=(
                "from frozen_selected import FrozenSelected\n"
                "from spatial_tempo import SpatialTempo\n"
                "class X:\n"
                " def f(self):\n"
                "  self.consumer = FrozenSelected()\n"
                "  self.spatial.install(self.controller)\n"
            ),
            cfg={"consumer":"frozen","terminal_route":False},
            extra={
                "frozen_selected.py":"from scheduler import *\n",
                "scheduler.py":"parent = _load('intact_arlene', HERE/'reference/next-panel/vendor/arlene.py')\n",
                "reference/next-panel/vendor/arlene.py":arlene,
                "spatial_tempo.py":spatial,
            },
        )

    def register_semantic_graph(self, root, *, mutate_source=None, omit_source=None,
                                checker_drift=False, wrong_state=False):
        checker = root/'candidates/v4'/g.V218_CHECKER_REL
        checker.parent.mkdir(parents=True,exist_ok=True)
        checker.write_text("# synthetic registered checker\n")
        checker_blob=g.git_blob(checker.read_bytes())
        source_ids={
            "main.py": g.git_blob((root/"main.py").read_bytes()),
            "titan_runtime.py": g.git_blob((root/"titan_runtime.py").read_bytes()),
            "TITAN-CONFIG.json": g.git_blob((root/"TITAN-CONFIG.json").read_bytes()),
            "frozen_selected.py": g.git_blob((root/"frozen_selected.py").read_bytes()),
            "scheduler.py": g.git_blob((root/"scheduler.py").read_bytes()),
            "reference/next-panel/vendor/arlene.py":
                g.git_blob((root/"reference/next-panel/vendor/arlene.py").read_bytes()),
            "spatial_tempo.py":
                g.git_blob((root/"spatial_tempo.py").read_bytes()),
        }
        if mutate_source is not None:
            source_ids[mutate_source]="0"*40
        if omit_source is not None:
            source_ids.pop(omit_source)
        receipt={
            "schema":"titan-v4-v218-native-semantic-equivalence/v1",
            "status":"source_revalidated_execution_not_rerun",
            "semantic_checker":{
                "path":g.V218_CHECKER_REL,
                "git_blob":("0"*40 if checker_drift else checker_blob),
                "semantic_disposition_when_all_fail_closed_probes_pass":
                    "NATIVE_SEMANTIC_EQUIVALENT_REQUIRES_RUNTIME_GATE",
            },
            "current_source_identities":source_ids,
            "semantic_evidence":{"frozen_nonterminal_config":True},
            "control_plane_disposition":"evidence_only_no_transform_required",
            "runtime_promotion_authority":False,
            "economic_authority":False,
        }
        receipt_path=root/'candidates/v4'/g.V218_RECEIPT_REL
        receipt_path.parent.mkdir(parents=True,exist_ok=True)
        receipt_path.write_text(json.dumps(receipt))
        graph={
            "schema":"titan-v4-composition/v1",
            "components":[{
                "id":g.V218_COMPONENT_ID,
                "state":"blocked" if wrong_state else "evidence_only",
                "package":g.V218_PACKAGE,
                "entrypoints":[g.V218_CHECKER_REL],
                "receipt":g.V218_RECEIPT_REL,
                "transforms":[],
                "requires":[],
                "before":[],
                "after":[],
                "conflicts":[],
            }],
        }
        graph_path=root/g.GRAPH_REL
        graph_path.parent.mkdir(parents=True,exist_ok=True)
        graph_path.write_text(json.dumps(graph))

    def test_unwired_blocks(self):
        with tempfile.TemporaryDirectory() as td:
            x=g.audit(self.tree(td))
            self.assertFalse(x['wired'])
            self.assertEqual(x['disposition'],'BLOCKED_AT_NATIVE_ASSEMBLY')

    def test_unused_runtime_import_is_diagnostic_not_wiring(self):
        with tempfile.TemporaryDirectory() as td:
            x=g.audit(self.tree(td, runtime='from r04_full_router import install\n'))
            self.assertFalse(x['wired'])
            self.assertFalse(x['explicit_binding'])
            self.assertTrue(x['source_binding_diagnostic'])
            self.assertGreater(x['router_ref_count'],0)
            self.assertEqual(x['disposition'],'DIRECT_BINDING_UNVERIFIED')

    def test_unimported_module_reference_is_diagnostic_not_wiring(self):
        with tempfile.TemporaryDirectory() as td:
            x=g.audit(self.tree(td,extra={'diagnostics.py':'import r04_full_router\n'}))
            self.assertFalse(x['wired'])
            self.assertFalse(x['explicit_binding'])
            self.assertTrue(x['source_binding_diagnostic'])
            self.assertEqual(x['disposition'],'DIRECT_BINDING_UNVERIFIED')
            self.assertIn('diagnostics.py',{row['path'] for row in x['source_binding_refs']})

    def test_dead_branch_import_is_diagnostic_not_wiring(self):
        with tempfile.TemporaryDirectory() as td:
            runtime="if False:\n import r04_full_router\n"
            x=g.audit(self.tree(td,runtime=runtime))
            self.assertFalse(x['wired'])
            self.assertFalse(x['explicit_binding'])
            self.assertTrue(x['source_binding_diagnostic'])
            self.assertEqual(x['disposition'],'DIRECT_BINDING_UNVERIFIED')

    def test_dead_function_token_is_diagnostic_not_wiring(self):
        with tempfile.TemporaryDirectory() as td:
            runtime="def diagnostic():\n return v218_probe\n"
            x=g.audit(self.tree(td,runtime=runtime))
            self.assertFalse(x['wired'])
            self.assertFalse(x['explicit_binding'])
            self.assertTrue(x['source_binding_diagnostic'])
            self.assertGreater(x['v218_ref_count'],0)
            self.assertEqual(x['disposition'],'DIRECT_BINDING_UNVERIFIED')

    def test_v218_config_is_diagnostic_not_wiring(self):
        with tempfile.TemporaryDirectory() as td:
            x=g.audit(self.tree(td,cfg={'r04_v218_movement_parity':False}))
            self.assertFalse(x['wired'])
            self.assertFalse(x['explicit_binding'])
            self.assertFalse(x['source_binding_diagnostic'])
            self.assertEqual(x['config']['v218_keys'],['r04_v218_movement_parity'])

    def test_inert_comment_and_string_tokens_do_not_wire(self):
        with tempfile.TemporaryDirectory() as td:
            runtime=(
                "class X: pass\n"
                "# r04_full_router v218 movement_parity documentation only\n"
                "DOC='r04_full_router v218 movement_parity'\n"
            )
            x=g.audit(self.tree(td,runtime=runtime))
            self.assertFalse(x['wired'])
            self.assertFalse(x['explicit_binding'])
            self.assertFalse(x['source_binding_diagnostic'])
            self.assertGreater(len(x['binding_refs']),0)
            self.assertEqual(x['source_binding_refs'],[])

    def test_reference_checks_do_not_fake_wiring(self):
        with tempfile.TemporaryDirectory() as td:
            x=g.audit(self.tree(td,extra={'checks/reference/note.py':'r04_full_router v218'}))
            self.assertFalse(x['wired'])

    def test_candidate_control_plane_tokens_do_not_fake_explicit_wiring(self):
        with tempfile.TemporaryDirectory() as td:
            r=self.tree(td,extra={'candidates/v4/note.py':'r04_full_router v218 movement_parity'})
            x=g.audit(r)
            self.assertFalse(x['explicit_binding'])
            self.assertFalse(x['source_binding_diagnostic'])
            self.assertFalse(x['wired'])

    def test_native_semantic_equivalence_requires_graph_registration(self):
        with tempfile.TemporaryDirectory() as td:
            r=self.semantic_tree(td)
            x=g.audit(r)
            self.assertTrue(x['native_semantic_equivalence']['equivalent'])
            self.assertFalse(x['semantic_wired'])
            self.assertEqual(x['disposition'],'BLOCKED_AT_GRAPH_REGISTRATION')

    def test_authenticated_graph_receipt_wires_native_semantic_equivalence(self):
        with tempfile.TemporaryDirectory() as td:
            r=self.semantic_tree(td)
            self.register_semantic_graph(r)
            x=g.audit(r)
            self.assertTrue(x['semantic_graph_registration']['registered'])
            self.assertTrue(x['semantic_wired'])
            self.assertTrue(x['wired'])
            self.assertEqual(x['disposition'],'NATIVE_SEMANTIC_EQUIVALENT_REQUIRES_RUNTIME_GATE')

    def test_receipt_source_pin_drift_blocks_semantic_wiring(self):
        with tempfile.TemporaryDirectory() as td:
            r=self.semantic_tree(td)
            self.register_semantic_graph(r,mutate_source="spatial_tempo.py")
            x=g.audit(r)
            self.assertFalse(x['semantic_graph_registration']['registered'])
            self.assertEqual(x['semantic_graph_registration']['reason'],'semantic_source_identity_mismatch')
            self.assertFalse(x['wired'])

    def test_receipt_main_pin_drift_blocks_semantic_wiring(self):
        with tempfile.TemporaryDirectory() as td:
            r=self.semantic_tree(td)
            self.register_semantic_graph(r,mutate_source="main.py")
            x=g.audit(r)
            self.assertFalse(x['semantic_graph_registration']['registered'])
            self.assertEqual(x['semantic_graph_registration']['reason'],'semantic_source_identity_mismatch')
            self.assertFalse(x['wired'])

    def test_receipt_source_omission_blocks_semantic_wiring(self):
        with tempfile.TemporaryDirectory() as td:
            r=self.semantic_tree(td)
            self.register_semantic_graph(r,omit_source="scheduler.py")
            x=g.audit(r)
            self.assertFalse(x['semantic_graph_registration']['registered'])
            self.assertEqual(x['semantic_graph_registration']['reason'],'semantic_source_identity_set_mismatch')
            self.assertFalse(x['wired'])

    def test_receipt_checker_pin_drift_blocks_semantic_wiring(self):
        with tempfile.TemporaryDirectory() as td:
            r=self.semantic_tree(td)
            self.register_semantic_graph(r,checker_drift=True)
            x=g.audit(r)
            self.assertFalse(x['semantic_graph_registration']['registered'])
            self.assertEqual(x['semantic_graph_registration']['reason'],'checker_identity_mismatch')
            self.assertFalse(x['wired'])

    def test_malformed_semantic_source_row_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            r=self.semantic_tree(td)
            self.register_semantic_graph(r)
            original=g._native_semantic_equivalence
            def malformed(root,config):
                result=original(root,config)
                result['sources']['main'].pop('path')
                return result
            with mock.patch.object(g,'_native_semantic_equivalence',side_effect=malformed):
                x=g.audit(r)
            self.assertFalse(x['wired'])
            self.assertEqual(x['semantic_graph_registration']['reason'],'semantic_source_receipt_missing')
            self.assertEqual(x['semantic_graph_registration']['source'],'main')

    def test_each_semantic_source_swap_after_proof_is_rejected(self):
        paths=(
            'main.py','titan_runtime.py','frozen_selected.py','scheduler.py',
            'reference/next-panel/vendor/arlene.py','spatial_tempo.py',
        )
        for rel in paths:
            with self.subTest(rel=rel):
                with tempfile.TemporaryDirectory() as td:
                    r=self.semantic_tree(td)
                    self.register_semantic_graph(r)
                    original=g._native_semantic_equivalence
                    def swapped(root,config,rel=rel):
                        result=original(root,config)
                        p=root/rel
                        p.write_text(p.read_text()+'\n# post-proof drift\n')
                        return result
                    with mock.patch.object(g,'_native_semantic_equivalence',side_effect=swapped):
                        x=g.audit(r)
                    self.assertFalse(x['semantic_wired'])
                    self.assertFalse(x['wired'])
                    self.assertEqual(x['semantic_graph_registration']['reason'],'semantic_source_changed_after_proof')
                    self.assertEqual(x['semantic_graph_registration']['source'],rel)

    def test_config_swap_after_proof_cannot_rebind_receipt(self):
        with tempfile.TemporaryDirectory() as td:
            r=self.semantic_tree(td)
            self.register_semantic_graph(r)
            original=g._native_semantic_equivalence
            receipt_path=r/'candidates/v4'/g.V218_RECEIPT_REL
            def swapped(root,config):
                result=original(root,config)
                config_path=root/'TITAN-CONFIG.json'
                config_path.write_text(json.dumps({'consumer':'other','terminal_route':True}))
                receipt=json.loads(receipt_path.read_text())
                receipt['current_source_identities']['TITAN-CONFIG.json']=g.git_blob(config_path.read_bytes())
                receipt_path.write_text(json.dumps(receipt))
                return result
            with mock.patch.object(g,'_native_semantic_equivalence',side_effect=swapped):
                x=g.audit(r)
            self.assertFalse(x['semantic_wired'])
            self.assertFalse(x['wired'])
            self.assertEqual(x['semantic_graph_registration']['reason'],'semantic_source_identity_mismatch')

    def test_graph_wrong_state_blocks_semantic_wiring(self):
        with tempfile.TemporaryDirectory() as td:
            r=self.semantic_tree(td)
            self.register_semantic_graph(r,wrong_state=True)
            x=g.audit(r)
            self.assertFalse(x['semantic_graph_registration']['registered'])
            self.assertEqual(x['semantic_graph_registration']['reason'],'semantic_component_not_evidence_only')
            self.assertFalse(x['wired'])

    def test_locked_move_bug_fails_equivalence(self):
        with tempfile.TemporaryDirectory() as td:
            x=g.audit(self.semantic_tree(td, locked_bug=True))
            self.assertFalse(x['native_semantic_equivalence']['equivalent'])
            self.assertFalse(x['native_semantic_equivalence']['rules']['locked_transit_matches_engine'])
            self.assertFalse(x['wired'])

    def test_three_corner_shed_bug_fails_equivalence(self):
        with tempfile.TemporaryDirectory() as td:
            x=g.audit(self.semantic_tree(td, shed_bug=True))
            self.assertFalse(x['native_semantic_equivalence']['equivalent'])
            self.assertFalse(x['native_semantic_equivalence']['rules']['all_four_shed_corners_eligible'])
            self.assertFalse(x['wired'])

    def test_cli_require_wired_exit3_without_graph_registration(self):
        with tempfile.TemporaryDirectory() as td:
            r=self.semantic_tree(td)
            self.assertEqual(g.main([str(r),'--require-wired']),3)

    def test_cli_semantic_graph_satisfies_require_wired(self):
        with tempfile.TemporaryDirectory() as td:
            r=self.semantic_tree(td)
            self.register_semantic_graph(r)
            self.assertEqual(g.main([str(r),'--require-wired']),0)


if __name__=='__main__':
    unittest.main()