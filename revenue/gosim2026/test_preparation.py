"""Local contract tests do not claim a contest score or model performance."""
import importlib.util
import io
import json
import pathlib
import unittest
import zipfile

ROOT = pathlib.Path(__file__).parent


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


adapter = load("adapter")
build = load("build")


class AdapterTests(unittest.TestCase):
    def test_platform_cli(self):
        original = ["/requirements", "--output-dir", "/workspace", "--type", "web"]
        self.assertEqual(adapter.translate_args(original), ["compile", *original])
        self.assertEqual(original[0], "/requirements")

    def test_native_cli_and_introspection(self):
        for args in ([], ["--help"], ["--version"], ["compile", "r", "-o", "o"]):
            self.assertEqual(adapter.translate_args(args), args)

    def test_gateway_values_and_visual_route_preserved(self):
        config = {"OPENAI_API_KEY": "unit-test-not-a-key", "OPENAI_BASE_URL": "https://gateway.invalid/v1",
                  "MODEL": "organizer-model", "VISUAL_BASE_URL": "https://wrong.invalid",
                  "VISUAL_MODEL": "wrong", "OTHER": "retained", "OPENAI_API_BASE": "https://wrong.invalid"}
        result = adapter.model_environment(config)
        self.assertEqual(result["OPENAI_BASE_URL"], config["OPENAI_BASE_URL"])
        self.assertEqual(result["VISUAL_BASE_URL"], config["OPENAI_BASE_URL"])
        self.assertEqual(result["VISUAL_MODEL"], config["MODEL"])
        self.assertEqual(result["OTHER"], "retained")
        self.assertEqual(result["OPENAI_API_BASE"], config["OPENAI_BASE_URL"])
        self.assertEqual(result["ARC_OPENAI_API_MODE"], "chat_completions")
        self.assertEqual(config["VISUAL_MODEL"], "wrong")

    def test_missing_gateway_has_no_provider_default_or_secret_output(self):
        with self.assertRaisesRegex(ValueError, "OPENAI_BASE_URL, MODEL") as error:
            adapter.model_environment({"OPENAI_API_KEY": "private-test-value"})
        self.assertNotIn("private-test-value", str(error.exception))

    def test_explicit_supported_api_mode_is_kept(self):
        result = adapter.model_environment({"OPENAI_API_KEY": "test", "OPENAI_BASE_URL": "https://example.invalid/v1",
                                            "MODEL": "test", "ARC_OPENAI_API_MODE": "responses"})
        self.assertEqual(result["ARC_OPENAI_API_MODE"], "responses")


class BuildTests(unittest.TestCase):
    def inputs(self):
        return {"src/main.py": b"print('source compiler')", "src/requirements.txt": b"openai\n",
                "src/arcbench_agent_runtime/__init__.py": b"", "src/core/workflow.py": b"",
                "LICENSE": b"test-license"}, {"catalog.yaml": b"templates: []"}

    def test_bundle_is_flat_complete_and_traceable(self):
        arc, template = self.inputs()
        entries = build.assemble(arc, template, b"print('adapter')")
        self.assertEqual(entries["main.py"], b"print('adapter')")
        self.assertEqual(entries["arc_cli.py"], arc["src/main.py"])
        self.assertEqual(entries["LICENSE-ARC"], b"test-license")
        manifest = json.loads(entries["BUILD-MANIFEST.json"])
        self.assertEqual(manifest["model_calls_during_build"], 0)
        self.assertIn("arc-template/catalog.yaml", manifest["files"])

    def test_tested_dependency_lock_is_used_in_upload(self):
        entries = build.assemble(*self.inputs(), b"", b"openai==3.8.0\n")
        self.assertEqual(entries["requirements.txt"], b"openai==3.8.0\n")
        self.assertEqual(entries["requirements.upstream.txt"], b"openai\n")

    def test_repeated_packaging_is_byte_identical(self):
        entries = build.assemble(*self.inputs(), b"print('adapter')")
        self.assertEqual(build.zip_bytes(entries), build.zip_bytes(dict(reversed(list(entries.items())))))
        with zipfile.ZipFile(io.BytesIO(build.zip_bytes(entries))) as zipped:
            self.assertIn("main.py", zipped.namelist())
            self.assertFalse(any(name.startswith("/") for name in zipped.namelist()))

    def test_missing_runtime_is_error_not_ready_claim(self):
        arc, template = self.inputs()
        del arc["src/core/workflow.py"]
        with self.assertRaisesRegex(ValueError, "Incomplete runnable"):
            build.assemble(arc, template, b"")

    def test_prohibited_dependency_is_not_packaged(self):
        arc, template = self.inputs()
        arc["src/requirements.txt"] = b"llama-cpp-python\n"
        with self.assertRaisesRegex(ValueError, "Prohibited"):
            build.assemble(arc, template, b"")

    def test_syntax_error_is_not_packaged(self):
        arc, template = self.inputs()
        arc["src/core/workflow.py"] = b"def broken("
        with self.assertRaises(SyntaxError):
            build.assemble(arc, template, b"")


if __name__ == "__main__":
    unittest.main()
