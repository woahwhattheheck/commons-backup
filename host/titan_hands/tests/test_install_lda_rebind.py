from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "host" / "titan_hands" / "install_lda_emulator.ps1"


class LdaAccessibilityRebindTests(unittest.TestCase):
    def test_reinstall_cycles_only_lda_service_before_readding_it(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        detect = "if ($service -in $parts)"
        preserve = "$others = @($parts | Where-Object { $_ -ne $service })"
        remove = "settings put secure enabled_accessibility_services ($others -join ':')"
        remove_last = "settings delete secure enabled_accessibility_services"
        readd = "$parts += $service"
        commit = "settings put secure enabled_accessibility_services ($parts -join ':')"

        self.assertIn(detect, text)
        self.assertIn(preserve, text)
        self.assertIn(remove, text)
        self.assertIn(remove_last, text)
        self.assertIn(readd, text)
        self.assertIn(commit, text)
        self.assertNotIn("if ($service -notin $parts) { $parts += $service }", text)
        self.assertLess(text.index(detect), text.index(readd))
        self.assertLess(text.index(remove), text.index(readd))
        self.assertLess(text.index(remove_last), text.index(readd))
        self.assertLess(text.index(readd), text.index(commit))


if __name__ == "__main__":
    unittest.main()
