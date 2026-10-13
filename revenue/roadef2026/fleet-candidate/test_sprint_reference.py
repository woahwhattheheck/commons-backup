"""Real reference ingestion and existing-comparator parity; no solver runs.

Supply --reference /path/to/sprint_results/loads_vector.csv. Candidate checker
files below are explicitly manufactured comparison fixtures, not team results.
"""
import argparse
import ast
import contextlib
import csv
from decimal import Decimal
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest

import compare_checker as C

REFERENCE = None
ORIGINAL = None


def fixture(vector, *, cost=0, valid=True):
    return {"valid": valid, "total_cost": cost,
            "saturations": [{"t": i, "from": "fixture-source", "to": "fixture-target", "sat": str(v)}
                            for i, v in enumerate(vector)]}


class SprintTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reference = C.load_sprint_reference(REFERENCE)
        cls.v = cls.reference["records"]["setA-01"]["vector"]

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.checker = self.root / "checker-6.json"

    def write(self, values=None, **kwargs):
        self.checker.write_text(json.dumps(fixture(self.v if values is None else values, **kwargs)))
        return C.load_result(self.checker)

    def cli(self, left, *args):
        return subprocess.run([sys.executable, "-B", str(Path(C.__file__).resolve()), str(left),
                               str(REFERENCE), "--sprint", *args],
                              capture_output=True, text=True, timeout=15)

    def parse(self, text):
        return C.parse_sprint_csv(text.encode())

    def test_exact_real_bytes_and_all_twenty_instances(self):
        raw = REFERENCE.read_bytes()
        self.assertEqual(len(raw), 315412)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), C.SPRINT_SHA256)
        self.assertEqual(set(self.reference["records"]), {f"setA-{n:02}" for n in range(1,21)})
        self.assertEqual(sum(len(v["vector"]) for v in self.reference["records"].values()),35944)

    def test_real_variable_width_rows_and_zero_tails_are_not_padded(self):
        counts = [160,300,500,500,792,1000,1000,1308,1500,1932,2000,1796,2000,2216,2500,2904,2540,3000,3996,4000]
        self.assertEqual([len(v["vector"]) for v in self.reference["records"].values()], counts)
        self.assertTrue(all(v["vector"][-1] == 0 for v in self.reference["records"].values()))

    def test_all_published_vectors_survive_checker_loading_and_compare_exactly(self):
        for name, target in self.reference["records"].items():
            with self.subTest(instance=name):
                candidate=self.write(target["vector"],cost=998877)
                r=C.compare_sprint(candidate,self.reference,name)
                self.assertEqual(r["winner"],"tie")
                self.assertEqual(r["load_count"],len(target["vector"]))
                self.assertFalse(r["cost_used_in_ranking"])
                self.assertFalse(r["input_file_identity_verified"])
                self.assertFalse(r["reference_link_time_coordinates_available"])

    def test_real_decimal_values_are_not_binary_float_rounding(self):
        self.assertEqual(self.v[0],Decimal("0.929383"))
        self.assertEqual(self.v[1],Decimal("0.551952"))
        self.assertEqual(C.compare_sprint(self.write(),self.reference,"setA-01")["candidate_mlu"],"0.929383")

    def test_deep_rank_changes_decide_both_directions(self):
        for delta, winner in ((Decimal("-0.000001"),"candidate"),(Decimal("0.000001"),"reference")):
            values=list(self.v); values[1]+=delta
            r=C.compare_sprint(self.write(values),self.reference,"setA-01")
            self.assertEqual(r["winner"],winner);self.assertEqual(r["first_changed_rank"],2)
            self.assertEqual(r["candidate_mlu"],r["reference_mlu"])

    def test_cost_is_diagnostic_even_on_exact_tie(self):
        r=C.compare_sprint(self.write(cost=123456),self.reference,"setA-01")
        self.assertEqual(r["winner"],"tie");self.assertIsNone(r["first_changed_rank"])
        self.assertEqual(r["candidate_total_cost_diagnostic"],123456)

    def test_invalid_candidate_not_invented_vector(self):
        r=C.compare_sprint(self.write([],valid=False),self.reference,"setA-01")
        self.assertEqual(r["comparison_status"],"candidate_invalid")
        self.assertEqual(r["winner"],"reference");self.assertNotIn("candidate_mlu",r)

    def test_wrong_length_never_compared_as_prefix(self):
        for v in (self.v[:-1],self.v+[Decimal(0)]):
            with self.assertRaisesRegex(ValueError,"unequal-length"):
                C.compare_sprint(self.write(v),self.reference,"setA-01")

    def test_unknown_instance_not_matched_by_length(self):
        for label in ("setB-01","setA-1","setA-21","", "setA-01 "):
            with self.assertRaisesRegex(ValueError,"No published sprint vector"):
                C.compare_sprint(self.write(),self.reference,label)

    def test_equal_length_instances_stay_distinct_with_caller_binding_caveat(self):
        a=self.reference["records"]["setA-03"]["vector"]
        candidate=self.write(a)
        self.assertEqual(C.compare_sprint(candidate,self.reference,"setA-03")["winner"],"tie")
        other=C.compare_sprint(candidate,self.reference,"setA-04")
        self.assertEqual(other["first_changed_rank"],1)
        self.assertEqual(other["reference_best_team"],"J27")
        self.assertFalse(other["input_file_identity_verified"])

    def test_hash_binding_refuses_mutated_reference(self):
        changed=self.root/'changed.csv';changed.write_bytes(REFERENCE.read_bytes()+b'\n')
        with self.assertRaisesRegex(ValueError,"SHA-256"):
            C.load_sprint_reference(changed)

    def test_format_parser_retains_variable_width_not_dictreader_padding(self):
        r=self.parse('Instance,Best team,1,2,3\na,S1,1,0.5\nb,S2,2,1,0\n')
        self.assertEqual(r['a']['vector'],[Decimal(1),Decimal('.5')])
        self.assertEqual(len(r['b']['vector']),3)

    def test_format_parser_rejects_invalid_headers(self):
        for text in ('', 'Instance,Best team\n','Name,Team,1\na,S1,1\n',
                     'Instance,Best team,1,3\na,S1,1,0\n','Instance,Best team,0\na,S1,1\n'):
            with self.subTest(text=text),self.assertRaises(ValueError):self.parse(text)

    def test_format_parser_rejects_duplicate_or_missing_labels(self):
        for body in ('a,S1,1\na,S2,1\n',',S1,1\n','a,,1\n',' a,S1,1\n','a, S1,1\n'):
            with self.subTest(body=body),self.assertRaises(ValueError):
                self.parse('Instance,Best team,1\n'+body)

    def test_format_parser_rejects_bad_numbers_and_missing_cells(self):
        for token in ('NaN','sNaN','Infinity','-Infinity','-0.1','0.0000001','bad',''):
            with self.subTest(token=token),self.assertRaises(ValueError):
                self.parse('Instance,Best team,1\na,S1,'+token+'\n')

    def test_format_parser_does_not_reorder_unsorted_reference(self):
        with self.assertRaisesRegex(ValueError,'descending'):
            self.parse('Instance,Best team,1,2\na,S1,1,2\n')

    def test_format_parser_rejects_empty_or_excess_rows(self):
        for body in ('','a,S1\n','a,S1,1,0\n','\n'):
            with self.subTest(body=body),self.assertRaises(ValueError):
                self.parse('Instance,Best team,1\n'+body)

    def test_candidate_loader_precision_and_duplicates_preserved(self):
        with self.assertRaisesRegex(ValueError,'>6 decimal'):
            self.write([Decimal('0.0000001')]*160)
        data=fixture(self.v);data['saturations'][1]=data['saturations'][0]
        self.checker.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError,'duplicate'):C.load_result(self.checker)

    def test_direct_cli_records_paths_hashes_rank_and_limits(self):
        self.write();out=self.root/'output'/'comparison.json'
        p=self.cli(self.checker,'--instance','setA-01','--output',str(out))
        self.assertEqual(p.returncode,0,p.stderr)
        doc=json.loads(out.read_text());self.assertEqual(doc,json.loads(p.stdout))
        self.assertEqual(doc['counts'],dict(candidate=0,reference=0,tie=1))
        self.assertEqual(len(doc['reference_instances_not_compared']),19)
        self.assertEqual(doc['reference']['sha256'],C.SPRINT_SHA256)
        self.assertIn('unknown',doc['competition_rank'])
        self.assertFalse(doc['resource_budgets_matched'])
        self.assertEqual(doc['instances'][0]['candidate_checker_sha256'],hashlib.sha256(self.checker.read_bytes()).hexdigest())

    def test_direct_cli_demands_explicit_instance(self):
        self.write();p=self.cli(self.checker)
        self.assertNotEqual(p.returncode,0);self.assertIn('requires --instance',p.stderr)

    def test_root_cli_compares_named_subset_and_preserves_uncompared_instances(self):
        for name in ('setA-02','setA-04'):
            p=self.root/name/'checker-6.json';p.parent.mkdir()
            p.write_text(json.dumps(fixture(self.reference['records'][name]['vector'])))
        process=self.cli(self.root);self.assertEqual(process.returncode,0,process.stderr)
        report=json.loads(process.stdout)
        self.assertEqual([r['instance'] for r in report['instances']],['setA-02','setA-04'])
        self.assertEqual(len(report['reference_instances_not_compared']),18)

    def test_root_cli_refuses_unknown_cases_instead_of_silently_dropping(self):
        p=self.root/'setB-01'/'checker-6.json';p.parent.mkdir();p.write_text(json.dumps(fixture(self.v)))
        process=self.cli(self.root)
        self.assertNotEqual(process.returncode,0);self.assertIn('absent from pinned',process.stderr)

    def test_root_cli_empty_or_ambiguous_instance_rejected(self):
        for args in ((),('--instance','setA-01')):
            process=self.cli(self.root,*args);self.assertNotEqual(process.returncode,0)

    def test_legacy_checker_cli_unchanged(self):
        self.write(); other=self.root/'right.json';other.write_text(self.checker.read_text())
        p=subprocess.run([sys.executable,'-B',C.__file__,str(self.checker),str(other)],capture_output=True,text=True,timeout=10)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(json.loads(p.stdout)['counts'],dict(left=0,right=0,tie=1,no_feasible_solution=0))

    def test_old_loader_ast_and_main_nonreference_behavior(self):
        old=ast.parse(ORIGINAL.read_text());new=ast.parse(Path(C.__file__).read_text())
        def f(tree,name):return ast.dump(next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name))
        self.assertEqual(f(old,'load_result'),f(new,'load_result'))
        self.write();other=self.root/'right.json';other.write_text(self.checker.read_text())
        cmd=[str(self.checker),str(other)]
        a=subprocess.run([sys.executable,'-B',str(ORIGINAL),*cmd],capture_output=True,text=True,timeout=10)
        b=subprocess.run([sys.executable,'-B',C.__file__,*cmd],capture_output=True,text=True,timeout=10)
        self.assertEqual(a.stdout,b.stdout);self.assertEqual(a.returncode,b.returncode)

    def test_original_full_vector_ranking_500_pairs(self):
        spec=importlib.util.spec_from_file_location('original_comparator',ORIGINAL)
        old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
        rng=random.Random(20260908)
        for i in range(500):
            n=rng.randint(1,150)
            a=sorted([Decimal(rng.randrange(300))/1000000 for _ in range(n)],reverse=True)
            b=a if i%5==0 else sorted([Decimal(rng.randrange(300))/1000000 for _ in range(n)],reverse=True)
            left=dict(valid=i%29!=0,vector=a,keys=set(range(n)),total_cost=i)
            right=dict(valid=i%31!=0,vector=b,keys=set(range(n)),total_cost=999-i)
            self.assertEqual(C.compare(left,right),old.compare(left,right))

    def test_reference_metadata_is_not_invented_coordinate_mapping(self):
        r=C.compare_sprint(self.write(),self.reference,'setA-01')
        self.assertNotIn('reference_keys',r)
        self.assertIn('caller-declared',r['instance_binding'])
        self.assertEqual(r['reference_csv_line'],2)

    def test_published_tail_is_included_not_mlu_only(self):
        values=list(self.v);values[-1]=Decimal('0.000001')
        r=C.compare_sprint(self.write(values),self.reference,'setA-01')
        self.assertEqual(r['winner'],'reference');self.assertGreater(r['first_changed_rank'],2)


if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('--reference',type=Path,required=True)
    ap.add_argument('--original',type=Path,required=True)
    args,remaining=ap.parse_known_args()
    REFERENCE=args.reference.resolve();ORIGINAL=args.original.resolve()
    unittest.main(argv=[sys.argv[0],*remaining])
