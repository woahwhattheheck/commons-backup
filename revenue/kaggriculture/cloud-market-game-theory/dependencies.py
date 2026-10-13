# SPDX-License-Identifier: Apache-2.0
"""Load accepted frozen receipt math; never instantiate a controller here."""
import hashlib
import importlib.util
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SELL = HERE.parent / 'cloud-titan-composition/vendor/sell'


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def receipt_source():
    path = SELL / 'scheduler.py'
    if hashlib.sha256(path.read_bytes()).hexdigest() != '32c8610c9827d1686a6f831e2c4b6af4c00d32d2aa04dcf25699d976d6d97dd9':
        raise ValueError('Expected the selected frozen SELL scheduler')
    sys.path.insert(0, str(SELL))
    return load(path, 't15_frozen_receipts')


def official_engine(directory):
    ev = load(HERE.parent / 'cloud-eval/evaluate.py', 't15_evaluator')
    engine, hashes = ev.get_engine(directory)
    return ev, engine, hashes
