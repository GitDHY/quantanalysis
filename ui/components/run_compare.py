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
            # PerformanceMetrics emits "Sharpe Ratio"; tests/older saves
            # may use lowercase variants. Try in production-first order.
            sharpe = (
                s.metrics.get("Sharpe Ratio")
                or s.metrics.get("sharpe_ratio")
                or s.metrics.get("sharpe")
            )
            st.text(f"Sharpe {sharpe:.2f}" if sharpe is not None else "")
        with cols[5]:
            # PerformanceMetrics emits "Total Return (%)" already in
            # percent units (152.0 for +152%); test fixtures often use
            # "total_return" as a fraction (1.52). Disambiguate here.
            tr_pct = s.metrics.get("Total Return (%)")
            tr_frac = s.metrics.get("total_return")
            if tr_pct is not None:
                st.text(f"{tr_pct:+.1f}%")
            elif tr_frac is not None:
                st.text(f"{tr_frac:+.1%}")
            else:
                st.text("")
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


def render_detail(run_id: str, store: RunHistoryStore) -> None:
    """Render a single run's detail view. Lazy-loads the detail.json."""
    summaries_by_id = {s.id: s for s in store.list_summaries()}
    summary = summaries_by_id.get(run_id)
    if summary is None:
        st.error(f"找不到 run_id={run_id}")
        return

    st.subheader(f"📊 {summary.name} — {summary.created_at:%Y-%m-%d %H:%M}")
    if summary.note:
        st.caption(f"📝 {summary.note}")

    try:
        detail = store.load_detail(run_id)
    except FileNotFoundError:
        st.error("详情文件丢失。")
        if st.button("清理这个孤立 summary"):
            store.delete(run_id)
            st.rerun()
        return

    # Equity curve
    import plotly.express as px
    fig = px.line(detail.portfolio_values, title="Equity Curve")
    fig.update_layout(showlegend=False, xaxis_title=None, yaxis_title="Value")
    st.plotly_chart(fig, use_container_width=True)

    # Inner tabs for the heavy data
    t_metrics, t_trades, t_weights, t_config = st.tabs([
        "Metrics", "Trades", "Weights", "Config & Code"
    ])
    with t_metrics:
        st.json(summary.metrics)
    with t_trades:
        if detail.trades:
            import pandas as pd
            st.dataframe(pd.DataFrame([t.to_dict() for t in detail.trades]))
        else:
            st.caption("No trades.")
    with t_weights:
        st.dataframe(detail.weights_history)
    with t_config:
        st.write("**Config**")
        st.json(summary.config)
        st.write("**Strategy code**")
        # strategy_code lives in summary.json but RunSummary excludes it;
        # re-read raw to fetch it.
        import json
        path = store.runs_dir / f"{run_id}.summary.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        st.code(raw.get("strategy_code", ""), language="python")


def render_compare(run_ids: List[str], store: RunHistoryStore) -> None:
    """Compare 2–4 runs: equity overlay, metrics table, inputs diff."""
    summaries_by_id = {s.id: s for s in store.list_summaries()}
    summaries = [summaries_by_id[rid] for rid in run_ids
                 if rid in summaries_by_id]

    if len(summaries) < 2:
        st.warning("compare 需要至少 2 个有效 run")
        return

    st.header(f"对比 {len(summaries)} 个 run")

    # 1. Equity overlay
    st.subheader("Equity Curves")
    import plotly.graph_objects as go
    fig = go.Figure()
    for s in summaries:
        try:
            d = store.load_detail(s.id)
        except FileNotFoundError:
            st.warning(f"{s.name}: detail 文件缺失,跳过")
            continue
        fig.add_trace(go.Scatter(
            x=d.portfolio_values.index,
            y=d.portfolio_values.values,
            mode="lines",
            name=f"{s.name} ({s.id[-9:]})",
        ))
    fig.update_layout(xaxis_title=None, yaxis_title="Value", hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)

    # 2. Metrics table — pivot summaries × metric names
    st.subheader("Metrics")
    import pandas as pd
    metric_keys = sorted({k for s in summaries for k in s.metrics.keys()})
    rows = {}
    for k in metric_keys:
        rows[k] = [s.metrics.get(k) for s in summaries]
    df_m = pd.DataFrame(rows, index=[f"{s.name}\n{s.id[-9:]}" for s in summaries]).T
    st.dataframe(df_m, use_container_width=True)

    # 3. Inputs Diff — only fields that differ
    st.subheader("Inputs Diff (only fields that differ)")
    diff = compute_inputs_diff(summaries)
    if not diff:
        st.success("✅ 所有输入字段一致 (prices_hash / code_hash / config 全相同)")
    else:
        diff_rows = {field_name: values for field_name, values in diff.items()}
        df_d = pd.DataFrame(
            diff_rows,
            index=[f"{s.name}\n{s.id[-9:]}" for s in summaries],
        ).T
        # Highlight differing cells: a cell highlights iff its value
        # ≠ all others in the row.
        def _highlight(row):
            return [
                "background-color: #ffe4b3" if v != row.iloc[0] or
                any(other != row.iloc[0] for other in row) else ""
                for v in row
            ]
        st.dataframe(df_d.style.apply(_highlight, axis=1),
                     use_container_width=True)
