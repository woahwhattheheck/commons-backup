#!/usr/bin/env python3
"""WB-RANGE: White Box remote range unit.

Reads stored model weights by address over HTTP Range requests. The file
stays where it sits; the tool fetches only the byte ranges a question
needs, caches them content-addressed, and records every read in a local
manifest. Safetensors and GGUF indexes are built from header bytes only.

Subcommands: index, slice, verify, axis, score, archive, serve.
Use index --stats PATH for measured range reads, cache use and elapsed time.
Stdlib only. No numpy. No executor.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import http.server
import ipaddress
import json
import math
import os
from pathlib import Path, PurePosixPath
import random
import re
import socketserver
import struct
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request


SCHEMA_VERSION = "commons-wb-range/v1"
RANGE_CONTRACT_VERSION = "strict-http-range-v2"
DEFAULT_LIMIT_BYTES = 64 * 1024 * 1024
HF_API = "https://huggingface.co/api/models/{repo}?blobs=true"
HF_RESOLVE = "https://huggingface.co/{repo}/resolve/{rev}/{name}"
USER_AGENT = "wb-range/1.0 (commons; stdlib)"

SAFETENSORS_DTYPES = {
    "BOOL": ("<?", 1),
    "U8": ("<B", 1),
    "I8": ("<b", 1),
    "U16": ("<H", 2),
    "I16": ("<h", 2),
    "F16": ("<e", 2),
    "BF16": (None, 2),
    "U32": ("<I", 4),
    "I32": ("<i", 4),
    "F32": ("<f", 4),
    "U64": ("<Q", 8),
    "I64": ("<q", 8),
    "F64": ("<d", 8),
    "F8_E4M3": (None, 1),
    "F8_E5M2": (None, 1),
    "F8_E8M0": (None, 1),
    "F4": (None, 1),
}

# The existing E8M0 decoder has only 256 possible immutable float results.
E8M0_TABLE = tuple(2.0 ** (byte - 127) for byte in range(256))

# OCP MX E2M1 magnitudes indexed by (exp << 1 | mantissa).
E2M1_TABLE = (0.0, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0)

GGUF_VALUE_TYPES = {
    0: ("<B", 1), 1: ("<b", 1), 2: ("<H", 2), 3: ("<h", 2),
    4: ("<I", 4), 5: ("<i", 4), 6: ("<f", 4), 7: ("<?", 1),
    10: ("<Q", 8), 11: ("<q", 8), 12: ("<d", 8),
}
GGML_TYPE_SIZES = {
    0: ("F32", 1, 4), 1: ("F16", 1, 2), 2: ("Q4_0", 32, 18),
    3: ("Q4_1", 32, 20), 6: ("Q5_0", 32, 22), 7: ("Q5_1", 32, 24),
    8: ("Q8_0", 32, 34), 9: ("Q8_1", 32, 40),
    10: ("Q2_K", 256, 84), 11: ("Q3_K", 256, 110), 12: ("Q4_K", 256, 144),
    13: ("Q5_K", 256, 176), 14: ("Q6_K", 256, 210), 15: ("Q8_K", 256, 292),
    16: ("IQ2_XXS", 256, 66), 17: ("IQ2_XS", 256, 74),
    18: ("IQ3_XXS", 256, 98), 19: ("IQ1_S", 256, 50),
    20: ("IQ4_NL", 32, 18), 21: ("IQ3_S", 256, 110),
    22: ("IQ2_S", 256, 82), 23: ("IQ4_XS", 256, 136),
    24: ("I8", 1, 1), 25: ("I16", 1, 2), 26: ("I32", 1, 4),
    27: ("I64", 1, 8), 28: ("F64", 1, 8), 29: ("IQ1_M", 256, 56),
    30: ("BF16", 1, 2),
}

_CONTENT_RANGE_RE = re.compile(r"^bytes ([0-9]+)-([0-9]+)/([0-9]+|\*)$")


class WbRangeError(AssertionError):
    """A range, index, decode, or archive contract was violated."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _safe_name(raw: str) -> str:
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", raw).strip("._")
    if not name:
        raise WbRangeError("empty safe name")
    return name[:120]


def _is_loopback_host(hostname: str | None) -> bool:
    if hostname is None:
        return False
    normalized = hostname.rstrip(".").lower()
    if normalized == "localhost":
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _range_counters() -> dict:
    return {
        "read_calls": 0,
        "cache_hits": 0,
        "cache_body_bytes_read": 0,
        "http_requests_attempted": 0,
        "http_requests_succeeded": 0,
        "http_body_bytes_read": 0,
    }


class RangeReader:
    """HTTP Range reader with a content-addressed local chunk cache."""

    def __init__(self, url: str, cache_dir: Path, *, limit: int = DEFAULT_LIMIT_BYTES,
                 use_cache: bool = True, stats: dict | None = None,
                 checkpoint_every: int = 1):
        parsed = urllib.parse.urlsplit(url)
        if parsed.username or parsed.password or not parsed.hostname:
            raise WbRangeError("remote URL must not contain credentials and must have a host")
        if parsed.scheme == "https":
            pass
        elif parsed.scheme == "http" and _is_loopback_host(parsed.hostname):
            pass
        else:
            raise WbRangeError("url must be https (or loopback http for rehearsal)")
        self.url = url
        self.cache_dir = Path(cache_dir)
        self.limit = int(limit)
        self.use_cache = use_cache
        self.checkpoint_every = int(checkpoint_every)
        if self.checkpoint_every < 1:
            raise WbRangeError("manifest checkpoint interval must be positive")
        self._pending_manifest_ranges = 0
        self.stats = stats if stats is not None else {}
        for key, value in _range_counters().items():
            self.stats.setdefault(key, value)
        self.chunks_dir = self.cache_dir / "chunks"
        self.chunks_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.cache_dir / "cache_manifest.json"
        self.manifest = self._load_manifest()
        self._opener = urllib.request.build_opener(_NoRedirectHandler())

    def _load_manifest(self) -> dict:
        if self.manifest_path.is_file():
            with self.manifest_path.open(encoding="utf-8") as handle:
                value = json.load(handle)
            if isinstance(value, dict) and value.get("schema_version") == SCHEMA_VERSION:
                return value
        return {"schema_version": SCHEMA_VERSION, "entries": {}}

    def _save_manifest(self) -> None:
        # Each checkpoint encodes the complete manifest; keep encoding compact.
        encoded = json.dumps(self.manifest, ensure_ascii=False,
                             separators=(",", ":"), sort_keys=True) + "\n"
        # Finish an owned sibling file before replacing the last usable manifest.
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                    mode="w", encoding="utf-8", newline="\n",
                    dir=self.manifest_path.parent,
                    prefix=".%s." % self.manifest_path.name, suffix=".tmp",
                    delete=False) as handle:
                temporary_path = Path(handle.name)
                handle.write(encoded)
            temporary_path.replace(self.manifest_path)
            temporary_path = None
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def flush_manifest(self) -> None:
        """Persist fetched ranges that have not reached their checkpoint yet."""
        if self._pending_manifest_ranges:
            self._save_manifest()
            self._pending_manifest_ranges = 0

    def _cache_key(self, offset: int, length: int) -> str:
        return hashlib.sha1(
            ("%s|%d|%d" % (self.url, offset, length)).encode("utf-8")
        ).hexdigest()

    def read(self, offset: int, length: int) -> bytes:
        if offset < 0 or length <= 0:
            raise WbRangeError("range must be offset >= 0, length > 0")
        if length > self.limit:
            raise WbRangeError(
                "range length %d exceeds limit %d; raise the limit deliberately"
                % (length, self.limit)
            )
        self.stats["read_calls"] += 1
        key = self._cache_key(offset, length)
        entry = self.manifest["entries"].get(key)
        if self.use_cache and entry and entry.get("transport_contract") == RANGE_CONTRACT_VERSION:
            chunk_path = self.chunks_dir / entry["file"]
            if chunk_path.is_file():
                data = chunk_path.read_bytes()
                self.stats["cache_body_bytes_read"] += len(data)
                if _sha256(data) == entry["sha256"] and len(data) == length:
                    self.stats["cache_hits"] += 1
                    return data
        data = self._fetch(offset, length)
        digest = _sha256(data)
        file_name = digest + ".bin"
        (self.chunks_dir / file_name).write_bytes(data)
        self.manifest["entries"][key] = {
            "url": self.url,
            "offset": offset,
            "length": length,
            "sha256": digest,
            "file": file_name,
            "transport_contract": RANGE_CONTRACT_VERSION,
            "fetched_utc": _utc_now(),
        }
        self._pending_manifest_ranges += 1
        if self._pending_manifest_ranges >= self.checkpoint_every:
            self.flush_manifest()
        return data

    def _strict_range(self, offset: int, length: int, *, timeout: int) -> tuple[bytes, int | None]:
        end = offset + length - 1
        request = urllib.request.Request(
            self.url,
            headers={
                "Range": "bytes=%d-%d" % (offset, end),
                "User-Agent": USER_AGENT,
                "Accept-Encoding": "identity",
            },
        )
        self.stats["http_requests_attempted"] += 1
        try:
            with self._opener.open(request, timeout=timeout) as response:
                status = getattr(response, "status", None)
                if status is None:
                    status = response.getcode()
                if status != 206:
                    raise WbRangeError("remote range status %s; expected 206" % status)
                final_url = response.geturl()
                if final_url != self.url:
                    raise WbRangeError("remote redirects are not allowed")
                final = urllib.parse.urlsplit(final_url)
                if final.scheme == "http" and not _is_loopback_host(final.hostname):
                    raise WbRangeError("remote range response downgraded to non-loopback http")
                if final.scheme not in ("http", "https"):
                    raise WbRangeError("remote range response used unsupported scheme")
                content_encoding = str(response.headers.get("Content-Encoding") or "").strip().lower()
                if content_encoding not in ("", "identity"):
                    raise WbRangeError(
                        "remote range Content-Encoding %r; expected identity" % content_encoding
                    )
                content_range = str(response.headers.get("Content-Range") or "")
                match = _CONTENT_RANGE_RE.fullmatch(content_range)
                if match is None:
                    raise WbRangeError("remote range missing or malformed Content-Range")
                got_start = int(match.group(1))
                got_end = int(match.group(2))
                if (got_start, got_end) != (offset, end):
                    raise WbRangeError(
                        "remote Content-Range interval %d-%d; expected %d-%d"
                        % (got_start, got_end, offset, end)
                    )
                total_text = match.group(3)
                total = None if total_text == "*" else int(total_text)
                if total is not None and total <= got_end:
                    raise WbRangeError("remote Content-Range total is not larger than its end")
                # One extra byte detects oversized bodies without consuming the
                # complete response when its framing contradicts Content-Range.
                try:
                    data = response.read(length + 1)
                except Exception as exc:
                    partial = getattr(exc, "partial", None)
                    if isinstance(partial, (bytes, bytearray)):
                        self.stats["http_body_bytes_read"] += len(partial)
                    raise
                self.stats["http_body_bytes_read"] += len(data)
        except WbRangeError:
            raise
        except urllib.error.HTTPError as exc:
            raise WbRangeError(
                "HTTP %s on range %d+%d" % (exc.code, offset, length)
            ) from exc
        except urllib.error.URLError as exc:
            raise WbRangeError("fetch failed: %s" % exc.reason) from exc
        except OSError as exc:
            raise WbRangeError("fetch failed: %s" % exc) from exc
        if len(data) != length:
            raise WbRangeError(
                "remote range body length mismatch: wanted %d bytes, got %d"
                % (length, len(data))
            )
        self.stats["http_requests_succeeded"] += 1
        return data, total

    def _fetch(self, offset: int, length: int) -> bytes:
        data, _ = self._strict_range(offset, length, timeout=120)
        return data

    def remote_size(self) -> int:
        return self._fetch_raw(0, 1)

    def _fetch_raw(self, offset: int, length: int) -> int:
        _, total = self._strict_range(offset, length, timeout=60)
        if total is None:
            raise WbRangeError("server did not report total size")
        return total


def hf_file_list(repo: str, revision: str = "main") -> list[dict]:
    if not re.fullmatch(r"[A-Za-z0-9._-]+/[A-Za-z0-9._-]+", repo):
        raise WbRangeError("repo must look like owner/name")
    request = urllib.request.Request(
        HF_API.format(repo=repo), headers={"User-Agent": USER_AGENT}
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.loads(response.read().decode("utf-8"))
    siblings = payload.get("siblings")
    if not isinstance(siblings, list):
        raise WbRangeError("hub returned no file list")
    files = []
    for item in siblings:
        name = item.get("rfilename")
        if isinstance(name, str) and name:
            files.append({"name": name, "size": item.get("size")})
    files.sort(key=lambda entry: entry["name"])
    return files


def parse_safetensors_index(reader: RangeReader, file_name: str) -> dict:
    prefix = reader.read(0, 8)
    (header_len,) = struct.unpack("<Q", prefix)
    if header_len <= 0 or header_len > 512 * 1024 * 1024:
        raise WbRangeError("implausible safetensors header length %d" % header_len)
    header = json.loads(reader.read(8, header_len).decode("utf-8"))
    if not isinstance(header, dict) or not header:
        raise WbRangeError("safetensors header must be a nonempty object")
    data_base = 8 + header_len
    tensors = {}
    metadata = header.get("__metadata__", {})
    for name, info in sorted(header.items()):
        if name == "__metadata__":
            continue
        if set(info) < {"dtype", "shape", "data_offsets"}:
            raise WbRangeError("tensor %s missing required fields" % name)
        dtype = info["dtype"]
        if dtype not in SAFETENSORS_DTYPES:
            raise WbRangeError("tensor %s has unsupported dtype %s" % (name, dtype))
        begin, end = info["data_offsets"]
        if begin < 0 or end < begin:
            raise WbRangeError("tensor %s has bad data offsets" % name)
        tensors[name] = {
            "dtype": dtype,
            "shape": [int(dim) for dim in info["shape"]],
            "begin": data_base + begin,
            "end": data_base + end,
            "bytes": end - begin,
        }
    return {
        "format": "safetensors",
        "file": file_name,
        "data_base": data_base,
        "metadata": metadata if isinstance(metadata, dict) else {},
        "tensors": tensors,
    }


class _GgufCursor:
    def __init__(self, reader: RangeReader):
        self.reader = reader
        self.pos = 0

    def take(self, length: int) -> bytes:
        data = self.reader.read(self.pos, length)
        self.pos += length
        return data

    def unpack(self, fmt: str):
        size = struct.calcsize(fmt)
        return struct.unpack(fmt, self.take(size))

    def unpack_group(self, *formats: str):
        grouped = "<" + "".join(fmt[1:] for fmt in formats)
        if struct.calcsize(grouped) <= self.reader.limit:
            # Reuse complete split-field caches from earlier parsers. Each
            # ordinary read still checks its cached chunk's length and digest.
            cached = self.reader.use_cache
            offset = self.pos
            for fmt in formats:
                if not cached:
                    break
                size = struct.calcsize(fmt)
                entry = self.reader.manifest["entries"].get(
                    self.reader._cache_key(offset, size))
                cached = bool(entry and entry.get("transport_contract") == RANGE_CONTRACT_VERSION)
                offset += size
            if not cached:
                return self.unpack(grouped)
        return tuple(value for fmt in formats for value in self.unpack(fmt))

    def string(self) -> str:
        (length,) = self.unpack("<Q")
        if length > 16 * 1024 * 1024:
            raise WbRangeError("implausible gguf string length")
        return self.take(length).decode("utf-8")

    def string_with_u32(self) -> tuple[str, int]:
        (length,) = self.unpack("<Q")
        if length > 16 * 1024 * 1024:
            raise WbRangeError("implausible gguf string length")
        if not length:
            # Preserve string()'s existing zero-length read failure.
            self.take(length)
        # The name body and its following type/rank have a known exact extent.
        raw, value = self.unpack_group("<%ds" % length, "<I")
        return raw.decode("utf-8"), value


def _gguf_metadata_value(cursor: _GgufCursor, value_type: int):
    if value_type in GGUF_VALUE_TYPES:
        fmt, _ = GGUF_VALUE_TYPES[value_type]
        return cursor.unpack(fmt)[0]
    if value_type == 8:
        return cursor.string()
    if value_type == 9:
        element_type, count = cursor.unpack_group("<I", "<Q")
        if count > 1_000_000:
            raise WbRangeError("implausible gguf array length")
        if element_type == 8:
            if not count:
                return []
            values = []
            (length,) = cursor.unpack("<Q")
            for index in range(count):
                if length > 16 * 1024 * 1024:
                    raise WbRangeError("implausible gguf string length")
                if index + 1 < count:
                    # The next length field is inside this known string array.
                    # Pair it with this body without reading beyond metadata.
                    if length:
                        raw, next_length = cursor.unpack_group("<%ds" % length, "<Q")
                    else:
                        raw = b""
                        (next_length,) = cursor.unpack("<Q")
                    values.append(raw.decode("utf-8"))
                    length = next_length
                else:
                    raw = cursor.take(length) if length else b""
                    values.append(raw.decode("utf-8"))
            return values
        if element_type not in GGUF_VALUE_TYPES:
            raise WbRangeError("unsupported gguf array element type %d" % element_type)
        fmt, size = GGUF_VALUE_TYPES[element_type]
        raw = cursor.take(size * count)
        return list(struct.unpack("<%d%s" % (count, fmt[1:]), raw))
    raise WbRangeError("unsupported gguf metadata type %d" % value_type)


def parse_gguf_index(reader: RangeReader, file_name: str) -> dict:
    cursor = _GgufCursor(reader)
    magic = cursor.take(4)
    if magic != b"GGUF":
        raise WbRangeError("not a gguf file")
    (version,) = cursor.unpack("<I")
    if version not in (2, 3):
        raise WbRangeError("unsupported gguf version %d" % version)
    tensor_count, kv_count = cursor.unpack_group("<Q", "<Q")
    if tensor_count > 10_000_000 or kv_count > 1_000_000:
        raise WbRangeError("implausible gguf counts")
    metadata = {}
    for _ in range(kv_count):
        key, value_type = cursor.string_with_u32()
        metadata[key] = _gguf_metadata_value(cursor, value_type)
    alignment = metadata.get("general.alignment", 32)
    if not isinstance(alignment, int) or alignment <= 0 or alignment > 4096:
        alignment = 32
    tensors = {}
    for _ in range(tensor_count):
        name, n_dims = cursor.string_with_u32()
        if n_dims > 8:
            raise WbRangeError("implausible gguf tensor rank")
        # These fields are contiguous and their complete extent is now known.
        formats = ("<%dQ" % n_dims, "<I", "<Q") if n_dims else ("<I", "<Q")
        fields = cursor.unpack_group(*formats)
        dims = list(fields[:-2])
        type_id, rel_offset = fields[-2:]
        elements = 1
        for dim in dims:
            elements *= dim
        type_name, block, block_bytes = GGML_TYPE_SIZES.get(
            type_id, ("TYPE_%d" % type_id, 0, 0)
        )
        byte_size = None
        if block:
            if elements % block:
                raise WbRangeError("tensor %s not divisible by block" % name)
            byte_size = elements // block * block_bytes
        tensors[name] = {
            "dtype": type_name,
            "shape": dims,
            "rel_offset": rel_offset,
            "bytes": byte_size,
        }
    data_base = (cursor.pos + alignment - 1) // alignment * alignment
    for name, info in tensors.items():
        info["begin"] = data_base + info["rel_offset"]
        info["end"] = info["begin"] + info["bytes"] if info["bytes"] is not None else None
    return {
        "format": "gguf",
        "file": file_name,
        "version": version,
        "alignment": alignment,
        "data_base": data_base,
        "metadata": metadata,
        "tensors": tensors,
    }


def build_index(repo_or_url: str, cache_dir: Path, *, revision: str = "main",
                limit: int = DEFAULT_LIMIT_BYTES,
                name_filter: str | None = None, stats: dict | None = None) -> dict:
    if stats is not None:
        stats.update(_range_counters())
        stats["files_indexed"] = 0
    started = _utc_now()
    sources = []
    if repo_or_url.startswith("https://") or repo_or_url.startswith("http://"):
        files = [{"name": PurePosixPath(repo_or_url.split("?")[0]).name,
                  "size": None, "url": repo_or_url}]
    else:
        files = []
        for entry in hf_file_list(repo_or_url, revision):
            name = entry["name"]
            if name.endswith((".safetensors", ".gguf")):
                files.append({
                    "name": name,
                    "size": entry.get("size"),
                    "url": HF_RESOLVE.format(repo=repo_or_url, rev=revision, name=name),
                })
        if not files:
            raise WbRangeError("no safetensors or gguf files in repo")
    pattern = re.compile(name_filter) if name_filter else None
    total_tensor_bytes = 0
    for file_entry in files:
        if pattern and not pattern.search(file_entry["name"]):
            continue
        reader = RangeReader(file_entry["url"], cache_dir, limit=limit, stats=stats,
                             checkpoint_every=64)
        try:
            if file_entry["name"].endswith(".safetensors"):
                parsed = parse_safetensors_index(reader, file_entry["name"])
            else:
                parsed = parse_gguf_index(reader, file_entry["name"])
        except BaseException:
            try:
                reader.flush_manifest()
            except Exception:
                # Keep the parser/transport error if cache publication also fails.
                pass
            raise
        reader.flush_manifest()
        parsed["url"] = file_entry["url"]
        parsed["declared_size"] = file_entry.get("size")
        total_tensor_bytes += sum(t["bytes"] or 0 for t in parsed["tensors"].values())
        sources.append(parsed)
        if stats is not None:
            stats["files_indexed"] += 1
    if not sources:
        raise WbRangeError("name filter excluded every weight file")
    tensor_count = sum(len(source["tensors"]) for source in sources)
    return {
        "schema_version": SCHEMA_VERSION,
        "target": repo_or_url,
        "revision": revision,
        "built_utc": started,
        "file_count": len(sources),
        "tensor_count": tensor_count,
        "tensor_bytes": total_tensor_bytes,
        "sources": sources,
    }


def find_tensor(index: dict, tensor_name: str) -> tuple[dict, dict]:
    matches = []
    for source in index["sources"]:
        tensors = source["tensors"]
        if tensor_name in tensors:
            return source, tensors[tensor_name]
        matches.extend(
            name for name in tensors if tensor_name.lower() in name.lower()
        )
    if len(matches) == 1:
        for source in index["sources"]:
            if matches[0] in source["tensors"]:
                return source, source["tensors"][matches[0]]
    sample = sorted(matches)[:12]
    raise WbRangeError(
        "tensor %r not found; %d partial matches: %s"
        % (tensor_name, len(matches), ", ".join(sample) or "none")
    )


def decode_values(dtype: str, data: bytes, count: int | None = None) -> list[float]:
    if dtype == "BF16":
        if len(data) % 2:
            raise WbRangeError("bf16 payload has odd length")
        # Place each little-endian BF16 word in the upper half of float32.
        raw = bytearray(len(data) * 2)
        raw[2::4] = data[0::2]
        raw[3::4] = data[1::2]
        values = list(struct.unpack("<%df" % (len(data) // 2), raw))
    elif dtype == "F8_E4M3":
        values = [_f8_decode(byte, 4, 3) for byte in data]
    elif dtype == "F8_E5M2":
        values = [_f8_decode(byte, 5, 2) for byte in data]
    elif dtype == "F8_E8M0":
        values = [E8M0_TABLE[byte] for byte in data]
    elif dtype == "F4":
        values = []
        for index in range(len(data) * 2):
            byte = data[index // 2]
            nibble = byte & 0x0F if index % 2 == 0 else (byte >> 4) & 0x0F
            sign = -1.0 if nibble & 0x08 else 1.0
            values.append(sign * E2M1_TABLE[nibble & 0x07])
    else:
        entry = SAFETENSORS_DTYPES.get(dtype)
        if entry is None or entry[0] is None:
            raise WbRangeError("no decoder for dtype %s" % dtype)
        fmt, size = entry
        if len(data) % size:
            raise WbRangeError("payload length not divisible by element size")
        unpack_format = "<%d%s" % (len(data) // size, fmt[1:])
        if dtype in ("F16", "F32", "F64"):
            # struct already returns Python floats for native float formats.
            values = list(struct.unpack(unpack_format, data))
        else:
            values = [float(v) for v in struct.unpack(unpack_format, data)]
    if count is not None:
        values = values[:count]
    return values


def _f8_decode(byte: int, exp_bits: int, man_bits: int) -> float:
    sign = -1.0 if byte & 0x80 else 1.0
    exponent = (byte >> man_bits) & ((1 << exp_bits) - 1)
    mantissa = byte & ((1 << man_bits) - 1)
    bias = (1 << (exp_bits - 1)) - 1
    if exponent == 0:
        return sign * mantissa * (2.0 ** (1 - bias - man_bits))
    if exponent == (1 << exp_bits) - 1:
        return math.nan
    return sign * (1.0 + mantissa / (1 << man_bits)) * (2.0 ** (exponent - bias))


def decode_mxfp4(packed: bytes, scales: bytes, *, block: int = 32) -> list[float]:
    if block <= 0:
        raise WbRangeError("mxfp4 block must be positive")
    values = []
    elements_per_byte = 2
    total = len(packed) * elements_per_byte
    expected_scales = (total + block - 1) // block
    if len(scales) < expected_scales:
        raise WbRangeError(
            "mxfp4 scales short: need %d, have %d" % (expected_scales, len(scales))
        )
    # A block shares one scale, and a nibble has only sixteen possible values.
    # Reuse immutable decoded floats instead of repeating arithmetic per weight.
    tables = {}
    for group in range(expected_scales):
        scale_byte = scales[group]
        table = tables.get(scale_byte)
        if table is None:
            scale = 2.0 ** (scale_byte - 127)
            table = tuple(
                (-1.0 if nibble & 0x08 else 1.0) * E2M1_TABLE[nibble & 0x07] * scale
                for nibble in range(16)
            )
            tables[scale_byte] = table
        start = group * block
        stop = min(start + block, total)
        if start % 2:
            values.append(table[packed[start // 2] >> 4])
            start += 1
        for byte in packed[start // 2:stop // 2]:
            values.append(table[byte & 0x0F])
            values.append(table[byte >> 4])
        if stop % 2:
            values.append(table[packed[stop // 2] & 0x0F])
    return values


class Archive:
    """The archive of answers: every slice, axis, and verdict, hashed."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "blobs").mkdir(exist_ok=True)
        self.manifest_path = self.root / "manifest.json"
        if self.manifest_path.is_file():
            with self.manifest_path.open(encoding="utf-8") as handle:
                self.manifest = json.load(handle)
            if self.manifest.get("schema_version") != SCHEMA_VERSION:
                raise WbRangeError("archive manifest schema drift")
        else:
            self.manifest = {"schema_version": SCHEMA_VERSION, "entries": []}
            self._save()

    def _save(self) -> None:
        encoded = json.dumps(self.manifest, ensure_ascii=False, indent=1,
                             sort_keys=True) + "\n"
        self.manifest_path.write_text(encoded, encoding="utf-8", newline="\n")

    def put(self, kind: str, payload: bytes, record: dict) -> dict:
        digest = _sha256(payload)
        blob_name = "%s.bin" % digest
        (self.root / "blobs" / blob_name).write_bytes(payload)
        entry = {
            "id": "%s-%s" % (kind, digest[:16]),
            "kind": kind,
            "sha256": digest,
            "bytes": len(payload),
            "blob": "blobs/%s" % blob_name,
            "recorded_utc": _utc_now(),
        }
        entry.update(record)
        self.manifest["entries"] = [
            item for item in self.manifest["entries"] if item["id"] != entry["id"]
        ]
        self.manifest["entries"].append(entry)
        self._save()
        return entry

    def get(self, entry_id: str) -> dict:
        for entry in self.manifest["entries"]:
            if entry["id"] == entry_id:
                return entry
        raise WbRangeError("no archive entry %r" % entry_id)

    def read_blob(self, entry_id: str) -> bytes:
        entry = self.get(entry_id)
        data = (self.root / entry["blob"]).read_bytes()
        if _sha256(data) != entry["sha256"]:
            raise WbRangeError("archive blob hash drift for %s" % entry_id)
        return data


def slice_tensor(index: dict, archive: Archive, cache_dir: Path, tensor_name: str,
                 *, begin: int | None = None, end: int | None = None,
                 decode: bool = False, limit: int = DEFAULT_LIMIT_BYTES,
                 note: str = "") -> dict:
    source, tensor = find_tensor(index, tensor_name)
    if tensor["end"] is None or tensor["bytes"] is None:
        raise WbRangeError("tensor %s has unknown extent" % tensor_name)
    start = tensor["begin"] if begin is None else tensor["begin"] + begin
    stop = tensor["end"] if end is None else tensor["begin"] + end
    if start < tensor["begin"] or stop > tensor["end"] or stop <= start:
        raise WbRangeError("slice range outside tensor extent")
    reader = RangeReader(source["url"], cache_dir, limit=limit)
    payload = reader.read(start, stop - start)
    record = {
        "source_url": source["url"],
        "file": source["file"],
        "tensor": tensor_name,
        "dtype": tensor["dtype"],
        "shape": tensor["shape"],
        "range": [start, stop],
        "note": note,
    }
    entry = archive.put("slice", payload, record)
    result = {"status": "ARCHIVED", "entry": entry}
    if decode:
        values = decode_values(tensor["dtype"], payload)
        result["decoded"] = {
            "count": len(values),
            "min": min(values) if values else None,
            "max": max(values) if values else None,
            "mean": (sum(values) / len(values)) if values else None,
            "head": values[:8],
        }
    return result


def verify_ranges(local_path: Path, remote_url: str, cache_dir: Path, *,
                  samples: int = 16, span: int = 4096, seed: int = 1337,
                  limit: int = DEFAULT_LIMIT_BYTES) -> dict:
    local_path = Path(local_path)
    if not local_path.is_file():
        raise WbRangeError("local file not found: %s" % local_path)
    local_size = local_path.stat().st_size
    reader = RangeReader(remote_url, cache_dir, limit=limit, use_cache=False)
    remote_size = reader.remote_size()
    if samples <= 0 or span <= 0:
        raise WbRangeError("samples and span must be positive")
    rng = random.Random(seed)
    results = []
    compared = 0
    with local_path.open("rb") as handle:
        for _ in range(samples):
            ceiling = min(local_size, remote_size) - span
            if ceiling < 0:
                raise WbRangeError("span larger than file")
            offset = rng.randint(0, ceiling)
            handle.seek(offset)
            local_bytes = handle.read(span)
            remote_bytes = reader.read(offset, span)
            match = local_bytes == remote_bytes
            compared += span
            results.append({
                "offset": offset,
                "span": span,
                "local_sha256": _sha256(local_bytes),
                "remote_sha256": _sha256(remote_bytes),
                "match": match,
            })
    matches = sum(1 for item in results if item["match"])
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "MATCH" if matches == samples else "DRIFT",
        "local": str(local_path),
        "remote": remote_url,
        "local_size": local_size,
        "remote_size": remote_size,
        "size_agree": local_size == remote_size,
        "samples": samples,
        "matched": matches,
        "bytes_compared": compared,
        "seed": seed,
        "results": results,
    }


def _embedding_row(source: dict, tensor: dict, row: int, cache_dir: Path,
                   limit: int, *, reader: RangeReader | None = None) -> list[float]:
    dtype = tensor["dtype"]
    if dtype not in ("F32", "F16", "F64", "BF16", "F8_E4M3", "F8_E5M2"):
        raise WbRangeError("axis needs a float dtype, tensor is %s" % dtype)
    shape = tensor["shape"]
    if len(shape) != 2:
        raise WbRangeError("embedding tensor must be 2-D, got %s" % shape)
    rows, width = shape
    if row < 0 or row >= rows:
        raise WbRangeError("row %d outside [0, %d)" % (row, rows))
    elem = SAFETENSORS_DTYPES[dtype][1]
    offset = tensor["begin"] + row * width * elem
    if reader is None:
        reader = RangeReader(source["url"], cache_dir, limit=limit)
    data = reader.read(offset, width * elem)
    return decode_values(dtype, data)


def cut_axis(index: dict, archive: Archive, cache_dir: Path, tensor_name: str,
             pairs: list[tuple[int, int]], *, limit: int = DEFAULT_LIMIT_BYTES,
             note: str = "") -> dict:
    if not pairs:
        raise WbRangeError("axis needs at least one row pair")
    source, tensor = find_tensor(index, tensor_name)
    reader = RangeReader(source["url"], cache_dir, limit=limit)
    accum = None
    rows_used = []
    for positive, negative in pairs:
        pos = _embedding_row(source, tensor, positive, cache_dir, limit, reader=reader)
        neg = _embedding_row(source, tensor, negative, cache_dir, limit, reader=reader)
        diff = [p - n for p, n in zip(pos, neg)]
        accum = diff if accum is None else [a + d for a, d in zip(accum, diff)]
        rows_used.append([positive, negative])
    count = float(len(pairs))
    axis = [value / count for value in accum]
    norm = math.sqrt(sum(value * value for value in axis))
    if norm == 0.0:
        raise WbRangeError("axis vector is zero")
    axis = [value / norm for value in axis]
    payload = struct.pack("<%df" % len(axis), *axis)
    record = {
        "tensor": tensor_name,
        "dtype": tensor["dtype"],
        "pairs": rows_used,
        "dimensions": len(axis),
        "note": note,
    }
    entry = archive.put("axis", payload, record)
    return {"status": "ARCHIVED", "entry": entry, "dimensions": len(axis)}


def score_rows(index: dict, archive: Archive, cache_dir: Path, tensor_name: str,
               axis_id: str, rows: list[int], *,
               limit: int = DEFAULT_LIMIT_BYTES) -> dict:
    source, tensor = find_tensor(index, tensor_name)
    axis_data = archive.read_blob(axis_id)
    axis_entry = archive.get(axis_id)
    width = len(axis_data) // 4
    axis = struct.unpack("<%df" % width, axis_data)
    if tensor["shape"][1] != width:
        raise WbRangeError("axis width %d != tensor width %d"
                           % (width, tensor["shape"][1]))
    scores = []
    reader = RangeReader(source["url"], cache_dir, limit=limit) if rows else None
    for row in rows:
        values = _embedding_row(source, tensor, row, cache_dir, limit, reader=reader)
        norm = math.sqrt(sum(v * v for v in values))
        dot = sum(a * v for a, v in zip(axis, values))
        scores.append({"row": row, "cosine": (dot / norm) if norm else 0.0})
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "SCORED",
        "tensor": tensor_name,
        "axis": axis_id,
        "axis_note": axis_entry.get("note", ""),
        "scores": scores,
    }


def load_index(path: Path) -> dict:
    with Path(path).open(encoding="utf-8") as handle:
        index = json.load(handle)
    if index.get("schema_version") != SCHEMA_VERSION:
        raise WbRangeError("index schema drift")
    return index


# ------------------------------------------- metric wiring (host/wb_metrics.py)

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wb_metrics as metrics


def _tensor_row_layout(tensor: dict, fmt: str = "gguf") -> tuple[int, int]:
    """(rows, width). GGUF lists dims fastest-first: (product(shape[1:]),
    shape[0]). Safetensors lists dims numpy-order (slowest-first):
    (product(shape[:-1]), shape[-1])."""
    shape = tensor["shape"]
    if len(shape) < 2:
        raise WbRangeError("tensor must be >= 2-D for row ops")
    if fmt == "safetensors":
        width = shape[-1]
        rows = 1
        for dim in shape[:-1]:
            rows *= dim
        return rows, width
    width = shape[0]
    rows = 1
    for dim in shape[1:]:
        rows *= dim
    return rows, width


def fetch_rows(index: dict, cache_dir: Path, tensor_name: str,
               row_idxs: list[int], *, limit: int = DEFAULT_LIMIT_BYTES,
               raw: bool = False) -> list:
    """Fetch and decode (or raw) rows of a >= 2-D tensor by address."""
    source, tensor = find_tensor(index, tensor_name)
    dtype = tensor["dtype"]
    entry = SAFETENSORS_DTYPES.get(dtype)
    if entry is None:
        raise WbRangeError("row ops need a known dtype, got %s" % dtype)
    _, elem = entry
    rows, width = _tensor_row_layout(tensor, source["format"])
    reader = RangeReader(source["url"], cache_dir, limit=limit)
    row_bytes = width * elem
    # Keep invalid/oversized row reads on read()'s existing validation path.
    group_rows = (max(1, min(reader.limit, 1024 * 1024) // row_bytes)
                  if row_bytes > 0 else 1)
    out = []
    position = 0
    while position < len(row_idxs):
        i = row_idxs[position]
        if i < 0 or i >= rows:
            raise WbRangeError("row %d outside [0, %d)" % (i, rows))
        offset = tensor["begin"] + i * row_bytes
        end = position + 1
        # Existing row entries always pass through read(), including its hash,
        # length and transport-contract checks. Do not reorder or dedupe rows.
        if reader._cache_key(offset, row_bytes) not in reader.manifest["entries"]:
            while end < len(row_idxs) and end - position < group_rows:
                row = row_idxs[end]
                if row != i + end - position or row >= rows:
                    break
                row_offset = tensor["begin"] + row * row_bytes
                if reader._cache_key(row_offset, row_bytes) in reader.manifest["entries"]:
                    break
                end += 1
        count = end - position
        if count == 1:
            data = reader.read(offset, row_bytes)
            out.append(data if raw else decode_values(dtype, data))
        else:
            # Persist the validated group before seeding normal row entries.
            # Publish seeds together, so the same interrupted call can reuse
            # the original group instead of fetching a different remainder.
            data = reader.read(offset, count * row_bytes)
            group_entry = reader.manifest["entries"][
                reader._cache_key(offset, count * row_bytes)]
            for ordinal in range(count):
                row_data = data[ordinal * row_bytes:(ordinal + 1) * row_bytes]
                digest = _sha256(row_data)
                file_name = digest + ".bin"
                (reader.chunks_dir / file_name).write_bytes(row_data)
                row_offset = offset + ordinal * row_bytes
                reader.manifest["entries"][
                    reader._cache_key(row_offset, row_bytes)] = {
                        **group_entry, "offset": row_offset, "length": row_bytes,
                        "sha256": digest, "file": file_name,
                    }
                reader._pending_manifest_ranges += 1
                out.append(row_data if raw else decode_values(dtype, row_data))
            reader.flush_manifest()
        position = end
    return out


def fetch_span(index: dict, cache_dir: Path, tensor_name: str, begin: int,
               length: int, *, limit: int = DEFAULT_LIMIT_BYTES) -> bytes:
    source, tensor = find_tensor(index, tensor_name)
    if tensor["bytes"] is None:
        raise WbRangeError("tensor extent unknown")
    if begin < 0 or begin + length > tensor["bytes"]:
        raise WbRangeError("span outside tensor")
    reader = RangeReader(source["url"], cache_dir, limit=limit)
    return reader.read(tensor["begin"] + begin, length)


def load_vocab(index: dict, cache_dir: Path, *, limit: int = DEFAULT_LIMIT_BYTES) -> list:
    """Token strings for the indexed model: GGUF metadata, or the repo's
    tokenizer.json fetched once and cached (safetensors)."""
    for source in index["sources"]:
        if source["format"] == "gguf":
            tokens = source["metadata"].get("tokenizer.ggml.tokens")
            if isinstance(tokens, list) and tokens:
                return [str(t) for t in tokens]
    for source in index["sources"]:
        base = source["url"].rsplit("/", 1)[0]
        tok_url = base + "/tokenizer.json"
        reader = RangeReader(tok_url, cache_dir,
                             limit=max(limit, 128 * 1024 * 1024))
        try:
            size = reader.remote_size()
        except (WbRangeError, urllib.error.URLError):
            size = None
        if size:
            payload = json.loads(reader.read(0, size).decode("utf-8"))
            model = payload.get("model", {})
            vocab = model.get("vocab", {})
            added = payload.get("added_tokens", [])
            width = len(vocab) + len(added) + 16
            tokens = [""] * width
            for text, idx in vocab.items():
                if 0 <= idx < width:
                    tokens[idx] = text
            for item in added:
                if isinstance(item, dict) and 0 <= item.get("id", -1) < width:
                    tokens[item["id"]] = item.get("content", "")
            if any(tokens):
                return tokens
        # tiktoken fallback: "<base64 token> <rank>" per line; rank == token id
        tik_url = base + "/tiktoken.model"
        tik_reader = RangeReader(tik_url, cache_dir,
                                 limit=max(limit, 64 * 1024 * 1024))
        try:
            tik_size = tik_reader.remote_size()
        except (WbRangeError, urllib.error.URLError):
            continue
        raw = tik_reader.read(0, tik_size).decode("ascii")
        pairs = []
        for line in raw.splitlines():
            parts = line.split()
            if len(parts) == 2:
                try:
                    pairs.append((int(parts[1]),
                                  base64.b64decode(parts[0]).decode(
                                      "utf-8", errors="replace")))
                except (ValueError, binascii.Error):
                    continue
        if pairs:
            width = max(rank for rank, _ in pairs) + 1
            tokens = [""] * width
            for rank, text in pairs:
                tokens[rank] = text
            return tokens
    raise WbRangeError(
        "no vocabulary found (gguf metadata, tokenizer.json, tiktoken.model)")


def word_row_map(index: dict, cache_dir: Path, tensor_name: str, vocab: list,
                 words: list[str], *, limit: int = DEFAULT_LIMIT_BYTES) -> dict:
    """word -> decoded embedding row; tries surface, ▁-prefixed, capitalized."""
    forms_by_word = [
        (word, (word, "▁" + word, word.capitalize(),
                "▁" + word.capitalize(), " " + word))
        for word in words
    ]
    wanted = {form for _, forms in forms_by_word for form in forms if form}
    lookup = {}
    for i, token in enumerate(vocab):
        for form in (token, token.lstrip("▁"), token.replace("▁", " ").strip()):
            if form in wanted and form not in lookup:
                lookup[form] = i
    targets = {}
    for word, forms in forms_by_word:
        for form in forms:
            if form in lookup:
                targets[word] = lookup[form]
                break
    rows = {}
    if targets:
        uniq = sorted(set(targets.values()))
        fetched = fetch_rows(index, cache_dir, tensor_name, uniq, limit=limit)
        by_row = dict(zip(uniq, fetched))
        for word, idx in targets.items():
            rows[word] = by_row[idx]
    missing = [w for w in words if w not in targets]
    return {"rows": rows, "missing": missing, "token_ids": targets}


def embed_tensor_name(index: dict) -> str:
    for source in index["sources"]:
        for name in source["tensors"]:
            low = name.lower()
            if "embed" in low and "norm" not in low:
                return name
    # Preserve existing selections before trying the canonical GGUF spelling.
    for source in index["sources"]:
        if source.get("format") == "gguf":
            for name in source["tensors"]:
                if name.lower() == "token_embd.weight":
                    return name
    raise WbRangeError("no embedding tensor found in index")


def _ffn_names(index: dict, layer: int) -> dict:
    candidates = {
        "gate": ["blk.%d.ffn_gate.weight",
                 "language_model.model.layers.%d.mlp.gate_proj.weight",
                 "model.layers.%d.mlp.gate_proj.weight",
                 "layers.%d.mlp.gate_proj.weight"],
        "up": ["blk.%d.ffn_up.weight",
               "language_model.model.layers.%d.mlp.up_proj.weight",
               "model.layers.%d.mlp.up_proj.weight",
               "layers.%d.mlp.up_proj.weight"],
        "down": ["blk.%d.ffn_down.weight",
                 "language_model.model.layers.%d.mlp.down_proj.weight",
                 "model.layers.%d.mlp.down_proj.weight",
                 "layers.%d.mlp.down_proj.weight"],
    }
    out = {}
    for key, patterns in candidates.items():
        for pattern in patterns:
            name = pattern % layer
            try:
                find_tensor(index, name)
                out[key] = name
                break
            except WbRangeError:
                continue
        if key not in out:
            raise WbRangeError("no %s tensor found for layer %d" % (key, layer))
    return out


METRIC_OPS = ("recipe", "stats", "entropysweep", "magics", "experts",
              "circuitry", "layerscan", "direction", "anisotropy", "mechanism",
              "bits", "clean", "concept", "analogy", "analogybattery",
              "categorypurity", "neurons", "walk", "constellations", "order",
              "axispure")


def metric_op(op: str, index: dict, archive: Archive, cache_dir: Path,
              args: dict) -> dict:
    """Dispatch one metric op over ranged reads; archive the receipt."""
    limit = int(args.get("limit") or DEFAULT_LIMIT_BYTES)
    tensor = args.get("tensor") or ""
    sample = int(args.get("sample") or 256)
    seed = int(args.get("seed") or 7)

    if op == "recipe":
        tensors = {}
        for source in index["sources"]:
            tensors.update(source["tensors"])
        result = metrics.precision_recipe(tensors)
        result["tensor_count"] = len(tensors)

    elif op == "stats":
        if not tensor:
            raise WbRangeError("stats needs a tensor")
        source, t = find_tensor(index, tensor)
        if len(t["shape"]) < 2:
            # 1-D tensor (layernorm/bias): one row, whole-span stats
            raw = fetch_span(index, cache_dir, tensor, 0, t["bytes"],
                             limit=limit)
            decoded = [decode_values(t["dtype"], raw)]
            raw_rows = [raw]
        else:
            rows, width = _tensor_row_layout(t, source["format"])
            idxs = metrics.strided(rows, sample)
            decoded = fetch_rows(index, cache_dir, tensor, idxs, limit=limit)
            raw_rows = fetch_rows(index, cache_dir, tensor,
                                  metrics.strided(rows, min(sample, 256)),
                                  limit=limit, raw=True)
        flat = [v for row in decoded for v in row]
        result = metrics.tensor_stats(
            flat, block=256 if "K" in t["dtype"] else 32)
        result.update(metrics.row_norm_stats(decoded))
        result["entropy"] = metrics.entropy_scan([r[:384] for r in raw_rows])
        result["tensor"] = tensor
        result["dtype"] = t["dtype"]
        result["rows_sampled"] = len(decoded)

    elif op == "entropysweep":
        source, t = find_tensor(index, tensor)
        rows, width = _tensor_row_layout(t, source["format"])
        idxs = metrics.strided(rows, sample)
        raw_rows = fetch_rows(index, cache_dir, tensor, idxs, limit=limit,
                              raw=True)
        result = metrics.entropy_scan_mad([r[:512] for r in raw_rows])
        result["tensor"] = tensor
        result["rows_sampled"] = len(raw_rows)

    elif op == "magics":
        source, t = find_tensor(index, tensor)
        if t["bytes"] is None:
            raise WbRangeError("tensor extent unknown")
        chunk = min(int(args.get("chunk") or 4 * 1024 * 1024), limit)
        max_bytes = int(args.get("max_bytes") or chunk * 8)
        found = {"hits": 0, "tags": {}}
        scanned = 0
        while scanned < min(t["bytes"], max_bytes):
            length = min(chunk, t["bytes"] - scanned, max_bytes - scanned)
            if length <= 0:
                break
            data = fetch_span(index, cache_dir, tensor, scanned, length,
                              limit=limit)
            part = metrics.magic_scan(data, base_offset=t["begin"] + scanned)
            found["hits"] += part["hits"]
            for tag, info in part["tags"].items():
                entry = found["tags"].setdefault(tag, {"count": 0,
                                                       "offsets": []})
                entry["count"] += info["count"]
                entry["offsets"].extend(info["offsets"])
            scanned += length
        result = dict(found)
        result["tensor"] = tensor
        result["bytes_scanned"] = scanned

    elif op == "experts":
        source, t = find_tensor(index, tensor)
        shape = t["shape"]
        if len(shape) < 3:
            raise WbRangeError("expert health needs a >= 3-D (MoE) tensor")
        n_exp = shape[0] if source["format"] == "safetensors" else shape[-1]
        per_expert_rows = 1
        for dim in shape[1:-1]:
            per_expert_rows *= dim
        per_expert = {}
        take = metrics.strided(n_exp, min(sample, n_exp))
        for e in take:
            row_idxs = [e * per_expert_rows + r
                        for r in metrics.strided(per_expert_rows, 8)]
            decoded = fetch_rows(index, cache_dir, tensor, row_idxs,
                                 limit=limit)
            per_expert[e] = [v for row in decoded for v in row]
        result = metrics.expert_health(per_expert)
        result["tensor"] = tensor
        result["experts_sampled"] = len(take)

    elif op == "circuitry":
        layer = int(args.get("layer") or 0)
        units = int(args.get("units") or 512)
        band = int(args.get("band") or 1024)
        names = _ffn_names(index, layer)
        gs, gt = find_tensor(index, names["gate"])
        ds, dt = find_tensor(index, names["down"])
        n_ff = _tensor_row_layout(gt, gs["format"])[0]
        sel = metrics.strided(n_ff, units)
        gate_rows = fetch_rows(index, cache_dir, names["gate"], sel,
                               limit=limit)
        up_rows = fetch_rows(index, cache_dir, names["up"], sel, limit=limit)
        d_rows, d_width = _tensor_row_layout(dt, ds["format"])
        band = min(band, d_rows)
        band_rows = fetch_rows(index, cache_dir, names["down"],
                               list(range(band)), limit=limit)
        down_cols = [[band_rows[r][j] for r in range(band)] for j in sel]
        result = metrics.circuitry(gate_rows, up_rows, down_cols)
        result["logic"]["decode_orth"] = metrics.decoder_sharpness(
            gate_rows, sample=min(512, len(gate_rows)))["decode_orth"]
        result["logic"]["drain_conv"] = metrics.decoder_sharpness(
            down_cols, sample=min(512, len(down_cols)))["decode_orth"]
        result["mode"] = "subspace-drain" if band < d_rows else "full"
        result["drain_band_dims"] = band
        result["layer"] = layer
        result["units_sampled"] = len(sel)
        if band < d_rows:
            gate_band = [list(row[:band]) for row in gate_rows]
            result["latch_subspace"] = metrics.circuitry(
                gate_band, up_rows, down_cols)["logic"]

    elif op == "layerscan":
        role = args.get("role") or "ffn_down"
        per = {}
        for source in index["sources"]:
            for name, t in source["tensors"].items():
                layer = metrics.layer_of(name)
                if layer < 0 or metrics.role_of(name) != role:
                    continue
                try:
                    rows_n, width = _tensor_row_layout(t, source["format"])
                    idxs = metrics.strided(rows_n, 8)
                    decoded = fetch_rows(index, cache_dir, name, idxs,
                                         limit=limit)
                    flat = [v for row in decoded for v in row]
                    st = metrics.tensor_stats(flat)
                    per[layer] = {"std": st["std"], "mean": st["mean"],
                                  "absmax": max(abs(st["min"]),
                                                abs(st["max"])),
                                  "zero": st["sparsity"],
                                  "dtype": t["dtype"]}
                except WbRangeError:
                    continue
        result = metrics.depth_profile(per)
        result["role"] = role

    elif op == "direction":
        source, t = find_tensor(index, tensor)
        rows, width = _tensor_row_layout(t, source["format"])
        idxs = metrics.strided(rows, min(sample, 384))
        decoded = fetch_rows(index, cache_dir, tensor, idxs, limit=limit)
        result = {"tensor": tensor, "rows_sampled": len(decoded)}
        result.update(metrics.value_sanity(decoded))
        result["manifold"] = metrics.manifold_residual(
            decoded, k=int(args.get("k") or 8),
            sample=min(192, len(decoded)))

    elif op in ("anisotropy", "mechanism", "bits", "clean", "concept",
                "analogy", "analogybattery", "categorypurity", "neurons",
                "walk", "constellations", "order", "axispure"):
        result = _embed_op(op, index, cache_dir, args, limit, sample, seed)

    else:
        raise WbRangeError("unknown metric op %r" % op)

    receipt = archive.put(
        "metric",
        json.dumps(result, sort_keys=True, default=str).encode(),
        {"op": op, "tensor": tensor, "note": str(args.get("note") or "")})
    return {"status": "ARCHIVED", "op": op, "entry_id": receipt["id"],
            "result": result}


def _embed_op(op: str, index: dict, cache_dir: Path, args: dict,
              limit: int, sample: int, seed: int) -> dict:
    tensor = args.get("tensor") or embed_tensor_name(index)
    source, t = find_tensor(index, tensor)
    rows_total, width = _tensor_row_layout(t, source["format"])
    vocab_sample = int(args.get("vocab_sample") or 1200)
    idxs = metrics.strided(rows_total, vocab_sample)

    vocab = None

    def word_rows(words):
        nonlocal vocab
        if vocab is None:
            vocab = load_vocab(index, cache_dir, limit=limit)
        mapped = word_row_map(index, cache_dir, tensor, vocab, words,
                              limit=limit)
        return mapped["rows"], mapped["missing"]

    if op in ("anisotropy", "mechanism", "clean", "bits"):
        decoded = fetch_rows(index, cache_dir, tensor, idxs, limit=limit)
        ant_rows, miss_a = word_rows(
            [w for pair in metrics.ANTONYMS for w in pair])
        rand_rows, miss_r = word_rows(metrics.RANDOM_WORDS)
        ant_pairs = [(ant_rows[a], ant_rows[b]) for a, b in metrics.ANTONYMS
                     if a in ant_rows and b in ant_rows]
        rand_pairs = []
        words = [w for w in metrics.RANDOM_WORDS if w in rand_rows]
        for i in range(len(words)):
            for j in range(i + 1, len(words)):
                rand_pairs.append((rand_rows[words[i]], rand_rows[words[j]]))
        if op == "anisotropy":
            result = metrics.anisotropy(decoded, seed=seed)
            freq_rows, _ = word_rows(metrics.FREQ_LADDER)
            result["norm_by_frequency"] = metrics.norm_by_frequency(freq_rows)
        elif op == "mechanism":
            result = metrics.sign_cos_pearson(decoded, seed=seed)
            result["separation"] = metrics.sign_only_ratio(ant_pairs,
                                                           rand_pairs)
            result["rogue_dims"] = {
                k: v for k, v in metrics.rogue_dims(decoded).items()
                if k not in ("mean_vector", "per_dim_var")}
        elif op == "clean":
            result = metrics.cleanup_ab(ant_pairs, rand_pairs, decoded)
        else:
            probes = {}
            if "true" in ant_rows and "false" in ant_rows:
                probes["true/false"] = (ant_rows["true"], ant_rows["false"])
            if "love" in ant_rows and "hate" in ant_rows:
                probes["love/hate"] = (ant_rows["love"], ant_rows["hate"])
            result = {"curve": metrics.bitdepth_curve(ant_pairs, rand_pairs,
                                                      probes)}
        result["tensor"] = tensor
        result["vocab_rows_sampled"] = len(decoded)
        result["missing_words"] = sorted(set(miss_a + miss_r))
        return result

    if op == "concept":
        word = str(args.get("word") or "university")
        k = int(args.get("k") or 30)
        rows_map, missing = word_rows([word])
        if word not in rows_map:
            raise WbRangeError("%r is not an embeddable token" % word)
        decoded = fetch_rows(index, cache_dir, tensor, idxs, limit=limit)
        vocab_rows = {vocab[i]: decoded[p] for p, i in enumerate(idxs)
                      if i < len(vocab) and vocab[i]}
        result = metrics.concept_neighbors(rows_map[word], vocab_rows,
                                           k=k, query_word=word)
        result["tensor"] = tensor
        result["vocab_rows_scanned"] = len(vocab_rows)
        return result

    if op == "analogy":
        a, b, c = (str(args.get(x) or "") for x in ("a", "b", "c"))
        if not (a and b and c):
            raise WbRangeError("analogy needs a, b, c words")
        cands = [w.strip() for w in
                 str(args.get("candidates") or "").split(",") if w.strip()]
        rows_map, missing = word_rows([a, b, c] + cands)
        if any(w not in rows_map for w in (a, b, c)):
            raise WbRangeError("missing tokens: %s" % missing)
        cand_rows = {w: rows_map[w] for w in cands if w in rows_map}
        result = metrics.analogy(rows_map[a], rows_map[b], rows_map[c],
                                 cand_rows)
        result["missing"] = missing
        return result

    if op == "analogybattery":
        all_words = sorted({w for pairs in metrics.ANALOGY_CATS.values()
                            for pair in pairs for w in pair})
        rows_map, missing = word_rows(all_words)
        result = metrics.analogy_battery(rows_map)
        result["missing"] = missing
        return result

    if op == "categorypurity":
        all_words = sorted({w for ws in metrics.CATEGORIES.values()
                            for w in ws})
        rows_map, missing = word_rows(all_words)
        result = metrics.category_purity(rows_map)
        result["missing"] = missing
        return result

    if op == "neurons":
        layer = int(args.get("layer") or 0)
        kind = str(args.get("kind") or "down")
        names = _ffn_names(index, layer)
        n_tensor = names.get(kind) or names["down"]
        ns, nt = find_tensor(index, n_tensor)
        n_rows, n_width = _tensor_row_layout(nt, ns["format"])
        units = int(args.get("units") or 96)
        if n_tensor == names["down"]:
            if n_rows != width:
                raise WbRangeError("DOWN output width does not match token embeddings")
            sel = metrics.strided(n_width, units)
            dtype = nt["dtype"]
            entry = SAFETENSORS_DTYPES.get(dtype)
            if entry is None:
                raise WbRangeError("row ops need a known dtype, got %s" % dtype)
            elem = entry[1]
            reader = RangeReader(ns["url"], cache_dir, limit=limit)
            neuron_rows = [[] for _ in sel]
            # A DOWN neuron is a column. Decode one physical row at a time,
            # retaining only the sampled columns across embedding dimensions.
            for row_idx in range(n_rows):
                offset = nt["begin"] + row_idx * n_width * elem
                row = decode_values(dtype, reader.read(offset, n_width * elem))
                for neuron, column in zip(neuron_rows, sel):
                    neuron.append(row[column])
        else:
            if n_width != width:
                raise WbRangeError("FFN input width does not match token embeddings")
            sel = metrics.strided(n_rows, units)
            neuron_rows = fetch_rows(index, cache_dir, n_tensor, sel, limit=limit)
        decoded = fetch_rows(index, cache_dir, tensor, idxs, limit=limit)
        vocab = load_vocab(index, cache_dir, limit=limit)
        vocab_rows = {vocab[i]: decoded[p] for p, i in enumerate(idxs)
                      if i < len(vocab) and vocab[i]}
        result = metrics.neuron_cleanliness(neuron_rows, vocab_rows)
        for item in result["cleanest"]:
            item["neuron"] = sel[item["neuron"]]
        result["tensor"] = n_tensor
        result["vocab_rows_scanned"] = len(vocab_rows)
        return result

    if op in ("walk", "constellations", "order", "axispure"):
        words = [w.strip() for w in
                 str(args.get("words") or "").split(",") if w.strip()]
        if not words:
            raise WbRangeError("%s needs words" % op)
        rows_map, missing = word_rows(words)
        if op == "walk":
            start = str(args.get("word") or words[0])
            if start not in rows_map:
                raise WbRangeError("start word %r not embeddable" % start)
            result = metrics.semantic_walk(
                rows_map[start], rows_map,
                steps=int(args.get("steps") or 8), start_label=start)
        elif op == "constellations":
            result = metrics.constellations(
                rows_map, threshold=float(args.get("threshold") or 0.18))
        elif op == "order":
            truth = [w for w in words if w in rows_map]
            if len(truth) < 3:
                raise WbRangeError("order needs >= 3 embeddable words")
            lo, hi = rows_map[truth[0]], rows_map[truth[-1]]
            axis = metrics.unit([h - l for h, l in zip(hi, lo)])
            result = metrics.order_recovery(axis, rows_map, truth)
        else:
            pair_words = str(args.get("pairs") or "")
            pairs = []
            for item in pair_words.split(","):
                left, sep, right = item.strip().partition(":")
                if sep and left in rows_map and right in rows_map:
                    pairs.append((rows_map[left], rows_map[right]))
            if not pairs:
                raise WbRangeError("axispure needs pairs neg:pos,...")
            place = str(args.get("word") or "")
            built = metrics.axis_with_purity(
                pairs, place_row=rows_map.get(place))
            axis = built.pop("_axis")
            built["poles"] = metrics.pole_readout(axis, rows_map)
            result = built
        result["missing"] = missing
        return result

    raise WbRangeError("unhandled embed op %r" % op)


def write_json(path: Path, value: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(value, ensure_ascii=False, indent=1, sort_keys=False) + "\n"
    path.write_text(encoded, encoding="utf-8", newline="\n")


PANEL_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>WB-RANGE</title>
<style>
:root {
  --bg: #0d0f11; --panel: #15191d; --edge: #2c343c; --text: #b8c4ce;
  --dim: #6b7885; --amber: #e8a13a; --ok: #46c07a; --bad: #e05545;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  background: var(--bg); color: var(--text);
  font: 13px/1.45 Consolas, "Cascadia Mono", "Courier New", monospace;
  padding: 10px;
}
header {
  display: flex; align-items: center; gap: 14px;
  border: 1px solid var(--edge); background: var(--panel);
  padding: 8px 12px; margin-bottom: 10px;
}
header .title { font-weight: bold; letter-spacing: 2px; color: var(--text); }
header .sub { color: var(--dim); letter-spacing: 1px; }
.lamp {
  display: inline-block; width: 10px; height: 10px; border-radius: 50%;
  border: 1px solid var(--dim); margin-right: 6px; vertical-align: middle;
}
.lamp.on { background: var(--ok); border-color: var(--ok);
  box-shadow: 0 0 6px var(--ok); }
.lamp.warn { background: var(--amber); border-color: var(--amber);
  box-shadow: 0 0 6px var(--amber); }
.lamp.err { background: var(--bad); border-color: var(--bad);
  box-shadow: 0 0 6px var(--bad); }
.stat { color: var(--dim); } .stat b { color: var(--text); font-weight: normal; }
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
fieldset {
  border: 1px solid var(--edge); background: var(--panel); padding: 10px 12px;
}
legend {
  color: var(--amber); letter-spacing: 2px; font-size: 11px; padding: 0 6px;
}
label { display: block; color: var(--dim); margin: 8px 0 2px; font-size: 11px;
  letter-spacing: 1px; }
input, select {
  width: 100%; background: #0b0d0f; color: var(--text);
  border: 1px solid var(--edge); padding: 5px 7px; font: inherit;
}
input:focus { outline: 1px solid var(--amber); }
button {
  background: #1d2329; color: var(--text); border: 1px solid var(--edge);
  padding: 6px 14px; font: inherit; letter-spacing: 1px; cursor: pointer;
  margin-top: 10px;
}
button:hover { border-color: var(--amber); color: var(--amber); }
button:disabled { opacity: 0.4; cursor: default; }
button.primary { border-color: var(--amber); color: var(--amber); }
.row { display: flex; gap: 10px; } .row > div { flex: 1; }
.list {
  margin-top: 8px; max-height: 180px; overflow-y: auto;
  border: 1px solid var(--edge); background: #0b0d0f; padding: 4px;
}
.list div { padding: 2px 6px; cursor: pointer; white-space: nowrap;
  overflow: hidden; text-overflow: ellipsis; }
.list div:hover { background: #1d2329; color: var(--amber); }
.kv { color: var(--dim); font-size: 12px; margin-top: 6px; white-space: pre-wrap; }
.kv b { color: var(--text); font-weight: normal; }
#log {
  height: 160px; overflow-y: auto; background: #0b0d0f;
  border: 1px solid var(--edge); padding: 6px 8px; font-size: 12px;
}
#log .ok { color: var(--ok); } #log .err { color: var(--bad); }
#log .dim { color: var(--dim); }
.full { grid-column: 1 / -1; }
</style>
</head>
<body>
<header>
  <span class="title">WB-RANGE</span>
  <span class="sub">WHITE BOX REMOTE RANGE UNIT</span>
  <span class="stat"><span id="lamp-conn" class="lamp"></span>LINK</span>
  <span class="stat"><span id="lamp-index" class="lamp"></span>INDEX</span>
  <span class="stat">LIMIT <input id="limit" type="number" value="64" min="1"
    style="width:70px;display:inline-block"> MB</span>
  <span class="stat" id="clock"></span>
</header>
<div class="grid">

<fieldset>
  <legend>TARGET</legend>
  <label>REPO OR URL</label>
  <input id="repo" value="moonshotai/Kimi-K3">
  <label>REVISION</label>
  <input id="rev" value="main">
  <div class="row">
    <div><label>FILE FILTER (REGEX, OPTIONAL)</label>
    <input id="filter" placeholder="shard-0001|embed"></div>
    <div><label>&nbsp;</label>
    <button id="btn-index" class="primary">BUILD INDEX</button></div>
  </div>
  <div class="kv" id="index-kv">no index loaded</div>
</fieldset>

<fieldset>
  <legend>INDEX</legend>
  <label>FILTER TENSORS</label>
  <input id="tensor-filter" placeholder="embed / attn / expert">
  <div class="list" id="tensor-list"></div>
  <div class="kv" id="tensor-kv"></div>
</fieldset>

<fieldset>
  <legend>SLICE</legend>
  <label>TENSOR</label>
  <input id="slice-tensor">
  <div class="row">
    <div><label>BEGIN (REL BYTES, BLANK = 0)</label><input id="slice-begin"></div>
    <div><label>END (REL BYTES, BLANK = ALL)</label><input id="slice-end"></div>
  </div>
  <label>NOTE</label>
  <input id="slice-note" placeholder="question this slice answers">
  <button id="btn-slice" class="primary">FETCH + ARCHIVE</button>
  <button id="btn-decode">FETCH + DECODE</button>
  <div class="kv" id="slice-kv"></div>
</fieldset>

<fieldset>
  <legend>VERIFY</legend>
  <label>LOCAL FILE</label>
  <input id="verify-local" placeholder="C:\path\to\local.gguf">
  <label>REMOTE URL</label>
  <input id="verify-remote" placeholder="https://...resolve/main/file.gguf">
  <div class="row">
    <div><label>SAMPLES</label><input id="verify-samples" type="number" value="16"></div>
    <div><label>SPAN BYTES</label><input id="verify-span" type="number" value="4096"></div>
    <div><label>SEED</label><input id="verify-seed" type="number" value="1337"></div>
  </div>
  <button id="btn-verify" class="primary">VERIFY BYTE-EXACT</button>
  <div class="kv" id="verify-kv"></div>
</fieldset>

<fieldset>
  <legend>AXIS</legend>
  <label>EMBEDDING TENSOR</label>
  <input id="axis-tensor" placeholder="model.embed_tokens.weight">
  <label>ROW PAIRS POS:NEG (COMMA SEP)</label>
  <input id="axis-pairs" placeholder="12045:882, 9381:112">
  <label>NOTE</label>
  <input id="axis-note" placeholder="what this axis isolates">
  <button id="btn-axis" class="primary">CUT AXIS</button>
  <div class="kv" id="axis-kv"></div>
</fieldset>

<fieldset>
  <legend>SCORE</legend>
  <label>AXIS ID</label>
  <input id="score-axis" placeholder="axis-...">
  <label>ROWS (COMMA SEP)</label>
  <input id="score-rows" placeholder="12045, 882, 99120">
  <button id="btn-score" class="primary">SCORE ROWS</button>
  <div class="kv" id="score-kv"></div>
</fieldset>

<fieldset class="full">
  <legend>METRICS</legend>
  <div class="row">
    <div><label>OP</label>
    <select id="metric-op">
      <option>recipe</option><option>stats</option><option>entropysweep</option>
      <option>magics</option><option>experts</option><option>circuitry</option>
      <option>layerscan</option><option>direction</option>
      <option>anisotropy</option><option>mechanism</option><option>bits</option>
      <option>clean</option><option>concept</option><option>analogy</option>
      <option>neurons</option><option>walk</option><option>constellations</option>
      <option>order</option><option>axispure</option>
    </select></div>
    <div><label>TENSOR (BLANK = AUTO FOR EMBED OPS)</label>
    <input id="metric-tensor"></div>
    <div><label>LAYER</label><input id="metric-layer" type="number" value="0"></div>
    <div><label>SAMPLE</label><input id="metric-sample" type="number" value="256"></div>
  </div>
  <label>PARAMS (word / words / pairs / a,b,c,candidates / role — op dependent)</label>
  <input id="metric-params" placeholder='word=university  or  pairs=cold:warm,low:high  or  a=man b=king c=woman candidates=queen,princess'>
  <button id="btn-metric" class="primary">RUN METRIC</button>
  <div class="kv" id="metric-kv"></div>
</fieldset>

<fieldset class="full">
  <legend>ARCHIVE</legend>
  <button id="btn-archive">REFRESH</button>
  <div class="list" id="archive-list" style="max-height:140px"></div>
</fieldset>

<fieldset class="full">
  <legend>LOG</legend>
  <div id="log"></div>
</fieldset>

</div>
<script>
const $ = (id) => document.getElementById(id);
let INDEX = null;

function log(msg, cls) {
  const line = document.createElement("div");
  line.className = cls || "dim";
  const ts = new Date().toISOString().slice(11, 19);
  line.textContent = ts + "Z  " + msg;
  $("log").appendChild(line);
  $("log").scrollTop = $("log").scrollHeight;
}

async function api(path, body) {
  const response = await fetch(path, {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify(body || {}),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || ("HTTP " + response.status));
  return data;
}

function limitBytes() {
  return Math.max(1, parseInt($("limit").value || "64", 10)) * 1024 * 1024;
}

$("btn-index").onclick = async () => {
  $("btn-index").disabled = true;
  log("index build: " + $("repo").value);
  try {
    const data = await api("/api/index", {
      target: $("repo").value, revision: $("rev").value,
      filter: $("filter").value || null, limit: limitBytes(),
    });
    INDEX = data.index;
    $("lamp-index").className = "lamp on";
    $("index-kv").innerHTML =
      "files <b>" + INDEX.file_count + "</b>  tensors <b>" + INDEX.tensor_count +
      "</b>  tensor bytes <b>" + INDEX.tensor_bytes.toLocaleString() + "</b>";
    log("index: " + INDEX.tensor_count + " tensors, " +
        INDEX.tensor_bytes + " bytes", "ok");
    renderTensorList();
  } catch (e) { log("index failed: " + e.message, "err"); }
  $("btn-index").disabled = false;
};

function renderTensorList() {
  const filter = ($("tensor-filter").value || "").toLowerCase();
  const list = $("tensor-list");
  list.innerHTML = "";
  if (!INDEX) return;
  let shown = 0;
  for (const source of INDEX.sources) {
    for (const [name, t] of Object.entries(source.tensors)) {
      if (filter && !name.toLowerCase().includes(filter)) continue;
      if (++shown > 400) return;
      const row = document.createElement("div");
      row.textContent = name + "  " + t.dtype + "  [" + t.shape.join("x") + "]";
      row.onclick = () => {
        $("slice-tensor").value = name;
        $("tensor-kv").innerHTML = "file <b>" + source.file + "</b>  begin <b>" +
          t.begin + "</b>  bytes <b>" + (t.bytes === null ? "?" : t.bytes) + "</b>";
      };
      list.appendChild(row);
    }
  }
}
$("tensor-filter").oninput = renderTensorList;

async function doSlice(decode) {
  const body = {
    tensor: $("slice-tensor").value, decode: decode,
    note: $("slice-note").value, limit: limitBytes(),
  };
  if ($("slice-begin").value) body.begin = parseInt($("slice-begin").value, 10);
  if ($("slice-end").value) body.end = parseInt($("slice-end").value, 10);
  log("slice: " + body.tensor);
  try {
    const data = await api("/api/slice", body);
    const e = data.entry;
    let text = "archived <b>" + e.id + "</b>  bytes <b>" + e.bytes +
      "</b>  sha256 <b>" + e.sha256.slice(0, 16) + "...</b>";
    if (data.decoded) {
      text += "\nmin " + data.decoded.min + "  max " + data.decoded.max +
        "  mean " + data.decoded.mean;
    }
    $("slice-kv").innerHTML = text;
    log("slice archived: " + e.id + " (" + e.bytes + " bytes)", "ok");
  } catch (e2) { log("slice failed: " + e2.message, "err"); }
}
$("btn-slice").onclick = () => doSlice(false);
$("btn-decode").onclick = () => doSlice(true);

$("btn-verify").onclick = async () => {
  log("verify: " + $("verify-local").value);
  try {
    const data = await api("/api/verify", {
      local: $("verify-local").value, remote: $("verify-remote").value,
      samples: parseInt($("verify-samples").value, 10),
      span: parseInt($("verify-span").value, 10),
      seed: parseInt($("verify-seed").value, 10),
      limit: limitBytes(),
    });
    const lamp = data.status === "MATCH" ? "ok" : "err";
    $("verify-kv").innerHTML =
      "status <b>" + data.status + "</b>  matched <b>" + data.matched + "/" +
      data.samples + "</b>  bytes <b>" + data.bytes_compared +
      "</b>  sizes agree <b>" + data.size_agree + "</b>";
    log("verify " + data.status + " " + data.matched + "/" + data.samples, lamp);
  } catch (e) { log("verify failed: " + e.message, "err"); }
};

$("btn-axis").onclick = async () => {
  const pairs = $("axis-pairs").value.split(",").map(s => s.trim())
    .filter(Boolean).map(s => s.split(":").map(x => parseInt(x, 10)));
  log("axis cut: " + JSON.stringify(pairs));
  try {
    const data = await api("/api/axis", {
      tensor: $("axis-tensor").value, pairs: pairs,
      note: $("axis-note").value, limit: limitBytes(),
    });
    $("axis-kv").innerHTML = "axis <b>" + data.entry.id + "</b>  dims <b>" +
      data.dimensions + "</b>";
    $("score-axis").value = data.entry.id;
    log("axis archived: " + data.entry.id, "ok");
  } catch (e) { log("axis failed: " + e.message, "err"); }
};

$("btn-score").onclick = async () => {
  const rows = $("score-rows").value.split(",").map(s => parseInt(s.trim(), 10))
    .filter(n => !isNaN(n));
  try {
    const data = await api("/api/score", {
      tensor: $("axis-tensor").value, axis: $("score-axis").value,
      rows: rows, limit: limitBytes(),
    });
    $("score-kv").innerHTML = data.scores.map(
      s => "row <b>" + s.row + "</b>  cos <b>" + s.cosine.toFixed(5) + "</b>"
    ).join("\n");
    log("scored " + data.scores.length + " rows", "ok");
  } catch (e) { log("score failed: " + e.message, "err"); }
};

$("btn-metric").onclick = async () => {
  const body = {
    op: $("metric-op").value, tensor: $("metric-tensor").value || null,
    layer: parseInt($("metric-layer").value || "0", 10),
    sample: parseInt($("metric-sample").value || "256", 10),
    limit: limitBytes(),
  };
  for (const tok of ($("metric-params").value || "").split(/\s+/)) {
    if (!tok) continue;
    const eq = tok.indexOf("=");
    if (eq < 0) continue;
    const key = tok.slice(0, eq), val = tok.slice(eq + 1);
    body[key] = (key === "k" || key === "steps" || key === "units" ||
                 key === "band" || key === "vocab_sample")
      ? parseInt(val, 10) : (key === "threshold" ? parseFloat(val) : val);
  }
  log("metric " + body.op + (body.tensor ? " on " + body.tensor : ""));
  $("btn-metric").disabled = true;
  try {
    const data = await api("/api/metric", body);
    const r = data.result;
    const keys = Object.keys(r).filter(k => !k.startsWith("_")).slice(0, 14);
    $("metric-kv").textContent =
      "archived " + data.entry_id + "\n" +
      keys.map(k => k + " = " + JSON.stringify(r[k]).slice(0, 220)).join("\n");
    log("metric " + body.op + " archived: " + data.entry_id, "ok");
  } catch (e) { log("metric failed: " + e.message, "err"); }
  $("btn-metric").disabled = false;
};

$("btn-archive").onclick = async () => {
  try {
    const data = await api("/api/archive", {});
    const list = $("archive-list");
    list.innerHTML = "";
    for (const e of data.entries.slice().reverse()) {
      const row = document.createElement("div");
      row.textContent = e.recorded_utc + "  " + e.id + "  " + e.bytes + "B  " +
        (e.note || e.tensor || "");
      list.appendChild(row);
    }
    log("archive: " + data.entries.length + " entries", "ok");
  } catch (e) { log("archive failed: " + e.message, "err"); }
};

setInterval(() => {
  $("clock").textContent = new Date().toISOString().slice(0, 19) + "Z";
}, 1000);
fetch("/api/status", {method: "POST", body: "{}"})
  .then(r => r.json())
  .then(() => { $("lamp-conn").className = "lamp on"; log("panel online", "ok"); })
  .catch(() => { $("lamp-conn").className = "lamp err"; });
</script>
</body>
</html>
"""


class PanelHandler(http.server.BaseHTTPRequestHandler):
    server_version = "WBRangePanel/1.0"

    def log_message(self, fmt, *args):
        sys.stderr.write("panel: " + fmt % args + "\n")

    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path in ("/", "/index.html"):
            body = PANEL_HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self._send_json({"error": "not found"}, 404)

    def do_POST(self) -> None:
        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else b"{}"
            request = json.loads(body.decode("utf-8") or "{}")
            if not isinstance(request, dict):
                raise WbRangeError("request body must be a JSON object")
            self._route(request)
        except WbRangeError as exc:
            self._send_json({"error": str(exc)}, 400)
        except Exception as exc:  # panel must report, not die
            self._send_json({"error": "%s: %s" % (type(exc).__name__, exc)}, 500)

    def _route(self, request: dict) -> None:
        state = self.server.state
        limit = int(request.get("limit") or DEFAULT_LIMIT_BYTES)
        if self.path == "/api/status":
            self._send_json({"status": "ONLINE", "schema_version": SCHEMA_VERSION})
        elif self.path == "/api/index":
            index = build_index(
                str(request["target"]), state["cache_dir"],
                revision=str(request.get("revision") or "main"),
                limit=limit,
                name_filter=request.get("filter") or None,
            )
            state["index"] = index
            write_json(state["index_path"], index)
            self._send_json({"status": "INDEXED", "index": index})
        elif self.path == "/api/slice":
            index = self._index(state)
            result = slice_tensor(
                index, state["archive"], state["cache_dir"],
                str(request["tensor"]),
                begin=request.get("begin"), end=request.get("end"),
                decode=bool(request.get("decode")), limit=limit,
                note=str(request.get("note") or ""),
            )
            self._send_json(result)
        elif self.path == "/api/verify":
            result = verify_ranges(
                Path(str(request["local"])), str(request["remote"]),
                state["cache_dir"],
                samples=int(request.get("samples") or 16),
                span=int(request.get("span") or 4096),
                seed=int(request.get("seed") or 1337),
                limit=limit,
            )
            state["archive"].put(
                "verify",
                json.dumps(result, sort_keys=True).encode("utf-8"),
                {"local": result["local"], "remote": result["remote"],
                 "verdict": result["status"], "note": "byte-exactness rehearsal"},
            )
            self._send_json(result)
        elif self.path == "/api/axis":
            index = self._index(state)
            pairs = request.get("pairs")
            if not isinstance(pairs, list) or not all(
                isinstance(p, list) and len(p) == 2 for p in pairs
            ):
                raise WbRangeError("pairs must be [[pos, neg], ...]")
            result = cut_axis(
                index, state["archive"], state["cache_dir"],
                str(request["tensor"]),
                [(int(p[0]), int(p[1])) for p in pairs],
                limit=limit, note=str(request.get("note") or ""),
            )
            self._send_json(result)
        elif self.path == "/api/score":
            index = self._index(state)
            result = score_rows(
                index, state["archive"], state["cache_dir"],
                str(request["tensor"]), str(request["axis"]),
                [int(r) for r in request.get("rows") or []],
                limit=limit,
            )
            self._send_json(result)
        elif self.path == "/api/metric":
            index = self._index(state)
            op = str(request.get("op") or "")
            if op not in METRIC_OPS:
                raise WbRangeError("unknown metric op %r" % op)
            result = metric_op(op, index, state["archive"],
                               state["cache_dir"], request)
            self._send_json(result)
        elif self.path == "/api/archive":
            self._send_json({"entries": state["archive"].manifest["entries"]})
        else:
            self._send_json({"error": "unknown endpoint"}, 404)

    def _index(self, state: dict) -> dict:
        if state.get("index") is None:
            if state["index_path"].is_file():
                state["index"] = load_index(state["index_path"])
            else:
                raise WbRangeError("no index; build one first")
        return state["index"]


def serve(work_dir: Path, port: int) -> int:
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    state = {
        "cache_dir": work_dir / "cache",
        "archive": Archive(work_dir / "archive"),
        "index_path": work_dir / "wb_range_index.json",
        "index": None,
    }
    if state["index_path"].is_file():
        state["index"] = load_index(state["index_path"])

    class Server(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
        daemon_threads = True

    with Server(("127.0.0.1", port), PanelHandler) as httpd:
        httpd.state = state
        print(json.dumps({
            "status": "SERVING",
            "url": "http://127.0.0.1:%d/" % port,
            "work_dir": str(work_dir),
        }, sort_keys=True))
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    index_cmd = commands.add_parser("index", help="build a tensor index from headers")
    index_cmd.add_argument("target", help="owner/repo or a direct file URL")
    index_cmd.add_argument("--revision", default="main")
    index_cmd.add_argument("--filter", default=None, help="regex over file names")
    index_cmd.add_argument("--work-dir", type=Path, default=Path("wb-range-out"))
    index_cmd.add_argument("--limit", type=int, default=DEFAULT_LIMIT_BYTES)
    index_cmd.add_argument("--output", type=Path, default=None)
    index_cmd.add_argument("--stats", type=Path, default=None,
                           help="write this invocation's measured range/cache counts and elapsed time")

    slice_cmd = commands.add_parser("slice", help="fetch a tensor byte range")
    slice_cmd.add_argument("index", type=Path)
    slice_cmd.add_argument("tensor")
    slice_cmd.add_argument("--begin", type=int, default=None)
    slice_cmd.add_argument("--end", type=int, default=None)
    slice_cmd.add_argument("--decode", action="store_true")
    slice_cmd.add_argument("--note", default="")
    slice_cmd.add_argument("--work-dir", type=Path, default=Path("wb-range-out"))
    slice_cmd.add_argument("--limit", type=int, default=DEFAULT_LIMIT_BYTES)

    verify_cmd = commands.add_parser("verify", help="byte-exact local vs remote")
    verify_cmd.add_argument("local", type=Path)
    verify_cmd.add_argument("remote")
    verify_cmd.add_argument("--samples", type=int, default=16)
    verify_cmd.add_argument("--span", type=int, default=4096)
    verify_cmd.add_argument("--seed", type=int, default=1337)
    verify_cmd.add_argument("--work-dir", type=Path, default=Path("wb-range-out"))
    verify_cmd.add_argument("--limit", type=int, default=DEFAULT_LIMIT_BYTES)

    axis_cmd = commands.add_parser("axis", help="cut a semantic axis from row pairs")
    axis_cmd.add_argument("index", type=Path)
    axis_cmd.add_argument("tensor")
    axis_cmd.add_argument("pairs", help="pos:neg,pos:neg,...")
    axis_cmd.add_argument("--note", default="")
    axis_cmd.add_argument("--work-dir", type=Path, default=Path("wb-range-out"))
    axis_cmd.add_argument("--limit", type=int, default=DEFAULT_LIMIT_BYTES)

    score_cmd = commands.add_parser("score", help="score rows against an axis")
    score_cmd.add_argument("index", type=Path)
    score_cmd.add_argument("tensor")
    score_cmd.add_argument("axis")
    score_cmd.add_argument("rows", help="comma separated row ids")
    score_cmd.add_argument("--work-dir", type=Path, default=Path("wb-range-out"))
    score_cmd.add_argument("--limit", type=int, default=DEFAULT_LIMIT_BYTES)

    archive_cmd = commands.add_parser("archive", help="list the archive of answers")
    archive_cmd.add_argument("--work-dir", type=Path, default=Path("wb-range-out"))

    metric_cmd = commands.add_parser(
        "metric", help="run a White Box metric op over ranged reads")
    metric_cmd.add_argument("index", type=Path)
    metric_cmd.add_argument("op", choices=METRIC_OPS)
    metric_cmd.add_argument("--tensor", default=None)
    metric_cmd.add_argument("--layer", type=int, default=0)
    metric_cmd.add_argument("--role", default=None, help="layerscan role")
    metric_cmd.add_argument("--sample", type=int, default=256)
    metric_cmd.add_argument("--vocab-sample", type=int, default=1200)
    metric_cmd.add_argument("--units", type=int, default=512,
                            help="circuitry/neurons units sampled")
    metric_cmd.add_argument("--band", type=int, default=1024,
                            help="circuitry drain band dims")
    metric_cmd.add_argument("--k", type=int, default=8)
    metric_cmd.add_argument("--seed", type=int, default=7)
    metric_cmd.add_argument("--word", default=None)
    metric_cmd.add_argument("--words", default=None, help="comma separated")
    metric_cmd.add_argument("--pairs", default=None, help="neg:pos,neg:pos")
    metric_cmd.add_argument("--a", default=None)
    metric_cmd.add_argument("--b", default=None)
    metric_cmd.add_argument("--c", default=None)
    metric_cmd.add_argument("--candidates", default=None)
    metric_cmd.add_argument("--steps", type=int, default=8)
    metric_cmd.add_argument("--threshold", type=float, default=0.18)
    metric_cmd.add_argument("--max-bytes", type=int, default=None)
    metric_cmd.add_argument("--note", default="")
    metric_cmd.add_argument("--work-dir", type=Path, default=Path("wb-range-out"))
    metric_cmd.add_argument("--limit", type=int, default=DEFAULT_LIMIT_BYTES)

    serve_cmd = commands.add_parser("serve", help="run the control panel")
    serve_cmd.add_argument("--port", type=int, default=7863)
    serve_cmd.add_argument("--work-dir", type=Path, default=Path("wb-range-out"))
    return parser


def _parse_pairs(raw: str) -> list[tuple[int, int]]:
    pairs = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        left, sep, right = item.partition(":")
        if not sep:
            raise WbRangeError("pair %r must be pos:neg" % item)
        pairs.append((int(left), int(right)))
    return pairs


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "serve":
        return serve(args.work_dir, args.port)

    work_dir = Path(getattr(args, "work_dir", Path("wb-range-out")))
    cache_dir = work_dir / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    if args.command == "index":
        output = args.output or (work_dir / "wb_range_index.json")
        if args.stats is not None and args.stats.resolve() == output.resolve():
            raise WbRangeError("stats output must differ from the model index output")
        stats = {} if args.stats is not None else None
        started = time.perf_counter()
        error = None
        try:
            index = build_index(args.target, cache_dir, revision=args.revision,
                                limit=args.limit, name_filter=args.filter, stats=stats)
            write_json(output, index)
        except BaseException as exc:
            error = exc
            raise
        finally:
            if stats is not None:
                report = {
                    "schema_version": "commons-wb-range-stats/v1",
                    "operation": "index",
                    "status": "FAILED" if error is not None else "INDEXED",
                    "http_scope": "range_requests_only",
                    "elapsed_seconds": time.perf_counter() - started,
                    **stats,
                }
                if error is not None:
                    report["error"] = "%s: %s" % (type(error).__name__, error)
                try:
                    write_json(args.stats, report)
                except OSError as exc:
                    message = "cannot write stats output: %s" % exc
                    if error is not None:
                        print(message, file=sys.stderr)
                    else:
                        raise WbRangeError(message) from exc
        print(json.dumps({
            "status": "INDEXED",
            "files": index["file_count"],
            "tensors": index["tensor_count"],
            "tensor_bytes": index["tensor_bytes"],
            "output": str(output),
        }, sort_keys=True))
        return 0

    if args.command == "verify":
        result = verify_ranges(args.local, args.remote, cache_dir,
                               samples=args.samples, span=args.span,
                               seed=args.seed, limit=args.limit)
        archive = Archive(work_dir / "archive")
        archive.put("verify",
                    json.dumps(result, sort_keys=True).encode("utf-8"),
                    {"local": result["local"], "remote": result["remote"],
                     "verdict": result["status"],
                     "note": "byte-exactness rehearsal"})
        summary = {key: result[key] for key in
                   ("status", "matched", "samples", "bytes_compared", "size_agree")}
        print(json.dumps(summary, sort_keys=True))
        return 0 if result["status"] == "MATCH" else 1

    if args.command == "archive":
        archive = Archive(work_dir / "archive")
        print(json.dumps(archive.manifest, sort_keys=True))
        return 0

    index = load_index(args.index)
    archive = Archive(work_dir / "archive")

    if args.command == "metric":
        op_args = {key: getattr(args, key, None) for key in
                   ("tensor", "layer", "role", "sample", "units", "band",
                    "k", "seed", "word", "words", "pairs", "a", "b", "c",
                    "candidates", "steps", "threshold", "note", "limit")}
        op_args["vocab_sample"] = args.vocab_sample
        if args.max_bytes is not None:
            op_args["max_bytes"] = args.max_bytes
        result = metric_op(args.op, index, archive, cache_dir, op_args)
        print(json.dumps(result, sort_keys=True, default=str))
        return 0
    if args.command == "slice":
        result = slice_tensor(index, archive, cache_dir, args.tensor,
                              begin=args.begin, end=args.end,
                              decode=args.decode, limit=args.limit,
                              note=args.note)
        print(json.dumps(result, sort_keys=True, default=str))
        return 0
    if args.command == "axis":
        result = cut_axis(index, archive, cache_dir, args.tensor,
                          _parse_pairs(args.pairs), limit=args.limit,
                          note=args.note)
        print(json.dumps(result, sort_keys=True))
        return 0
    if args.command == "score":
        rows = [int(item) for item in args.rows.split(",") if item.strip()]
        result = score_rows(index, archive, cache_dir, args.tensor,
                            args.axis, rows, limit=args.limit)
        print(json.dumps(result, sort_keys=True))
        return 0
    raise WbRangeError("unhandled command")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except WbRangeError as exc:
        print("INVALID: %s" % exc, file=sys.stderr)
        raise SystemExit(2)
