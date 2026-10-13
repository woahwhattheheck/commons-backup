# SPDX-License-Identifier: Apache-2.0
"""Focused contracts for V5 candidate experiment identity."""

import json
from pathlib import Path
import tempfile

from v5_candidate_identity import IdentityError, build_manifest, main, validate_manifest


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def expect_error(fn, contains):
    try:
        fn()
    except IdentityError as exc:
        check(contains in str(exc), (contains, str(exc)))
    else:
        raise AssertionError(f"expected IdentityError containing {contains!r}")


def expect_cli_error(argv):
    try:
        main(argv)
    except SystemExit as exc:
        check(exc.code == 2, f"expected CLI exit 2, got {exc.code!r}")
    else:
        raise AssertionError("expected CLI identity failure")


def fixture(root):
    root = Path(root)
    (root / "a.py").write_text("A = 1\n", encoding="utf-8")
    (root / "b.py").write_text("B = 2\n", encoding="utf-8")
    return {
        "base_id": "main@abc123",
        "engine_id": "engine@3c202c7e",
        "opponent_pack_id": "top30@v1",
        "config": {"joint": True, "mode": "mild", "budget": 1.0},
        "components": [
            {"name": "joint", "source": "a.py", "activation": {"joint": True}},
            {"name": "mild", "source": "b.py", "activation": {"mode": "mild"}},
        ],
    }


def test_deterministic_and_order_independent():
    with tempfile.TemporaryDirectory() as one, tempfile.TemporaryDirectory() as two:
        first = fixture(one)
        second = fixture(two)
        second["config"] = {"budget": 1.0, "mode": "mild", "joint": True}
        second["components"].reverse()
        left = build_manifest(one, first)
        right = build_manifest(two, second)
        check(left == right, "identity changed with root/config/component order")
        check(left["candidate_id"].startswith("v5c:"), "candidate prefix")
        check(len(left["candidate_id"]) == 68, "candidate digest length")


def test_source_path_aliases_share_canonical_identity():
    with tempfile.TemporaryDirectory() as root_name:
        root = Path(root_name)
        canonical_spec = fixture(root)
        canonical = build_manifest(root, canonical_spec)

        (root / "nested").mkdir()
        parent_alias_spec = fixture(root)
        parent_alias_spec["components"][0]["source"] = "nested/../a.py"
        parent_alias = build_manifest(root, parent_alias_spec)
        check(parent_alias == canonical, "parent-segment alias minted a new identity")

        symlink = root / "a-alias.py"
        symlink.symlink_to("a.py")
        symlink_alias_spec = fixture(root)
        symlink_alias_spec["components"][0]["source"] = "a-alias.py"
        symlink_alias = build_manifest(root, symlink_alias_spec)
        check(symlink_alias == canonical, "in-root symlink alias minted a new identity")

        sources = {item["name"]: item["source"] for item in canonical["components"]}
        check(sources["joint"] == "a.py", "manifest source is not canonical root-relative")


def test_activation_is_type_exact_and_fail_closed():
    with tempfile.TemporaryDirectory() as root:
        spec = fixture(root)
        spec["components"][0]["activation"]["joint"] = 1
        expect_error(lambda: build_manifest(root, spec), "activation mismatch")
        spec = fixture(root)
        spec["config"]["joint"] = 1
        expect_error(lambda: build_manifest(root, spec), "activation mismatch")
        spec = fixture(root)
        spec["components"][0]["activation"] = {"missing": True}
        expect_error(lambda: build_manifest(root, spec), "activation key missing")


def test_reserved_metadata_cannot_certify_activation_and_remains_hashed():
    with tempfile.TemporaryDirectory() as root:
        spec = fixture(root)
        spec["config"]["_ablation"] = "joint-off"
        spec["components"][0]["activation"] = {"_ablation": "joint-off"}
        expect_error(lambda: build_manifest(root, spec), "reserved metadata")

        first = fixture(root)
        second = fixture(root)
        first["config"]["_run_note"] = "one"
        second["config"]["_run_note"] = "two"
        left = build_manifest(root, first)
        right = build_manifest(root, second)
        check(
            left["candidate_id"] != right["candidate_id"],
            "full config metadata stopped contributing to candidate identity",
        )


def test_source_aliases_canonicalize_to_same_identity():
    with tempfile.TemporaryDirectory() as root:
        spec = fixture(root)
        base = build_manifest(root, spec)

        Path(root, "sub").mkdir()
        lexical = fixture(root)
        lexical["components"][0]["source"] = "sub/../a.py"
        lexical_manifest = build_manifest(root, lexical)
        check(lexical_manifest == base, "lexical source alias minted a second identity")
        check(
            lexical_manifest["components"][0]["source"] == "a.py",
            "manifest did not record resolved root-relative source",
        )

        link = Path(root, "a-link.py")
        link.symlink_to("a.py")
        symlinked = fixture(root)
        symlinked["components"][0]["source"] = "a-link.py"
        symlinked_manifest = build_manifest(root, symlinked)
        check(symlinked_manifest == base, "in-root source symlink minted a second identity")


def test_unconditional_requires_explicit_exact_bool():
    with tempfile.TemporaryDirectory() as root:
        spec = fixture(root)
        spec["components"] = [
            {"name": "base", "source": "a.py", "unconditional": True}
        ]
        manifest = build_manifest(root, spec)
        check(
            manifest["components"][0]["activation"]["mode"] == "unconditional",
            "unconditional component not recorded",
        )
        spec["components"][0]["unconditional"] = 1
        expect_error(lambda: build_manifest(root, spec), "exact bool")


def test_source_drift_and_manifest_tamper_are_detected():
    with tempfile.TemporaryDirectory() as root:
        spec = fixture(root)
        manifest = build_manifest(root, spec)
        validate_manifest(root, spec, manifest)
        Path(root, "a.py").write_text("A = 99\n", encoding="utf-8")
        expect_error(lambda: validate_manifest(root, spec, manifest), "does not match")
        fresh = build_manifest(root, spec)
        check(fresh["candidate_id"] != manifest["candidate_id"], "source drift kept identity")
        fresh["candidate_id"] = manifest["candidate_id"]
        expect_error(lambda: validate_manifest(root, spec, fresh), "does not match")


def test_path_escape_missing_file_and_nonfinite_config_rejected():
    with tempfile.TemporaryDirectory() as parent:
        root = Path(parent, "root")
        root.mkdir()
        Path(parent, "outside.py").write_text("X=1\n", encoding="utf-8")
        spec = fixture(root)
        spec["components"][0]["source"] = "../outside.py"
        expect_error(lambda: build_manifest(root, spec), "escapes root")
        spec = fixture(root)
        spec["components"][0]["source"] = "missing.py"
        expect_error(lambda: build_manifest(root, spec), "not a file")
        spec = fixture(root)
        spec["config"]["budget"] = float("nan")
        expect_error(lambda: build_manifest(root, spec), "non-finite")


def test_cli_build_and_validate():
    with tempfile.TemporaryDirectory() as root:
        spec = fixture(root)
        spec_path = Path(root, "spec.json")
        manifest_path = Path(root, "manifest.json")
        spec_path.write_text(json.dumps(spec), encoding="utf-8")
        rc = main(
            ["--root", root, "build", str(spec_path), "--output", str(manifest_path)]
        )
        check(rc == 0, "build CLI failed")
        saved = json.loads(manifest_path.read_text(encoding="utf-8"))
        check(saved == build_manifest(root, spec), "CLI manifest differs from API")
        rc = main(
            ["--root", root, "validate", str(spec_path), str(manifest_path)]
        )
        check(rc == 0, "validate CLI failed")


def test_cli_rejects_duplicate_keys_and_nonstandard_numbers():
    with tempfile.TemporaryDirectory() as root:
        spec = fixture(root)
        spec_path = Path(root, "spec.json")
        canonical = json.dumps(spec)
        cases = {
            "duplicate-top": canonical.replace(
                '"base_id": "main@abc123"',
                '"base_id": "main@old", "base_id": "main@abc123"',
                1,
            ),
            "duplicate-component": canonical.replace(
                '"source": "a.py"',
                '"source": "b.py", "source": "a.py"',
                1,
            ),
            "duplicate-config": canonical.replace(
                '"budget": 1.0', '"budget": 9.0, "budget": 1.0', 1
            ),
            "nan": canonical.replace('"budget": 1.0', '"budget": NaN', 1),
            "infinity": canonical.replace(
                '"budget": 1.0', '"budget": Infinity', 1
            ),
            "negative-infinity": canonical.replace(
                '"budget": 1.0', '"budget": -Infinity', 1
            ),
        }
        for label, text in cases.items():
            spec_path.write_text(text, encoding="utf-8")
            output = Path(root, f"{label}.manifest.json")
            expect_cli_error(
                ["--root", root, "build", str(spec_path), "--output", str(output)]
            )
            check(not output.exists(), f"{label}: invalid JSON published a manifest")

        spec_path.write_text(canonical, encoding="utf-8")
        manifest = build_manifest(root, spec)
        manifest_path = Path(root, "ambiguous-manifest.json")
        manifest_text = json.dumps(manifest)
        candidate = manifest["candidate_id"]
        manifest_text = manifest_text.replace(
            f'"candidate_id": "{candidate}"',
            f'"candidate_id": "v5c:{"0" * 64}", "candidate_id": "{candidate}"',
            1,
        )
        manifest_path.write_text(manifest_text, encoding="utf-8")
        expect_cli_error(
            ["--root", root, "validate", str(spec_path), str(manifest_path)]
        )


def test_cli_output_does_not_reuse_foreign_temp_path():
    with tempfile.TemporaryDirectory() as root:
        spec = fixture(root)
        spec_path = Path(root, "spec.json")
        manifest_path = Path(root, "manifest.json")
        foreign_temp = manifest_path.with_name(manifest_path.name + ".tmp")
        spec_path.write_text(json.dumps(spec), encoding="utf-8")
        foreign_temp.write_text("foreign-writer\n", encoding="utf-8")

        rc = main(
            ["--root", root, "build", str(spec_path), "--output", str(manifest_path)]
        )
        check(rc == 0, "build CLI failed with foreign temp present")
        check(
            foreign_temp.read_text(encoding="utf-8") == "foreign-writer\n",
            "publisher reused or removed another writer's temp path",
        )
        saved = json.loads(manifest_path.read_text(encoding="utf-8"))
        check(saved == build_manifest(root, spec), "collision-safe manifest differs")
        leftovers = list(Path(root).glob(f".{manifest_path.name}.*.tmp"))
        check(not leftovers, f"publisher leaked private temp files: {leftovers}")


def run():
    tests = [
        value
        for name, value in sorted(globals().items())
        if name.startswith("test_") and callable(value)
    ]
    for test in tests:
        test()
    print(f"PASS {len(tests)}/{len(tests)}")


if __name__ == "__main__":
    run()
