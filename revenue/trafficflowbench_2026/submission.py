from __future__ import annotations

import csv
import hashlib
import io
import math
from collections.abc import Iterable, Mapping

from .contract import UPSTREAM, authority_ceiling, canonical_json_bytes

OUT_COLUMNS = ("submission_id", "task", "speed_kmh", "flow_vph", "queue_pred", "path_flow")
KEYS = {
    "state": ("panel", "timestamp", "station_id", "link_id", "mask_regime"),
    "queue": ("window_id", "timestamp", "link_id"),
    "odme": ("panel", "departure_time", "path_id"),
}
VALUES = {"state": ("speed_kmh", "flow_vph"), "queue": ("queue_pred",), "odme": ("path_flow",)}
RECEIPT_FIELDS = frozenset({
    "schema",
    "upstreamCommit",
    "submissionKeySha256",
    "inputSha256",
    "rows",
    "gaps",
    "requireComplete",
    "csvSha256",
    "authority",
    "receiptSha256",
})


def _key(row: Mapping[str, object], task: str) -> tuple[str, ...]:
    values: list[str] = []
    try:
        for column in KEYS[task]:
            raw = row[column]
            if raw is None or not str(raw).strip():
                raise ValueError(f"blank {task} natural key field: {column}")
            values.append(str(raw))
    except KeyError as exc:
        raise ValueError(f"missing {task} key field: {exc.args[0]}") from exc
    return tuple(values)


def _normalize_key_record(row: Mapping[str, object]) -> tuple[dict[str, object], tuple[str, ...]]:
    task = str(row.get("task", ""))
    if task not in KEYS:
        raise ValueError(f"unknown task in submission key: {task!r}")
    try:
        sid = int(str(row["submission_id"]))
    except (KeyError, ValueError) as exc:
        raise ValueError("submission_id must be an integer") from exc
    key = _key(row, task)
    record: dict[str, object] = {"submission_id": sid, "task": task}
    record.update(dict(zip(KEYS[task], key)))
    return record, key


def _number(value: object, name: str, *, nonnegative: bool = True) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} is not numeric") from exc
    if not math.isfinite(out) or (nonnegative and out < 0):
        raise ValueError(f"{name} must be finite" + (" and non-negative" if nonnegative else ""))
    return out


def _table(rows: Iterable[Mapping[str, object]], task: str) -> tuple[dict[tuple[str, ...], tuple[float, ...]], str]:
    table: dict[tuple[str, ...], tuple[float, ...]] = {}
    records: list[tuple[tuple[str, ...], dict[str, object]]] = []
    for row in rows:
        key = _key(row, task)
        if key in table:
            raise ValueError(f"duplicate {task} natural key: {key}")
        vals = tuple(_number(row.get(column), column) for column in VALUES[task])
        if task == "state" and key[-1] not in {"R1", "R2", "R3"}:
            raise ValueError("mask_regime must be R1, R2, or R3")
        if task == "queue" and vals[0] not in (0.0, 1.0):
            raise ValueError("queue_pred must be 0 or 1")
        record: dict[str, object] = {"task": task}
        record.update(dict(zip(KEYS[task], key)))
        record.update(dict(zip(VALUES[task], vals)))
        if task == "odme":
            for zone in ("origin_zone", "destination_zone"):
                raw = row.get(zone)
                if raw is None or not str(raw).strip():
                    raise ValueError(f"{zone} is required for ODME rows")
                record[zone] = str(raw)
        table[key] = vals
        records.append((key, record))
    hasher = hashlib.sha256()
    for _, record in sorted(records, key=lambda item: item[0]):
        hasher.update(canonical_json_bytes(record))
        hasher.update(b"\n")
    return table, hasher.hexdigest()


def _feed_key_digest(hasher: "hashlib._Hash", record: Mapping[str, object]) -> None:
    hasher.update(canonical_json_bytes(record))
    hasher.update(b"\n")


def _is_sha256(value: object) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


def compile_submission(
    submission_key_rows: Iterable[Mapping[str, object]],
    *,
    state_rows: Iterable[Mapping[str, object]],
    queue_rows: Iterable[Mapping[str, object]],
    odme_rows: Iterable[Mapping[str, object]],
    require_complete: bool = True,
) -> tuple[str, dict[str, object]]:
    """Compile the official six-column shape without contacting Kaggle.

    The receipt binds the exact ordered ``submission_key`` generation. Keep that
    same key iterable for ``verify_compiled_submission``.
    """
    if require_complete is not True:
        raise ValueError("source-safe compiler requires complete predictions")
    state_table, state_sha = _table(state_rows, "state")
    queue_table, queue_sha = _table(queue_rows, "queue")
    odme_table, odme_sha = _table(odme_rows, "odme")
    tables = {"state": state_table, "queue": queue_table, "odme": odme_table}
    input_sha256 = {"state": state_sha, "queue": queue_sha, "odme": odme_sha}
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(OUT_COLUMNS), lineterminator="\n")
    writer.writeheader()
    seen_ids: set[int] = set()
    gaps = {task: 0 for task in tables}
    key_hasher = hashlib.sha256()
    row_count = 0
    for row in submission_key_rows:
        record, key = _normalize_key_record(row)
        task = str(record["task"])
        sid = int(record["submission_id"])
        if sid in seen_ids:
            raise ValueError(f"duplicate submission_id: {sid}")
        seen_ids.add(sid)
        _feed_key_digest(key_hasher, record)
        values = tables[task].get(key)
        if values is None:
            gaps[task] += 1
            raise ValueError(f"missing {task} value for key {key}")
        out = {
            "submission_id": sid,
            "task": task,
            "speed_kmh": 0.0,
            "flow_vph": 0.0,
            "queue_pred": 0.0,
            "path_flow": 0.0,
        }
        for column, value in zip(VALUES[task], values):
            out[column] = value
        writer.writerow(out)
        row_count += 1
    if row_count == 0:
        raise ValueError("submission key is empty")
    payload = buffer.getvalue()
    receipt = {
        "schema": "trafficflowbench-local-submission/v2",
        "upstreamCommit": UPSTREAM["commit"],
        "submissionKeySha256": key_hasher.hexdigest(),
        "inputSha256": input_sha256,
        "rows": row_count,
        "gaps": gaps,
        "requireComplete": True,
        "csvSha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        "authority": authority_ceiling(),
    }
    receipt["receiptSha256"] = hashlib.sha256(canonical_json_bytes(receipt)).hexdigest()
    return payload, receipt


def _receipt_digest(receipt: Mapping[str, object]) -> str:
    body = dict(receipt)
    body.pop("receiptSha256", None)
    return hashlib.sha256(canonical_json_bytes(body)).hexdigest()


def verify_compiled_submission(
    payload: str,
    receipt: Mapping[str, object],
    submission_key_rows: Iterable[Mapping[str, object]],
    *,
    state_rows: Iterable[Mapping[str, object]],
    queue_rows: Iterable[Mapping[str, object]],
    odme_rows: Iterable[Mapping[str, object]],
) -> bool:
    """Fail-closed local verifier bound to the exact ordered submission key."""
    if not isinstance(receipt, Mapping) or set(receipt) != RECEIPT_FIELDS:
        return False
    if receipt.get("schema") != "trafficflowbench-local-submission/v2":
        return False
    if receipt.get("upstreamCommit") != UPSTREAM["commit"]:
        return False
    if not _is_sha256(receipt.get("submissionKeySha256")) or not _is_sha256(receipt.get("csvSha256")):
        return False
    input_sha256 = receipt.get("inputSha256")
    if not isinstance(input_sha256, Mapping) or set(input_sha256) != set(KEYS):
        return False
    if any(not _is_sha256(input_sha256[task]) for task in KEYS):
        return False
    if not _is_sha256(receipt.get("receiptSha256")) or receipt.get("receiptSha256") != _receipt_digest(receipt):
        return False
    if receipt.get("authority") != authority_ceiling():
        return False
    if type(receipt.get("rows")) is not int or receipt["rows"] <= 0:
        return False
    if receipt.get("requireComplete") is not True:
        return False
    gaps = receipt.get("gaps")
    if not isinstance(gaps, Mapping) or set(gaps) != set(KEYS):
        return False
    if any(type(gaps[task]) is not int or gaps[task] != 0 for task in KEYS):
        return False
    if hashlib.sha256(payload.encode("utf-8")).hexdigest() != receipt["csvSha256"]:
        return False
    try:
        key_material = list(submission_key_rows)
        state_material = list(state_rows)
        queue_material = list(queue_rows)
        odme_material = list(odme_rows)
        expected_payload, expected_receipt = compile_submission(
            key_material,
            state_rows=state_material,
            queue_rows=queue_material,
            odme_rows=odme_material,
        )
    except (AttributeError, TypeError, ValueError):
        return False
    if payload != expected_payload or dict(receipt) != expected_receipt:
        return False
    try:
        rows = list(csv.DictReader(io.StringIO(payload)))
    except csv.Error:
        return False
    if not rows or tuple(rows[0].keys()) != OUT_COLUMNS or receipt["rows"] != len(rows):
        return False

    key_hasher = hashlib.sha256()
    key_count = 0
    try:
        for key_count, key_row in enumerate(key_material, start=1):
            if key_count > len(rows):
                return False
            record, _ = _normalize_key_record(key_row)
            _feed_key_digest(key_hasher, record)
            out = rows[key_count - 1]
            if out["submission_id"] != str(record["submission_id"]) or out["task"] != record["task"]:
                return False
    except (AttributeError, TypeError, ValueError):
        return False
    if key_count != len(rows) or key_hasher.hexdigest() != receipt["submissionKeySha256"]:
        return False

    seen: set[int] = set()
    for row in rows:
        if any(row.get(column, "") == "" for column in OUT_COLUMNS):
            return False
        if row["task"] not in KEYS:
            return False
        try:
            sid = int(row["submission_id"])
        except ValueError:
            return False
        if sid in seen:
            return False
        seen.add(sid)
        try:
            speed, flow, queue, path = [float(row[c]) for c in ("speed_kmh", "flow_vph", "queue_pred", "path_flow")]
        except ValueError:
            return False
        values = [speed, flow, queue, path]
        if any(not math.isfinite(v) or v < 0 for v in values):
            return False
        if row["task"] == "state" and (queue != 0.0 or path != 0.0):
            return False
        if row["task"] == "queue" and (speed != 0.0 or flow != 0.0 or path != 0.0 or queue not in (0.0, 1.0)):
            return False
        if row["task"] == "odme" and (speed != 0.0 or flow != 0.0 or queue != 0.0):
            return False
    return True
