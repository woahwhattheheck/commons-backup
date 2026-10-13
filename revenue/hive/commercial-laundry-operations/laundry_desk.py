from __future__ import annotations

"""Public import surface for the commercial laundry operations desk.

The public facade and ``laundry_desk_core`` intentionally expose the exact same
class object.  There is no second implementation layer whose semantics can
drift or be recovered through MRO/alternate-loader tricks.
"""

import laundry_desk_core as _core

for _name, _value in vars(_core).items():
    if not _name.startswith("__"):
        globals()[_name] = _value

del _name, _value
