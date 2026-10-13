# SPDX-License-Identifier: Apache-2.0
"""Materialize the default-off mirror SELL queue arm from exact production-v3."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from build_delivery import archive_bytes, digest, members

PRODUCTION_V3_SHA = "20f201161b14af7755146b08207593f9fa5df641d2f31e680792ea62c0e24239"
FROZEN_SELECTED_SHA256 = "5ca1bc39efed756de71207f46926744ea69f9d2f300dd7b9c1a8cc4dbefeb9ef"
MAIN_SHA256 = "b98aec64f83ea9a216def7ab1fef320a6498ae37816f506af1f891c934027035"
CONFIG_SHA256 = "ba18563683125fd89d5473ddb8a5c3e9431db1787a3046f618a9e03af2cb44af"
MIRROR_DONOR_GIT_BLOB = "90052d735316461c7b3320a7e968dcddbb2c364e"
MIRROR_DONOR_REL = Path("v4/repairs/gameplay/row-shed-sell-order/mirror_collision_value.py")
FEATURE = "r04_mirror_sell_queue"
PACKAGE_FLAG = "_r04_mirror_sell_queue"


def git_blob_sha(body: bytes) -> str:
    header = b"blob " + str(len(body)).encode("ascii") + b"\0"
    return hashlib.sha1(header + body).hexdigest()


def patch_main(body: bytes) -> bytes:
    newline = b"\r\n" if b"\r\n" in body else b"\n"
    feature_anchor = newline.join((
        b"    from titan_runtime import TitanAgent, Features, load",
        b"    feature_data = _runtime_feature_data(feature_data)",
    ))
    if body.count(feature_anchor) != 1:
        raise ValueError("expected one main feature-binding seam")
    feature_replacement = newline.join((
        b"    from titan_runtime import TitanAgent, Features, load",
        b"    mirror_sell_queue_enabled = feature_data.get('_r04_mirror_sell_queue', False)",
        b"    if type(mirror_sell_queue_enabled) is not bool:",
        b"        raise TypeError('_r04_mirror_sell_queue must be bool')",
        b"    feature_data = _runtime_feature_data(feature_data)",
    ))
    init_anchor = newline.join((
        b"            super()._initialize()",
        b"            import sys",
    ))
    if body.count(init_anchor) != 1:
        raise ValueError("expected one main consumer-initialize seam")
    init_replacement = newline.join((
        b"            super()._initialize()",
        b"            self.consumer.mirror_sell_queue_enabled = mirror_sell_queue_enabled",
        b"            import sys",
    ))
    return body.replace(feature_anchor, feature_replacement, 1).replace(
        init_anchor, init_replacement, 1)


def patch_frozen_selected(body: bytes) -> bytes:
    newline = b"\r\n" if b"\r\n" in body else b"\n"
    anchor = newline.join((
        b"        self.previous=seller_public_observation(obs)",
        b"        return out",
    ))
    if body.count(anchor) != 1:
        raise ValueError("expected one FrozenSelected final-return seam")
    replacement = newline.join((
        b"        self.previous=seller_public_observation(obs)",
        b"        if getattr(self,'mirror_sell_queue_enabled',False):",
        b"            from mirror_sell_queue import MirrorSellQueue",
        b"            mirror_config=dict(config)",
        b"            mirror_config['r04_mirror_sell_queue']=True",
        b"            out=MirrorSellQueue().transform(",
        b"                obs,mirror_config,out,post_unit_shed=shed,fallback_action=out)",
        b"        return out",
    ))
    return body.replace(anchor, replacement, 1)


def enable_config(body: bytes) -> bytes:
    try:
        data = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("production-v3 TITAN-CONFIG is not canonical UTF-8 JSON") from error
    if not isinstance(data, dict):
        raise ValueError("production-v3 TITAN-CONFIG must be an object")
    if PACKAGE_FLAG in data:
        raise ValueError("production-v3 already declares mirror SELL package flag")
    data[PACKAGE_FLAG] = True
    return (json.dumps(data, indent=2) + "\n").encode("utf-8")


def compose(
    production: dict[str, bytes], transformer: bytes, donor: bytes, *, enabled: bool = False
) -> dict[str, bytes]:
    if type(enabled) is not bool:
        raise TypeError("enabled must be bool")
    files = dict(production)
    frozen = files.get("frozen_selected.py")
    main = files.get("main.py")
    config = files.get("TITAN-CONFIG.json")
    if frozen is None or digest(frozen) != FROZEN_SELECTED_SHA256:
        raise ValueError("production-v3 FrozenSelected authority drift")
    if main is None or digest(main) != MAIN_SHA256:
        raise ValueError("production-v3 main authority drift")
    if config is None or digest(config) != CONFIG_SHA256:
        raise ValueError("production-v3 TITAN-CONFIG authority drift")
    if git_blob_sha(donor) != MIRROR_DONOR_GIT_BLOB:
        raise ValueError("mirror assignment donor Git blob drift")
    for name in ("mirror_sell_queue.py", "mirror_collision_value.py"):
        if name in files:
            raise ValueError("production-v3 already contains mirror SELL experiment member")
    files["mirror_sell_queue.py"] = transformer
    files["mirror_collision_value.py"] = donor
    files["main.py"] = patch_main(main)
    files["frozen_selected.py"] = patch_frozen_selected(frozen)
    if enabled:
        files["TITAN-CONFIG.json"] = enable_config(config)
    return files


def _same_destination(left: Path, right: Path) -> bool:
    return Path(left).resolve(strict=False) == Path(right).resolve(strict=False)


def _unlink_if_owned(path: Path, identity: tuple[int, int] | None) -> None:
    if identity is None:
        return
    try:
        stat = os.lstat(path)
    except FileNotFoundError:
        return
    if (stat.st_dev, stat.st_ino) == identity:
        os.unlink(path)


def _publish_pair(tar_path: Path, packed: bytes, receipt_path: Path, receipt: dict) -> None:
    """Reserve tar+receipt create-exclusively before publishing either payload."""
    tar_path = Path(tar_path)
    receipt_path = Path(receipt_path)
    if _same_destination(tar_path, receipt_path):
        raise ValueError("candidate tar and receipt paths must be different")

    tar_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    tar_fd = receipt_fd = None
    tar_identity = receipt_identity = None
    try:
        tar_fd = os.open(tar_path, flags, 0o666)
        tar_stat = os.fstat(tar_fd)
        tar_identity = (tar_stat.st_dev, tar_stat.st_ino)

        receipt_fd = os.open(receipt_path, flags, 0o666)
        receipt_stat = os.fstat(receipt_fd)
        receipt_identity = (receipt_stat.st_dev, receipt_stat.st_ino)

        with os.fdopen(tar_fd, "wb") as stream:
            tar_fd = None
            stream.write(packed)
            stream.flush()
            os.fsync(stream.fileno())

        with os.fdopen(receipt_fd, "w", encoding="utf-8") as stream:
            receipt_fd = None
            json.dump(receipt, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        if tar_fd is not None:
            os.close(tar_fd)
        if receipt_fd is not None:
            os.close(receipt_fd)
        _unlink_if_owned(tar_path, tar_identity)
        _unlink_if_owned(receipt_path, receipt_identity)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--production-v3", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--tar", type=Path, required=True)
    parser.add_argument(
        "--enable", action="store_true",
        help="emit the matched experimental ON archive; absent means package-default OFF",
    )
    args = parser.parse_args()
    receipt_path = args.out.parent / (args.out.name + "-manifest.json")
    if _same_destination(args.tar, receipt_path):
        parser.error("candidate tar and manifest paths must be different")
    if any(path.exists() for path in (args.out, args.tar, receipt_path)):
        parser.error("use new output directory, archive and manifest paths")

    production = members(args.production_v3, PRODUCTION_V3_SHA)
    here = Path(__file__).resolve().parent
    transformer = (here / "mirror_sell_queue.py").read_bytes()
    donor_path = here.parents[1] / MIRROR_DONOR_REL
    donor = donor_path.read_bytes()
    files = compose(production, transformer, donor, enabled=args.enable)
    packed = archive_bytes(files)

    args.out.mkdir(parents=True)
    for name, body in files.items():
        path = args.out / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)

    receipt = {
        "schema": "titan-v5-mirror-sell-queue-build/v2",
        "parent_archive_sha256": PRODUCTION_V3_SHA,
        "candidate_archive_sha256": digest(packed),
        "feature": FEATURE,
        "feature_default": False,
        "feature_enabled": bool(args.enable),
        "source_authority": {
            "frozen_selected_sha256": FROZEN_SELECTED_SHA256,
            "main_sha256": MAIN_SHA256,
            "config_sha256": CONFIG_SHA256,
            "mirror_assignment_git_blob": MIRROR_DONOR_GIT_BLOB,
        },
        "files": {name: digest(body) for name, body in sorted(files.items())},
        "kaggle_submission_hold": True,
    }
    try:
        _publish_pair(args.tar, packed, receipt_path, receipt)
    except FileExistsError:
        parser.error("use new output directory, archive and manifest paths")

    print(json.dumps({
        "out": str(args.out),
        "members": len(files),
        "candidate_archive_sha256": digest(packed),
        "feature_default": False,
        "feature_enabled": bool(args.enable),
    }))


if __name__ == "__main__":
    main()
