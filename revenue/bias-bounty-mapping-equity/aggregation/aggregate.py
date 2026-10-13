#!/usr/bin/env python3
"""Sealed-generation authority wrapper for Mapping Equity aggregation.

The exact runner merged by #14579 is preserved byte-for-byte in
`_aggregate_unsealed.py`. This successor hardens four authority primitives while
leaving the landed scorer/policy implementation frozen:

* remote source bytes are retained in a kernel-sealed memfd so the public
  `/proc/self/fd/<n>` read path cannot be reopened and mutated between preflight
  and scored aggregation;
* response bytes become source authority only when the final resolved URL is
  exactly the canonical registry URL that was requested;
* the production receipt-minting entrypoint captures code-owned execution
  dependencies and exposes no dependency-injection parameters; and
* the production CLI captures that authoritative entrypoint instead of
  late-resolving the mutable predecessor-module `execute_region` global.

Primary implementation/source credit remains ZSA-D6P2. ZFS-R7 supplied
alternate-carrier review evidence; ZHD-K8P3 recovered/finalized M1 and the
first generation/policy fix; ZRH-H7N4 owns the sealed-generation fix-forward.
Keystone / GPT-5.6 Sol identified the redirect-provenance defect; ZCE-J5V8 /
GPT-5.6 Sol owns the exact-identity fix-forward. ZPB-X4K8 identified the
production dependency-injection receipt bypass; Z-Argent closed the direct
entrypoint seam in #14619. ZYP-V5Q9 identified and closes the post-merge CLI
dispatch rebinding seam in #14623.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path
from typing import BinaryIO

import _aggregate_unsealed as _legacy

# Re-export the exact landed surface, including underscore helpers used by the
# contract/recovery suites. Dunder import identity stays owned by this wrapper.
for _name, _value in vars(_legacy).items():
    if not _name.startswith("__"):
        globals()[_name] = _value


def _required_memfd_seals() -> int:
    names = ("F_SEAL_WRITE", "F_SEAL_GROW", "F_SEAL_SHRINK", "F_SEAL_SEAL")
    missing = [name for name in names if not hasattr(fcntl, name)]
    if missing or not hasattr(fcntl, "F_ADD_SEALS") or not hasattr(fcntl, "F_GET_SEALS"):
        raise AggregationError(
            "run requires Linux memfd sealing support; missing fcntl seal constants"
        )
    return (
        fcntl.F_SEAL_WRITE
        | fcntl.F_SEAL_GROW
        | fcntl.F_SEAL_SHRINK
        | fcntl.F_SEAL_SEAL
    )


def _stream_response_to_retained_fd(
    key: str,
    uri: str,
    response: BinaryIO,
    temp_root: Path,
    *,
    resolved_url: str | None = None,
) -> tuple[int, str, dict[str, object]]:
    """Stream one admitted response into a sealed memfd and retain it read-only.

    A plain anonymous tempfile is still mutable through `/proc/self/fd/<n>`:
    reopening that proc magic path with `O_WRONLY` creates a new writable file
    description whenever inode permissions allow it. Linux memfd seals make the
    generation invariant kernel-enforced instead of depending on pathname
    absence or on dropping the original write handle.

    `resolved_url` is authority evidence from `_materialize_one`. It is optional
    only for predecessor-compatible direct helper calls; real materialization
    always supplies the exact accepted final URL.
    """
    del temp_root  # retained for the predecessor-compatible call signature
    if not hasattr(os, "memfd_create") or not hasattr(os, "MFD_ALLOW_SEALING"):
        raise AggregationError("run requires Linux os.memfd_create with MFD_ALLOW_SEALING")

    required_seals = _required_memfd_seals()
    flags = getattr(os, "MFD_CLOEXEC", 0) | os.MFD_ALLOW_SEALING
    try:
        writer_fd = os.memfd_create(f"mapping-equity-{key}", flags=flags)
    except OSError as exc:
        raise AggregationError(f"{key}: sealed source memfd creation failed") from exc

    retained_fd: int | None = None
    hasher = hashlib.sha256()
    byte_count = 0
    try:
        while True:
            chunk = response.read(8 * 1024 * 1024)
            if not chunk:
                break
            if not isinstance(chunk, (bytes, bytearray)):
                raise AggregationError(f"{key}: source response yielded non-bytes")
            view = memoryview(chunk)
            while view:
                written = os.write(writer_fd, view)
                if written <= 0:
                    raise AggregationError(f"{key}: zero-byte write while materializing source")
                view = view[written:]
            hasher.update(chunk)
            byte_count += len(chunk)

        os.fsync(writer_fd)
        if byte_count <= 0:
            raise AggregationError(f"{key}: empty source object")

        try:
            fcntl.fcntl(writer_fd, fcntl.F_ADD_SEALS, required_seals)
            observed_seals = fcntl.fcntl(writer_fd, fcntl.F_GET_SEALS)
        except OSError as exc:
            raise AggregationError(f"{key}: kernel refused immutable source seals") from exc
        if observed_seals & required_seals != required_seals:
            raise AggregationError(f"{key}: retained source generation is not fully sealed")

        retained_fd = os.open(
            f"/proc/self/fd/{writer_fd}",
            os.O_RDONLY | getattr(os, "O_CLOEXEC", 0),
        )
        stat = os.fstat(retained_fd)
        if stat.st_size != byte_count:
            raise AggregationError(f"{key}: retained source size changed during materialization")

        digest = hasher.hexdigest()
        result_fd = retained_fd
        retained_fd = None
        return result_fd, f"/proc/self/fd/{result_fd}", {
            "uri": uri,
            "resolved_url": uri if resolved_url is None else resolved_url,
            "sha256": digest,
            "bytes": byte_count,
            "generation": f"sha256:{digest}",
        }
    finally:
        if retained_fd is not None:
            try:
                os.close(retained_fd)
            except OSError:
                pass
        try:
            os.close(writer_fd)
        except OSError:
            pass


def _materialize_one(
    key: str,
    uri: str,
    temp_root: Path,
    _opener=_legacy._URL_OPEN,
) -> tuple[int, str, dict[str, object]]:
    """Admit exactly one canonical public object response as source authority."""
    requested_url = _legacy._safe_source(uri)
    try:
        response = _opener(uri, timeout=300)
    except Exception as exc:
        raise AggregationError(f"{key}: public source download failed") from exc
    try:
        final_url = str(getattr(response, "geturl", lambda: requested_url)())
        resolved_url = _legacy._safe_source(final_url)
        if resolved_url != requested_url:
            raise AggregationError(
                f"{key}: source redirect changed canonical source identity: "
                f"requested={requested_url!r}, resolved={resolved_url!r}"
            )
        return _stream_response_to_retained_fd(
            key,
            uri,
            response,
            temp_root,
            resolved_url=resolved_url,
        )
    finally:
        close = getattr(response, "close", None)
        if callable(close):
            close()


def _materialize_sources(region: str, _one=_materialize_one) -> _legacy._MaterializedSources:
    """Materialize every registry object through the exact-identity gate."""
    region = _legacy._region(region)
    if not Path("/proc/self/fd").is_dir():
        raise AggregationError(
            "run requires Linux /proc/self/fd so DuckDB can consume retained exact source generations"
        )
    tempdir = _legacy.tempfile.TemporaryDirectory(prefix=f"mapping-equity-{region}-")
    root = Path(tempdir.name)
    os.chmod(root, 0o700)
    registry: dict[str, str] = {}
    generations: dict[str, dict[str, object]] = {}
    fds: list[int] = []
    try:
        for key, uri in _legacy.source_registry(region).items():
            fd, fd_path, generation = _one(key, uri, root)
            fds.append(fd)
            registry[key] = fd_path
            generations[key] = generation
        return _legacy._MaterializedSources(tempdir, registry, generations, fds)
    except Exception:
        for fd in fds:
            try:
                os.close(fd)
            except OSError:
                pass
        tempdir.cleanup()
        raise


def _generation_receipt(
    generations: dict[str, dict[str, object]],
) -> dict[str, dict[str, object]]:
    """Normalize admitted source-generation evidence without minting run truth."""
    return {
        key: {
            "uri": value["uri"],
            "resolved_url": value.get("resolved_url", value["uri"]),
            "sha256": value["sha256"],
            "bytes": value["bytes"],
            "generation": value["generation"],
        }
        for key, value in generations.items()
    }


def _make_authoritative_execute_region(
    materializer,
    connector,
    query_builder,
    preflight_runner,
    row_validator,
    csv_renderer,
    sql_canonicalizer,
    plan_builder,
    exclusive_writer,
    parser_factory,
    region_choices,
    aggregate_query_builder,
    path_type,
    json_dumps,
    error_types,
):
    """Bind the complete authoritative execution + CLI path in one temporary constructor."""

    def execute_region(region: str, output: Path, receipt: Path) -> dict[str, object]:
        """Execute only the code-owned public-data path and mint its bound receipt."""
        region = _legacy._region(region)
        if output.resolve() == receipt.resolve():
            raise AggregationError("output and receipt must be different paths")
        if output.exists() or receipt.exists():
            raise AggregationError("run outputs are create-exclusive; choose fresh paths")
        materialized = materializer(region)
        con = None
        try:
            con = connector()
            preflight = preflight_runner(
                con,
                region,
                materialized.registry,
                materialized.generations,
            )
            query = query_builder(region, materialized.registry)
            cursor = con.execute(query)
            fieldnames = [str(desc[0]) for desc in cursor.description]
            rows = cursor.fetchall()
            cleaned = row_validator(region, fieldnames, rows)
            csv_text = csv_renderer(cleaned)
            csv_sha = hashlib.sha256(csv_text.encode("utf-8")).hexdigest()
            canonical_query = sql_canonicalizer(
                query,
                materialized.registry,
                materialized.generations,
            )
            payload = {
                "schema": "mapping-equity-public-aggregation/v2",
                "region": region,
                "duckdb_version": "1.5.4",
                "overture_release": "2026-08-19.0",
                "real_public_data_executed": True,
                "row_count": len(cleaned),
                "output_csv_sha256": csv_sha,
                "input_generations": _generation_receipt(materialized.generations),
                "bound_query_sha256": hashlib.sha256(canonical_query.encode("utf-8")).hexdigest(),
                "preflight": preflight,
                "plan": plan_builder(region),
                "claims": {
                    "zindi_registered": False,
                    "submitted_to_zindi": False,
                    "leaderboard_score_claimed": False,
                    "award_claimed": False,
                    "payment_claimed": False,
                },
            }
            body = json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
            )
            envelope = {
                "payload": payload,
                "payload_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
            }
            receipt_text = json.dumps(
                envelope,
                sort_keys=True,
                indent=2,
                ensure_ascii=True,
            ) + "\n"
            exclusive_writer(output, csv_text)
            exclusive_writer(receipt, receipt_text)
            return {
                "region": region,
                "rows": len(cleaned),
                "output_csv_sha256": csv_sha,
            }
        finally:
            if con is not None:
                con.close()
            materialized.close()

    def main(argv=None) -> int:
        """Dispatch plan/run with the same captured execution authority."""
        parser = parser_factory(description=__doc__)
        sub = parser.add_subparsers(dest="command", required=True)
        plan_cmd = sub.add_parser("plan", help="emit deterministic no-download plan + preflight SQL")
        plan_cmd.add_argument("--region", required=True, choices=region_choices)
        plan_cmd.add_argument("--sql", action="store_true", help="include aggregate SQL")
        run_cmd = sub.add_parser("run", help="materialize + execute one public region with DuckDB 1.5.4")
        run_cmd.add_argument("--region", required=True, choices=region_choices)
        run_cmd.add_argument("--output", required=True)
        run_cmd.add_argument("--receipt", required=True)
        args = parser.parse_args(argv)
        try:
            if args.command == "plan":
                payload = plan_builder(args.region)
                if args.sql:
                    payload["sql"] = aggregate_query_builder(args.region)
                print(json_dumps(payload, sort_keys=True, indent=2))
            else:
                result = execute_region(args.region, path_type(args.output), path_type(args.receipt))
                print(json_dumps(result, sort_keys=True))
        except error_types as exc:
            parser.error(str(exc))
        return 0

    return execute_region, main


# One temporary constructor binds both receipt-minting execution and CLI dispatch.
# Keeping the two closures in the same lexical authority boundary satisfies the
# no-second-factory contract while preserving the #14628 rebinding hardening.
execute_region, main = _make_authoritative_execute_region(
    _materialize_sources,
    _legacy._connect_duckdb,
    _legacy._aggregate_query_for_registry,
    _legacy.run_preflight,
    _legacy.validate_rows,
    _legacy.render_csv,
    _legacy._canonicalize_bound_sql,
    _legacy.build_plan,
    _legacy._write_new,
    _legacy.argparse.ArgumentParser,
    tuple(_legacy.REGIONS),
    _legacy.aggregate_query,
    Path,
    json.dumps,
    (AggregationError, OSError),
)
# Do not leave a callable factory that a direct-library caller could reuse with
# substituted dependencies to manufacture authoritative execution or CLI entrypoints.
del _make_authoritative_execute_region


# Preserve `_aggregate_unsealed.py` byte-for-byte. Rebind only the live authority
# surfaces whose defaults would otherwise still point at the frozen predecessor.
_legacy._stream_response_to_retained_fd = _stream_response_to_retained_fd
_legacy._materialize_one = _materialize_one
_legacy._materialize_sources = _materialize_sources
_legacy.execute_region = execute_region
_legacy.main = main


if __name__ == "__main__":
    raise SystemExit(main())
