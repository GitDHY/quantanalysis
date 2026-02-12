"""
Portfolio management page.
Allows users to create, edit, and manage investment portfolios.
"""

import streamlit as st
import pandas as pd
from typing import Dict, List, Tuple

from portfolio.manager import PortfolioManager, Portfolio
from ui.components.charts import render_allocation_pie
from data.fetcher import get_data_fetcher


def validate_ticker(ticker: str) -> Tuple[bool, str, pd.DataFrame]:
    """
    Validate a ticker symbol by checking if historical data can be fetched.
    
    Args:
        ticker: Stock ticker symbol
        
    Returns:
        Tuple of (is_valid, message, sample_data)
    """
    if not ticker or not ticker.strip():
        return False, "请输入有效的股票代码", pd.DataFrame()
    
    ticker = ticker.strip().upper()
    
    try:
        fetcher = get_data_fetcher()
        # Try to fetch recent 30 days of data to validate
        df = fetcher.fetch_prices(ticker, lookback_days=30, use_cache=False)
        
        if df is None or df.empty:
            return False, f"❌ 无法获取 {ticker} 的数据，请检查代码是否正确", pd.DataFrame()
        
        if ticker not in df.columns:
            # Check if data was returned under a different name
            if len(df.columns) == 1:
                df.columns = [ticker]
            else:
                return False, f"❌ 数据获取异常，请检查 {ticker} 是否正确", pd.DataFrame()
        
        # Check if we have enough valid data points
        valid_count = df[ticker].notna().sum()
        if valid_count < 5:
            return False, f"❌ {ticker} 历史数据不足（仅有 {valid_count} 条记录）", pd.DataFrame()
        
        return True, f"✅ {ticker} 验证通过，获取到 {valid_count} 条历史数据", df
        
    except Exception as e:
        return False, f"❌ 验证 {ticker} 时发生错误: {str(e)}", pd.DataFrame()


def validate_multiple_tickers(tickers: List[str]) -> Tuple[List[str], List[str], Dict[str, str]]:
    """
    Validate multiple ticker symbols.
    
    Args:
        tickers: List of ticker symbols
        
    Returns:
        Tuple of (valid_tickers, invalid_tickers, messages_dict)
    """
    valid = []
    invalid = []
    messages = {}
    
    for ticker in tickers:
        ticker = ticker.strip().upper()
        if not ticker:
            continue
            
        is_valid, message, _ = validate_ticker(ticker)
        messages[ticker] = message
        
        if is_valid:
            valid.append(ticker)
        else:
            invalid.append(ticker)
    
    return valid, invalid, messages


def render_portfolio_page():
    """Render the portfolio management page."""
    
    st.title("📊 投资组合管理")
    st.caption("管理你的美股和新加坡股市投资组合")
    
    # Initialize portfolio manager
    manager = PortfolioManager()
    
    # Sidebar: Portfolio list
    with st.sidebar:
        st.subheader("📁 我的组合")
        
        portfolios = manager.get_all()
        portfolio_names = list(portfolios.keys())
        
        # Import from legacy
        if st.button("📥 导入旧版组合", help="从现有 portfolios.json 导入"):
            imported = manager.import_legacy()
            if imported > 0:
                st.success(f"成功导入 {imported} 个组合")
                st.rerun()
            else:
                st.info("没有可导入的组合")
        
        st.divider()
        
        # Portfolio selection
        if portfolio_names:
            selected_name = st.selectbox(
                "选择组合",
                portfolio_names,
                key="portfolio_select"
            )
        else:
            selected_name = None
            st.info("暂无组合，请创建新组合")
    
    # Main content area
    tab1, tab2 = st.tabs(["📝 编辑组合", "➕ 创建新组合"])
    
    with tab1:
        if selected_name:
            render_portfolio_editor(manager, selected_name)
        else:
            st.info("👈 请先选择或创建一个组合")
    
    with tab2:
        render_portfolio_creator(manager)


def render_portfolio_editor(manager: PortfolioManager, portfolio_name: str):
    """Render portfolio editor."""
    
    portfolio = manager.get(portfolio_name)
    if portfolio is None:
        st.error("组合不存在")
        return
    
    st.subheader(f"编辑: {portfolio_name}")
    
    # Portfolio info
    col1, col2 = st.columns([2, 1])
    
    with col1:
        new_name = st.text_input("组合名称", value=portfolio.name, key="edit_name")
        description = st.text_area(
            "描述",
            value=portfolio.description,
            key="edit_description",
            height=80
        )
    
    with col2:
        st.metric("资产数量", len(portfolio.tickers))
        st.metric("总权重", f"{portfolio.total_weight:.1f}%")
    
    st.divider()
    
    # Asset management
    st.subheader("📈 资产配置")
    
    # Add new ticker
    col_add1, col_add2, col_add3, col_add4 = st.columns([2, 1, 1, 1])
    with col_add1:
        new_ticker = st.text_input(
            "添加标的",
            placeholder="输入股票代码，如 IWY, G3B.SI",
            key="new_ticker"
        ).upper()
    with col_add2:
        new_weight = st.number_input("权重 (%)", min_value=0.0, max_value=100.0, value=10.0, key="new_weight")
    with col_add3:
        st.write("")  # Spacing
        st.write("")
        validate_clicked = st.button("🔍 验证", width="stretch", key="validate_ticker_btn")
    with col_add4:
        st.write("")  # Spacing
        st.write("")
        add_clicked = st.button("➕ 添加", width="stretch", key="add_ticker_btn")
    
    # Validation logic
    if validate_clicked and new_ticker:
        with st.spinner(f"正在验证 {new_ticker}..."):
            is_valid, message, sample_df = validate_ticker(new_ticker)
            if is_valid:
                st.success(message)
                if not sample_df.empty:
                    st.caption("最近价格数据预览:")
                    st.line_chart(sample_df.tail(20))
                st.session_state['ticker_validated'] = new_ticker
            else:
                st.error(message)
                st.session_state['ticker_validated'] = None
    
    # Add ticker logic
    if add_clicked:
        if new_ticker and new_ticker not in portfolio.tickers:
            # Always validate before adding
            with st.spinner(f"正在验证并添加 {new_ticker}..."):
                is_valid, message, _ = validate_ticker(new_ticker)
                if is_valid:
                    portfolio.tickers.append(new_ticker)
                    portfolio.weights[new_ticker] = new_weight
                    manager.update(portfolio)
                    st.success(f"已添加 {new_ticker}")
                    st.session_state['ticker_validated'] = None
                    st.rerun()
                else:
                    st.error(message)
        elif new_ticker in portfolio.tickers:
            st.warning(f"{new_ticker} 已存在")
    
    # Edit existing assets
    if portfolio.tickers:
        st.write("**当前持仓:**")
        
        # Create editable dataframe
        df_data = []
        for ticker in portfolio.tickers:
            df_data.append({
                "标的": ticker,
                "权重 (%)": portfolio.weights.get(ticker, 0.0),
            })
        
        df = pd.DataFrame(df_data)
        
        edited_df = st.data_editor(
            df,
            column_config={
                "标的": st.column_config.TextColumn("标的", disabled=True),
                "权重 (%)": st.column_config.NumberColumn(
                    "权重 (%)",
                    min_value=0,
                    max_value=100,
                    step=1,
                    format="%.1f"
                ),
            },
            hide_index=True,
            width="stretch",
            key="weights_editor"
        )
        
        # Delete buttons
        st.write("**删除资产:**")
        cols = st.columns(min(len(portfolio.tickers), 6))
        for i, ticker in enumerate(portfolio.tickers):
            col_idx = i % 6
            with cols[col_idx]:
                if st.button(f"🗑️ {ticker}", key=f"del_{ticker}", width="stretch"):
                    portfolio.tickers.remove(ticker)
                    if ticker in portfolio.weights:
                        del portfolio.weights[ticker]
                    manager.update(portfolio)
                    st.rerun()
        
        # Visualization
        st.divider()
        col_chart, col_summary = st.columns([2, 1])
        
        with col_chart:
            render_allocation_pie(
                {row["标的"]: row["权重 (%)"] for _, row in edited_df.iterrows()},
                title="配置比例"
            )
        
        with col_summary:
            total = edited_df["权重 (%)"].sum()
            st.metric("总权重", f"{total:.1f}%")
            
            if abs(total - 100) > 0.1:
                st.warning("⚠️ 权重总和不等于 100%")
            else:
                st.success("✅ 权重配置正确")
    
    st.divider()
    
    # Action buttons
    col_save, col_delete, col_rename = st.columns(3)
    
    with col_save:
        if st.button("💾 保存修改", type="primary", width="stretch"):
            # Update weights from editor
            for _, row in edited_df.iterrows():
                portfolio.weights[row["标的"]] = row["权重 (%)"]
            
            portfolio.description = description
            
            if manager.update(portfolio):
                st.success("保存成功!")
            else:
                st.error("保存失败")
    
    with col_delete:
        if st.button("🗑️ 删除组合", type="secondary", width="stretch"):
            if manager.delete(portfolio_name):
                st.success("已删除")
                st.rerun()
    
    with col_rename:
        if new_name != portfolio_name:
            if st.button("✏️ 重命名", width="stretch"):
                if manager.rename(portfolio_name, new_name):
                    st.success(f"已重命名为 {new_name}")
                    st.rerun()


def render_portfolio_creator(manager: PortfolioManager):
    """Render new portfolio creation form."""
    
    st.subheader("创建新组合")
    
    # Basic info
    name = st.text_input("组合名称", placeholder="例如: 我的成长组合", key="create_name")
    description = st.text_area("描述 (可选)", placeholder="描述这个组合的投资目标", key="create_desc", height=80)
    
    st.divider()
    
    # Quick templates
    st.write("**快速模板:**")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("🇺🇸 美股成长", width="stretch"):
            st.session_state['template_tickers'] = "IWY, QQQ, SPY"
            st.session_state['template_weights'] = "50, 30, 20"
    
    with col2:
        if st.button("🌏 全球分散", width="stretch"):
            st.session_state['template_tickers'] = "IWY, LVHI, G3B.SI, GSD.SI"
            st.session_state['template_weights'] = "40, 20, 20, 20"
    
    with col3:
        if st.button("🛡️ 保守型", width="stretch"):
            st.session_state['template_tickers'] = "LVHI, MBH.SI, GSD.SI"
            st.session_state['template_weights'] = "40, 40, 20"
    
    st.divider()
    
    # Manual input
    st.write("**手动输入:**")
    
    default_tickers = st.session_state.get('template_tickers', '')
    default_weights = st.session_state.get('template_weights', '')
    
    tickers_input = st.text_input(
        "标的代码 (逗号分隔)",
        value=default_tickers,
        placeholder="IWY, LVHI, G3B.SI, GSD.SI",
        key="create_tickers"
    )
    
    weights_input = st.text_input(
        "权重 (逗号分隔, %)",
        value=default_weights,
        placeholder="40, 20, 20, 20",
        key="create_weights"
    )
    
    # Preview
    if tickers_input and weights_input:
        try:
            tickers = [t.strip().upper() for t in tickers_input.split(',') if t.strip()]
            weights = [float(w.strip()) for w in weights_input.split(',') if w.strip()]
            
            if len(tickers) == len(weights):
                st.write("**预览:**")
                
                preview_df = pd.DataFrame({
                    "标的": tickers,
                    "权重 (%)": weights
                })
                
                st.dataframe(preview_df, hide_index=True, width="stretch")
                
                total = sum(weights)
                if abs(total - 100) > 0.1:
                    st.warning(f"⚠️ 权重总和为 {total:.1f}%，将自动归一化")
                
                # Validation button for all tickers
                if st.button("🔍 验证所有标的", key="validate_all_tickers"):
                    with st.spinner("正在验证所有标的..."):
                        valid, invalid, messages = validate_multiple_tickers(tickers)
                        
                        if valid:
                            st.success(f"✅ {len(valid)} 个标的验证通过: {', '.join(valid)}")
                        
                        if invalid:
                            st.error(f"❌ {len(invalid)} 个标的验证失败:")
                            for ticker in invalid:
                                st.write(f"  • {messages.get(ticker, ticker)}")
                        
                        # Store validation result in session state
                        st.session_state['validated_tickers'] = valid
                        st.session_state['invalid_tickers'] = invalid
            else:
                st.error(f"标的数量 ({len(tickers)}) 与权重数量 ({len(weights)}) 不匹配")
        except ValueError as e:
            st.error(f"输入格式错误: {e}")
    
    st.divider()
    
    # Create button
    if st.button("✅ 创建组合", type="primary", width="stretch"):
        if not name:
            st.error("请输入组合名称")
        elif not tickers_input or not weights_input:
            st.error("请输入标的和权重")
        else:
            try:
                tickers = [t.strip().upper() for t in tickers_input.split(',') if t.strip()]
                weights_list = [float(w.strip()) for w in weights_input.split(',') if w.strip()]
                
                if len(tickers) != len(weights_list):
                    st.error("标的数量与权重数量不匹配")
                else:
                    # Validate all tickers before creating
                    with st.spinner("正在验证所有标的..."):
                        valid, invalid, messages = validate_multiple_tickers(tickers)
                    
                    if invalid:
                        st.error(f"以下标的验证失败，无法创建组合:")
                        for ticker in invalid:
                            st.write(f"  • {messages.get(ticker, ticker)}")
                    else:
                        weights_dict = dict(zip(tickers, weights_list))
                        
                        portfolio = Portfolio(
                            name=name,
                            tickers=tickers,
                            weights=weights_dict,
                            description=description,
                        )
                        
                        if manager.create(portfolio):
                            st.success(f"✅ 组合 '{name}' 创建成功!")
                            # Clear template and validation state
                            for key in ['template_tickers', 'template_weights', 'validated_tickers', 'invalid_tickers']:
                                if key in st.session_state:
                                    del st.session_state[key]
                            st.rerun()
                        else:
                            st.error("创建失败，组合名称可能已存在")
            except ValueError as e:
                st.error(f"输入格式错误: {e}")


# Common ticker suggestions
TICKER_SUGGESTIONS = {
    "美股": ["IWY", "LVHI", "SPY", "QQQ", "TLT", "WTMF", "GLD"],
    "新加坡": ["G3B.SI", "MBH.SI", "GSD.SI", "SRT.SI", "AJBU.SI"],
}
