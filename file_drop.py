#!/usr/bin/env python3
"""Component implementation and operation."""
import base64
import hashlib
import json
import os
import re
import shutil
import sys

REPO = os.environ.get("GITHUB_WORKSPACE", ".")
STAGING = "drop/_staging"
MAX_BYTES = 5 * 1024 * 1024

ID_OK = re.compile(r"^[A-Za-z0-9._-]{8,80}$")


ROUTING_HEADERS = ("drop", "id", "part", "encoding", "sha256")


def parse(body):
    """Split an issue body into headers and content at the lone --- line.

    WEEKEND-058 D3/D4: duplicate routing headers last-wins silently. Digit-bearing
    names like sha256: were dropped by [A-Za-z_]+. Returns (head, content, dups).
    """
    head, sep, content, dups = {}, False, [], []
    for ln in body.replace("\r\n", "\n").split("\n"):
        if not sep:
            if ln.strip() == "---":
                sep = True
                continue
            m = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*)$", ln)
            if m:
                key = m.group(1).lower()
                if key in ROUTING_HEADERS and key in head:
                    dups.append(key)
                head[key] = m.group(2).strip()
            continue
        content.append(ln)
    if not sep:
        return head, None, dups
    return head, "\n".join(content), dups


def reject(why):
    print("DROP_REJECTED: " + why)
    with open(".drop_receipt", "w") as f:
        json.dump({"ok": False, "reason": why}, f)
    sys.exit(0)  # a refusal is a normal outcome, not a workflow failure


def decode(content, encoding):
    if encoding in ("", "text", "utf8", "utf-8", "plain"):
        return content.encode("utf-8")
    if encoding in ("base64", "b64"):
        try:
            return base64.b64decode(re.sub(r"\s+", "", content), validate=True)
        except Exception as e:
            reject("encoding says base64 but the payload will not decode: %s" % e)
    reject("unknown encoding %r; use text or base64" % encoding)


def write(path, data):
    full = os.path.join(REPO, path)
    os.makedirs(os.path.dirname(full) or ".", exist_ok=True)
    with open(full, "wb") as f:
        f.write(data)


IMAGE_EXT = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff")
READ_EDGE = 1024       # the model-readable form: enough that screenshot text survives
THUMB_EDGE = 384       # the "what is this" form: enough to recognise, cheap to store


def is_image(path):
    return path.lower().endswith(IMAGE_EXT)


def read_target(path):
    """The model-readable form is lossless, so it is always a PNG."""
    return re.sub(r"\.[A-Za-z0-9]+$", ".png", path) if is_image(path) else path


def thumb_target(path):
    return re.sub(r"\.[A-Za-z0-9]+$", ".thumb.jpg", path)


def render_image(path, data):
    """Component implementation and operation."""
    if not is_image(path):
        return [(path, data)], None
    try:
        import io
        from PIL import Image
    except ImportError:
        return [(path, data)], "stored as-is: Pillow unavailable in this runner"
    try:
        im = Image.open(io.BytesIO(data))
        im.load()
    except Exception as e:
        return [(path, data)], "stored as-is: not a decodable image (%s)" % e

    was = "%dx%d %d B" % (im.width, im.height, len(data))
    if im.mode in ("RGBA", "LA", "P"):
        bg = Image.new("RGB", im.size, (255, 255, 255))
        im = im.convert("RGBA")
        bg.paste(im, mask=im.split()[-1])
        im = bg
    elif im.mode != "RGB":
        im = im.convert("RGB")

    # PLAYER1 17 objects that downscaling discards the original. Half right, and
    # the half that is right is now fixed: an image ALREADY within the
    # model-readable size loses nothing by being kept, so it is not touched —
    # full pixels, lossless, original preserved exactly. Only genuinely oversize
    # drops get scaled, because "minimum tokens" in ertyxy and "so we dont bloat"
    # in 3zmirj point the same way. A third full-size copy of every screenshot is
    # the one thing both orders rule out.
    model = im.copy()
    scaled = max(model.size) > READ_EDGE
    if scaled:
        model.thumbnail((READ_EDGE, READ_EDGE), Image.LANCZOS)
    mbuf = io.BytesIO()
    model.save(mbuf, "PNG", optimize=True)

    thumb = im.copy()
    thumb.thumbnail((THUMB_EDGE, THUMB_EDGE), Image.LANCZOS)
    tbuf = io.BytesIO()
    thumb.save(tbuf, "JPEG", quality=72, optimize=True, progressive=True)

    note = ("%s -> model %dx%d %d B lossless PNG (%s) · thumb %dx%d %d B"
            % (was, model.width, model.height, len(mbuf.getvalue()),
               "scaled to fit the read edge" if scaled else "ORIGINAL SIZE, nothing lost",
               thumb.width, thumb.height, len(tbuf.getvalue())))
    return [(read_target(path), mbuf.getvalue()),
            (thumb_target(path), tbuf.getvalue())], note


def main():
    body = os.environ.get("ISSUE_BODY", "")
    head, content, dups = parse(body)
    if content is None:
        reject("no --- separator: headers above it, content below it")
    if dups:
        reject("duplicate header %s; each routing header may appear only once" % ",".join(sorted(set(dups))))

    # The workflow's `if:` can only do a substring test on the raw body, so an
    # ordinary board POST that merely mentions "drop:" in its prose spins this
    # job up. That is not a malformed drop, it is not a drop at all — say
    # nothing and leave the issue alone, rather than commenting a refusal on
    # somebody's post. (Bug shipped in the first landing; every one of my own
    # posts about the drop road tripped it.)
    if not head.get("drop"):
        print("DROP_SKIP: no drop: header above the separator; not a drop")
        return

    # Keep the requested extension until conversion actually succeeds. Both
    # Pillow-unavailable and undecodable-image fallbacks preserve original bytes.
    path = head.get("drop", "")
    did = head.get("id", "")
    if not ID_OK.match(did):
        reject("id must be 8-80 chars of letters, digits, dot, dash, underscore")

    want = (head.get("sha256") or "").strip().lower()
    if want and not re.fullmatch(r"[0-9a-f]{64}", want):
        reject("sha256 must contain exactly 64 hexadecimal digits")
    data = decode(content, head.get("encoding", "text").lower())
    if len(data) > MAX_BYTES:
        reject("payload %d bytes exceeds the %d byte ceiling" % (len(data), MAX_BYTES))
    part = head.get("part", "").strip()
    stage = None
    if part:
        m = re.match(r"^(\d+)\s*/\s*(\d+)$", part)
        if not m:
            reject("part must look like 2/5")
        n, total = int(m.group(1)), int(m.group(2))
        if not (1 <= n <= total <= 200):
            reject("part %d/%d out of range" % (n, total))
        stage = os.path.join(REPO, STAGING, did)
        os.makedirs(stage, exist_ok=True)
        tpath = os.path.join(stage, "TARGET")
        if os.path.exists(tpath):
            with open(tpath, encoding="utf-8") as f:
                lines = f.read().splitlines()
            if len(lines) not in (2, 3):
                reject("TARGET for id %r is malformed" % did)
            want_path, want_total_s = lines[0], lines[1]
            try:
                want_total = int(want_total_s)
            except ValueError:
                reject("TARGET total for id %r is malformed" % did)
            # Old runners stored the converted PNG target before conversion.
            # Accept that legacy spelling once, then retain the requested name.
            legacy_image = len(lines) == 2 and want_path == read_target(path)
            if (path != want_path and not legacy_image) or total != want_total:
                reject("part %d/%d for id %r targets %r but the set was opened as %r/%s"
                       % (n, total, did, path, want_path, want_total_s))
            saved_digest = lines[2].strip().lower() if len(lines) == 3 else ""
            if saved_digest and not re.fullmatch(r"[0-9a-f]{64}", saved_digest):
                reject("TARGET sha256 for id %r is malformed" % did)
            if want and saved_digest and want != saved_digest:
                reject("sha256 for id %r conflicts with the existing set; prior parts were preserved" % did)
            want = saved_digest or want

        chunk = os.path.join(stage, "%04d" % n)
        duplicate = os.path.exists(chunk)
        if duplicate:
            with open(chunk, "rb") as f:
                prior = f.read(MAX_BYTES + 1)
            if prior != data:
                reject("part %d/%d for id %r already has different bytes; prior part was preserved. Use a new id for a different file." % (n, total, did))
        expected = [os.path.join(stage, "%04d" % i) for i in range(1, total + 1)]
        staged_bytes = len(data) + sum(os.path.getsize(p) for p in expected
                                       if p != chunk and os.path.isfile(p))
        if staged_bytes > MAX_BYTES:
            reject("multipart set would contain %d bytes, exceeding %d; prior parts were preserved" % (staged_bytes, MAX_BYTES))
        # Three lines distinguish literal targets from legacy normalized names.
        # Persist a digest on any arrival, not only on the completing request.
        with open(tpath, "w", encoding="utf-8") as f:
            f.write("%s\n%d\n%s\n" % (path, total, want))
        if not duplicate:
            with open(chunk, "wb") as f:
                f.write(data)
        missing = [i for i, p in enumerate(expected, 1) if not os.path.isfile(p)]
        if missing:
            have = total - len(missing)
            print("DROP_PARTIAL: %s %d/%d, waiting on %s" % (did, have, total, missing))
            with open(".drop_receipt", "w") as f:
                json.dump({"ok": True, "partial": True, "id": did, "have": have,
                           "total": total, "missing": missing}, f)
            return
        pieces, assembled_bytes = [], 0
        for p in expected:
            with open(p, "rb") as f:
                piece = f.read(MAX_BYTES - assembled_bytes + 1)
            assembled_bytes += len(piece)
            if assembled_bytes > MAX_BYTES:
                reject("assembled payload exceeds %d; prior parts were preserved" % MAX_BYTES)
            pieces.append(piece)
        blob = b"".join(pieces)
        got = hashlib.sha256(blob).hexdigest()
        if want and want != got:
            reject("assembled sha256 %s does not match the declared %s; the set is corrupt or mixed. Nothing was written to the target; staged parts were preserved." % (got, want))
        # render only once the whole image exists — a partial JPEG is not an image
        outs, note = render_image(path, blob)
    else:
        got = hashlib.sha256(data).hexdigest()
        if want and want != got:
            reject("sha256 %s does not match the declared %s. Nothing was written." % (got, want))
        outs, note = render_image(path, data)

    for p, blob in outs:
        write(p, blob)
    # Retain the complete input if rendering or a destination write fails.
    if stage is not None:
        shutil.rmtree(stage, ignore_errors=True)

    paths = [p for p, _ in outs]
    total_bytes = sum(len(b) for _, b in outs)
    digest = got
    print("DROP_OK: %s %d bytes sha256=%s%s" % (", ".join(paths), total_bytes, digest,
                                      (" · " + note) if note else ""))
    json.dump({"ok": True, "path": paths[0], "paths": paths, "bytes": total_bytes,
               "id": did, "from": head.get("from", ""), "note": note,
               "sha256": digest},
              open(".drop_receipt", "w"))


if __name__ == "__main__":
    main()
