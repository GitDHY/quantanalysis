"""Unit tests for ui/components/run_compare.py — pure logic only."""

from datetime import datetime
from backtest.history import RunSummary
from ui.components.run_compare import compute_inputs_diff


def _summary(id_: str, *, prices_hash: str, code_hash: str,
             commission_pct: float, start_date: str = "2020-01-01"):
    return RunSummary(
        id=id_,
        created_at=datetime(2026, 6, 4, 14, 23, 18),
        mode="dynamic", name=id_, note="", pinned=False,
        metrics={"sharpe": 1.0},
        fingerprint={"prices_hash": prices_hash, "code_hash": code_hash,
                     "bars_count": 100, "pandas_version": "2.0.3"},
        config={"start_date": start_date, "end_date": "2024-12-31",
                "commission_pct": commission_pct, "rebalance_freq": "monthly"},
        tickers=["SPY"],
    )


def test_inputs_diff_only_shows_differing_fields():
    a = _summary("a", prices_hash="P1", code_hash="C1", commission_pct=0.001)
    b = _summary("b", prices_hash="P1", code_hash="C1", commission_pct=0.002)
    diff = compute_inputs_diff([a, b])
    assert "commission_pct" in diff
    assert diff["commission_pct"] == [0.001, 0.002]
    assert "prices_hash" not in diff
    assert "code_hash" not in diff
    assert "rebalance_freq" not in diff


def test_inputs_diff_hides_unanimous_fields():
    a = _summary("a", prices_hash="P1", code_hash="C1", commission_pct=0.001)
    b = _summary("b", prices_hash="P1", code_hash="C1", commission_pct=0.001)
    c = _summary("c", prices_hash="P1", code_hash="C1", commission_pct=0.001)
    assert compute_inputs_diff([a, b, c]) == {}


def test_inputs_diff_three_runs_two_vs_one_split():
    a = _summary("a", prices_hash="P1", code_hash="C1", commission_pct=0.001)
    b = _summary("b", prices_hash="P1", code_hash="C1", commission_pct=0.001)
    c = _summary("c", prices_hash="P1", code_hash="C1", commission_pct=0.002)
    diff = compute_inputs_diff([a, b, c])
    assert diff["commission_pct"] == [0.001, 0.001, 0.002]


def test_inputs_diff_handles_empty_input():
    assert compute_inputs_diff([]) == {}


def test_inputs_diff_single_run_returns_empty():
    a = _summary("a", prices_hash="P1", code_hash="C1", commission_pct=0.001)
    assert compute_inputs_diff([a]) == {}
