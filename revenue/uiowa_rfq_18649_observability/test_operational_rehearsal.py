"""Retained boundary and real-CLI regressions; all source records are fictional."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import observability as engine
import rehearsal

HERE = Path(__file__).resolve().parent
EXPECTED_BASELINE_SHA256 = "bf299589458c11905470fbaee1f643b43f05fb2d13d7de0182e9cfa0d2a934ea"


def packet():
    return json.loads((HERE / "examples.json").read_text(encoding="utf-8"))


def objective(p):
    return p["services"][0]["objectives"][0]


def first(p):
    return engine.assess_packet(p)["findings"][0]


def command(script, *args, optimize=None):
    mode = sys.flags.optimize if optimize is None else optimize
    return [sys.executable] + (["-" + "O" * mode] if mode else []) + [str(HERE / script), *map(str, args)]


class EvidenceBoundaryTests(unittest.TestCase):
    def test_original_three_service_output_is_byte_identical(self):
        data = (json.dumps(engine.assess_packet(packet()), indent=2, sort_keys=True) + "\n").encode()
        self.assertEqual(hashlib.sha256(data).hexdigest(), EXPECTED_BASELINE_SHA256)

    def test_original_fixture_stays_pinned(self):
        self.assertEqual(rehearsal.git_blob((HERE / "examples.json").read_bytes()), rehearsal.EXAMPLES_BLOB)

    def test_explicit_true_and_false_remain_distinct(self):
        for value in (True, False):
            p=packet(); objective(p)["indicator"]["user_visible"]=value
            out=first(p); self.assertIs(out["user_visible"],value)
            self.assertEqual("indicator_not_user_visible" in out["issues"], value is False)

    def test_absent_and_null_visibility_stay_unknown(self):
        for omit in (True,False):
            p=packet(); flag=objective(p)["indicator"]
            if omit: flag.pop("user_visible")
            else: flag["user_visible"]=None
            out=first(p); self.assertIsNone(out["user_visible"])
            self.assertIn("indicator_user_visibility_unknown",out["issues"])
            self.assertNotIn("indicator_not_user_visible",out["issues"])

    def test_non_boolean_visibility_is_rejected(self):
        for value in ("false","true",0,1,[],{}):
            with self.subTest(value=value):
                p=packet(); objective(p)["indicator"]["user_visible"]=value
                with self.assertRaisesRegex(ValueError,"Boolean or null"):first(p)

    def test_nonfinite_ratio_components_are_rejected(self):
        for key in ("numerator","denominator"):
            for value in (float("nan"),float("inf"),float("-inf")):
                with self.subTest(key=key,value=value):
                    p=packet();objective(p)["measurement_evidence"][key]=value
                    with self.assertRaisesRegex(ValueError,"finite number"):first(p)

    def test_boolean_or_text_ratio_components_are_rejected(self):
        for key in ("numerator","denominator"):
            for value in (True,False,"19940",[],{}):
                p=packet();objective(p)["measurement_evidence"][key]=value
                with self.assertRaises(ValueError):first(p)

    def test_bad_component_is_not_hidden_by_other_missing_component(self):
        for key,other in (("numerator","denominator"),("denominator","numerator")):
            p=packet();e=objective(p)["measurement_evidence"];e[key]=float("nan");e.pop(other)
            with self.assertRaises(ValueError):first(p)

    def test_missing_measurement_is_unknown_not_zero(self):
        for omit in (True,False):
            p=packet()
            if omit:objective(p).pop("measurement_evidence")
            else:objective(p)["measurement_evidence"]=None
            out=first(p);self.assertEqual(out["status"],"UNKNOWN")
            self.assertIn("measurement_evidence_missing",out["issues"])

    def test_empty_measurement_mapping_is_unknown(self):
        p=packet();objective(p)["measurement_evidence"]={}
        self.assertEqual(first(p)["status"],"UNKNOWN")

    def test_measurement_wrong_shape_is_rejected(self):
        for value in ("uncollected",False,[],0):
            p=packet();objective(p)["measurement_evidence"]=value
            with self.assertRaisesRegex(ValueError,"object or null"):first(p)

    def test_finite_invalid_counts_remain_partial_questions(self):
        for n,d,issue in ((0,0,"invalid_denominator"),(1,-1,"invalid_denominator"),(-1,10,"invalid_ratio_counts"),(11,10,"invalid_ratio_counts")):
            p=packet();objective(p)["measurement_evidence"].update(numerator=n,denominator=d)
            out=first(p);self.assertEqual(out["status"],"PARTIAL");self.assertIn(issue,out["issues"])

    def test_finite_fractional_ratios_keep_existing_support(self):
        p=packet();objective(p)["measurement_evidence"].update(numerator=1.5,denominator=2.0)
        self.assertEqual(first(p)["status"],"SUPPORTED")

    def test_missing_components_remain_partial(self):
        for key in ("numerator","denominator"):
            p=packet();objective(p)["measurement_evidence"].pop(key)
            out=first(p);self.assertEqual(out["status"],"PARTIAL");self.assertIn("ratio_components_missing",out["issues"])

    def test_blank_source_definition_and_period_are_missing(self):
        for key,issue in (("source_ref","measurement_source_missing"),("definition_ref","indicator_definition_missing"),("period_start","measurement_period_missing"),("period_end","measurement_period_missing")):
            p=packet();objective(p)["measurement_evidence"][key]="  "
            out=first(p);self.assertEqual(out["status"],"PARTIAL");self.assertIn(issue,out["issues"])

    def test_reference_and_timestamp_types_are_not_coerced(self):
        for key in ("source_ref","definition_ref","period_start","period_end"):
            for value in (True,123,[],{}):
                p=packet();objective(p)["measurement_evidence"][key]=value
                with self.assertRaises(ValueError):first(p)

    def test_reversed_and_equal_periods_are_partial(self):
        for start in ("2026-08-01T00:00:00Z","2026-07-30T23:59:59Z"):
            p=packet();objective(p)["measurement_evidence"]["period_start"]=start
            out=first(p);self.assertEqual(out["status"],"PARTIAL");self.assertIn("measurement_period_invalid",out["issues"])

    def test_periods_compare_instants_not_lexical_text(self):
        p=packet();objective(p)["measurement_evidence"].update(period_start="2026-07-02T00:30:00+02:00",period_end="2026-07-01T23:00:00Z")
        self.assertEqual(first(p)["status"],"SUPPORTED")
        objective(p)["measurement_evidence"]["period_end"]="2026-07-01T22:00:00Z"
        self.assertIn("measurement_period_invalid",first(p)["issues"])

    def test_invalid_calendar_naive_and_offset_timestamps_rejected(self):
        for value in ("2026-02-30T00:00:00Z","2026-07-01","2026-07-01T00:00:00","2026-07-01T00:00:00+00:99","2026-07-01T00:00:00+24:00","2026-7-1T00:00:00Z"):
            p=packet();objective(p)["measurement_evidence"]["period_start"]=value
            with self.assertRaises(ValueError):first(p)

    def test_historical_and_fractional_time_are_not_currentness_claims(self):
        p=packet();objective(p)["measurement_evidence"].update(period_start="2020-01-01T00:00:00.001Z",period_end="2020-01-01T00:00:00.002Z")
        self.assertEqual(first(p)["status"],"SUPPORTED")

    def test_duplicate_service_ids_are_rejected_after_normalization(self):
        p=packet();other=deepcopy(p["services"][0]);other["service_id"]=" SYN-REG ";p["services"].append(other)
        with self.assertRaisesRegex(ValueError,"duplicate service_id"):engine.assess_packet(p)

    def test_duplicate_objective_ids_are_rejected_within_service(self):
        p=packet();other=deepcopy(objective(p));other["objective_id"]=" REG-01 ";p["services"][0]["objectives"].append(other)
        with self.assertRaisesRegex(ValueError,"duplicate objective_id"):engine.assess_packet(p)

    def test_same_objective_id_in_different_services_is_not_duplicate(self):
        p=packet();p["services"][1]["objectives"][0]["objective_id"]="REG-01"
        self.assertEqual(engine.assess_packet(p)["finding_count"],3)

    def test_invalid_packet_service_objective_shapes_raise_domain_errors(self):
        for p in (None,[],False,{"services":[False]},{"services":[{"service_id":"S","service_name":"Synthetic","objectives":[None]}]}):
            with self.assertRaises(ValueError):engine.assess_packet(p)

    def test_schema_and_synthetic_fields_are_checked_when_present(self):
        p=packet();p["schema"]="other-schema"
        with self.assertRaises(ValueError):engine.assess_packet(p)
        for value in ("false",None,0):
            p=packet();p["synthetic"]=value
            with self.assertRaises(ValueError):engine.assess_packet(p)
        p=packet();p.pop("schema");p.pop("synthetic")
        self.assertEqual(engine.assess_packet(p)["finding_count"],3)

    def test_target_nonfinite_bool_and_contradictory_units_are_rejected(self):
        targets=[False,"99%",{"operator":">=","value":True},{"operator":">=","value":float("nan")},{"operator":">=","value":1.1},{"operator":">=","value":0.99,"value_ms":5},{"operator":"sometimes","value":0.99}]
        for target in targets:
            p=packet();objective(p)["target"]=target
            with self.assertRaises(ValueError):first(p)

    def test_incomplete_target_is_an_independent_question_not_measurement_failure(self):
        for target in ({},{"operator":">="},{"value":0.99}):
            p=packet();objective(p)["target"]=target
            out=first(p);self.assertEqual(out["status"],"SUPPORTED");self.assertIn("target_incomplete",out["issues"])

    def test_count_and_duration_targets_remain_supported(self):
        for kind,target in (("count",{"operator":"<=","value":3}),("duration",{"operator":"<=","value_seconds":5.5})):
            p=packet();o=objective(p);o["indicator"]["kind"]=kind;o["target"]=target
            self.assertEqual(first(p)["status"],"SUPPORTED")

    def test_latency_percentile_bounds_are_validated(self):
        for value in (True,0,101,float("inf")):
            p=packet();p["services"][2]["objectives"][0]["target"]["percentile"]=value
            with self.assertRaises(ValueError):engine.assess_packet(p)

    def test_dependency_and_decision_wrong_shapes_are_domain_errors(self):
        for key,value in (("dependencies",[{"name":"x","visibility":[]}]),("dependencies",[{"name":True,"visibility":"visible"}]),("decision_evidence",[{"decision_ref":True,"outcome":"x"}])):
            p=packet();objective(p)[key]=value
            with self.assertRaises(ValueError):first(p)

    def test_whitespace_decision_is_not_evidence_of_use(self):
        p=packet();objective(p)["decision_evidence"]=[{"decision_ref":"  ","outcome":"  "}]
        self.assertIn("decision_evidence_incomplete",first(p)["issues"])

    def test_input_records_are_not_mutated(self):
        p=packet();before=deepcopy(p);engine.assess_packet(p);self.assertEqual(p,before)


class ObservabilityCliTests(unittest.TestCase):
    def invoke(self,source,args=(),optimize=None):
        return subprocess.run(command("observability.py",source,*args,optimize=optimize),capture_output=True,text=True,timeout=15)

    def test_real_cli_normal_optimized_and_api_agree(self):
        expected=engine.assess_packet(packet())
        for mode in (0,1,2):
            cp=self.invoke(HERE/"examples.json",optimize=mode)
            self.assertEqual(cp.returncode,0,cp.stderr);self.assertEqual(cp.stderr,"");self.assertEqual(json.loads(cp.stdout),expected)

    def test_new_output_is_created_and_read_back(self):
        with tempfile.TemporaryDirectory() as td:
            target=Path(td)/"new.json";cp=self.invoke(HERE/"examples.json",("--out",target))
            self.assertEqual(cp.returncode,0,cp.stderr);self.assertEqual(cp.stdout,"")
            self.assertEqual(json.loads(target.read_text()),engine.assess_packet(packet()))

    def test_existing_report_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as td:
            target=Path(td)/"prior.json";target.write_bytes(b"prior retained evidence")
            cp=self.invoke(HERE/"examples.json",("--out",target))
            self.assertEqual(cp.returncode,2);self.assertEqual(target.read_bytes(),b"prior retained evidence");self.assertNotIn("Traceback",cp.stderr)

    def test_input_path_cannot_be_output_path(self):
        with tempfile.TemporaryDirectory() as td:
            source=Path(td)/"source.json";source.write_bytes((HERE/"examples.json").read_bytes());before=source.read_bytes()
            cp=self.invoke(source,("--out",source))
            self.assertEqual(cp.returncode,2);self.assertEqual(source.read_bytes(),before)

    def test_input_hardlink_alias_is_preserved(self):
        with tempfile.TemporaryDirectory() as td:
            source=Path(td)/"source.json";source.write_bytes((HERE/"examples.json").read_bytes());alias=Path(td)/"alias.json";os.link(source,alias)
            cp=self.invoke(source,("--out",alias));self.assertEqual(cp.returncode,2);self.assertEqual(alias.read_bytes(),(HERE/"examples.json").read_bytes())

    def test_existing_output_symlink_is_not_followed(self):
        with tempfile.TemporaryDirectory() as td:
            target=Path(td)/"foreign.txt";target.write_bytes(b"foreign");alias=Path(td)/"alias.json";alias.symlink_to(target)
            cp=self.invoke(HERE/"examples.json",("--out",alias));self.assertEqual(cp.returncode,2);self.assertTrue(alias.is_symlink());self.assertEqual(target.read_bytes(),b"foreign")

    def test_malformed_json_does_not_create_output(self):
        with tempfile.TemporaryDirectory() as td:
            source=Path(td)/"source.json";source.write_text('{"services":');target=Path(td)/"new.json"
            cp=self.invoke(source,("--out",target));self.assertEqual(cp.returncode,2);self.assertFalse(target.exists());self.assertNotIn("Traceback",cp.stderr)

    def test_duplicate_keys_and_nonfinite_json_are_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            source=Path(td)/"source.json"
            for text in ('{"services":[],"services":[]}',json.dumps(packet()).replace('19940','NaN'),json.dumps(packet()).replace('19940','Infinity')):
                source.write_text(text);cp=self.invoke(source);self.assertEqual(cp.returncode,2);self.assertEqual(cp.stdout,"");self.assertNotIn("Traceback",cp.stderr)

    def test_invalid_utf8_and_missing_file_have_no_traceback(self):
        with tempfile.TemporaryDirectory() as td:
            source=Path(td)/"source.json";source.write_bytes(b"\xff")
            for path in (source,Path(td)/"missing.json"):
                cp=self.invoke(path);self.assertEqual(cp.returncode,2);self.assertNotIn("Traceback",cp.stderr)

    def test_missing_output_parent_is_not_created(self):
        with tempfile.TemporaryDirectory() as td:
            target=Path(td)/"absent"/"output.json";cp=self.invoke(HERE/"examples.json",("--out",target))
            self.assertEqual(cp.returncode,2);self.assertFalse(target.parent.exists())


class RehearsalTests(unittest.TestCase):
    def test_nine_cases_include_seven_assessments_and_two_rejections(self):
        report=rehearsal.build_rehearsal();self.assertIs(report["synthetic"],True)
        self.assertEqual(report["case_count"],9);self.assertEqual(len({r["id"] for r in report["cases"]}),9)
        self.assertEqual(sum(r["outcome"]=="ASSESSED" for r in report["cases"]),7)
        self.assertEqual(sum(r["outcome"]=="REJECTED" for r in report["cases"]),2)

    def test_every_assessment_is_real_engine_output(self):
        for row in rehearsal.build_rehearsal()["cases"]:
            if row["outcome"]=="ASSESSED":self.assertEqual(row["assessment"],engine.assess_packet(row["input"]))
            else:
                with self.assertRaises(ValueError):engine.assess_packet(row["input"])

    def test_every_case_runs_through_real_cli(self):
        with tempfile.TemporaryDirectory() as td:
            for row in rehearsal.build_rehearsal()["cases"]:
                source=Path(td)/(row["id"]+".json");source.write_text(json.dumps(row["input"]))
                cp=subprocess.run(command("observability.py",source),capture_output=True,text=True,timeout=15)
                if row["outcome"]=="ASSESSED":
                    self.assertEqual(cp.returncode,0,cp.stderr);self.assertEqual(json.loads(cp.stdout),row["assessment"])
                else:self.assertEqual(cp.returncode,2);self.assertIn(row["expected_error"],cp.stderr)

    def test_target_miss_does_not_change_measurement_support(self):
        row=next(r for r in rehearsal.build_rehearsal()["cases"] if r["id"]=="registration_target_missed")
        e=objective(row["input"])["measurement_evidence"]
        self.assertEqual(e["numerator"]*100,99*e["denominator"])
        self.assertLess(e["numerator"]/e["denominator"],objective(row["input"])["target"]["value"])
        self.assertEqual(row["assessment"]["findings"][0]["status"],"SUPPORTED")

    def test_markdown_keeps_unknown_and_percentile_limits(self):
        text=rehearsal.render_markdown(rehearsal.build_rehearsal())
        for needle in ("UNKNOWN","not target attainment","No latency samples","0 / 0","99.0%","ZZ-Sol"):
            self.assertIn(needle,text)

    def test_report_is_repeatable_and_detached(self):
        a=rehearsal.build_rehearsal();expected=deepcopy(a);a["cases"][0]["input"]["services"].clear()
        self.assertEqual(rehearsal.build_rehearsal(),expected)

    def test_false_expected_result_cannot_pass_rehearsal(self):
        real=engine.assess_packet
        def wrong(p):
            result=real(p);result["findings"][0]["status"]="UNKNOWN";return result
        with patch.object(engine,"assess_packet",wrong):
            with self.assertRaisesRegex(ValueError,"expected assessment behavior changed"):rehearsal.build_rehearsal()

    def test_rehearsal_cli_module_script_and_optimized_outputs_match(self):
        root=HERE.parents[1]
        commands=[command("rehearsal.py","--format","json",optimize=mode) for mode in (0,1,2)]
        commands.append([sys.executable,"-m","revenue.uiowa_rfq_18649_observability.rehearsal","--format","json"])
        outputs=[]
        for cmd in commands:
            cp=subprocess.run(cmd,cwd=root,capture_output=True,timeout=20);self.assertEqual(cp.returncode,0,cp.stderr);outputs.append(cp.stdout)
        self.assertEqual(len(set(outputs)),1)

    def test_invalid_rehearsal_argument_is_rejected(self):
        cp=subprocess.run(command("rehearsal.py","--format","send"),capture_output=True,text=True,timeout=10)
        self.assertEqual(cp.returncode,2);self.assertEqual(cp.stdout,"")

    def test_source_identities_match_actual_files(self):
        report=rehearsal.build_rehearsal()
        for name,sha in report["source_git_blobs"].items():self.assertEqual(sha,rehearsal.git_blob((HERE/name).read_bytes()))


if __name__ == "__main__":
    unittest.main()
