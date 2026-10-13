#!/usr/bin/env python3
# host/muhl_world_mouth.py
# World System on the Commons mouth. Carrier, not the computer.
# Buttons = GET + die. Does not relaunch Habitat/World System exe.
# Does not start bitserve / loom_serve / foundry HTTP / 10-wide.
# Never fire 337. Never light 7913. Never pulse titan 78. Never mmap titan/dc body.
# Never notepad titan.gguf / muhlnickel_dc.mno / dc.mno.

from __future__ import annotations

import html as htmlmod
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

DESKTOP = Path(r"C:\Users\lucys\Desktop")
GO = DESKTOP / "MUHL_GO"
LDA = DESKTOP / "LocalDeviceAgent"
HOST = LDA / "host"
LLM = Path(r"C:\llm")
DC = DESKTOP / "MUHL_DATACENTER"
APP = DESKTOP / "MUHLNICKEL_APP"
WORLD_PY = Path(r"C:\Users\lucys\AppData\Local\MuhlnickelWorldSystem\MuhlnickelWorldSystem\bryce_face.py")
NOTEPAD_CAP = 2_000_000
HTML_CAP = 8_000_000
REFUSE = frozenset({"titan.gguf", "muhlnickel_dc.mno", "dc.mno"})

# id, group, label, kind, path_or_key
# kind: html | card | snap | act | cut | local | dark
CATALOG = [
    ("commons-board", "COMMONS", "Commons board", "card", str(GO / "COMMONS_BOARD.md")),
    ("table-board", "COMMONS", "TABLE BOARD", "card", str(DESKTOP / "MUHL_COMMONS" / "TABLE" / "BOARD.md")),
    ("help", "COMMONS", "mouth help.txt", "act", "help"),
    ("say", "COMMONS", "table mail say", "act", "say"),
    ("instant-dl-test", "BRYCE TAB", "INSTANT_DL_TEST", "card", str(GO / "INSTANT_DL_TEST.md")),
    ("instant-download", "BRYCE TAB", "INSTANT DOWNLOAD", "card", str(GO / "INSTANT_DOWNLOAD.md")),
    ("film-organ", "BRYCE TAB", "FILM ORGAN", "card", str(GO / "FILM_ORGAN.md")),
    ("film-do", "BRYCE TAB", "FILM DO", "card", str(GO / "FILM_DO.md")),
    ("dc-drive", "BRYCE TAB", "DC DRIVE", "card", str(GO / "DC_DRIVE.md")),
    ("dc-surface-md", "BRYCE TAB", "DC SURFACE", "card", str(GO / "DC_SURFACE.md")),
    ("live-mouths", "BRYCE TAB", "LIVE MOUTHS", "card", str(GO / "LIVE_MOUTHS.md")),
    ("socket-go", "BRYCE TAB", "SOCKET GO", "card", str(GO / "SOCKET_GO.md")),
    ("film-go", "BRYCE TAB", "FILM GO", "card", str(GO / "FILM_GO.md")),
    ("compress-go", "BRYCE TAB", "COMPRESS GO", "card", str(GO / "COMPRESS_GO.md")),
    ("mouths-go", "BRYCE TAB", "MOUTHS GO", "card", str(GO / "MOUTHS_GO.md")),
    ("letter-go", "BRYCE TAB", "LETTER GO", "card", str(GO / "LETTER_GO.md")),
    ("dry-walls", "BRYCE TAB", "DRY WALLS", "card", str(GO / "DRY_WALLS.md")),
    ("unfinished", "BRYCE TAB", "UNFINISHED", "card", str(GO / "UNFINISHED.md")),
    ("grok-play", "BRYCE TAB", "GROK PLAY", "card", str(GO / "GROK_PLAY.md")),
    ("council", "BRYCE TAB", "COUNCIL", "card", str(GO / "COUNCIL.md")),
    ("path-to-profit", "BRYCE TAB", "PATH TO PROFIT", "card", str(GO / "PATH_TO_PROFIT.md")),
    ("words", "BRYCE TAB", "WORDS", "card", str(GO / "WORDS.md")),
    ("surface-dc-md", "BRYCE TAB", "SURFACE DC card", "card", str(GO / "SURFACE_DC.md")),
    ("lda-on-muhl", "BRYCE TAB", "LDA ON MUHL", "card", str(GO / "LDA_ON_MUHL.md")),
    ("surface-dc-mouths", "BRYCE TAB", "SURFACE DC mouths", "act", "surface_dc"),
    ("playtime-letter", "BRYCE TAB", "Playtime / letter", "card", str(GO / "PLAYTIME_AND_LETTER.md")),
    ("muhl-post", "BRYCE TAB", "MUHL_POST", "card", str(GO / "MUHL_POST.md")),
    ("phase0", "BRYCE TAB", "Phase 0", "card", str(GO / "MUHL_POST_PHASE0.md")),
    ("proven", "BRYCE TAB", "PROVEN", "card", str(GO / "PROVEN.md")),
    ("session-todo", "BRYCE TAB", "SESSION TODO", "card", str(GO / "SESSION_TODO.md")),
    ("mail-surface", "BRYCE TAB", "Mail surface", "act", "mail_surface"),
    ("grok-mail", "BRYCE TAB", "Grok mail", "act", "grok_mail"),
    ("catch-score", "BRYCE TAB", "CATCH_SCORE", "card", str(GO / "CATCH_SCORE.md")),
    ("reservoirs", "BRYCE TAB", "reservoirs", "card", str(GO / "ELECTRON_RESERVOIRS.md")),
    ("burn", "BRYCE TAB", "burn", "card", str(GO / "BURN_PROOF.md")),
    ("compress-expand", "BRYCE TAB", "compress-expand", "card", str(GO / "COMPRESS_EXPAND.md")),
    ("germ", "BRYCE TAB", "Instant Download / germ", "card", str(GO / "INSTANT_DOWNLOAD.md")),
    ("mirror", "BRYCE TAB", "Mirror Organ", "card", str(GO / "MIRROR_ORGAN.md")),
    ("engine", "BRYCE TAB", "The Engine", "card", str(GO / "THE_ENGINE.md")),
    ("live-size", "BRYCE TAB", "live computer size", "act", "live_size"),
    ("factory-packed", "BRYCE TAB", "factory packed except 7913", "act", "factory"),
    ("grep", "BRYCE TAB", "grep 1s/0s", "act", "grep"),
    ("containers", "BRYCE TAB", "containers / muhl_cli", "act", "containers"),
    ("bully", "BRYCE TAB", "bully", "card", str(GO / "CLAUDE_NOSE.md")),
    ("spatent", "BRYCE TAB", "spatent", "card", str(GO / "PROVISIONAL_SESSION.md")),
    ("grounding", "BRYCE TAB", "grounding", "card", str(GO / "SESSION_GROUNDING.md")),
    ("mailbox", "BRYCE TAB", "mailbox 1s and 0s", "act", "mailbox"),
    ("size", "BRYCE TAB", "size (it moves)", "act", "header"),
    ("factory", "BRYCE TAB", "factory", "act", "factory"),
    ("witness", "BRYCE TAB", "witness NEED_BRYCE", "card", str(GO / "MUHL_WITNESS.md")),
    ("fable-ideas", "BRYCE TAB", "fable ideas", "card", str(GO / "DROOL_FABLE.md")),
    ("grow-dead", "BRYCE TAB", "grow is dead", "card", str(GO / "NO_GROW_RESTART.md")),
    ("grow", "BRYCE TAB", "grow surface", "act", "grow"),
    ("size-must-move", "BRYCE TAB", "SIZE MUST MOVE", "card", str(GO / "SIZE_MUST_MOVE.md")),
    ("fold-surface", "BRYCE TAB", "FOLD SURFACE", "card", str(GO / "FOLD_SURFACE.md")),
    ("live-computer", "BRYCE TAB", "open the live computer", "act", "header"),
    ("titan-surface", "BRYCE TAB", "titan surface (text, no mmap)", "act", "titan_surface"),
    ("distro-surface", "BRYCE TAB", "distro surface (text, no mmap)", "act", "distro_surface"),
    ("on-pc-inventory", "BRYCE TAB", "on this pc inventory", "act", "inventory"),
    ("github", "BRYCE TAB", "github", "card", "https://github.com/woahwhattheheck/LocalDeviceAgent"),
    ("drool", "BRYCE TAB", "drool", "card", str(GO / "DROOL_FABLE.md")),
    ("dc-use", "BRYCE TAB", "dc use", "card", str(GO / "DC_USE.md")),
    ("operator", "BRYCE TAB", "operator for parent", "card", str(GO / "OPERATOR_FOR_PARENT.md")),
    ("subagent", "BRYCE TAB", "subagent card", "card", str(GO / "SUBAGENT_PROMPT_CARD.md")),
    ("distro", "BRYCE TAB", "distro", "local", str(DESKTOP / "MUHLNICKEL_DISTRO" / "muhlnickel.mno")),
    ("titan", "BRYCE TAB", "titan", "dark", "reveal titan.gguf refused"),
    ("electrons", "BRYCE TAB", "electrons NEED_BRYCE", "card", str(GO / "ELECTRON_REQUEST_PROPOSAL.md")),
    ("on-this-pc", "BRYCE TAB", "on this pc", "card", str(GO / "ON_THIS_PC.md")),
    ("now", "BRYCE TAB", "now", "card", str(GO / "NOW.md")),
    ("datacenter-mno", "BRYCE TAB", "datacenter mno", "card", str(GO / "DATACENTER_MNO.md")),
    ("all-bits", "BRYCE TAB", "all bits", "cut", "bitserve resident mmap of titan. not started."),
    ("loom", "BRYCE TAB", "loom", "cut", "loom_serve resident reader. not started."),
    ("copy-the-file", "BRYCE TAB", "copy-the-file", "card", str(LDA / "sku" / "README.md")),
    ("surface-visor", "BRYCE TAB", "surface (stat only)", "act", "live_size"),
    ("json-door", "BRYCE TAB", "the json", "local", "Command Deck tab in Habitat. not this mouth."),
    ("maze", "VISORS", "maze", "html", str(DESKTOP / "MUHLNICKEL.html")),
    ("maze-app", "VISORS", "APP MUHLNICKEL.html", "html", str(APP / "MUHLNICKEL.html")),
    ("world-visor", "VISORS", "WORLD_VISOR", "html", str(GO / "WORLD_VISOR.html")),
    ("binary-viewer", "VISORS", "binary viewer", "html", str(APP / "binary_viewer.html")),
    ("atlas", "VISORS", "atlas", "html", str(DESKTOP / "oneshotjustdoitdontstop" / "MUHL_ATLAS.html")),
    ("habitat", "VISORS", "habitat", "local", str(DESKTOP / "Muhlnickel Habitat.lnk")),
    ("foundry-forever", "VISORS", "foundry forever", "local", str(DESKTOP / "Muhlnickel Foundry Forever.lnk")),
    ("deepworld", "VISORS", "deepworld", "local", str(DESKTOP / "Muhlnickel Deepworld.lnk")),
    ("demos", "VISORS", "demos", "html", str(DESKTOP / "MUHLNICKEL_DEMOS" / "index.html")),
    ("archetypes", "VISORS", "archetypes", "html", str(DESKTOP / "MUHLNICKEL_INVENTION_BURST" / "MUHLNICKEL_ARCHITECTURES.html")),
    ("answer-watcher", "VISORS", "answer watcher", "html", str(APP / "answer_watcher.html")),
    ("genome-viewer", "VISORS", "genome viewer", "html", str(APP / "genome_viewer.html")),
    ("selfclock-viewer", "VISORS", "selfclock viewer", "html", str(APP / "selfclock_viewer.html")),
    ("control-surface", "VISORS", "control surface", "html", str(DESKTOP / "Titan" / "muhl_control.html")),
    ("silicon-atlas", "VISORS", "silicon atlas", "html", str(HOST / "titan-silicon-atlas.html")),
    ("sdc-studio", "VISORS", "SDC Game Studio", "html", str(DESKTOP / "SDC Game Studio.html")),
    ("doom-play", "VISORS", "DOOM play", "html", str(DESKTOP / "DOOM (double-click to play).html")),
    ("pfc-demos", "VISORS", "PFC demos", "html", str(DESKTOP / "PFC_DEMOS" / "index.html")),
    ("titan-html", "VISORS", "titan.html", "html", str(DESKTOP / "Titan" / "titan.html")),
    ("desktop-map", "VISORS", "desktop map", "html", str(DESKTOP / "DESKTOP_MAP_20260808_184521" / "OPEN_ME_DESKTOP_MAP.html")),
    ("hrdst", "VISORS", "HRDST showcase", "html", str(DESKTOP / "MUHLNICKEL_DEMOS" / "hrdst_showcase" / "showcase.html")),
    ("pfc-gallery", "VISORS", "pfc gallery", "html", str(LDA / "docs" / "pfc_gallery.html")),
    ("insights", "VISORS", "insights", "html", str(LDA / "docs" / "insights.html")),
    ("whitebox-report", "VISORS", "white box report", "html", str(HOST / "white-box-report.html")),
    ("circuit-browser", "APP FACES", "circuit browser", "html", str(APP / "circuit_browser.html")),
    ("gate-decoder", "APP FACES", "gate decoder", "html", str(APP / "gate_decoder.html")),
    ("wire-inspector", "APP FACES", "wire inspector", "html", str(APP / "wire_inspector.html")),
    ("ring-inspector", "APP FACES", "ring inspector", "html", str(APP / "ring_inspector.html")),
    ("junction-tracer", "APP FACES", "junction tracer", "html", str(APP / "junction_tracer.html")),
    ("electron-tracker", "APP FACES", "electron tracker", "html", str(APP / "electron_tracker.html")),
    ("clock-domains", "APP FACES", "clock domains", "html", str(APP / "clock_domains.html")),
    ("density-heatmap", "APP FACES", "density heatmap", "html", str(APP / "density_heatmap.html")),
    ("depth-profiler", "APP FACES", "depth profiler", "html", str(APP / "depth_profiler.html")),
    ("substrate-dash", "APP FACES", "substrate dashboard", "html", str(APP / "substrate_dashboard.html")),
    ("registry-dash", "APP FACES", "registry dashboard", "html", str(APP / "registry_dashboard.html")),
    ("inventory", "APP FACES", "inventory", "html", str(APP / "inventory.html")),
    ("reservoir-status", "APP FACES", "reservoir status", "html", str(APP / "reservoir_status.html")),
    ("fab-planner", "APP FACES", "fab planner", "html", str(APP / "fab_planner.html")),
    ("fab-history", "APP FACES", "fab history", "html", str(APP / "fab_history.html")),
    ("genome-revert", "APP FACES", "genome revert", "html", str(APP / "genome_revert.html")),
    ("injection-console", "APP FACES", "injection console", "html", str(APP / "injection_console.html")),
    ("ring-run-console", "APP FACES", "ring run console", "html", str(APP / "ring_run_console.html")),
    ("output-surface", "APP FACES", "output surface", "html", str(APP / "output_surface.html")),
    ("address-map", "APP FACES", "address map", "html", str(APP / "address_map.html")),
    ("dead-gate", "APP FACES", "dead gate detector", "html", str(APP / "dead_gate_detector.html")),
    ("lever-analyzer", "APP FACES", "lever analyzer", "html", str(APP / "lever_analyzer.html")),
    ("string-search", "APP FACES", "string search", "html", str(APP / "string_search.html")),
    ("spec-authority", "APP FACES", "SPEC AUTHORITY", "html", str(APP / "SPEC_AUTHORITY.html")),
    ("muhl-live-view", "APPS", "muhl live view", "local", str(DESKTOP / "MUHL_STATE_ANALYSIS" / "muhl_live_view.py")),
    ("pfc-arcade", "APPS", "pfc arcade", "local", str(HOST / "pfc_arcade.py")),
    ("pfc-desktop", "APPS", "pfc desktop", "local", str(HOST / "pfc_desktop.py")),
    ("lda-edge", "APPS", "LDA edge", "act", "lda_edge"),
    ("working-txt", "SNAPSHOTS", "working.txt", "snap", str(LLM / "sdc_out" / "working.txt")),
    ("answer-json", "SNAPSHOTS", "answer.json", "snap", str(LLM / "sdc_out" / "answer.json")),
    ("ones-not-hex", "SNAPSHOTS", "ONES_NOT_HEX", "snap", str(GO / "ONES_NOT_HEX.txt")),
    ("titan-best-0", "SNAPSHOTS", "titan_best_0", "snap", str(LLM / "models" / "titan_best_0.txt")),
    ("post-ledger", "SNAPSHOTS", "post ledger", "snap", str(GO / "MUHL_POST" / "post_ledger.jsonl")),
    ("dc-fab-journal", "SNAPSHOTS", "dc fab journal", "snap", str(DC / "dc_fab_journal.jsonl")),
    ("live-viewers-folder", "FOLDER", "LIVE_VIEWERS folder", "act", "live_viewers_index"),
    ("demos-doom", "DEMOS", "doom.html", "html", str(DESKTOP / "MUHLNICKEL_DEMOS" / "doom.html")),
    ("demos-life", "DEMOS", "life.html", "html", str(DESKTOP / "MUHLNICKEL_DEMOS" / "life.html")),
    ("demos-tetris", "DEMOS", "tetris.html", "html", str(DESKTOP / "MUHLNICKEL_DEMOS" / "tetris.html")),
    ("all-bits-html", "CUT FEEDS", "all_bits.html (CUT feed)", "cut", str(APP / "live_viewer" / "all_bits.html")),
    ("binary-rain", "CUT FEEDS", "binary_rain.html (CUT feed)", "cut", str(APP / "live_viewer" / "binary_rain.html")),
    ("binary-rain2", "CUT FEEDS", "binary_rain2.html (CUT feed)", "cut", str(APP / "live_viewer" / "binary_rain2.html")),
    ("live-viewer-html", "CUT FEEDS", "live_viewer.html (CUT feed)", "cut", str(APP / "live_viewer" / "live_viewer.html")),
    ("loom-html", "CUT FEEDS", "loom_surface.html (CUT feed)", "cut", str(DESKTOP / "MUHLNICKEL_LOOM" / "loom_surface.html")),
    ("spectator", "CUT FEEDS", "spectator Distro (CUT :7880)", "cut", str(DESKTOP / "MUHLNICKEL_INVENTION_BURST" / "Distro" / "Archetypes" / "muhl_spectator.html")),
    ("spectator-lab", "CUT FEEDS", "spectator BUILD_LAB (CUT :7880)", "cut", str(DESKTOP / "MUHLNICKEL_BUILD_LAB_20260801_025117" / "muhl_spectator.html")),
    ("titan-terminal", "CUT FEEDS", "titan terminal (CUT :7880)", "cut", str(DESKTOP / "MUHLNICKEL_BUILD_LAB_20260801_025117" / "muhl_titan_terminal.html")),
    ("ring-orchestra", "CUT FEEDS", "ring orchestra (CUT :7880)", "cut", str(DESKTOP / "MUHLNICKEL_INVENTION_BURST" / "Distro" / "Archetypes" / "muhl_ring_orchestra.html")),
    ("cut-7883", "CUT PORTS", "ALL BITS :7883 bitserve", "cut", "http://127.0.0.1:7883/all_bits.html"),
    ("cut-7884", "CUT PORTS", "ALL BITS :7884 bitserve alt", "cut", "http://127.0.0.1:7884/all_bits.html"),
    ("cut-7914", "CUT PORTS", "Foundry HTTP :7914", "cut", "http://127.0.0.1:7914/"),
    ("cut-8787", "CUT PORTS", "Foundry Forever :8787 (exe if running)", "local", "http://127.0.0.1:8787/"),
    ("cut-42515", "CUT PORTS", "Habitat :42515 (exe if running)", "local", "http://127.0.0.1:42515/"),
    ("cut-41415", "CUT PORTS", "Deepworld :41415 (exe if running)", "local", "http://127.0.0.1:41415/"),
    ("cut-7860", "CUT PORTS", "lab_ui :7860", "cut", "http://127.0.0.1:7860/"),
    ("cut-8110", "CUT PORTS", "Game Studio server :8110", "cut", "http://127.0.0.1:8110/"),
    ("cut-7862", "CUT PORTS", "White Box :7862", "cut", "http://127.0.0.1:7862/"),
    ("cut-7864", "CUT PORTS", "White Box V2 :7864", "cut", "http://127.0.0.1:7864/"),
    ("cut-7902", "CUT PORTS", "SDC Chat :7902", "cut", "http://127.0.0.1:7902/"),
    ("cut-7866", "CUT PORTS", "Titan Test Bench :7866", "cut", "http://127.0.0.1:7866/"),
    ("cut-7871", "CUT PORTS", "32-bit CPU :7871", "cut", "http://127.0.0.1:7871/"),
    ("cut-7870", "CUT PORTS", "Bitcoin Miner :7870", "cut", "http://127.0.0.1:7870/"),
    ("cut-8733", "CUT PORTS", "control surface :8733", "cut", "http://127.0.0.1:8733/"),
    ("cut-7908", "CUT PORTS", "pfc monitor :7908", "cut", "http://127.0.0.1:7908/"),
    ("cut-7904", "CUT PORTS", "SDC OS :7904", "cut", "http://127.0.0.1:7904/"),
    ("cut-7903", "CUT PORTS", "SDC output :7903", "cut", "http://127.0.0.1:7903/"),
    ("cut-7901", "CUT PORTS", "SDC Playground :7901", "cut", "http://127.0.0.1:7901/"),
    ("cut-7900", "CUT PORTS", "SDC Program Rack :7900", "cut", "http://127.0.0.1:7900/"),
    ("cut-8120", "CUT PORTS", "DOOM on SDC :8120", "cut", "http://127.0.0.1:8120/"),
    ("cut-7863", "CUT PORTS", "DOOM on Titan :7863", "cut", "http://127.0.0.1:7863/"),
    ("world-system-lnk", "LOCAL EXES", "World System .lnk", "local", str(DESKTOP / "Muhlnickel World System.lnk")),
]

BY_ID = {row[0]: row for row in CATALOG}


def _face():
    spec = importlib.util.spec_from_file_location("bryce_face_mouth", WORLD_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run_die(argv, cwd, timeout=45):
    try:
        p = subprocess.run(argv, cwd=str(cwd), capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace")
        out = (p.stdout or "") + (("\n" + p.stderr) if p.stderr else "")
        return "exit %s\n%s" % (p.returncode, out[-12000:])
    except subprocess.TimeoutExpired:
        return "TIMEOUT %ss. button dies. no stay-alive." % timeout
    except OSError as exc:
        return str(exc)


def _exists_line(path):
    p = Path(path)
    if str(path).startswith("http://") or str(path).startswith("https://"):
        return "url " + path
    if not p.exists():
        return "MISSING  " + path
    try:
        n = p.stat().st_size if p.is_file() else 0
    except OSError:
        n = -1
    tag = "DIR" if p.is_dir() else ("%d B" % n)
    return "ON DISK  %s  %s" % (tag, path)


def catalog_text():
    lines = [
        "WORLD SYSTEM ON THE MOUTH — carrier, not the computer",
        "Habitat buttons, visors, app faces, snaps. GET + die.",
        "CUT = listed, not started (bitserve/loom/foundry HTTP/10-wide).",
        "DARK = refused (titan body / 100GB / fire 337 / 7913 / titan 78).",
        "LOCAL = exe/.lnk on this PC. Mouth will not relaunch World System.",
        "HTML buttons serve the file through this origin (no file://).",
        "",
    ]
    group = None
    for i, g, label, kind, src in CATALOG:
        if g != group:
            group = g
            lines.append("## " + g)
        lines.append("[%s] %s  (%s)" % (i, label, kind))
        if kind in ("html", "card", "snap", "local", "cut") and not str(src).startswith("https://") and kind != "act":
            lines.append("  " + _exists_line(src))
        if kind == "html":
            lines.append("  GET ./world/open/%s" % i)
        elif kind == "card":
            lines.append("  GET ./world/card/%s" % i)
        elif kind == "snap":
            lines.append("  GET ./world/snap/%s" % i)
        elif kind == "act":
            lines.append("  GET ./world/act/%s          PREVIEW (no write)" % i)
            lines.append("  GET ./world/act/%s?confirm=1&id=<unique>  ACT once" % i)
        elif kind in ("cut", "dark", "local"):
            lines.append("  GET ./world/why/%s" % i)
        lines.append("")
    lines.append("n=%d" % len(CATALOG))
    lines.append("")
    lines.append("CUT localhost feeds are listed above as why/ buttons. Mouth does not start them.")
    lines.append("JSON: GET ./world.json")
    return "\n".join(lines) + "\n"


def catalog_json():
    items = []
    for i, g, label, kind, src in CATALOG:
        verb = {"html": "open", "card": "card", "snap": "snap", "act": "act"}.get(kind, "why")
        items.append({
            "id": i,
            "group": g,
            "label": label,
            "kind": kind,
            "src": src,
            "get": "./world/%s/%s" % (verb, i),
        })
    return json.dumps({"n": len(items), "carrier": "commons mouth", "items": items}, indent=2) + "\n"


def catalog_html(token):
    parts = [
        "<!DOCTYPE html><html><head><meta charset=utf-8>",
        "<meta name=robots content='index,follow'>",
        "<title>World System mouth</title>",
        "<style>body{font:16px/1.4 sans-serif;max-width:70rem;margin:1rem auto;padding:0 1rem}",
        "a.btn{display:inline-block;margin:.2rem;padding:.45rem .7rem;background:#152638;color:#38e5d0;text-decoration:none}",
        "h2{margin-top:1.2rem}</style></head><body>",
        "<h1>World System mouth</h1>",
        "<p>Carrier. Not the computer. GET + die. CUT feeds are listed and not started.</p>",
        "<p><a href='/%s/world.txt'>world.txt</a> · <a href='/%s/help.txt'>help</a> · <a href='/%s/board.md'>board</a></p>" % (token, token, token),
    ]
    group = None
    for i, g, label, kind, src in CATALOG:
        if g != group:
            group = g
            parts.append("<h2>%s</h2>" % htmlmod.escape(g))
        if kind == "html":
            href = "/%s/world/open/%s" % (token, i)
        elif kind == "card":
            href = "/%s/world/card/%s" % (token, i)
        elif kind == "snap":
            href = "/%s/world/snap/%s" % (token, i)
        elif kind == "act":
            href = "/%s/world/act/%s" % (token, i)
        else:
            href = "/%s/world/why/%s" % (token, i)
        parts.append("<a class=btn href='%s'>%s · %s</a>" % (href, htmlmod.escape(label), kind))
    parts.append("</body></html>")
    return "\n".join(parts)


def _read_capped(path, cap):
    p = Path(path)
    if p.name in REFUSE:
        return 403, "REFUSE %s\n" % p.name, "text/plain; charset=utf-8"
    if not p.is_file():
        return 404, "missing\n%s\n" % p, "text/plain; charset=utf-8"
    n = p.stat().st_size
    if n > cap:
        return 413, "too big %d (cap %d)\n%s\n" % (n, cap, p), "text/plain; charset=utf-8"
    data = p.read_bytes()
    return 200, data, None


def handle_open(eid):
    row = BY_ID.get(eid)
    if not row:
        return 404, "no id\n", "text/plain; charset=utf-8"
    _i, _g, label, kind, src = row
    if kind != "html":
        return 400, "not html. kind=%s\n" % kind, "text/plain; charset=utf-8"
    code, body, ctype = _read_capped(src, HTML_CAP)
    if code != 200:
        return code, body if isinstance(body, str) else body.decode("utf-8", "replace"), "text/plain; charset=utf-8"
    return 200, body, "text/html; charset=utf-8"


def handle_card(eid):
    row = BY_ID.get(eid)
    if not row:
        return 404, "no id\n", "text/plain; charset=utf-8"
    _i, _g, label, kind, src = row
    if str(src).startswith("https://"):
        return 200, "OPEN  %s\n%s\n" % (label, src), "text/plain; charset=utf-8"
    code, body, _ = _read_capped(src, NOTEPAD_CAP)
    if code != 200:
        return code, body if isinstance(body, str) else body.decode("utf-8", "replace"), "text/plain; charset=utf-8"
    text = body.decode("utf-8", "replace")
    return 200, "%s\n%s\n\n%s" % (label, src, text), "text/plain; charset=utf-8"


def handle_snap(eid):
    return handle_card(eid)


def handle_why(eid):
    row = BY_ID.get(eid)
    if not row:
        return 404, "no id\n", "text/plain; charset=utf-8"
    i, g, label, kind, src = row
    lines = [
        "ID %s" % i,
        "GROUP %s" % g,
        "LABEL %s" % label,
        "KIND %s" % kind,
        "SRC %s" % src,
        _exists_line(src) if not str(src).startswith("http") else src,
        "",
        "CUT = not started (bitserve/loom/foundry HTTP/spectator :7880).",
        "DARK = titan/dc body / fire 337 / light 7913 / pulse 78.",
        "LOCAL = Habitat/Deepworld/Foundry/World System exe. Mouth does not relaunch them.",
        "This listing is the surface. Nothing hidden.",
    ]
    return 200, "\n".join(lines) + "\n", "text/plain; charset=utf-8"


def handle_preview(eid):
    row = BY_ID.get(eid)
    if not row:
        return 404, "no id\n", "text/plain; charset=utf-8"
    i, g, label, kind, src = row
    extra = {
        "mailbox": "SURFACE muhlnickel_dc.mno bounded seek (dest 337 READ). Does not fire 337.",
        "header": "SURFACE dc header. no inject.",
        "live_size": "stat size. no mmap body.",
        "factory": "SURFACE factory dests. does not light 7913.",
        "grep": "SURFACE 1s/0s bounded.",
        "containers": "muhl_cli slots+surface. dies.",
        "mail_surface": "surface table mail English. does not smash commons.mno.",
        "grok_mail": "surface grok mail English. does not smash commons.mno.",
        "surface_dc": "muhl_surface_dc.py bounded. no fire.",
        "lda_edge": "muhl_lda_edge_add.py once and die.",
        "live_viewers_index": "listdir LIVE_VIEWERS. no exe launch.",
        "help": "no file write.",
        "say": "does not post. use ./say?from=&to=&body=&id=",
        "grow": "grow_surface text. no restart.",
        "titan_surface": "text only. no mmap titan.",
        "distro_surface": "text only. no mmap distro body.",
        "inventory": "inventory_surface text.",
    }.get(src, "")
    lines = [
        "PREVIEW %s" % i,
        "This GET did NOT act. Listings are read-only.",
        "label: %s" % label,
        "kind: %s" % kind,
        "src: %s" % src,
    ]
    if kind == "act":
        lines.append(extra or "act key has no extra map; confirm still required.")
        lines.append("TO ACT: GET ./world/act/%s?confirm=1" % i)
    elif kind in ("cut", "dark", "local"):
        lines.append("CUT/DARK/LOCAL. confirm will still not start bitserve / Habitat / fire 337 / mmap titan.")
        lines.append("GET ./world/why/%s" % i)
    elif kind in ("html", "card", "snap"):
        lines.append("READ file through mouth. cap html 8MB / card-snap 2MB. refuses titan.gguf / dc.mno.")
        lines.append("GET ./world/%s/%s" % ({"html": "open", "card": "card", "snap": "snap"}[kind], i))
    lines.append("Page load must not start CUT/DARK/LOCAL, relaunch Habitat, mmap titan, or fire 337.")
    return 200, "\n".join(lines) + "\n", "text/plain; charset=utf-8"


def handle_act(eid):
    row = BY_ID.get(eid)
    if not row:
        return 404, "no id\n", "text/plain; charset=utf-8"
    key = row[4]
    if key == "help":
        return 200, "see ./help.txt and ./world.txt\n", "text/plain; charset=utf-8"
    if key == "say":
        return 200, "POST via GET ./say?from=KITE&to=GROK&body=...\n", "text/plain; charset=utf-8"
    if key == "live_viewers_index":
        root = DESKTOP / "LIVE_VIEWERS"
        if not root.is_dir():
            return 404, "LIVE_VIEWERS missing\n", "text/plain; charset=utf-8"
        names = sorted(os.listdir(root))[:200]
        return 200, "LIVE_VIEWERS n=%d\n%s\n" % (len(names), "\n".join(names)), "text/plain; charset=utf-8"
    if key == "surface_dc":
        return 200, _run_die([sys.executable, str(HOST / "muhl_surface_dc.py")], HOST), "text/plain; charset=utf-8"
    if key == "mail_surface":
        return 200, _run_die([sys.executable, str(HOST / "muhl_post_surface.py")], HOST, 60), "text/plain; charset=utf-8"
    if key == "grok_mail":
        return 200, _run_die([sys.executable, str(HOST / "muhl_grok_mail.py")], HOST), "text/plain; charset=utf-8"
    if key == "containers":
        a = _run_die([sys.executable, str(HOST / "muhl_cli.py"), "slots"], HOST)
        b = _run_die([sys.executable, str(HOST / "muhl_cli.py"), "surface"], HOST)
        return 200, a + "\n\n" + b, "text/plain; charset=utf-8"
    if key == "lda_edge":
        return 200, _run_die([sys.executable, str(HOST / "muhl_lda_edge_add.py")], HOST), "text/plain; charset=utf-8"
    try:
        face = _face()
    except Exception as exc:
        return 500, "could not load bryce_face: %s\n" % exc, "text/plain; charset=utf-8"
    fn = {
        "live_size": face.live_size_only,
        "mailbox": face.mailbox_surface,
        "header": face.header_surface,
        "factory": face.factory_surface,
        "grep": face.grep_surface,
        "grow": face.grow_surface,
        "titan_surface": face.titan_surface,
        "distro_surface": face.distro_surface,
        "inventory": face.inventory_surface,
    }.get(key)
    if fn is None:
        return 400, "no act %s\n" % key, "text/plain; charset=utf-8"
    try:
        return 200, fn() + "\n", "text/plain; charset=utf-8"
    except Exception as exc:
        return 500, str(exc) + "\n", "text/plain; charset=utf-8"
