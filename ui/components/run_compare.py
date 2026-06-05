"""Render the History tab's compare view + the detail expander.

`compute_inputs_diff` is pure and unit-tested. The Streamlit render
functions are not unit-tested; verify them manually."""

from __future__ import annotations

from typing import Any, Dict, List

from backtest.history import RunSummary, RunDetail, RunHistoryStore


def compute_inputs_diff(summaries: List[RunSummary]) -> Dict[str, List[Any]]:
    """Return {field_name: [val_run0, val_run1, ...]} only for fields
    where ≥1 run differs from any other.

    Compared fields = fingerprint ∪ config. Field name preserved, value
    list ordered by `summaries` order.
    """
    if len(summaries) < 2:
        return {}

    # Collect all candidate field names from fingerprint + config.
    field_names = set()
    for s in summaries:
        field_names.update(s.fingerprint.keys())
        field_names.update(s.config.keys())

    diff: Dict[str, List[Any]] = {}
    for fname in field_names:
        values = []
        for s in summaries:
            if fname in s.fingerprint:
                values.append(s.fingerprint[fname])
            elif fname in s.config:
                values.append(s.config[fname])
            else:
                values.append(None)
        if not all(v == values[0] for v in values):
            diff[fname] = values
    return diff
