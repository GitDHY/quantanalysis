"""
Data coverage warning component.
Professional UI/UX design for displaying data availability warnings.

设计原则:
1. 渐进式披露 - 先显示摘要，按需展开详情
2. 清晰的视觉层次 - 用颜色和图标区分严重程度
3. 可操作性 - 提供明确的行动建议和快捷操作
4. 无干扰 - 数据完整时不显示多余信息
"""

import streamlit as st
import pandas as pd
from datetime import date
from typing import Optional, Tuple, List

from backtest.engine import DataValidationResult, TickerCoverageInfo, DataCoverageStatus


def render_data_coverage_banner(
    validation: DataValidationResult,
    show_details: bool = True,
    allow_date_adjustment: bool = True,
    key_prefix: str = ""
) -> Tuple[bool, Optional[date]]:
    """
    渲染数据覆盖警告横幅 - 主要入口组件。
    
    这个组件遵循以下 UX 原则:
    - 无警告时：完全不显示，不干扰用户
    - 轻微警告：显示可折叠的信息提示
    - 严重警告：显示醒目的警告框，需要用户确认
    
    Args:
        validation: 数据验证结果
        show_details: 是否显示详情表格
        allow_date_adjustment: 是否允许一键调整日期
        key_prefix: Streamlit 组件 key 前缀
        
    Returns:
        (should_proceed, adjusted_start_date): 
        - should_proceed: 用户是否确认继续
        - adjusted_start_date: 如果用户选择调整日期，返回建议的开始日期
    """
    # 数据完整，无需显示任何警告
    if not validation.has_warnings:
        return True, None
    
    severity = validation.get_severity_level()
    
    # 根据严重程度选择不同的显示策略
    if severity == 'critical':
        return _render_critical_error(validation, key_prefix), None
    elif severity == 'error':
        return _render_error_with_exclusions(
            validation, show_details, allow_date_adjustment, key_prefix
        )
    else:  # warning
        return _render_partial_coverage_warning(
            validation, show_details, allow_date_adjustment, key_prefix
        )


def _render_critical_error(
    validation: DataValidationResult,
    key_prefix: str
) -> bool:
    """
    渲染严重错误 - 无法进行回测。
    使用红色错误框，不可忽略。
    """
    st.error(
        "🚫 **无法进行回测**\n\n"
        "所有标的在指定时间范围内都没有可用数据。请调整回测时间范围或更换标的。",
        icon="🚫"
    )
    
    # 显示被排除的标的
    if validation.excluded_tickers:
        st.write("**无数据的标的：**")
        for ticker in validation.excluded_tickers:
            st.write(f"- ❌ {ticker}")
    
    return False


def _render_error_with_exclusions(
    validation: DataValidationResult,
    show_details: bool,
    allow_date_adjustment: bool,
    key_prefix: str
) -> Tuple[bool, Optional[date]]:
    """
    渲染有标的被排除的警告。
    使用橙色警告框，需要用户确认。
    """
    # 构建摘要信息
    excluded_count = len(validation.excluded_tickers)
    usable_count = validation.usable_tickers_count
    total_count = validation.total_tickers_count
    
    st.warning(
        f"⚠️ **部分标的将被排除**\n\n"
        f"在 {total_count} 个标的中，有 **{excluded_count} 个** 无法获取数据，"
        f"将使用剩余 **{usable_count} 个** 标的进行回测。",
        icon="⚠️"
    )
    
    # 详情折叠面板
    with st.expander("📋 查看详情", expanded=False):
        _render_coverage_details_table(validation)
        
        # 如果有部分覆盖的标的，显示建议
        if validation.has_partial_tickers and allow_date_adjustment:
            _render_date_adjustment_suggestion(validation, key_prefix)
    
    # 用户确认区域
    return _render_confirmation_buttons(validation, allow_date_adjustment, key_prefix)


def _render_partial_coverage_warning(
    validation: DataValidationResult,
    show_details: bool,
    allow_date_adjustment: bool,
    key_prefix: str
) -> Tuple[bool, Optional[date]]:
    """
    渲染部分覆盖警告（无标的被排除，但有标的数据不完整）。
    使用信息提示框，可选确认。
    """
    partial_count = len(validation.partial_tickers)
    
    # 使用更友好的信息框而非警告框
    st.info(
        f"ℹ️ **数据预检结果**\n\n"
        f"有 **{partial_count} 个** 标的的**成立日期**晚于回测开始日期。"
        f"这些标的在成立前没有历史数据，回测将从各标的的成立日期开始计算。",
        icon="ℹ️"
    )
    
    # 详情折叠面板
    with st.expander("📋 查看标的成立日期详情", expanded=False):
        _render_coverage_details_table(validation)
        
        if allow_date_adjustment:
            _render_date_adjustment_suggestion(validation, key_prefix)
    
    return _render_confirmation_buttons(validation, allow_date_adjustment, key_prefix)


def _render_coverage_details_table(validation: DataValidationResult):
    """
    渲染数据覆盖详情表格。
    使用清晰的视觉层次和颜色编码。
    重点突出：标的成立时间 vs 回测开始时间 的对比
    """
    # 构建表格数据
    table_data = []
    
    for ticker, info in validation.coverage_info.items():
        # 判断是否可用于回测
        if info.actual_start and info.requested_start:
            if info.actual_start > info.requested_start:
                inception_status = f"⚠️ 晚于回测 {info.missing_start_days} 天"
            else:
                inception_status = "✅ 早于回测开始"
        else:
            inception_status = "❌ 无数据"
        
        row = {
            '标的': ticker,
            '成立日期': info.actual_start.strftime('%Y-%m-%d') if info.actual_start else '无数据',
            '回测开始': info.requested_start.strftime('%Y-%m-%d'),
            '对比结果': inception_status,
            '数据覆盖率': f"{info.coverage_pct:.0f}%" if info.is_usable else '-',
        }
        
        table_data.append(row)
    
    # 按状态排序：无数据 > 部分 > 完整
    status_order = {DataCoverageStatus.NO_DATA: 0, DataCoverageStatus.PARTIAL: 1, DataCoverageStatus.FULL: 2}
    table_data.sort(key=lambda x: status_order.get(
        validation.coverage_info.get(x['标的'], TickerCoverageInfo(
            ticker='', status=DataCoverageStatus.FULL,
            requested_start=date.today(), requested_end=date.today()
        )).status, 
        2
    ))
    
    df = pd.DataFrame(table_data)
    
    # 使用 Streamlit 的数据表格
    st.dataframe(
        df,
        hide_index=True,
        width="stretch",
        column_config={
            '标的': st.column_config.TextColumn(width="medium"),
            '成立日期': st.column_config.TextColumn(width="medium"),
            '回测开始': st.column_config.TextColumn(width="medium"),
            '对比结果': st.column_config.TextColumn(width="large"),
            '数据覆盖率': st.column_config.TextColumn(width="small"),
        }
    )


def _render_date_adjustment_suggestion(
    validation: DataValidationResult,
    key_prefix: str
):
    """
    渲染日期调整建议卡片。
    提供清晰的行动建议。
    """
    if not validation.effective_start_date:
        return
    
    st.divider()
    
    # 计算推荐日期与原始日期的差距
    first_ticker_info = list(validation.coverage_info.values())[0]
    original_start = first_ticker_info.requested_start
    suggested_start = validation.effective_start_date
    days_diff = (suggested_start - original_start).days
    
    # 使用卡片式设计显示建议
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.markdown(
            f"""
            **💡 建议**
            
            将回测开始日期调整为 **{suggested_start.strftime('%Y-%m-%d')}**，
            可确保所有标的都有完整数据覆盖。
            
            这比当前设置晚 **{days_diff} 天**。
            """
        )
    
    with col2:
        st.metric(
            label="建议开始日期",
            value=suggested_start.strftime('%Y-%m-%d'),
            delta=f"+{days_diff}天",
            delta_color="off"
        )


def _render_confirmation_buttons(
    validation: DataValidationResult,
    allow_date_adjustment: bool,
    key_prefix: str
) -> Tuple[bool, Optional[date]]:
    """
    渲染确认按钮组。
    提供明确的操作选项。
    """
    st.divider()
    
    should_proceed = True  # 默认继续
    adjusted_date = None
    
    if allow_date_adjustment and validation.effective_start_date:
        suggested_date = validation.effective_start_date
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**选择操作：**")
            st.caption("继续使用当前设置，或调整到建议日期")
        
        with col2:
            # 使用按钮来应用调整
            if st.button(
                f"📅 应用建议日期 ({suggested_date.strftime('%Y-%m-%d')})", 
                key=f"{key_prefix}_apply_date_btn",
                type="primary"
            ):
                adjusted_date = suggested_date
    
    return should_proceed, adjusted_date


def render_data_coverage_summary(
    validation: DataValidationResult,
    compact: bool = True
) -> None:
    """
    渲染数据覆盖摘要 - 用于回测结果页面。
    
    Args:
        validation: 数据验证结果
        compact: 是否使用紧凑模式
    """
    if not validation.has_warnings:
        if not compact:
            st.success("✅ 所有标的数据完整覆盖回测期间")
        return
    
    severity = validation.get_severity_level()
    
    # 摘要指标
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            "标的总数",
            validation.total_tickers_count,
        )
    
    with col2:
        st.metric(
            "完整覆盖",
            len(validation.full_coverage_tickers),
            delta=None
        )
    
    with col3:
        st.metric(
            "部分覆盖",
            len(validation.partial_tickers),
            delta=f"-{len(validation.partial_tickers)}" if validation.partial_tickers else None,
            delta_color="off" if validation.partial_tickers else "normal"
        )
    
    with col4:
        st.metric(
            "已排除",
            len(validation.excluded_tickers),
            delta=f"-{len(validation.excluded_tickers)}" if validation.excluded_tickers else None,
            delta_color="inverse" if validation.excluded_tickers else "normal"
        )
    
    # 实际回测期间
    if validation.effective_start_date and validation.effective_end_date:
        st.caption(
            f"📅 实际回测期间：{validation.effective_start_date.strftime('%Y-%m-%d')} "
            f"至 {validation.effective_end_date.strftime('%Y-%m-%d')}"
        )


def render_inline_coverage_indicator(
    validation: Optional[DataValidationResult],
    key: str = ""
) -> None:
    """
    渲染内联的覆盖状态指示器 - 用于侧边栏或紧凑空间。
    
    这是一个小型组件，只显示图标和简短文字。
    """
    if validation is None:
        return
    
    if not validation.has_warnings:
        st.caption("✅ 数据完整")
        return
    
    severity = validation.get_severity_level()
    
    if severity == 'critical':
        st.caption("🚫 无可用数据")
    elif severity == 'error':
        excluded = len(validation.excluded_tickers)
        st.caption(f"⚠️ {excluded}个标的无数据")
    else:
        partial = len(validation.partial_tickers)
        st.caption(f"ℹ️ {partial}个标的部分覆盖")


def render_pre_backtest_validation(
    tickers: List[str],
    start_date: date,
    end_date: date,
    backtest_engine,
    key_prefix: str = "precheck"
) -> Tuple[bool, Optional[date], Optional[DataValidationResult]]:
    """
    渲染回测前的数据验证 - 完整的预检流程。
    
    这个函数封装了完整的预检逻辑，包括：
    1. 执行数据验证
    2. 显示警告（如有）
    3. 获取用户确认
    
    Args:
        tickers: 标的列表
        start_date: 回测开始日期
        end_date: 回测结束日期
        backtest_engine: 回测引擎实例
        key_prefix: Streamlit key 前缀
        
    Returns:
        (should_proceed, adjusted_start_date, validation_result)
    """
    # 执行验证
    validation = backtest_engine.validate_data_coverage(tickers, start_date, end_date)
    
    # 如果数据完整，直接返回
    if not validation.has_warnings:
        return True, None, validation
    
    # 显示警告并获取用户决定
    should_proceed, adjusted_date = render_data_coverage_banner(
        validation=validation,
        show_details=True,
        allow_date_adjustment=True,
        key_prefix=key_prefix
    )
    
    return should_proceed, adjusted_date, validation
