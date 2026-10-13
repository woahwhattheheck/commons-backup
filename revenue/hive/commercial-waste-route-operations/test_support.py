#!/usr/bin/env python3

import json
import sqlite3
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path

from desk import (
    BillingBlocked,
    MAX_SQLITE_INTEGER,
    OperationConflict,
    StateConflict,
    ValidationError,
    WasteRouteDesk,
)


MANIFEST = {
    "business_timezone": "UTC",
    "customers": [
        {
            "id": "ACME",
            "name": "Acme Coffee Group",
            "currency": "USD",
            "sites": [
                {
                    "id": "ACME-DOWNTOWN",
                    "name": "Downtown Cafe",
                    "containers": [
                        {
                            "id": "ACME-DOWNTOWN-8YD",
                            "label": "Rear 8yd",
                            "container_type": "front-load 8yd",
                            "plans": [
                                {
                                    "id": "PLAN-ACME-DOWNTOWN",
                                    "weekday": 0,
                                    "service_code": "RECURRENT_PICKUP",
                                    "price_minor": 12900,
                                }
                            ],
                        }
                    ],
                },
                {
                    "id": "ACME-MARKET",
                    "name": "Market Cafe",
                    "containers": [
                        {
                            "id": "ACME-MARKET-4YD",
                            "label": "Dock 4yd",
                            "container_type": "front-load 4yd",
                            "plans": [
                                {
                                    "id": "PLAN-ACME-MARKET",
                                    "weekday": 0,
                                    "service_code": "RECURRENT_PICKUP",
                                    "price_minor": 9900,
                                }
                            ],
                        }
                    ],
                },
            ],
        },
        {
            "id": "BETA",
            "name": "Beta Office Partners",
            "currency": "USD",
            "sites": [
                {
                    "id": "BETA-HQ",
                    "name": "Beta HQ",
                    "containers": [
                        {
                            "id": "BETA-HQ-6YD",
                            "label": "East lot 6yd",
                            "container_type": "front-load 6yd",
                            "plans": [
                                {
                                    "id": "PLAN-BETA-HQ",
                                    "weekday": 0,
                                    "service_code": "RECURRENT_PICKUP",
                                    "price_minor": 14900,
                                }
                            ],
                        }
                    ],
                }
            ],
        },
    ],
}


class WasteRouteDeskTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / "desk.sqlite3")
        self.desk = WasteRouteDesk(self.db)
        self.desk.import_manifest(MANIFEST, "manifest-v2")
        self.today = self.desk.business_date()
        self.current_monday = self.today - timedelta(days=self.today.weekday())
        self.prior_monday = self.current_monday - timedelta(days=7)
        self.next_monday = self.current_monday + timedelta(days=7)

    def tearDown(self):
        if self.desk is not None:
            self.desk.close()
        self.tmp.cleanup()

    def _monday_route(self, day=None, op="route-1"):
        day = self.current_monday if day is None else day
        return self.desk.generate_route(day.isoformat(), op)

    def _settle_customer(self, route, customer_id, prefix):
        stops = [s for s in route["stops"] if s["customer_id"] == customer_id]
        for index, stop in enumerate(stops):
            self.desk.record_stop(
                stop["id"], "SERVICED", f"{prefix}-{index}"
            )
        return stops

