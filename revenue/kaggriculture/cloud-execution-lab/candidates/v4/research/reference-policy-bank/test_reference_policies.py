# SPDX-License-Identifier: Apache-2.0
"""Run with BASALT_KG_ROOT and BASALT_ENGINE_DIR set to recovered sources.

No network, simulator clone, policy modification, or production activation.
Only tests needing the real existing evaluator are skipped without those paths.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest

import reference_policies as rp

KG = os.environ.get("BASALT_KG_ROOT")
ENGINE = os.environ.get("BASALT_ENGINE_DIR")


class FilePins(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "a.py").write_text("answer = 42\n")
        self.files = {"a.py": rp.digest(self.root / "a.py")}

    def test_exact_bytes_and_changed_source(self):
        rp.verify_files(self.root, self.files)
        (self.root / "a.py").write_text("answer = 41\n")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            rp.verify_files(self.root, self.files)

    def test_empty_or_missing_closure_rejected(self):
        with self.assertRaises(ValueError):
            rp.verify_files(self.root, {})
        with self.assertRaises(FileNotFoundError):
            rp.verify_files(self.root, {"missing.py": "0" * 64})

    def test_escape_absolute_and_symlink_rejected(self):
        for path in ("../outside.py", "/absolute.py"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                rp.checked_path(self.root, path)
        (self.root / "link.py").symlink_to(self.root / "a.py")
        with self.assertRaisesRegex(ValueError, "Symlink"):
            rp.checked_path(self.root, "link.py")

    def test_timeout_and_rng_validation_precede_files(self):
        for value in (0, -1, float("nan"), float("inf"), True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                rp.ReferencePolicy(self.root, self.root, action_timeout=value)
        with self.assertRaises(TypeError):
            rp.ReferencePolicy(self.root, self.root, rng_seed=True)


@unittest.skipUnless(KG and ENGINE, "set BASALT_KG_ROOT/BASALT_ENGINE_DIR for process/engine checks")
class ExistingActorIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="basalt-tests-")
        cls.root = Path(cls.temp.name)
        cls.kg = cls.root / "kg"
        shutil.copytree(KG, cls.kg)
        cls.engine = Path(ENGINE)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.n = self.id().rsplit(".", 1)[-1]

    def fixture(self, code):
        source = self.kg / "fixture" / self.n
        source.mkdir(parents=True)
        (source / "main.py").write_text(code)
        registry = self.root / (self.n + ".json")
        registry.write_text(json.dumps({"policies": {"probe": {
            "root": source.relative_to(self.kg).as_posix(), "entry": "main.py",
            "kind": "test_only", "files": {"main.py": rp.digest(source / "main.py")}}}}))
        runtime = self.root / (self.n + "-runtime")
        rp.prepare("probe", self.kg, runtime, registry)
        return runtime

    def policy(self, runtime, **kw):
        p = rp.ReferencePolicy(runtime, self.engine, **kw)
        self.addCleanup(p.close)
        return p

    def obs(self, step=0, seat=0):
        return {"step": step, "player": seat, "private": {"probe": []}}

    def test_fresh_process_globals_rng_and_working_directory(self):
        runtime = self.fixture("import random, os\nN = 0\ndef agent(obs, cfg):\n"
            " global N\n N += 1\n return {'farmer':['PASS'], 'probe':[N,random.randrange(10**6),os.getpid(),os.getcwd()]}\n")
        a, b = self.policy(runtime), self.policy(runtime)
        one, two = a(self.obs(), {}), b(self.obs(seat=1), {})
        self.assertEqual(one["probe"][:2], two["probe"][:2])
        self.assertNotEqual(one["probe"][2:], two["probe"][2:])
        self.assertEqual(a(self.obs(1), {})["probe"][0], 2)
        a.close()
        c = self.policy(runtime)
        self.assertEqual(one["probe"][:2], c(self.obs(), {})["probe"][:2])

    def test_official_last_callable_and_one_argument_contract(self):
        runtime = self.fixture("def agent(obs):\n raise RuntimeError('wrong callable')\n"
                               "def actually_last(obs):\n return {'farmer':['PASS'],'probe':'last'}\n")
        self.assertEqual(self.policy(runtime)(self.obs(), {})["probe"], "last")

    def test_private_observation_and_configuration_cannot_mutate_parent(self):
        runtime = self.fixture("def agent(obs,cfg):\n obs.private.probe.append('bad')\n"
                               " cfg['changed']=True\n return {'farmer':['PASS']}\n")
        p = self.policy(runtime)
        obs, cfg = self.obs(), {"turnsPerDay": 12}
        before = copy.deepcopy((obs, cfg))
        p(obs, cfg)
        self.assertEqual((obs, cfg), before)

    def test_seed_seat_and_step_boundary(self):
        p = self.policy(self.fixture("def agent(obs,cfg):\n return {'farmer':['PASS']}\n"))
        with self.assertRaisesRegex(ValueError, "private engine seed"):
            p(self.obs(), {"seed": 11})
        p(self.obs(), {})
        for obs in (self.obs(), self.obs(2), self.obs(1, 1)):
            with self.subTest(obs=obs), self.assertRaises(ValueError):
                p(obs, {})
        p(self.obs(1), {})
        p.close()
        p.close()
        with self.assertRaises(RuntimeError):
            p(self.obs(2), {})

    def test_body_typeerror_is_not_retried_or_converted_to_pass(self):
        p = self.policy(self.fixture("N=0\ndef agent(obs,cfg):\n global N\n N+=1\n"
                                     " raise TypeError('body_failure_calls'+str(N))\n"))
        with self.assertRaises(rp.PolicyFailure) as caught:
            p(self.obs(), {})
        self.assertEqual(caught.exception.response["kind"], "crash")
        self.assertIn("body_failure_calls1", caught.exception.response["error"])
        self.assertTrue(p.closed)
        self.assertIsNotNone(p.actor.proc.poll())

    def test_timeout_terminates_actor_no_pass(self):
        p = self.policy(self.fixture("import time\ndef agent(obs,cfg):\n time.sleep(10)\n"
                                     " return {'farmer':['PASS']}\n"), action_timeout=0.1)
        with self.assertRaises(rp.PolicyFailure) as caught:
            p(self.obs(), {})
        self.assertEqual(caught.exception.response["kind"], "timeout")
        self.assertTrue(p.closed)
        self.assertIsNotNone(p.actor.proc.poll())

    def test_non_json_action_is_failure(self):
        p = self.policy(self.fixture("def agent(obs,cfg):\n return {'farmer':['PASS'],'bad':float('nan')}\n"))
        with self.assertRaises(rp.PolicyFailure) as caught:
            p(self.obs(), {})
        self.assertEqual(caught.exception.response["kind"], "invalid_action")

    def test_preparation_and_runtime_pin_enforcement(self):
        runtime = self.fixture("def agent(obs,cfg):\n return {'farmer':['PASS']}\n")
        with self.assertRaises(FileExistsError):
            rp.prepare("probe", self.kg, runtime, self.root / (self.n + ".json"))
        with (runtime / "policy/main.py").open("a") as handle:
            handle.write("# mutation\n")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            self.policy(runtime)

    def test_support_pin_enforcement(self):
        runtime = self.fixture("def agent(obs,cfg):\n return {'farmer':['PASS']}\n")
        f = self.kg / "cloud-pack/official.py"
        old = f.read_bytes()
        try:
            f.write_bytes(old + b"\n# changed\n")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                self.policy(runtime)
        finally:
            f.write_bytes(old)

    def test_import_is_inside_first_timed_action(self):
        p = self.policy(self.fixture("import time\ntime.sleep(.04)\n"
                                     "def agent(obs,cfg):\n return {'farmer':['PASS']}\n"))
        p(self.obs(), {})
        self.assertGreaterEqual(p.report()["max_call_seconds"], .04)

    def test_network_guard_installed_before_policy_load(self):
        p = self.policy(self.fixture("import socket\ndef agent(obs,cfg):\n"
            " try:\n  socket.socket()\n except PermissionError:\n  return {'farmer':['PASS'],'blocked':True}\n"
            " return {'farmer':['PASS'],'blocked':False}\n"))
        self.assertTrue(p(self.obs(), {})["blocked"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
