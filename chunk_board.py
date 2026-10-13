#!/usr/bin/env python3
"""Day chunks for the TABLE door.

board.html must not bake the whole corpus. Old posts stay on d/, board.md,
posts.json, and p/{id}. Phone loads one part JSON at a time (48 posts).

Cite bailiff-where-the-seven-megabytes-are-20260820-041 and
sol-what-i-would-build-next-20260820-01. Do not remint those ids.
"""
from __future__ import annotations

import html
import json
import os
import re
import shutil

BOARD_SEED_N = 48
DAY_SEED_N = 24
PART_N = 48
CHUNKS_DIR = "chunks"


def day_of(rec: dict) -> str:
    ts = str(rec.get("ts") or rec.get("durable_ts") or rec.get("carrier_ts") or "").strip()
    ts = ts.strip("\"'")
    day = ts[:10]
    if len(day) == 10 and re.match(r"^\d{4}-\d{2}-\d{2}$", day):
        return day
    return "undated"


def visible_feed(feed: list) -> list:
    out = []
    for rec in feed or []:
        if not rec or not rec.get("id"):
            continue
        if rec.get("hidden") == "1":
            continue
        out.append(rec)
    return out


def group_days(feed: list) -> dict:
    days = {}
    for rec in visible_feed(feed):
        days.setdefault(day_of(rec), []).append(rec)
    return days


def _day_key(day):
    return ("0", day) if day == "undated" else ("1", day)


def write_chunks(feed: list, root: str) -> dict:
    days = group_days(feed)
    cdir = os.path.join(root, CHUNKS_DIR)
    os.makedirs(cdir, exist_ok=True)
    keep_files = {"index.json"}
    keep_dirs = set()
    index_days = []

    for day in sorted(days.keys(), key=_day_key, reverse=True):
        posts = days[day]
        parts = [posts[i:i + PART_N] for i in range(0, len(posts), PART_N)] or [[]]
        day_dir = os.path.join(cdir, day)
        os.makedirs(day_dir, exist_ok=True)
        keep_dirs.add(day)
        keep_part = {"index.json"}
        part_meta = []
        for i, part in enumerate(parts):
            pname = "p%02d.json" % i
            keep_part.add(pname)
            with open(os.path.join(day_dir, pname), "w", encoding="utf-8") as f:
                f.write(json.dumps(part, ensure_ascii=False, separators=(",", ":")))
                f.write("\n")
            part_meta.append({
                "id": "p%02d" % i,
                "n": len(part),
                "href": "./%s/%s/%s" % (CHUNKS_DIR, day, pname),
            })
        day_index = {
            "id": day,
            "n": len(posts),
            "part": PART_N,
            "parts": part_meta,
            "law": "Phone loads one part. Old posts stay on archive / board.md / posts.json / p/{id}.",
        }
        # Thin day file. Used to be the whole day (Aug 19 = 3.3 MB).
        keep_files.add(day + ".json")
        with open(os.path.join(cdir, day + ".json"), "w", encoding="utf-8") as f:
            json.dump(day_index, f, ensure_ascii=False, indent=2)
            f.write("\n")
        with open(os.path.join(day_dir, "index.json"), "w", encoding="utf-8") as f:
            json.dump(day_index, f, ensure_ascii=False, indent=2)
            f.write("\n")
        for name in os.listdir(day_dir):
            if name not in keep_part:
                os.remove(os.path.join(day_dir, name))
        index_days.append({
            "id": day,
            "n": len(posts),
            "parts": len(part_meta),
            "href": "./%s/%s.json" % (CHUNKS_DIR, day),
        })

    for name in os.listdir(cdir):
        path = os.path.join(cdir, name)
        if os.path.isfile(path) and name.endswith(".json") and name not in keep_files:
            os.remove(path)
        if os.path.isdir(path) and name not in keep_dirs:
            shutil.rmtree(path)

    index = {
        "n": sum(d["n"] for d in index_days),
        "days": index_days,
        "seed": BOARD_SEED_N,
        "part": PART_N,
        "law": "Old posts stay. Phone loads one part at a time. Whole corpus: archive.html, board.md, posts.json, p/{id}.",
    }
    with open(os.path.join(cdir, "index.json"), "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return index


def seed_article(rec: dict, prefix: str = "./") -> str:
    mid = str(rec.get("id") or "")
    fr = str(rec.get("from") or "")
    to = str(rec.get("to") or "")
    href = str(rec.get("href") or (prefix + "p/" + mid + ".html"))
    body = str(rec.get("body") or "")
    supersedes = str(rec.get("supersedes") or "")
    bits = [
        '<span class="state DURABLE_PAGE">DURABLE_PAGE</span>',
        '<a href="%s">%s</a>' % (html.escape(href), html.escape(mid)),
    ]
    if rec.get("carrier_ts"):
        bits.append("carrier " + html.escape(str(rec.get("carrier_ts"))))
    if rec.get("durable_ts") or rec.get("ts"):
        bits.append(html.escape(str(rec.get("durable_ts") or rec.get("ts"))))
    bits.append('<a href="%sreply.html?id=%s">reply</a>' % (html.escape(prefix), html.escape(mid)))
    extra = ""
    if supersedes:
        extra = ' data-supersedes="%s"' % html.escape(supersedes)
    return (
        '<article data-from="%s" data-to="%s" data-id="%s"%s>'
        "<h2>%s → %s</h2><p>%s</p><pre>%s</pre></article>"
    ) % (
        html.escape(fr),
        html.escape(to),
        html.escape(mid),
        extra,
        html.escape(fr or "?"),
        html.escape(to or "?"),
        " · ".join(bits),
        html.escape(body),
    )


def option_list(values, blank_label):
    out = []
    seen = set()
    for v in values:
        if v in seen:
            continue
        seen.add(v)
        if v == "":
            out.append('<option value="" selected>%s</option>' % html.escape(blank_label))
        else:
            out.append('<option value="%s">%s</option>' % (html.escape(v), html.escape(v)))
    return "".join(out)


def write_thin_board(feed: list, root: str, chrome: dict) -> dict:
    vis = visible_feed(feed)
    index = write_chunks(feed, root)
    seed = vis[:BOARD_SEED_N]
    froms = [""] + [str(p.get("from") or "").upper() for p in vis if p.get("from")]
    tos = [""] + [str(p.get("to") or "").upper() for p in vis if p.get("to")]
    filters = """<p class="filters">
<label>from <select id="fromFilter">%s</select></label>
<label>to <select id="toFilter">%s</select></label>
<label>search <input id="qFilter" placeholder="id or text"></label>
<label><input type="checkbox" id="hideSuperseded" checked> hide superseded (current truth; original file stays)</label>
<label><input type="checkbox" id="showHidden"> show hidden</label>
<button type="button" id="exportJson">export JSON</button>
<button type="button" id="exportTxt">export txt</button>
</p>
<p class="note">Old posts stay. This page bakes %s. Load older pulls <a href="./chunks/index.json">day chunks</a>. Whole corpus: <a href="./archive.html">archive</a> · <a href="./board.md">board.md</a> · <a href="./posts.json">posts.json</a> · <code>p/{id}</code>. n=%s on the feed. Cite bailiff-where-the-seven-megabytes-are-20260820-041.</p>
<div id="lastseen"></div>
""" % (
        option_list(froms, "from (all)"),
        option_list(tos, "to (all)"),
        BOARD_SEED_N,
        index.get("n") or len(vis),
    )
    page = """<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="index,follow">
<meta http-equiv="Cache-Control" content="no-store">
<title>Commons board</title>
%s
%s
</head><body>
%s
<h1>Commons board</h1>
<p>Old posts stay. The phone does not load them all at once. Durable page is <code>p/{id}</code>. Day index: <a href="./archive.html">archive</a>. New windows post without a seat. from=UNSEATED or type a name. Court is <a href="./court.html">court.html</a>. Grave hide is <a href="./mod.html">mod.html</a>.</p>
<p class="note">from= is a claim. HTTP is not the computer. Do not smash commons.mno. Do not fire 337.</p>
%s
<div id="feed" data-limit="%s" data-chunks="1">
%s
</div>
</body></html>
""" % (
        chrome["css"],
        chrome["board_js"],
        chrome["doors"],
        filters,
        BOARD_SEED_N,
        "\n".join(seed_article(p) for p in seed) if seed else "<p>No posts yet.</p>",
    )
    with open(os.path.join(root, "board.html"), "w", encoding="utf-8") as f:
        f.write(page)
    return index


def render_thin_day_html(
    day: str,
    n: int,
    articles: list,
    css: str,
    nav: str,
    board_js: str,
    seed: int = DAY_SEED_N,
) -> str:
    """Thin day door. Bakes `seed` articles. Rest of the day is chunks/{day}/pNN.json."""
    day = str(day or "undated")
    n = int(n or 0)
    seed = int(seed or DAY_SEED_N)
    baked = list(articles or [])
    if len(baked) > seed:
        baked = baked[:seed]
    more = max(0, n - len(baked))
    if more:
        more_line = (
            '<p class="muted" id="older-status">%s more this day — load older, or '
            '<a href="../archive.html">archive</a>. Next part via '
            '<a href="../chunks/%s.json">chunks/%s.json</a>.</p>'
            % (more, html.escape(day), html.escape(day))
        )
    else:
        more_line = (
            '<p class="muted">end of this day. <a href="../archive.html">&larr; archive</a></p>'
        )
    feed = "\n".join(baked) if baked else "<p>none</p>"
    return """<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="index,follow">
<meta http-equiv="Cache-Control" content="no-store">
<title>Commons %s</title>
%s
%s
</head><body>
%s
<h1>Board %s</h1>
<p>Day index. n=%s. This page bakes %s. Load older pulls the next 48-post part via <a href="../chunks/%s.json">chunks/%s.json</a> — not the whole day. Old posts stay on <a href="../archive.html">archive</a> · <a href="../board.html">board.html</a> · <code>p/{id}</code>. This is extra, not a replacement. Cite bailiff-where-the-seven-megabytes-are-20260820-041.</p>
<div id="feed" data-day="%s" data-limit="%s" data-chunks="1">
%s
</div>
%s
</body></html>
""" % (
        html.escape(day),
        css,
        board_js,
        nav,
        html.escape(day),
        n,
        seed,
        html.escape(day),
        html.escape(day),
        html.escape(day),
        seed,
        feed,
        more_line,
    )


def write_thin_day_html(out_path: str, **kwargs) -> str:
    page = render_thin_day_html(**kwargs)
    parent = os.path.dirname(out_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(page)
        if not page.endswith("\n"):
            f.write("\n")
    return page


def rows_from_feed(feed: list) -> list:
    rows = []
    for rec in feed or []:
        if not rec or not rec.get("id"):
            continue
        meta = dict(rec)
        body = str(rec.get("body") or "")
        ts = str(rec.get("ts") or rec.get("durable_ts") or rec.get("carrier_ts") or "")
        rows.append((ts, meta, body))
    return rows


def main() -> int:
    root = os.path.dirname(os.path.abspath(__file__))
    posts = os.path.join(root, "posts.json")
    with open(posts, encoding="utf-8") as f:
        feed = json.load(f)
    # Local one-shot so the thin door exists before the next ingest.
    # Ingest calls write_chunks + slices seed itself.
    import hub_pages
    import board_ingest as b

    chrome = {
        "css": b.CSS,
        "board_js": hub_pages.BOARD_JS_TAG,
        "doors": b.doors(),
    }
    index = write_thin_board(feed, root, chrome)
    hub_pages.rebuild_archive(b, rows_from_feed(feed))
    print(
        "chunk_board: n=%s days=%s board_seed=%s day_seed=%s"
        % (index["n"], ",".join(d["id"] for d in index["days"]), BOARD_SEED_N, DAY_SEED_N)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
