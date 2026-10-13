#!/usr/bin/env python3
"""Local-first commercial waste route, exception, and invoice-draft desk."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import sqlite3
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class DeskError(Exception):
    pass


class ValidationError(DeskError):
    pass


class OperationConflict(DeskError):
    pass


class StateConflict(DeskError):
    pass


class BillingBlocked(DeskError):
    pass


MAX_SQLITE_INTEGER = (1 << 63) - 1
SYSTEM_LOCAL_TIMEZONE = "SYSTEM_LOCAL"


def canon(v: Any) -> str:
    return json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(v: Any) -> str:
    return hashlib.sha256(canon(v).encode()).hexdigest()


def ident(v: Any, field: str) -> str:
    if not isinstance(v, str) or not v.strip() or len(v.strip()) > 128:
        raise ValidationError(f"{field} must be a non-empty string <=128 chars")
    return v.strip()


def text(v: Any, field: str) -> str:
    if not isinstance(v, str) or not v.strip() or len(v.strip()) > 240:
        raise ValidationError(f"{field} must be a non-empty string <=240 chars")
    return v.strip()


def money(v: Any, field: str) -> int:
    if (
        isinstance(v, bool)
        or not isinstance(v, int)
        or v < 0
        or v > MAX_SQLITE_INTEGER
    ):
        raise ValidationError(
            f"{field} must be a non-negative SQLite-safe integer minor-unit amount"
        )
    return v


def iso(v: Any, field: str) -> str:
    if not isinstance(v, str):
        raise ValidationError(f"{field} must be canonical YYYY-MM-DD")
    try:
        d = date.fromisoformat(v)
    except ValueError as exc:
        raise ValidationError(f"{field} must be canonical YYYY-MM-DD") from exc
    if d.isoformat() != v:
        raise ValidationError(f"{field} must be canonical YYYY-MM-DD")
    return v


def currency(v: Any) -> str:
    if not isinstance(v, str) or len(v) != 3 or not v.isascii() or not v.isalpha():
        raise ValidationError("currency must be a 3-letter ASCII code")
    return v.upper()


def business_timezone(v: Any) -> str:
    if not isinstance(v, str) or not v.strip() or len(v.strip()) > 128:
        raise ValidationError(
            "business_timezone must be SYSTEM_LOCAL, UTC, or an IANA timezone name"
        )
    value = v.strip()
    if value in {SYSTEM_LOCAL_TIMEZONE, "UTC"}:
        return value
    try:
        ZoneInfo(value)
    except ZoneInfoNotFoundError as exc:
        raise ValidationError(
            "business_timezone is unavailable on this host; use SYSTEM_LOCAL, UTC, "
            "or an installed IANA timezone name"
        ) from exc
    return value


SCHEMA = """
CREATE TABLE IF NOT EXISTS workspace_settings(
 key TEXT PRIMARY KEY,
 value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS customers(id TEXT PRIMARY KEY,name TEXT NOT NULL,currency TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sites(id TEXT PRIMARY KEY,customer_id TEXT NOT NULL REFERENCES customers(id),name TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS containers(id TEXT PRIMARY KEY,site_id TEXT NOT NULL REFERENCES sites(id),label TEXT NOT NULL,container_type TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS plans(id TEXT PRIMARY KEY,container_id TEXT NOT NULL REFERENCES containers(id),weekday INTEGER NOT NULL CHECK(weekday BETWEEN 0 AND 6),service_code TEXT NOT NULL,price_minor INTEGER NOT NULL CHECK(price_minor>=0),active INTEGER NOT NULL DEFAULT 1 CHECK(active IN(0,1)));
CREATE TABLE IF NOT EXISTS routes(id TEXT PRIMARY KEY,service_date TEXT NOT NULL UNIQUE);
CREATE TABLE IF NOT EXISTS stops(
 id TEXT PRIMARY KEY,route_id TEXT NOT NULL REFERENCES routes(id),plan_id TEXT NOT NULL REFERENCES plans(id),
 customer_id TEXT NOT NULL REFERENCES customers(id),site_id TEXT NOT NULL REFERENCES sites(id),
 container_id TEXT NOT NULL REFERENCES containers(id),sequence INTEGER NOT NULL,
 status TEXT NOT NULL CHECK(status IN('PENDING','SERVICE_CONFIRMED','EXCEPTION_OPEN','RESOLVED_NO_CHARGE','RESOLVED_BILLABLE')),
 exception_code TEXT,resolution TEXT,makeup_service_date TEXT,
 charge_minor INTEGER NOT NULL DEFAULT 0 CHECK(charge_minor>=0),UNIQUE(route_id,plan_id));
CREATE TABLE IF NOT EXISTS invoice_drafts(
 id TEXT PRIMARY KEY,customer_id TEXT NOT NULL REFERENCES customers(id),period_start TEXT NOT NULL,period_end TEXT NOT NULL,
 total_minor INTEGER NOT NULL CHECK(total_minor>=0),currency TEXT NOT NULL,receipt_digest TEXT NOT NULL,payload_json TEXT NOT NULL,
 UNIQUE(customer_id,period_start,period_end));
CREATE TABLE IF NOT EXISTS invoice_lines(
 invoice_id TEXT NOT NULL REFERENCES invoice_drafts(id),
 stop_id TEXT NOT NULL UNIQUE REFERENCES stops(id),
 PRIMARY KEY(invoice_id,stop_id)
);
CREATE TABLE IF NOT EXISTS operations(op_key TEXT PRIMARY KEY,action TEXT NOT NULL,request_digest TEXT NOT NULL,result_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events(
 id INTEGER PRIMARY KEY AUTOINCREMENT,op_key TEXT NOT NULL UNIQUE REFERENCES operations(op_key) DEFERRABLE INITIALLY DEFERRED,
 event_type TEXT NOT NULL,entity_kind TEXT NOT NULL,entity_id TEXT NOT NULL,payload_json TEXT NOT NULL,event_digest TEXT NOT NULL);
CREATE TRIGGER IF NOT EXISTS workspace_settings_no_update BEFORE UPDATE ON workspace_settings BEGIN SELECT RAISE(ABORT,'workspace settings are immutable'); END;
CREATE TRIGGER IF NOT EXISTS workspace_settings_no_delete BEFORE DELETE ON workspace_settings BEGIN SELECT RAISE(ABORT,'workspace settings are immutable'); END;
CREATE TRIGGER IF NOT EXISTS invoice_drafts_no_update BEFORE UPDATE ON invoice_drafts BEGIN SELECT RAISE(ABORT,'invoice drafts are immutable'); END;
CREATE TRIGGER IF NOT EXISTS invoice_drafts_no_delete BEFORE DELETE ON invoice_drafts BEGIN SELECT RAISE(ABORT,'invoice drafts are immutable'); END;
CREATE TRIGGER IF NOT EXISTS invoice_lines_no_update BEFORE UPDATE ON invoice_lines BEGIN SELECT RAISE(ABORT,'invoice line custody is immutable'); END;
CREATE TRIGGER IF NOT EXISTS invoice_lines_no_delete BEFORE DELETE ON invoice_lines BEGIN SELECT RAISE(ABORT,'invoice line custody is immutable'); END;
CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT,'events are immutable'); END;
CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT,'events are immutable'); END;
"""

