#!/usr/bin/env python3
"""Restore a Conversation Desk JSON export into one new SQLite workspace."""
from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import os
from pathlib import Path
import tempfile

import app

FORMAT = "conversation-desk-export-v1"
CONVERSATION_KEYS = {"id", *app.FIELDS, "revision", "created", "updated", "images"}
IMAGE_META_KEYS = {"id", "name", "mime", "sha256", "size"}
IMAGE_KEYS = {"id", "conversation_id", "name", "mime", "sha256", "data_base64"}


class RestoreError(ValueError):
    """The export cannot be restored without weakening its saved-data contract."""


def _text(value, label, *, allow_empty=False, max_chars=1000):
    if not isinstance(value, str) or (not allow_empty and not value) or len(value) > max_chars or "\x00" in value:
        qualifier = "text" if allow_empty else "non-empty text"
        raise RestoreError(f"{label} must be {qualifier} of at most {max_chars} characters without NUL.")
    try:
        value.encode("utf-8")
    except UnicodeError:
        raise RestoreError(f"{label} contains invalid Unicode.") from None
    return value


def _id(value, label):
    return _text(value, label, max_chars=200)


def _sha256(value, label):
    if not isinstance(value, str) or len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise RestoreError(f"{label} must be a lowercase SHA-256 hex digest.")
    return value


def _exact_keys(value, expected, label):
    if not isinstance(value, dict):
        raise RestoreError(f"{label} must be a JSON object.")
    keys = set(value)
    if keys != expected:
        missing = sorted(expected - keys)
        extra = sorted(keys - expected)
        detail = []
        if missing:
            detail.append("missing " + ", ".join(missing))
        if extra:
            detail.append("unexpected " + ", ".join(extra))
        raise RestoreError(f"{label} has the wrong shape ({'; '.join(detail)}).")


def _decode_image(record, label):
    try:
        data, detected_mime, name = app.image_bytes({
            "name": record["name"],
            "data_base64": record["data_base64"],
        })
    except app.DeskError as exc:
        raise RestoreError(f"{label}: {exc}") from None
    if record["mime"] != detected_mime:
        raise RestoreError(f"{label} MIME does not match the encoded screenshot bytes.")
    actual_sha = hashlib.sha256(data).hexdigest()
    if record["sha256"] != actual_sha:
        raise RestoreError(f"{label} SHA-256 does not match the encoded screenshot bytes.")
    return data, detected_mime, name


def validate_export(value):
    """Validate a complete v1 export before any destination file is created."""
    if not isinstance(value, dict):
        raise RestoreError("The export must be a JSON object.")
    expected_top = {"format", "exported", "conversations", "images"}
    _exact_keys(value, expected_top, "export")
    if value["format"] != FORMAT:
        raise RestoreError(f"Unsupported export format; expected {FORMAT}.")
    _text(value["exported"], "exported timestamp", max_chars=200)
    if not isinstance(value["conversations"], list) or not isinstance(value["images"], list):
        raise RestoreError("conversations and images must be JSON arrays.")

    conversations = []
    conversation_ids = set()
    nested_images = {}
    nested_owner = {}
    for index, raw in enumerate(value["conversations"]):
        label = f"conversation[{index}]"
        _exact_keys(raw, CONVERSATION_KEYS, label)
        cid = _id(raw["id"], f"{label}.id")
        if cid in conversation_ids:
            raise RestoreError(f"Duplicate conversation id: {cid}")
        conversation_ids.add(cid)
        fields = {key: raw[key] for key in app.FIELDS}
        try:
            normalized = app.validate_fields(fields)
        except app.DeskError as exc:
            raise RestoreError(f"{label}: {exc}") from None
        if set(normalized) != set(app.FIELDS):
            raise RestoreError(f"{label} is missing one or more saved Conversation Desk fields.")
        revision = raw["revision"]
        if type(revision) is not int or revision < 1:
            raise RestoreError(f"{label}.revision must be a positive integer.")
        _text(raw["created"], f"{label}.created", max_chars=200)
        _text(raw["updated"], f"{label}.updated", max_chars=200)
        if not isinstance(raw["images"], list):
            raise RestoreError(f"{label}.images must be a JSON array.")
        ordered_ids = []
        for image_index, meta in enumerate(raw["images"]):
            meta_label = f"{label}.images[{image_index}]"
            _exact_keys(meta, IMAGE_META_KEYS, meta_label)
            iid = _id(meta["id"], f"{meta_label}.id")
            if iid in nested_images:
                raise RestoreError(f"Duplicate nested image id: {iid}")
            _text(meta["name"], f"{meta_label}.name", max_chars=200)
            _text(meta["mime"], f"{meta_label}.mime", max_chars=100)
            _sha256(meta["sha256"], f"{meta_label}.sha256")
            if type(meta["size"]) is not int or meta["size"] < 1:
                raise RestoreError(f"{meta_label}.size must be a positive integer.")
            nested_images[iid] = dict(meta)
            nested_owner[iid] = cid
            ordered_ids.append(iid)
        conversations.append({
            "old_id": cid,
            "fields": fields,
            "source_revision": revision,
            "source_created": raw["created"],
            "source_updated": raw["updated"],
            "image_ids": ordered_ids,
        })

    images = {}
    for index, raw in enumerate(value["images"]):
        label = f"image[{index}]"
        _exact_keys(raw, IMAGE_KEYS, label)
        iid = _id(raw["id"], f"{label}.id")
        if iid in images:
            raise RestoreError(f"Duplicate top-level image id: {iid}")
        cid = _id(raw["conversation_id"], f"{label}.conversation_id")
        if cid not in conversation_ids:
            raise RestoreError(f"{label} references unknown conversation id {cid}.")
        _text(raw["name"], f"{label}.name", max_chars=200)
        _text(raw["mime"], f"{label}.mime", max_chars=100)
        _sha256(raw["sha256"], f"{label}.sha256")
        data, mime, name = _decode_image(raw, label)
        images[iid] = {
            "old_id": iid,
            "conversation_id": cid,
            "name": name,
            "mime": mime,
            "sha256": raw["sha256"],
            "data": data,
            "data_base64": raw["data_base64"],
        }

    if set(images) != set(nested_images):
        missing_top = sorted(set(nested_images) - set(images))
        missing_nested = sorted(set(images) - set(nested_images))
        detail = []
        if missing_top:
            detail.append("nested-only ids " + ", ".join(missing_top))
        if missing_nested:
            detail.append("top-level-only ids " + ", ".join(missing_nested))
        raise RestoreError("Image metadata/data sets disagree (" + "; ".join(detail) + ").")

    for iid, image in images.items():
        meta = nested_images[iid]
        if nested_owner[iid] != image["conversation_id"]:
            raise RestoreError(f"Image {iid} is associated with different conversations in metadata and data.")
        if meta["name"] != image["name"] or meta["mime"] != image["mime"] or meta["sha256"] != image["sha256"]:
            raise RestoreError(f"Image {iid} metadata does not match its top-level record.")
        if meta["size"] != len(image["data"]):
            raise RestoreError(f"Image {iid} size metadata does not match its encoded screenshot bytes.")

    return {
        "format": FORMAT,
        "conversations": conversations,
        "images": images,
    }


def load_export(path):
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise RestoreError(f"Could not read the export as UTF-8 JSON: {exc}") from None
    try:
        def reject_constant(_):
            raise ValueError("non-finite constant")
        value = json.loads(text, parse_constant=reject_constant)
    except (ValueError, UnicodeError, RecursionError):
        raise RestoreError("The export is not valid finite JSON.") from None
    return validate_export(value)


def _verify_restored(validated, restored, conversation_map, image_map):
    restored_conversations = {row["id"]: row for row in restored["conversations"]}
    restored_images = {row["id"]: row for row in restored["images"]}
    if len(restored_conversations) != len(validated["conversations"]):
        raise RestoreError("Internal verification found an unexpected restored conversation count.")
    if len(restored_images) != len(validated["images"]):
        raise RestoreError("Internal verification found an unexpected restored image count.")

    for source in validated["conversations"]:
        old_cid = source["old_id"]
        new_cid = conversation_map[old_cid]
        target = restored_conversations.get(new_cid)
        if target is None:
            raise RestoreError(f"Internal verification lost restored conversation {old_cid}.")
        for field, expected in source["fields"].items():
            if target[field] != expected:
                raise RestoreError(f"Internal verification changed field {field} for conversation {old_cid}.")
        expected_new_images = [image_map[iid] for iid in source["image_ids"]]
        actual_new_images = [meta["id"] for meta in target["images"]]
        if actual_new_images != expected_new_images:
            raise RestoreError(f"Internal verification changed image order/association for conversation {old_cid}.")

    for old_iid, source in validated["images"].items():
        new_iid = image_map[old_iid]
        target = restored_images.get(new_iid)
        if target is None:
            raise RestoreError(f"Internal verification lost restored image {old_iid}.")
        if target["conversation_id"] != conversation_map[source["conversation_id"]]:
            raise RestoreError(f"Internal verification changed conversation association for image {old_iid}.")
        if target["name"] != source["name"] or target["mime"] != source["mime"] or target["sha256"] != source["sha256"]:
            raise RestoreError(f"Internal verification changed metadata for image {old_iid}.")
        try:
            decoded = base64.b64decode(target["data_base64"], validate=True)
        except (ValueError, binascii.Error):
            raise RestoreError(f"Internal verification produced invalid base64 for image {old_iid}.") from None
        if decoded != source["data"]:
            raise RestoreError(f"Internal verification changed screenshot bytes for image {old_iid}.")


def _remove_temp(path):
    for suffix in ("", "-journal", "-wal", "-shm"):
        try:
            Path(str(path) + suffix).unlink()
        except FileNotFoundError:
            pass


def restore_export(source_path, database_path):
    """Restore after complete validation, never overwriting an existing destination."""
    destination = Path(database_path)
    if os.path.lexists(destination):
        raise RestoreError("Refusing to overwrite an existing destination database or link.")
    if not destination.parent.is_dir():
        raise RestoreError("The destination parent directory must already exist.")

    validated = load_export(source_path)
    fd, temp_name = tempfile.mkstemp(prefix=f".{destination.name}.restore-", suffix=".sqlite3", dir=destination.parent)
    os.close(fd)
    temp_path = Path(temp_name)
    conversation_map = {}
    image_map = {}
    try:
        store = app.Store(temp_path)
        for source in validated["conversations"]:
            created = store.create(source["fields"])
            new_cid = created["id"]
            conversation_map[source["old_id"]] = new_cid
            revision = created["revision"]
            for old_iid in source["image_ids"]:
                image = validated["images"][old_iid]
                updated = store.add_image(new_cid, {
                    "name": image["name"],
                    "data_base64": image["data_base64"],
                }, revision)
                revision = updated["revision"]
                new_meta = updated["images"][-1]
                image_map[old_iid] = new_meta["id"]

        restored = app.Store(temp_path).export()
        _verify_restored(validated, restored, conversation_map, image_map)

        try:
            os.link(temp_path, destination, follow_symlinks=False)
        except FileExistsError:
            raise RestoreError("Destination appeared during restore; nothing was overwritten.") from None
        except OSError as exc:
            raise RestoreError(f"Could not atomically publish the new database without overwrite: {exc}") from None
        temp_path.unlink()
        return {
            "restored": True,
            "format": FORMAT,
            "database": str(destination),
            "conversations": len(conversation_map),
            "images": len(image_map),
            "conversation_id_map": conversation_map,
            "image_id_map": image_map,
            "regenerated": ["ids", "revisions", "timestamps"],
        }
    except Exception:
        _remove_temp(temp_path)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("export", help="Conversation Desk v1 JSON export")
    parser.add_argument("database", help="NEW destination SQLite path; must not already exist")
    args = parser.parse_args()
    try:
        receipt = restore_export(args.export, args.database)
    except RestoreError as exc:
        print(json.dumps({"restored": False, "error": str(exc)}, ensure_ascii=True))
        raise SystemExit(2)
    print(json.dumps(receipt, ensure_ascii=True, sort_keys=True))


if __name__ == "__main__":
    main()
