#!/usr/bin/env python3
"""Resumable multi-video production queue for Short Video Studio.

This module layers durable campaign execution and deterministic delivery
manifests over the existing local-only ``studio.render_project`` renderer.
It does not upload, publish, contact customers, or perform provider actions.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import tempfile
from typing import Any, Callable

from studio import ProjectError, render_project, validate_project

MANIFEST_SCHEMA = "short-video-production-manifest/v1"
STATE_SCHEMA = "short-video-production-state/v2"
DELIVERY_SCHEMA = "short-video-production-delivery/v2"
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,95}$")
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_AUTHORITY = {
    "external_publication_performed": False,
    "customer_delivery_performed": False,
    "provider_action_authorized": False,
    "payment_verified": False,
    "revenue_recognized": False,
}


class ProductionError(ValueError):
    """Raised when production evidence or local custody is unsafe."""


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ProductionError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def loads_strict(text: str) -> Any:
    try:
        return json.loads(
            text,
            object_pairs_hook=_strict_object,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ProductionError(f"non-finite JSON value: {value}")
            ),
        )
    except ProductionError:
        raise
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise ProductionError(f"invalid JSON: {exc}") from exc


def canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ProductionError(f"value is not canonical JSON: {exc}") from exc


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_json(value: Any) -> str:
    return sha256_bytes(canonical_json(value).encode("utf-8"))


def _exact_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise ProductionError(
            f"{label} keys mismatch; missing={sorted(expected - set(value))} "
            f"unknown={sorted(set(value) - expected)}"
        )


def _plain_dict(value: Any, label: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise ProductionError(f"{label} must be a JSON object")
    return value


def _opaque(value: Any, label: str) -> str:
    if type(value) is not str or not _ID_RE.fullmatch(value):
        raise ProductionError(f"{label} is malformed")
    return value


def _relative_path(
    root: pathlib.Path,
    value: Any,
    *,
    label: str,
    must_exist: bool = False,
    suffix: str | None = None,
) -> tuple[str, pathlib.Path]:
    if type(value) is not str or not value or "\x00" in value:
        raise ProductionError(f"{label} must be a nonempty relative path")
    raw = pathlib.Path(value)
    if raw.is_absolute():
        raise ProductionError(f"{label} must be relative")
    root = root.resolve()
    candidate = root / raw
    if candidate.is_symlink():
        raise ProductionError(f"{label} may not be a symlink")
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ProductionError(f"{label} escapes campaign directory") from exc
    if must_exist and not resolved.is_file():
        raise ProductionError(f"{label} does not exist as a file: {value}")
    if suffix is not None and resolved.suffix.lower() != suffix:
        raise ProductionError(f"{label} must end in {suffix}")
    normalized = resolved.relative_to(root).as_posix()
    return normalized, resolved


def _read_json(path: pathlib.Path) -> Any:
    try:
        return loads_strict(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ProductionError(f"cannot read {path}: {exc}") from exc


def _file_sha(path: pathlib.Path) -> str:
    try:
        return sha256_bytes(path.read_bytes())
    except OSError as exc:
        raise ProductionError(f"cannot read artifact {path}: {exc}") from exc


def _same_existing_file(left: pathlib.Path, right: pathlib.Path) -> bool:
    if left.resolve() == right.resolve():
        return True
    try:
        return left.exists() and right.exists() and left.samefile(right)
    except OSError:
        return False


def validate_manifest(manifest: Any, *, root: pathlib.Path) -> dict[str, Any]:
    root = root.resolve()
    obj = _plain_dict(manifest, "manifest")
    _exact_keys(obj, {"schema", "campaign_id", "brand", "jobs"}, "manifest")
    if obj.get("schema") != MANIFEST_SCHEMA:
        raise ProductionError("manifest schema mismatch")
    campaign_id = _opaque(obj.get("campaign_id"), "campaign_id")

    brand = _plain_dict(obj.get("brand"), "brand")
    _exact_keys(brand, {"brand_id", "preset_id"}, "brand")
    normalized_brand = {
        "brand_id": _opaque(brand.get("brand_id"), "brand.brand_id"),
        "preset_id": _opaque(brand.get("preset_id"), "brand.preset_id"),
    }

    jobs = obj.get("jobs")
    if type(jobs) is not list or not jobs:
        raise ProductionError("jobs must be a nonempty list")
    if len(jobs) > 100:
        raise ProductionError("jobs exceeds local campaign limit of 100")

    normalized_jobs: list[dict[str, str]] = []
    job_ids: set[str] = set()
    project_paths: list[pathlib.Path] = []
    output_paths: list[pathlib.Path] = []
    caption_paths: list[pathlib.Path] = []

    for index, raw in enumerate(jobs):
        job = _plain_dict(raw, f"jobs[{index}]")
        _exact_keys(job, {"job_id", "project", "output"}, f"jobs[{index}]")
        job_id = _opaque(job.get("job_id"), f"jobs[{index}].job_id")
        if job_id in job_ids:
            raise ProductionError(f"duplicate job_id: {job_id}")
        job_ids.add(job_id)
        project_rel, project_path = _relative_path(
            root,
            job.get("project"),
            label=f"jobs[{index}].project",
            must_exist=True,
            suffix=".json",
        )
        output_rel, output_path = _relative_path(
            root,
            job.get("output"),
            label=f"jobs[{index}].output",
            suffix=".mp4",
        )
        caption_path = output_path.with_suffix(".srt")
        caption_candidate = (root / output_rel).with_suffix(".srt")
        if caption_candidate.is_symlink():
            raise ProductionError(f"jobs[{index}] caption target may not be a symlink")
        normalized_jobs.append(
            {"job_id": job_id, "project": project_rel, "output": output_rel}
        )
        project_paths.append(project_path)
        output_paths.append(output_path)
        caption_paths.append(caption_path)

    all_outputs = output_paths + caption_paths
    canonical_outputs = [str(path.resolve()) for path in all_outputs]
    if len(set(canonical_outputs)) != len(canonical_outputs):
        raise ProductionError("output/caption targets must be globally unique")

    for index, artifact in enumerate(all_outputs):
        for other in all_outputs[index + 1 :]:
            if _same_existing_file(artifact, other):
                raise ProductionError(
                    "output/caption targets must be globally unique by file identity"
                )
        for project in project_paths:
            if _same_existing_file(artifact, project):
                raise ProductionError(
                    f"output/caption target aliases project source: {artifact}"
                )

    return {
        "schema": MANIFEST_SCHEMA,
        "campaign_id": campaign_id,
        "brand": normalized_brand,
        "jobs": normalized_jobs,
    }


def load_manifest(path: pathlib.Path) -> tuple[dict[str, Any], pathlib.Path]:
    path = path.resolve()
    manifest = validate_manifest(_read_json(path), root=path.parent)
    return manifest, path.parent


def _project_info(project_path: pathlib.Path) -> tuple[str, dict[str, Any]]:
    raw = _read_json(project_path)
    try:
        normalized = validate_project(raw, project_path.parent)
    except ProjectError as exc:
        raise ProductionError(f"invalid renderer project {project_path.name}: {exc}") from exc
    return _file_sha(project_path), normalized


def _job_spec_sha(job: dict[str, str]) -> str:
    return sha256_json(job)


def _campaign_definition_sha(manifest: dict[str, Any]) -> str:
    return sha256_json(
        {
            "campaign_id": manifest["campaign_id"],
            "brand": manifest["brand"],
        }
    )


def _empty_state(campaign_id: str, campaign_definition_sha256: str) -> dict[str, Any]:
    return {
        "schema": STATE_SCHEMA,
        "campaign_id": campaign_id,
        "campaign_definition_sha256": campaign_definition_sha256,
        "jobs": {},
    }


def _validate_state(
    value: Any,
    campaign_id: str,
    campaign_definition_sha256: str,
) -> dict[str, Any]:
    state = _plain_dict(value, "state")
    schema = state.get("schema")
    if schema != STATE_SCHEMA:
        if schema == "short-video-production-state/v1":
            raise ProductionError(
                "legacy v1 state must be reset before v2 campaign custody"
            )
        raise ProductionError("state schema mismatch")
    _exact_keys(
        state,
        {"schema", "campaign_id", "campaign_definition_sha256", "jobs"},
        "state",
    )
    if state.get("campaign_id") != campaign_id:
        raise ProductionError("state campaign_id mismatch")
    state_definition_sha = state.get("campaign_definition_sha256")
    if type(state_definition_sha) is not str or not _SHA_RE.fullmatch(state_definition_sha):
        raise ProductionError("state campaign_definition_sha256 is invalid")
    if state_definition_sha != campaign_definition_sha256:
        raise ProductionError(
            "state campaign definition mismatch; brand/preset identity changed"
        )
    jobs = _plain_dict(state.get("jobs"), "state.jobs")
    normalized_jobs: dict[str, Any] = {}
    for job_id, raw in jobs.items():
        _opaque(job_id, "state job_id")
        record = _plain_dict(raw, f"state.jobs.{job_id}")
        _exact_keys(
            record,
            {
                "status",
                "campaign_definition_sha256",
                "job_spec_sha256",
                "project_sha256",
                "output_sha256",
                "captions_sha256",
                "error",
            },
            f"state.jobs.{job_id}",
        )
        record_definition_sha = record.get("campaign_definition_sha256")
        if type(record_definition_sha) is not str or not _SHA_RE.fullmatch(record_definition_sha):
            raise ProductionError(
                f"state.jobs.{job_id}.campaign_definition_sha256 is invalid"
            )
        if record_definition_sha != campaign_definition_sha256:
            raise ProductionError(
                f"state.jobs.{job_id}.campaign definition mismatch"
            )
        status = record.get("status")
        if status not in {"RENDERED", "FAILED"}:
            raise ProductionError(f"state.jobs.{job_id}.status is invalid")
        spec_sha = record.get("job_spec_sha256")
        project_sha = record.get("project_sha256")
        if type(spec_sha) is not str or not _SHA_RE.fullmatch(spec_sha):
            raise ProductionError(f"state.jobs.{job_id}.job_spec_sha256 is invalid")
        if type(project_sha) is not str or not _SHA_RE.fullmatch(project_sha):
            raise ProductionError(f"state.jobs.{job_id}.project_sha256 is invalid")
        output_sha = record.get("output_sha256")
        captions_sha = record.get("captions_sha256")
        error = record.get("error")
        if status == "RENDERED":
            if type(output_sha) is not str or not _SHA_RE.fullmatch(output_sha):
                raise ProductionError(f"state.jobs.{job_id}.output_sha256 is invalid")
            if type(captions_sha) is not str or not _SHA_RE.fullmatch(captions_sha):
                raise ProductionError(f"state.jobs.{job_id}.captions_sha256 is invalid")
            if error is not None:
                raise ProductionError(
                    f"state.jobs.{job_id}.error must be null when rendered"
                )
        else:
            if output_sha is not None or captions_sha is not None:
                raise ProductionError(
                    f"failed state job {job_id} cannot claim artifact hashes"
                )
            if type(error) is not str or not error:
                raise ProductionError(f"failed state job {job_id} requires error text")
        normalized_jobs[job_id] = dict(record)
    return {
        "schema": STATE_SCHEMA,
        "campaign_id": campaign_id,
        "campaign_definition_sha256": campaign_definition_sha256,
        "jobs": normalized_jobs,
    }


def _safe_operational_path(
    root: pathlib.Path,
    value: pathlib.Path,
    *,
    label: str,
    manifest_path: pathlib.Path,
    manifest: dict[str, Any],
) -> pathlib.Path:
    root = root.resolve()
    raw = value if value.is_absolute() else root / value
    resolved = raw.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ProductionError(f"{label} escapes campaign directory") from exc
    if raw.is_symlink():
        raise ProductionError(f"{label} may not be a symlink")
    protected = {manifest_path.resolve()}
    for job in manifest["jobs"]:
        protected.add((root / job["project"]).resolve())
        output = (root / job["output"]).resolve()
        protected.add(output)
        protected.add(output.with_suffix(".srt"))
    if any(_same_existing_file(resolved, item) for item in protected):
        raise ProductionError(f"{label} aliases campaign source/output artifact")
    return resolved


def _load_state(
    path: pathlib.Path,
    campaign_id: str,
    campaign_definition_sha256: str,
) -> dict[str, Any]:
    if not path.exists():
        return _empty_state(campaign_id, campaign_definition_sha256)
    if path.is_symlink() or not path.is_file():
        raise ProductionError("state path must be an ordinary file")
    return _validate_state(_read_json(path), campaign_id, campaign_definition_sha256)


def _atomic_json(path: pathlib.Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ProductionError("refusing to replace symlink state/output")
    data = canonical_json(value) + "\n"
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp_path = pathlib.Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass


def _rendered_record_valid(
    record: Any,
    *,
    job: dict[str, str],
    project_sha: str,
    root: pathlib.Path,
    campaign_definition_sha256: str,
) -> bool:
    if type(record) is not dict or record.get("status") != "RENDERED":
        return False
    if record.get("campaign_definition_sha256") != campaign_definition_sha256:
        return False
    if record.get("job_spec_sha256") != _job_spec_sha(job):
        return False
    if record.get("project_sha256") != project_sha:
        return False
    output = (root / job["output"]).resolve()
    captions = output.with_suffix(".srt")
    if not output.is_file() or not captions.is_file():
        return False
    try:
        return (
            _file_sha(output) == record.get("output_sha256")
            and _file_sha(captions) == record.get("captions_sha256")
        )
    except ProductionError:
        return False


def _all_current_records_valid(
    state: dict[str, Any],
    manifest: dict[str, Any],
    root: pathlib.Path,
    campaign_definition_sha256: str,
) -> bool:
    for job in manifest["jobs"]:
        project_path = (root / job["project"]).resolve()
        try:
            project_sha, _ = _project_info(project_path)
        except ProductionError:
            return False
        if not _rendered_record_valid(
            state["jobs"].get(job["job_id"]),
            job=job,
            project_sha=project_sha,
            root=root,
            campaign_definition_sha256=campaign_definition_sha256,
        ):
            return False
    return True


def run_campaign(
    manifest_path: pathlib.Path,
    state_path: pathlib.Path | None = None,
    *,
    renderer: Callable[[pathlib.Path, pathlib.Path], Any] | None = None,
    continue_on_error: bool = True,
) -> dict[str, Any]:
    manifest_path = manifest_path.resolve()
    manifest, root = load_manifest(manifest_path)
    campaign_definition_sha256 = _campaign_definition_sha(manifest)
    state_candidate = state_path or pathlib.Path("production-state.json")
    state_path = _safe_operational_path(
        root,
        state_candidate,
        label="state path",
        manifest_path=manifest_path,
        manifest=manifest,
    )
    state = _load_state(
        state_path,
        manifest["campaign_id"],
        campaign_definition_sha256,
    )
    render = renderer or render_project
    actions: list[dict[str, Any]] = []

    for job in manifest["jobs"]:
        project_path = (root / job["project"]).resolve()
        output_path = (root / job["output"]).resolve()
        project_sha, _ = _project_info(project_path)
        prior = state["jobs"].get(job["job_id"])
        if _rendered_record_valid(
            prior,
            job=job,
            project_sha=project_sha,
            root=root,
            campaign_definition_sha256=campaign_definition_sha256,
        ):
            actions.append({"job_id": job["job_id"], "action": "SKIPPED_VERIFIED"})
            continue

        spec_sha = _job_spec_sha(job)
        try:
            render(project_path, output_path)
            post_render_project_sha = _file_sha(project_path)
            if post_render_project_sha != project_sha:
                raise ProductionError(
                    "project bytes changed during render; refusing to bind stale authority"
                )
            captions_path = output_path.with_suffix(".srt")
            if not output_path.is_file() or not captions_path.is_file():
                raise ProductionError(
                    "renderer did not produce both MP4 and SRT artifacts"
                )
            state["jobs"][job["job_id"]] = {
                "status": "RENDERED",
                "campaign_definition_sha256": campaign_definition_sha256,
                "job_spec_sha256": spec_sha,
                "project_sha256": project_sha,
                "output_sha256": _file_sha(output_path),
                "captions_sha256": _file_sha(captions_path),
                "error": None,
            }
            actions.append({"job_id": job["job_id"], "action": "RENDERED"})
        except Exception as exc:
            state["jobs"][job["job_id"]] = {
                "status": "FAILED",
                "campaign_definition_sha256": campaign_definition_sha256,
                "job_spec_sha256": spec_sha,
                "project_sha256": project_sha,
                "output_sha256": None,
                "captions_sha256": None,
                "error": f"{type(exc).__name__}: {exc}",
            }
            actions.append({"job_id": job["job_id"], "action": "FAILED"})
            _atomic_json(state_path, state)
            if not continue_on_error:
                raise ProductionError(
                    f"render failed for {job['job_id']}: {exc}"
                ) from exc
            continue
        _atomic_json(state_path, state)

    # Re-run structural custody after render now that output/caption targets exist.
    # This catches hard-link aliases created by a renderer after the initial manifest check.
    validate_manifest(manifest, root=root)
    all_rendered = _all_current_records_valid(
        state,
        manifest,
        root,
        campaign_definition_sha256,
    )
    return {
        "campaign_id": manifest["campaign_id"],
        "campaign_definition_sha256": campaign_definition_sha256,
        "state_path": str(state_path),
        "actions": actions,
        "all_rendered": all_rendered,
    }


def compile_delivery(
    manifest_path: pathlib.Path,
    state_path: pathlib.Path | None = None,
) -> dict[str, Any]:
    manifest_path = manifest_path.resolve()
    manifest, root = load_manifest(manifest_path)
    campaign_definition_sha256 = _campaign_definition_sha(manifest)
    state_candidate = state_path or pathlib.Path("production-state.json")
    state_path = _safe_operational_path(
        root,
        state_candidate,
        label="state path",
        manifest_path=manifest_path,
        manifest=manifest,
    )
    state = _load_state(
        state_path,
        manifest["campaign_id"],
        campaign_definition_sha256,
    )
    jobs: list[dict[str, Any]] = []

    for job in manifest["jobs"]:
        project_path = (root / job["project"]).resolve()
        output_path = (root / job["output"]).resolve()
        captions_path = output_path.with_suffix(".srt")
        project_sha, normalized_project = _project_info(project_path)
        record = state["jobs"].get(job["job_id"])
        ready = _rendered_record_valid(
            record,
            job=job,
            project_sha=project_sha,
            root=root,
            campaign_definition_sha256=campaign_definition_sha256,
        )
        if ready:
            status = "READY_FOR_DELIVERY"
            output_sha = record["output_sha256"]
            captions_sha = record["captions_sha256"]
            error = None
        elif (
            type(record) is dict
            and record.get("status") == "FAILED"
            and record.get("campaign_definition_sha256") == campaign_definition_sha256
            and record.get("job_spec_sha256") == _job_spec_sha(job)
            and record.get("project_sha256") == project_sha
        ):
            status = "FAILED"
            output_sha = None
            captions_sha = None
            error = record.get("error")
        elif record is None:
            status = "PENDING"
            output_sha = None
            captions_sha = None
            error = None
        else:
            status = "STALE"
            output_sha = None
            captions_sha = None
            error = None
        jobs.append(
            {
                "job_id": job["job_id"],
                "project": job["project"],
                "output": job["output"],
                "captions": captions_path.relative_to(root).as_posix(),
                "campaign_definition_sha256": campaign_definition_sha256,
                "project_sha256": project_sha,
                "job_spec_sha256": _job_spec_sha(job),
                "project_preset": normalized_project["preset"],
                "status": status,
                "output_sha256": output_sha,
                "captions_sha256": captions_sha,
                "error": error,
            }
        )

    payload: dict[str, Any] = {
        "schema": DELIVERY_SCHEMA,
        "campaign_id": manifest["campaign_id"],
        "brand": manifest["brand"],
        "campaign_definition_sha256": campaign_definition_sha256,
        "manifest_sha256": sha256_json(manifest),
        "state": (
            "DELIVERY_READY"
            if all(job["status"] == "READY_FOR_DELIVERY" for job in jobs)
            else "INCOMPLETE"
        ),
        "jobs": jobs,
        "authority": dict(_AUTHORITY),
    }
    payload["delivery_sha256"] = sha256_json(payload)
    return payload


def write_delivery(
    manifest_path: pathlib.Path,
    output_path: pathlib.Path,
    state_path: pathlib.Path | None = None,
) -> dict[str, Any]:
    manifest_path = manifest_path.resolve()
    manifest, root = load_manifest(manifest_path)
    safe_output = _safe_operational_path(
        root,
        output_path,
        label="delivery path",
        manifest_path=manifest_path,
        manifest=manifest,
    )
    state_candidate = state_path or pathlib.Path("production-state.json")
    safe_state = _safe_operational_path(
        root,
        state_candidate,
        label="state path",
        manifest_path=manifest_path,
        manifest=manifest,
    )
    if _same_existing_file(safe_output, safe_state):
        raise ProductionError("delivery path may not alias state path")
    if safe_output.exists():
        raise ProductionError(f"refusing to overwrite existing delivery: {safe_output}")
    if safe_output.is_symlink():
        raise ProductionError("delivery path may not be a symlink")
    delivery = compile_delivery(manifest_path, safe_state)
    safe_output.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(safe_output, flags, 0o600)
    except OSError as exc:
        raise ProductionError(f"cannot create delivery output: {exc}") from exc
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(canonical_json(delivery) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        try:
            safe_output.unlink(missing_ok=True)
        finally:
            raise
    return delivery


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("validate", help="validate a production manifest")
    check.add_argument("manifest", type=pathlib.Path)

    run = sub.add_parser("run", help="render or resume a production manifest")
    run.add_argument("manifest", type=pathlib.Path)
    run.add_argument("--state", type=pathlib.Path)

    delivery = sub.add_parser(
        "delivery", help="write a deterministic delivery manifest"
    )
    delivery.add_argument("manifest", type=pathlib.Path)
    delivery.add_argument("--state", type=pathlib.Path)
    delivery.add_argument("--output", required=True, type=pathlib.Path)

    args = parser.parse_args()
    try:
        if args.command == "validate":
            manifest_path = args.manifest.resolve()
            manifest = validate_manifest(
                _read_json(manifest_path), root=manifest_path.parent
            )
            print(
                canonical_json(
                    {
                        "ok": True,
                        "manifest_sha256": sha256_json(manifest),
                        "campaign_definition_sha256": _campaign_definition_sha(manifest),
                    }
                )
            )
            return 0
        if args.command == "run":
            result = run_campaign(args.manifest, args.state)
            print(canonical_json({"ok": True, **result}))
            return 0 if result["all_rendered"] else 3
        result = write_delivery(args.manifest, args.output, args.state)
        print(
            canonical_json(
                {
                    "ok": True,
                    "state": result["state"],
                    "delivery_sha256": result["delivery_sha256"],
                }
            )
        )
        return 0 if result["state"] == "DELIVERY_READY" else 3
    except ProductionError as exc:
        print(canonical_json({"ok": False, "error": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
