#!/usr/bin/env python3
from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from studio import render_project

for path in sorted(HERE.glob("project_*.json")):
    output = HERE / "exports" / (path.stem + ".mp4")
    result = render_project(path, output)
    print(path.name, result["probe"]["format"]["duration"], result["probe"]["format"]["size"])
