from __future__ import annotations

import csv
import hashlib
import io
import json
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Iterable, Mapping, Sequence

VERSION = "delivery-backplanner/v1"
MAX_TASKS = 24
MAX_RESOURCES = 16
MAX_CALENDARS = 8
MAX_HORIZON_DAYS = 366
MAX_COMMITMENTS = 256
MAX_SEARCH_LIMIT = 2_000_000
MAX_ID_LEN = 80


class BackplannerError(ValueError):
    pass
