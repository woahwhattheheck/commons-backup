#!/usr/bin/env python3
"""One saved Commons Door exposes the integrated capability surfaces."""
from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parent
INDEX = ROOT / "index.html"
RESOURCES = ROOT / "resources.html"

HUMAN_LINKS = ("./commerce.html", "./orchestration.html")
MACHINE_LINKS = (
    "./revenue/outcome_commerce/manifest.json",
    "./revenue/outcome_commerce/catalog.json",
    "./orchestration/jeffersonville/frameworks.json",
    "./orchestration/jeffersonville/topology.json",
)


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() != "a":
            return
        values = dict(attrs)
        self.links.append((values.get("href", ""), values.get("class", "")))


def links_in(path: Path) -> list[tuple[str, str]]:
    parser = LinkParser()
    parser.feed(path.read_text(encoding="utf-8"))
    return parser.links


def relative_target(source: Path, href: str) -> Path:
    parts = urlsplit(href)
    if parts.scheme or parts.netloc:
        raise AssertionError(f"expected a relative link, got {href}")
    target = (source.parent / parts.path).resolve()
    try:
        target.relative_to(ROOT)
    except ValueError as exc:
        raise AssertionError(f"link escapes the repository: {href}") from exc
    return target


class CapabilityEntrypointTests(unittest.TestCase):
    def test_one_saved_door_has_first_class_capability_buttons(self) -> None:
        index = INDEX.read_text(encoding="utf-8")
        parsed = links_in(INDEX)
        for href in HUMAN_LINKS:
            # Catalog prose may repeat a destination; navigation buttons stay unique.
            matches = [
                css for candidate, css in parsed
                if candidate == href and "door-btn" in css.split()
            ]
            self.assertEqual(len(matches), 1, href)
            self.assertIn("door-btn", matches[0].split(), href)

        self.assertIn(
            "This is the only link the operator should need to save or share.",
            index,
        )
        self.assertIn("crawler-access.json", index)

    def test_common_resources_composes_human_and_machine_surfaces(self) -> None:
        hrefs = {href for href, _css in links_in(RESOURCES)}
        for href in HUMAN_LINKS + MACHINE_LINKS:
            self.assertIn(href, hrefs)

    def test_new_relative_links_resolve_to_checked_in_files(self) -> None:
        for source, hrefs in (
            (INDEX, HUMAN_LINKS),
            (RESOURCES, HUMAN_LINKS + MACHINE_LINKS),
        ):
            for href in hrefs:
                target = relative_target(source, href)
                self.assertTrue(target.is_file(), f"{source.name}: {href}")

    def test_destination_pages_are_indexable_and_return_home(self) -> None:
        for href in HUMAN_LINKS:
            target = relative_target(INDEX, href)
            html = target.read_text(encoding="utf-8")
            head = html[:4096].lower()
            self.assertIn('name="robots"', head, href)
            self.assertIn("index,follow", head, href)
            destination_links = {candidate for candidate, _css in links_in(target)}
            self.assertTrue(
                destination_links.intersection({"./", "./index.html", "index.html"}),
                f"{href} has no Commons-home link",
            )

    def test_entrypoint_truth_labels_match_machine_records(self) -> None:
        resources = RESOURCES.read_text(encoding="utf-8")
        self.assertIn("does not move money", resources)
        self.assertIn("reference-only adapter and benchmark catalog", resources)
        self.assertIn("NOT_DEPLOYED", resources)
        self.assertIn("no data-center build or Rust/Go rewrite is authorized", resources)
        self.assertIn("public open doors", resources)

        frameworks = json.loads(
            relative_target(RESOURCES, MACHINE_LINKS[2]).read_text(encoding="utf-8")
        )
        topology = json.loads(
            relative_target(RESOURCES, MACHINE_LINKS[3]).read_text(encoding="utf-8")
        )
        self.assertEqual(frameworks["deployment_status"], "NOT_DEPLOYED")
        self.assertEqual(topology["deployment_status"], "NOT_DEPLOYED")

    def test_entrypoints_do_not_claim_an_a2a_agent_card(self) -> None:
        combined = INDEX.read_text(encoding="utf-8") + RESOURCES.read_text(encoding="utf-8")
        self.assertNotIn(".well-known/agent-card.json", combined)

    def test_chargeable_checkout_receipt_has_no_extra_blank_line_at_eof(self) -> None:
        """Regression for capability-entrypoints run 33190244507 (line 32 new blank line at EOF)."""
        receipt = ROOT / "p/grok-build-chargeable-checkout-20260828-01.md"
        raw = receipt.read_bytes()
        self.assertTrue(raw.endswith(b"\n"), "POSIX text files end with one newline")
        self.assertFalse(
            raw.endswith(b"\n\n"),
            "extra blank line at EOF fails capability-entrypoints whitespace guard",
        )
        self.assertNotIn(b"\r", raw)
        text = raw.decode("utf-8")
        self.assertTrue(text.endswith("\n"))
        self.assertTrue(text.rstrip("\n"), "receipt body must remain nonempty")
        self.assertNotEqual(text.splitlines()[-1], "")
        correction = ROOT / "p/grok-chargeable-checkout-eof-blank-20260828-01.md"
        correction_raw = correction.read_bytes()
        self.assertTrue(correction_raw.endswith(b"\n"))
        self.assertFalse(correction_raw.endswith(b"\n\n"))
        self.assertIn(b"33190244507", correction_raw)
        self.assertIn(b"1af978d35fb9e87ca7890064f18a04d203778385", correction_raw)

    def test_extra_blank_line_at_eof_fails_git_diff_check(self) -> None:
        receipt = ROOT / "p/grok-build-chargeable-checkout-20260828-01.md"
        good = receipt.read_bytes()
        self.assertFalse(good.endswith(b"\n\n"))
        bad = good.rstrip(b"\n") + b"\n\n"
        self.assertNotEqual(good, bad)
        with tempfile.TemporaryDirectory(prefix="capability-eof-") as tmp:
            repo = Path(tmp)

            def git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
                return subprocess.run(
                    ["git", "-C", str(repo), *args],
                    check=check,
                    capture_output=True,
                    text=True,
                )

            git("init")
            git("config", "user.email", "rivet@example.invalid")
            git("config", "user.name", "RIVET")
            target = repo / "receipt.md"
            target.write_bytes(good)
            git("add", "receipt.md")
            git("commit", "-m", "clean")
            target.write_bytes(bad)
            git("add", "receipt.md")
            git("commit", "-m", "extra eof blank")
            failed = git("diff", "--check", "HEAD^", check=False)
            self.assertNotEqual(failed.returncode, 0)
            blob = failed.stdout + failed.stderr
            self.assertIn("new blank line at EOF", blob)
            target.write_bytes(good)
            git("add", "receipt.md")
            git("commit", "-m", "repair extra eof blank")
            repaired = git("diff", "--check", "HEAD^")
            self.assertEqual(repaired.returncode, 0)
            self.assertNotIn("new blank line at EOF", repaired.stdout + repaired.stderr)

    def test_capability_entrypoints_workflow_keeps_whitespace_guard(self) -> None:
        workflow = (ROOT / ".github/workflows/capability-entrypoints.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("test_capability_entrypoints.py", workflow)
        self.assertIn("git diff --check HEAD^", workflow)
        self.assertIn("open_door_guard.py --diff-file -", workflow)
        self.assertEqual(workflow.count("git diff --check HEAD^"), 1)


if __name__ == "__main__":
    unittest.main()
