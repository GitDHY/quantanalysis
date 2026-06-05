"""Tests for backtest/history.py — RunHistoryStore + helpers."""

import re
from datetime import datetime
from pathlib import Path

from backtest.history import (
    RunSummary,
    RunDetail,
    RunHistoryStore,
    _hash_strategy_code,
    _hash_config,
    _make_run_id,
)


def test_module_imports_ok():
    """Smoke test: the symbols documented in the spec are importable."""
    assert RunSummary is not None
    assert RunDetail is not None
    assert RunHistoryStore is not None


def test_hash_strategy_code_is_deterministic():
    code = "def strategy():\n    return None\n"
    assert _hash_strategy_code(code) == _hash_strategy_code(code)


def test_hash_strategy_code_differs_on_change():
    a = "def strategy():\n    return None\n"
    b = "def strategy():\n    return {}\n"
    assert _hash_strategy_code(a) != _hash_strategy_code(b)


def test_hash_strategy_code_empty_string_is_handled():
    h = _hash_strategy_code("")
    assert isinstance(h, str) and len(h) == 64  # sha256 hex


def test_hash_config_is_order_independent():
    a = {"start_date": "2020-01-01", "end_date": "2024-12-31", "commission_pct": 0.001}
    b = {"commission_pct": 0.001, "end_date": "2024-12-31", "start_date": "2020-01-01"}
    assert _hash_config(a) == _hash_config(b)


def test_make_run_id_format(tmp_path):
    rid = _make_run_id(strategy_code="def strategy(): pass", runs_dir=tmp_path,
                       at=datetime(2026, 6, 4, 14, 23, 18))
    assert re.fullmatch(r"20260604T142318_[0-9a-f]{4}", rid), rid


def test_make_run_id_collision_appends_suffix(tmp_path):
    code = "def s(): pass"
    at = datetime(2026, 6, 4, 14, 23, 18)
    rid1 = _make_run_id(strategy_code=code, runs_dir=tmp_path, at=at)
    (tmp_path / f"{rid1}.summary.json").write_text("{}", encoding="utf-8")
    rid2 = _make_run_id(strategy_code=code, runs_dir=tmp_path, at=at)
    assert rid2 == f"{rid1}_2"
    (tmp_path / f"{rid2}.summary.json").write_text("{}", encoding="utf-8")
    rid3 = _make_run_id(strategy_code=code, runs_dir=tmp_path, at=at)
    assert rid3 == f"{rid1}_3"
