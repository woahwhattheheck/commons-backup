"""Pure, fail-closed Bitcoin compact-target decoding and same-job binding."""

from __future__ import annotations

import struct


PACKED_HEADER76 = 76


def compact_target(nbits):
    """Decode valid Bitcoin compact nBits, rejecting negative/zero/overflow."""
    if not isinstance(nbits, int) or not 0 <= nbits <= 0xFFFFFFFF:
        raise ValueError("nbits must be one unsigned 32-bit integer")
    exponent = nbits >> 24
    mantissa = nbits & 0x007FFFFF
    if nbits & 0x00800000:
        raise ValueError("negative compact target")
    if mantissa == 0:
        raise ValueError("zero compact target")
    overflow = (
        exponent > 34
        or (mantissa > 0xFF and exponent > 33)
        or (mantissa > 0xFFFF and exponent > 32)
    )
    if overflow:
        raise ValueError("compact target overflows 256 bits")
    if exponent <= 3:
        target = mantissa >> (8 * (3 - exponent))
    else:
        target = mantissa << (8 * (exponent - 3))
    if not 0 < target < (1 << 256):
        raise ValueError("compact target outside the 256-bit positive range")
    return target


def target_for_job(job, prefix76):
    """Bind the block target to nBits in this exact job-derived header."""
    if len(prefix76) != PACKED_HEADER76:
        raise ValueError("job prefix must be exactly 76 bytes")
    try:
        advertised_nbits = int(job["nbits"], 16)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("job nbits is missing or malformed") from exc
    header_nbits = struct.unpack("<I", prefix76[72:76])[0]
    if header_nbits != advertised_nbits:
        raise ValueError("job/header nbits mismatch")
    return header_nbits, compact_target(header_nbits)
