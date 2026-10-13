import json
import tempfile
import unittest
from pathlib import Path

import evidence_search as mod

ROOT = Path(__file__).parent
MANIFEST = ROOT / "fixtures" / "manifest.json"

class SearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = mod.load_manifest(MANIFEST)
        cls.index = mod.build_index(cls.records)

    def test_real_merged_schema_counts(self):
        self.assertEqual(len(self.records), 27)  # 12 source + 8 obs + 3 findings + 4 extracted segments
        self.assertEqual(sum(r['record_type']=='source_metadata' for r in self.records), 12)
        self.assertEqual(sum(r['record_type']=='observation' for r in self.records), 8)
        self.assertEqual(sum(r['record_type']=='finding' for r in self.records), 3)
        self.assertEqual(sum(r['record_type']=='extracted_text' for r in self.records), 4)

    def test_vulnerability_ownership_hit_preserves_source_ref(self):
        rows = mod.search(self.index, "vulnerability ownership", limit=3)
        self.assertEqual(rows[0]['record_id'], 'RIS-SEC-01')
        self.assertEqual(rows[0]['source_url'], 'synthetic://uiowa-rfq18649/RIS-SEC-01')
        self.assertEqual(rows[0]['upstream_blob_sha'], '1d58638c067b35dbdc210365ac3f30d6e72c9548')

    def test_end_to_end_propagation_finds_finding_and_observation(self):
        rows = mod.search(self.index, "end to end propagation", limit=5)
        ids = [r['record_id'] for r in rows]
        self.assertIn('F-002', ids)
        self.assertIn('E-005', ids)
        f = next(r for r in rows if r['record_id']=='F-002')
        self.assertEqual(f['linked_ids'], ['E-004','E-005','E-006'])

    def test_extracted_locator_is_exact(self):
        rows = mod.search(self.index, "independent review before merge", limit=2)
        self.assertEqual(rows[0]['record_type'], 'extracted_text')
        self.assertEqual(rows[0]['locator'], 'lines 2-2')
        self.assertTrue(rows[0]['source_url'].endswith('/revenue/uiowa_rfq_18649_document_extraction/fixtures/sample.txt'))

    def test_stale_deployment_search_finds_iam_source(self):
        rows = mod.search(self.index, "deployment runbook intentionally stale", limit=3)
        self.assertEqual(rows[0]['record_id'], 'IAM-DEP-01')

    def test_missing_term_returns_no_result(self):
        self.assertEqual(mod.search(self.index, "nonexistentquasarword"), [])

    def test_unicode_tokenizer_and_multiline_snippet(self):
        record = mod._base('U-1','observation','Café','naïve café\ncontinuation text','x.csv','a'*40,'row 1','https://example.test/x')
        idx = mod.build_index([record])
        rows = mod.search(idx, 'NAÏVE café')
        self.assertEqual(rows[0]['record_id'],'U-1')
        self.assertNotIn('\n', rows[0]['snippet'])

    def test_index_serialization_is_deterministic(self):
        a = json.dumps(self.index, ensure_ascii=False, sort_keys=True, separators=(',',':'))
        b = json.dumps(mod.build_index(list(reversed(self.records))), ensure_ascii=False, sort_keys=True, separators=(',',':'))
        self.assertEqual(a,b)

    def test_missing_provenance_fails_closed(self):
        bad = dict(self.records[0]); bad['upstream_blob_sha']=''
        with self.assertRaisesRegex(mod.SearchError, 'missing upstream_blob_sha'):
            mod.build_index([bad])

if __name__ == '__main__':
    unittest.main()
