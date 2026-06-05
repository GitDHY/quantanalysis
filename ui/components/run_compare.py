"""Render the History tab's compare view + the detail expander.

`compute_inputs_diff` is pure and unit-tested. The Streamlit render
functions are not unit-tested; verify them manually."""

from __future__ import annotations

from typing import Any, Dict, List

import streamlit as st

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


def render_history_list(store: RunHistoryStore) -> List[str]:
    """Render the list view. Returns the list of run_ids the user
    selected via checkbox (0–N items).

    Side effects: pin/unpin/note edits/delete go through `store` directly.
    """
    summaries = store.list_summaries()
    if not summaries:
        st.info("还没有保存的回测。跑一次动态/静态回测即可自动入库。")
        return []

    n_pinned = sum(1 for s in summaries if s.pinned)
    n_recent = len(summaries) - n_pinned
    st.caption(f"共 {len(summaries)} 个 run "
               f"({n_pinned} pinned + {n_recent} recent)")

    selected_ids: List[str] = []
    for s in summaries:
        cols = st.columns([0.5, 0.4, 1.5, 1.7, 1.0, 1.0, 2.0, 0.8])
        with cols[0]:
            picked = st.checkbox("", key=f"pick_{s.id}", label_visibility="collapsed")
            if picked:
                selected_ids.append(s.id)
        with cols[1]:
            star_label = "⭐" if s.pinned else "☆"
            if st.button(star_label, key=f"pin_{s.id}", help="切换 pin"):
                if s.pinned:
                    store.unpin(s.id)
                else:
                    store.pin(s.id)
                st.rerun()
        with cols[2]:
            st.text(s.created_at.strftime("%Y-%m-%d %H:%M"))
        with cols[3]:
            st.text(s.name)
        with cols[4]:
            sharpe = s.metrics.get("sharpe_ratio") or s.metrics.get("sharpe")
            st.text(f"Sharpe {sharpe:.2f}" if sharpe is not None else "")
        with cols[5]:
            tr = s.metrics.get("total_return")
            st.text(f"{tr:+.1%}" if tr is not None else "")
        with cols[6]:
            new_note = st.text_input(
                "", value=s.note, key=f"note_{s.id}",
                label_visibility="collapsed", placeholder="备注...",
            )
            if new_note != s.note:
                store.update_note(s.id, new_note)
        with cols[7]:
            if st.button("🗑", key=f"del_{s.id}", help="删除"):
                store.delete(s.id)
                st.rerun()

    return selected_ids
