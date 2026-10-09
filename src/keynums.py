"""
keynums.py - tiny key-value store (outputs/tables/key_numbers.json).

Every analysis script saves the numbers it computes here; the README and INTERVIEW_NOTES are
rendered from this file (step 10). That is how we guarantee: no number in the docs is hand-typed.
(Named keynums, not numbers, so it does not clash with Python's standard-library 'numbers' module.)
"""
import json

import numpy as np

import config as cfg

PATH = cfg.TABLES / "key_numbers.json"


def _plain(v):
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return None if np.isnan(v) else float(v)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    if isinstance(v, float) and np.isnan(v):
        return None
    return v


def load():
    return json.loads(PATH.read_text(encoding="utf-8")) if PATH.exists() else {}


def save(new_values):
    """Merge new_values into the JSON file (existing keys are overwritten)."""
    cfg.ensure_dirs()
    data = load()
    data.update({k: _plain(v) for k, v in new_values.items()})
    PATH.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    return data
