import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from . import authority as a
from .test_authority import HostAuthority, NOW, packet


class CurrentSurfaceTests(unittest.TestCase):
    def test_current_helper_has_no_registry_injection_parameter(self):
        with tempfile.TemporaryDirectory() as td:
            host = HostAuthority(Path(td)); p = packet(); reg = host.sign(p)
            with patch.object(a, "_host_paths", return_value=host.paths):
                with self.assertRaises(TypeError):
                    a._compile_current_at(p, NOW, registry=reg)


if __name__ == "__main__":
    unittest.main()
