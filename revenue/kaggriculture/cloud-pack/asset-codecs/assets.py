"""Build deployable codec bundles and measure total archives and cold restore."""
from __future__ import annotations

import argparse
import gzip
import io
import json
import os
from pathlib import Path
import resource
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time

import asset_codec as ac

HERE = Path(__file__).resolve().parent


def json_write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def worker_limits():
    resource.setrlimit(resource.RLIMIT_AS, (512*1024**2, 512*1024**2))
    resource.setrlimit(resource.RLIMIT_CPU, (30, 30))


def execute(script, arguments, cwd):
    start = time.perf_counter()
    result = subprocess.run([sys.executable, "-B", "-I", str(script), *map(str, arguments)],
        cwd=cwd, env={"PATH": os.defpath, "PYTHONHASHSEED": "0", "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True, text=True, timeout=40, preexec_fn=worker_limits)
    elapsed = time.perf_counter() - start
    if result.returncode:
        raise RuntimeError(f"Child exit {result.returncode}: {result.stderr[-1500:]}")
    value = json.loads(result.stdout)
    value["parent_process_wall_seconds"] = elapsed
    return value


def archive(root, destination, compression):
    """Identical sorted tar headers for ordinary and custom-codec distributions."""
    root, destination = Path(root), Path(destination)
    if compression == "gz":
        raw = destination.open("xb")
        stream = gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0, compresslevel=9)
        tar = tarfile.open(fileobj=stream, mode="w", format=tarfile.PAX_FORMAT)
    else:
        raw = stream = None
        tar = tarfile.open(destination, "x:" + compression, format=tarfile.PAX_FORMAT)
    try:
        for path in sorted(root.rglob("*")):
            if not path.is_file(): continue
            info = tarfile.TarInfo(str(path.relative_to(root)))
            info.size, info.mode, info.mtime = path.stat().st_size, 0o644, 0
            info.uid = info.gid = 0
            with path.open("rb") as inp: tar.addfile(info, inp)
    finally:
        tar.close()
        if stream is not None: stream.close()
        if raw is not None: raw.close()
    return {"bytes": destination.stat().st_size, "sha256": ac.sha_file(destination)}


def extract_created_archive(path, target):
    """Extract our just-created regular-file tar, recording actual startup work."""
    target.mkdir()
    with tarfile.open(path) as tar:
        for entry in tar:
            name = Path(entry.name)
            if not entry.isfile() or name.is_absolute() or ".." in name.parts:
                raise ValueError("Unexpected member in generated archive")
            output = target / name
            output.parent.mkdir(parents=True, exist_ok=True)
            with tar.extractfile(entry) as inp, output.open("xb") as out:
                shutil.copyfileobj(inp, out)


def build(source, license_path, notice, codec, output, max_bytes=ac.DEFAULT_BUDGET):
    source, license_path, output = Path(source).resolve(), Path(license_path).resolve(), Path(output).resolve()
    if source.stat().st_size > max_bytes:
        raise ValueError("Input exceeds byte budget; sample the large file first")
    if license_path.stat().st_size > 1024**2: raise ValueError("License file exceeds 1 MiB")
    output.mkdir(parents=True, exist_ok=False)
    payload = output / "payload"
    payload.mkdir()
    encoding = execute(HERE / "asset_codec.py", ["encode", source, payload / "asset.kac",
        "--codec", codec, "--max-bytes", max_bytes], output)
    shutil.copyfile(HERE / "asset_codec.py", payload / "asset_codec.py")
    shutil.copyfile(license_path, payload / "ASSET-LICENSE.txt")
    (payload / "ASSET-NOTICE.txt").write_text(notice + "\n")
    for name in ("NOTICE.txt", "LICENSE-MIT.txt"):
        shutil.copyfile(HERE / name, payload / name)
    (payload / "NOTICE.txt").write_text((payload / "NOTICE.txt").read_text() +
        "This decoder bundle selects the MIT option for the new integration; its complete grant is included.\n")
    vendor_files = []
    if codec.startswith("muhc-"): vendor_files = ["muhc.py", "evolve.py", "foldpack.py"]
    elif codec.startswith("rdv1"): vendor_files = ["ringdelta.py"]
    if vendor_files:
        (payload / "vendor").mkdir()
        for name in [*vendor_files, "LICENSE"]:
            shutil.copyfile(HERE / "vendor" / name, payload / "vendor" / name)
        provenance = json.loads((HERE / "vendor/manifest.json").read_text())
        provenance["files"] = {k:v for k,v in provenance["files"].items() if k in [*vendor_files, "LICENSE"]}
        json_write(payload / "vendor/manifest.json", provenance)
    (payload / "restore.py").write_text(
        '"""Restore the original asset once before using it; supplied asset license applies."""\n'
        'from pathlib import Path\nimport sys, time, json, resource, importlib.util\n'
        'def restore(destination):\n'
        '    root = Path(__file__).resolve().parent\n'
        '    spec = importlib.util.spec_from_file_location("_kag_local_asset_codec", root / "asset_codec.py")\n'
        '    module = importlib.util.module_from_spec(spec)\n'
        '    spec.loader.exec_module(module)\n'
        f'    return module.decode_file(root / "asset.kac", destination, max_bytes={encoding["source_bytes"]})\n'
        'if __name__ == "__main__":\n'
        '    start = time.perf_counter()\n    result = restore(sys.argv[1])\n'
        '    use = resource.getrusage(resource.RUSAGE_SELF)\n'
        '    result.update(operation_seconds=time.perf_counter()-start,\n'
        '        process_cpu_seconds=use.ru_utime+use.ru_stime,\n'
        '        peak_rss_kib=use.ru_maxrss/(1024 if sys.platform=="darwin" else 1))\n'
        '    print(json.dumps(result))\n')
    members = {str(p.relative_to(payload)): {"bytes":p.stat().st_size, "sha256":ac.sha_file(p)}
               for p in sorted(payload.rglob("*")) if p.is_file()}
    json_write(payload / "ASSET-MANIFEST.json", {"schema_version":1,"codec":codec,
        "source_name":source.name,"source_sha256":encoding["source_sha256"],
        "source_bytes":encoding["source_bytes"],"notice":notice,"members":members})
    packed = archive(payload, output / "asset-bundle.tar.gz", "gz")
    with tempfile.TemporaryDirectory(prefix="kag-asset-cold-") as temporary:
        temporary = Path(temporary)
        start = time.perf_counter()
        extracted = temporary / "extracted"
        extract_created_archive(output / "asset-bundle.tar.gz", extracted)
        extraction_seconds = time.perf_counter() - start
        decoded = execute(extracted / "restore.py", [temporary / "restored.bin"], temporary)
        exact = ac.sha_file(temporary / "restored.bin") == encoding["source_sha256"]
        if not exact: raise ValueError("Extracted bundle did not restore the source")
    receipt = {"schema_version":1,"codec":codec,"encoding":encoding,"decoding":decoded,
        "archive":packed,"exact":exact,"extraction_seconds":extraction_seconds,
        "extract_plus_cold_restore_seconds":extraction_seconds + decoded["parent_process_wall_seconds"],
        "decoder_source_bytes":sum(v["bytes"] for k,v in members.items() if k.endswith(".py")),
        "distribution_non_asset_bytes":sum(v["bytes"] for k,v in members.items() if k!="asset.kac") +
             (payload / "ASSET-MANIFEST.json").stat().st_size,
        "limits":{"frame_bytes":ac.MAX_FRAME,"input_budget_bytes":max_bytes,
                  "child_address_space_bytes":512*1024**2,"child_cpu_seconds":30,"child_wall_seconds":40},
        "environment":{"python":sys.version,"platform":sys.platform,"hosted_runtime":False},
        "asset_license_sha256":ac.sha_file(license_path)}
    json_write(output / "receipt.json", receipt)
    return receipt


def ordinary(source, license_path, notice, output):
    source, license_path, output = Path(source), Path(license_path), Path(output)
    output.mkdir()
    payload = output / "payload"
    payload.mkdir()
    shutil.copyfile(source, payload / "asset.bin")
    shutil.copyfile(license_path, payload / "ASSET-LICENSE.txt")
    (payload / "ASSET-NOTICE.txt").write_text(notice + "\n")
    json_write(payload / "ASSET-MANIFEST.json", {"source_name":source.name,
        "source_bytes":source.stat().st_size,"source_sha256":ac.sha_file(source),
        "license_sha256":ac.sha_file(license_path),"notice":notice})
    rows = {}
    for compression in ("gz", "bz2", "xz"):
        path = output / ("asset.tar." + compression)
        started = time.perf_counter()
        row = archive(payload, path, compression)
        row["encode_seconds"] = time.perf_counter() - started
        with tempfile.TemporaryDirectory() as tmp:
            start = time.perf_counter()
            extract_created_archive(path, Path(tmp)/"extracted")
            row["extract_seconds"] = time.perf_counter()-start
            row["exact"] = ac.sha_file(Path(tmp)/"extracted/asset.bin") == ac.sha_file(source)
        rows[compression] = row
    json_write(output / "receipt.json", rows)
    return rows


def benchmark(inputs, license_path, notice, output, codecs=ac.CODECS, max_bytes=ac.DEFAULT_BUDGET):
    inputs = [Path(p).resolve() for p in inputs]
    if not inputs or sum(p.stat().st_size for p in inputs) > 1024**2:
        raise ValueError("Measurement batch must contain 1..1048576 input bytes total")
    if any(p.stat().st_size > max_bytes for p in inputs): raise ValueError("Input exceeds measurement byte budget")
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    report = {"schema_version":1,"purpose":"bounded asset codec measurement, not model-weight extrapolation",
              "inputs":[],"tool_sha256":ac.sha_file(__file__),"codec_driver_sha256":ac.sha_file(HERE/"asset_codec.py")}
    for index, source in enumerate(inputs):
        folder = output / f"input-{index}"
        folder.mkdir()
        row = {"name":source.name,"bytes":source.stat().st_size,"sha256":ac.sha_file(source),
               "ordinary":ordinary(source, license_path, notice, folder/"ordinary"),"codecs":{}}
        report["inputs"].append(row)
        for codec in codecs:
            try:
                row["codecs"][codec] = build(source, license_path, notice, codec, folder/codec, max_bytes)
            except Exception as exc:
                row["codecs"][codec] = {"status":"failed","error":f"{type(exc).__name__}: {exc}"}
            json_write(output/"report.json", report)
            print(json.dumps({"input":source.name,"codec":codec,"exact":row["codecs"][codec].get("exact",False)}), flush=True)
    return report


def compose(profile, bundle, destination, prefix):
    profile, bundle, destination = Path(profile).resolve(), Path(bundle).resolve(), Path(destination).resolve()
    if not prefix.isidentifier(): raise ValueError("Use a Python identifier for the asset package prefix")
    original = json.loads(profile.read_text())
    for value in original["files"].values():
        value["source"] = os.path.relpath((profile.parent/value["source"]).resolve(), destination.parent)
    for path in sorted((bundle/"payload").rglob("*")):
        if not path.is_file(): continue
        name = prefix + "/" + str(path.relative_to(bundle/"payload"))
        if name in original["files"]: raise ValueError("Asset name collides with existing profile: " + name)
        original["files"][name] = {"source":os.path.relpath(path, destination.parent),"sha256":ac.sha_file(path)}
    original["provenance"]["optional_asset_bundle"] = {"prefix":prefix,"receipt_sha256":ac.sha_file(bundle/"receipt.json")}
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x") as out: json.dump(original,out,indent=2);out.write("\n")
    return {"profile":str(destination),"source_candidate_unchanged":True,
            "activation":"Candidate must explicitly call the asset restore function before using the restored file."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs=parser.add_subparsers(dest="command",required=True)
    for name in ("build","bench"):
        sub=subs.add_parser(name)
        sub.add_argument("--input",type=Path,required=True,action="append" if name=="bench" else "store")
        sub.add_argument("--asset-license",type=Path,required=True)
        sub.add_argument("--notice",required=True)
        sub.add_argument("--output",type=Path,required=True)
        sub.add_argument("--max-bytes",type=int,default=ac.DEFAULT_BUDGET)
        sub.add_argument("--codec",choices=ac.CODECS,action="append" if name=="bench" else "store",required=name=="build")
    sub=subs.add_parser("compose-profile")
    sub.add_argument("--profile",type=Path,required=True)
    sub.add_argument("--bundle",type=Path,required=True)
    sub.add_argument("--output",type=Path,required=True)
    sub.add_argument("--prefix",default="asset_bundle")
    args=parser.parse_args()
    if args.command=="build":
        result=build(args.input,args.asset_license,args.notice,args.codec,args.output,args.max_bytes)
    elif args.command=="bench":
        result=benchmark(args.input,args.asset_license,args.notice,args.output,args.codec or ac.CODECS,args.max_bytes)
        result={"report":str(args.output/"report.json"),"inputs":len(result["inputs"])}
    else:
        result=compose(args.profile,args.bundle,args.output,args.prefix)
    print(json.dumps(result,indent=2))


if __name__=="__main__":
    main()
