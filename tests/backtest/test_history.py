"""Tests for backtest/history.py — RunHistoryStore + helpers."""

from backtest.history import (
    RunSummary,
    RunDetail,
    RunHistoryStore,
)


def test_module_imports_ok():
    """Smoke test: the symbols documented in the spec are importable."""
    assert RunSummary is not None
    assert RunDetail is not None
    assert RunHistoryStore is not None
