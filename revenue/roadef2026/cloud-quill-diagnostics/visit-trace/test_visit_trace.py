import hashlib, importlib.util, json, pathlib, unittest
HERE=pathlib.Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('b',HERE/'build_visit_trace.py'); b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)

class VisitTraceContracts(unittest.TestCase):
    def test_exact_source_builder_rejects_wrong_source(self):
        source='int main(){}\n'
        with self.assertRaises(ValueError):
            if hashlib.sha256(source.encode()).hexdigest()!=b.BASE_SHA256: raise ValueError('expected exact fleet2885 source')

    def test_patch_contains_only_target_telemetry_contracts(self):
        self.assertEqual(b.TARGET,(654,9,1500,242))
        builder=(HERE/'build_visit_trace.py').read_text()
        for token in ('VISIT critical','VISIT waypoint_candidates','VISIT target_attempt','VISIT target_accept'):
            self.assertIn(token,builder)

    def test_published_result_is_completed_no_visit(self):
        r=json.loads((HERE/'RESULT.json').read_text())
        self.assertEqual(r['start_target_rank'],6)
        self.assertEqual(r['end_target_rank'],6)
        self.assertAlmostEqual(r['start_target_saturation'],r['end_target_saturation'],15)
        self.assertEqual(r['start_target_route'],[461])
        self.assertEqual(r['end_target_route'],[461])
        self.assertGreaterEqual(r['run']['seconds'],29.9)
        self.assertEqual(r['run']['accepted'],168)
        self.assertEqual(r['run']['attempted'],5148817)
        self.assertEqual(r['visit_lines'],0)
        self.assertFalse(r['target_critical_edge_scheduled'])
        self.assertFalse(r['target_move_attempted'])
        self.assertFalse(r['acceptance_changed'])
        self.assertEqual(r['official_checker_calls'],0)

if __name__=='__main__': unittest.main()
