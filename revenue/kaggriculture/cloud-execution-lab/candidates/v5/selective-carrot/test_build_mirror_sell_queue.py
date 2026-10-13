import hashlib
import json
from pathlib import Path
import sys
import tempfile
import types
from unittest import mock

stub = types.ModuleType("build_delivery")
stub.archive_bytes = lambda files: b""
stub.digest = lambda body: hashlib.sha256(body).hexdigest()
stub.members = lambda path, sha: {}
sys.modules.setdefault("build_delivery", stub)

import build_mirror_sell_queue as builder
from build_mirror_sell_queue import enable_config, git_blob_sha, patch_frozen_selected, patch_main


def test_git_blob_sha_matches_git_object_format():
    assert git_blob_sha(b"test content\n") == "d670460b4b4aece5915caf5c68d12f560a9fe3e4"


def test_patch_frozen_one_lf_seam_and_package_gate():
    body = b"x\n        self.previous=seller_public_observation(obs)\n        return out\ny\n"
    out = patch_frozen_selected(body)
    assert out.count(b"mirror_sell_queue_enabled") == 1
    assert b"mirror_config['r04_mirror_sell_queue']=True" in out
    assert b"post_unit_shed=shed" in out
    assert out.startswith(b"x\n") and out.endswith(b"y\n")


def test_patch_frozen_preserves_crlf():
    body = b"x\r\n        self.previous=seller_public_observation(obs)\r\n        return out\r\ny\r\n"
    out = patch_frozen_selected(body)
    assert b"\r\n" in out
    assert out.replace(b"\r\n", b"").find(b"\n") == -1


def test_patch_frozen_rejects_missing_or_duplicate_seam():
    for body in (
        b"x\n",
        b"        self.previous=seller_public_observation(obs)\n        return out\n"
        b"        self.previous=seller_public_observation(obs)\n        return out\n",
    ):
        try:
            patch_frozen_selected(body)
        except ValueError as error:
            assert "one FrozenSelected final-return seam" in str(error)
        else:
            raise AssertionError("expected fail-closed seam rejection")


def _main_fixture(newline="\n"):
    rows = [
        "def _new_instance(root, feature_data):",
        "    from titan_runtime import TitanAgent, Features, load",
        "    feature_data = _runtime_feature_data(feature_data)",
        "    class FinalPressureAgent(TitanAgent):",
        "        def _initialize(self):",
        "            super()._initialize()",
        "            import sys",
    ]
    return (newline.join(rows) + newline).encode()


def test_patch_main_binds_reserved_package_flag_and_consumer():
    out = patch_main(_main_fixture())
    assert out.count(b"_r04_mirror_sell_queue") == 2
    assert b"self.consumer.mirror_sell_queue_enabled = mirror_sell_queue_enabled" in out
    assert b"feature_data = _runtime_feature_data(feature_data)" in out


def test_patch_main_preserves_crlf_and_rejects_missing_seams():
    out = patch_main(_main_fixture("\r\n"))
    assert out.replace(b"\r\n", b"").find(b"\n") == -1
    for body in (
        b"x\n",
        _main_fixture().replace(b"            import sys\n", b""),
    ):
        try:
            patch_main(body)
        except ValueError as error:
            assert "seam" in str(error)
        else:
            raise AssertionError("expected main seam rejection")


def test_enable_config_adds_only_reserved_true_flag():
    original = b'{"consumer":"frozen","seed":true}\n'
    enabled = enable_config(original)
    data = json.loads(enabled)
    assert data == {"consumer": "frozen", "seed": True, "_r04_mirror_sell_queue": True}
    try:
        enable_config(b'{"_r04_mirror_sell_queue":false}\n')
    except ValueError as error:
        assert "already declares" in str(error)
    else:
        raise AssertionError("expected predeclared flag rejection")


def test_compose_off_vs_on_diff_is_config_only_after_shared_code_patch():
    frozen = b"        self.previous=seller_public_observation(obs)\n        return out\n"
    main = _main_fixture()
    config = b'{"consumer":"frozen","seed":true}\n'
    donor = b"research donor\n"
    transformer = b"transformer\n"
    old = (builder.FROZEN_SELECTED_SHA256, builder.MAIN_SHA256,
           builder.CONFIG_SHA256, builder.MIRROR_DONOR_GIT_BLOB)
    builder.FROZEN_SELECTED_SHA256 = hashlib.sha256(frozen).hexdigest()
    builder.MAIN_SHA256 = hashlib.sha256(main).hexdigest()
    builder.CONFIG_SHA256 = hashlib.sha256(config).hexdigest()
    builder.MIRROR_DONOR_GIT_BLOB = git_blob_sha(donor)
    try:
        production = {"frozen_selected.py": frozen, "main.py": main,
                      "TITAN-CONFIG.json": config, "keep.py": b"same\n"}
        off = builder.compose(production, transformer, donor, enabled=False)
        on = builder.compose(production, transformer, donor, enabled=True)
    finally:
        (builder.FROZEN_SELECTED_SHA256, builder.MAIN_SHA256,
         builder.CONFIG_SHA256, builder.MIRROR_DONOR_GIT_BLOB) = old
    assert set(off) == set(on)
    changed = [name for name in off if off[name] != on[name]]
    assert changed == ["TITAN-CONFIG.json"]
    assert off["TITAN-CONFIG.json"] == config
    assert json.loads(on["TITAN-CONFIG.json"])["_r04_mirror_sell_queue"] is True
    assert b"mirror_sell_queue_enabled" in off["main.py"]
    assert b"mirror_sell_queue_enabled" in off["frozen_selected.py"]


def test_pair_publication_rolls_back_tar_if_receipt_is_taken():
    with tempfile.TemporaryDirectory() as temp:
        tar = Path(temp) / "candidate.tar.gz"
        receipt = Path(temp) / "candidate-manifest.json"
        receipt.write_bytes(b"sentinel")
        try:
            builder._publish_pair(tar, b"candidate", receipt, {"schema": "test"})
        except FileExistsError:
            pass
        else:
            raise AssertionError("expected create-exclusive receipt collision")
        assert not tar.exists()
        assert receipt.read_bytes() == b"sentinel"


def test_pair_publication_rolls_back_both_on_receipt_write_failure():
    with tempfile.TemporaryDirectory() as temp:
        tar = Path(temp) / "candidate.tar.gz"
        receipt = Path(temp) / "candidate-manifest.json"
        with mock.patch.object(builder.json, "dump", side_effect=OSError("receipt write failed")):
            try:
                builder._publish_pair(tar, b"candidate", receipt, {"schema": "test"})
            except OSError as error:
                assert "receipt write failed" in str(error)
            else:
                raise AssertionError("expected injected receipt write failure")
        assert not tar.exists()
        assert not receipt.exists()


def test_pair_publication_rejects_alias_before_creation():
    with tempfile.TemporaryDirectory() as temp:
        target = Path(temp) / "candidate"
        try:
            builder._publish_pair(target, b"candidate", target.parent / "." / target.name,
                                  {"schema": "test"})
        except ValueError as error:
            assert "must be different" in str(error)
        else:
            raise AssertionError("expected tar/receipt alias rejection")
        assert not target.exists()


def test_pair_publication_writes_exact_deterministic_bytes():
    with tempfile.TemporaryDirectory() as temp:
        tar = Path(temp) / "candidate.tar.gz"
        receipt = Path(temp) / "candidate-manifest.json"
        payload = b"candidate"
        document = {"schema": "test", "archive_sha256": hashlib.sha256(payload).hexdigest()}
        builder._publish_pair(tar, payload, receipt, document)
        assert tar.read_bytes() == payload
        assert receipt.read_text(encoding="utf-8") == json.dumps(document, indent=2) + "\n"
