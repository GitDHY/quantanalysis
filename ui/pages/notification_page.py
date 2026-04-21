"""
Notification settings page.
Professional UX design with step-by-step wizard flow.

Flow:
1. User selects strategy and portfolio (订阅管理)
2. User configures scheduled check settings (定时设置)
3. User configures email/WeChat push settings (推送渠道)
4. User can test notifications or wait for scheduled trigger (测试/运行)
"""

import streamlit as st
from datetime import datetime
import uuid

from config.settings import get_settings, NotificationDefaults, NotificationSubscription
from notification.email_sender import EmailSender
from notification.wechat_push import WeChatPush
from notification.scheduler import AlertScheduler
from strategy.engine import StrategyEngine
from portfolio.manager import PortfolioManager


def render_notification_page():
    """Render the notification settings page with improved UX."""
    
    st.title("🔔 通知设置")
    st.caption("配置策略信号提醒，让调仓信号自动推送到您的邮箱或微信")
    
    settings = get_settings()
    config = settings.load_notification_config()
    
    # Check configuration status for progress indicator
    has_subscriptions = len(config.subscriptions) > 0
    has_schedule = config.check_time != ""
    has_email = bool(config.email_from and config.email_pwd)
    has_wechat = bool(config.serverchan_key or config.pushplus_token)
    has_channel = has_email or has_wechat
    
    # Progress indicator
    render_progress_indicator(has_subscriptions, has_schedule, has_channel)
    
    st.divider()
    
    # Tab navigation with step numbers
    tab1, tab2, tab3, tab4 = st.tabs([
        "① 订阅管理", 
        "② 定时设置", 
        "③ 推送渠道", 
        "④ 测试运行"
    ])
    
    with tab1:
        render_subscription_manager(settings, config)
    
    with tab2:
        render_scheduler_settings(settings, config)
    
    with tab3:
        render_channel_settings(settings, config)
    
    with tab4:
        render_test_and_run(settings, config)


def render_progress_indicator(has_subscriptions: bool, has_schedule: bool, has_channel: bool):
    """Render a visual progress indicator showing setup completion."""
    
    steps = [
        ("订阅策略", has_subscriptions, "选择要监控的策略"),
        ("定时设置", has_schedule, "配置检查时间"),
        ("推送渠道", has_channel, "配置邮件或微信"),
    ]
    
    completed = sum(1 for _, done, _ in steps if done)
    total = len(steps)
    
    # Overall status
    if completed == total:
        st.success(f"✅ 配置完成！系统将在设定时间自动检查策略信号并推送通知。")
    else:
        st.info(f"📋 配置进度: {completed}/{total} - 请完成以下步骤以启用自动通知")
    
    # Step indicators
    cols = st.columns(len(steps))
    for col, (name, done, desc) in zip(cols, steps):
        with col:
            if done:
                st.markdown(f"""
                <div style="text-align: center; padding: 10px; background: #d4edda; border-radius: 8px;">
                    <div style="font-size: 24px;">✅</div>
                    <div style="font-weight: bold; color: #155724;">{name}</div>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div style="text-align: center; padding: 10px; background: #f8f9fa; border-radius: 8px; border: 2px dashed #dee2e6;">
                    <div style="font-size: 24px;">⬜</div>
                    <div style="color: #6c757d;">{name}</div>
                </div>
                """, unsafe_allow_html=True)


def render_subscription_manager(settings, config: NotificationDefaults):
    """Render subscription management - selecting strategy and portfolio pairs."""
    
    st.subheader("📋 策略订阅管理")
    st.info("💡 选择要监控的策略和对应的投资组合，当策略产生调仓信号时，系统会自动通知您。")
    
    # Load available strategies and portfolios
    strategy_engine = StrategyEngine()
    portfolio_manager = PortfolioManager()
    
    strategies = strategy_engine.get_all()
    portfolios = portfolio_manager.get_all()
    
    strategy_names = list(strategies.keys())
    portfolio_names = list(portfolios.keys())
    
    if not strategy_names:
        st.warning("⚠️ 请先在「策略编辑器」中创建策略")
        return
    
    if not portfolio_names:
        st.warning("⚠️ 请先在「投资组合」中创建组合")
        return
    
    # Existing subscriptions
    st.write("**当前订阅**")
    
    if not config.subscriptions:
        st.caption("暂无订阅，请在下方添加")
    else:
        for i, sub in enumerate(config.subscriptions):
            with st.container():
                col1, col2, col3, col4, col5 = st.columns([3, 3, 2, 2, 1])
                
                with col1:
                    st.markdown(f"**📊 {sub.strategy_name}**")
                
                with col2:
                    st.markdown(f"📁 {sub.portfolio_name}")
                
                with col3:
                    channels = []
                    if sub.notify_email:
                        channels.append("📧")
                    if sub.notify_wechat:
                        channels.append("💬")
                    st.markdown(" ".join(channels) if channels else "无")
                
                with col4:
                    status = "🟢 启用" if sub.enabled else "⚪ 停用"
                    st.markdown(status)
                
                with col5:
                    if st.button("🗑️", key=f"del_sub_{sub.id}", help="删除此订阅"):
                        config.subscriptions = [s for s in config.subscriptions if s.id != sub.id]
                        settings.save_notification_config(config)
                        st.rerun()
    
    st.divider()
    
    # Add new subscription
    st.write("**➕ 添加新订阅**")
    
    with st.form("add_subscription_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            selected_strategy = st.selectbox(
                "选择策略",
                options=strategy_names,
                key="new_sub_strategy",
                help="选择要监控的策略"
            )
            
            # Show strategy info
            if selected_strategy and selected_strategy in strategies:
                strategy_info = strategies[selected_strategy]
                linked_portfolio = strategy_info.get('portfolio_name', '')
                if linked_portfolio:
                    st.caption(f"💡 此策略已关联组合: {linked_portfolio}")
        
        with col2:
            # Default to strategy's linked portfolio if available
            default_portfolio = ""
            if selected_strategy and selected_strategy in strategies:
                default_portfolio = strategies[selected_strategy].get('portfolio_name', '')
            
            default_idx = 0
            if default_portfolio in portfolio_names:
                default_idx = portfolio_names.index(default_portfolio)
            
            selected_portfolio = st.selectbox(
                "选择组合",
                options=portfolio_names,
                index=default_idx,
                key="new_sub_portfolio",
                help="选择用于运行策略的投资组合"
            )
        
        # Notification options
        st.write("**通知方式**")
        col_email, col_wechat, col_threshold = st.columns(3)
        
        with col_email:
            notify_email = st.checkbox("📧 邮件通知", value=True, key="new_sub_email")
        
        with col_wechat:
            notify_wechat = st.checkbox("💬 微信通知", value=True, key="new_sub_wechat")
        
        with col_threshold:
            threshold = st.number_input(
                "变动阈值 (%)",
                min_value=0.0,
                max_value=50.0,
                value=1.0,
                step=0.5,
                help="只有当仓位变动超过此阈值时才发送通知",
                key="new_sub_threshold"
            )
        
        # Weight normalization option
        normalize_weights = st.checkbox(
            "自动归一化权重",
            value=True,
            key="new_sub_normalize_weights",
            help=(
                "开启时（默认），策略返回的目标权重会自动缩放到总和为 100%。"
                "关闭时，按字面值使用权重：总和 < 100% 视为持有部分现金；"
                "总和 > 100% 视为杠杆，信号日志会给出警告提示。"
            ),
        )
        
        submitted = st.form_submit_button("➕ 添加订阅", type="primary", width="stretch")
        
        if submitted:
            if not notify_email and not notify_wechat:
                st.error("请至少选择一种通知方式")
            else:
                # Check for duplicate
                exists = any(
                    s.strategy_name == selected_strategy and s.portfolio_name == selected_portfolio
                    for s in config.subscriptions
                )
                
                if exists:
                    st.warning("此策略-组合组合已存在订阅")
                else:
                    new_sub = NotificationSubscription(
                        id=str(uuid.uuid4())[:8],
                        strategy_name=selected_strategy,
                        portfolio_name=selected_portfolio,
                        enabled=True,
                        notify_email=notify_email,
                        notify_wechat=notify_wechat,
                        threshold_pct=threshold,
                        normalize_weights=normalize_weights,
                        created_at=datetime.now().isoformat(),
                    )
                    config.subscriptions.append(new_sub)
                    
                    if settings.save_notification_config(config):
                        st.success(f"✅ 已添加订阅: {selected_strategy} + {selected_portfolio}")
                        st.rerun()
                    else:
                        st.error("保存失败")


def render_scheduler_settings(settings, config: NotificationDefaults):
    """Render scheduler settings with improved UX."""
    
    st.subheader("⏰ 定时检查设置")
    st.info("💡 设置系统自动检查策略信号的时间。建议设置在美股收盘后（如北京时间 09:00）。")
    
    scheduler = AlertScheduler()
    sched_config = scheduler.load_config()
    status = scheduler.get_status()
    
    # Status cards
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if sched_config.enabled:
            st.metric("状态", "✅ 已启用", delta="运行中" if status['running'] else "等待中")
        else:
            st.metric("状态", "⚪ 未启用", delta="请启用定时检查")
    
    with col2:
        st.metric("检查时间", sched_config.check_time)
    
    with col3:
        last_run = sched_config.last_run or "从未运行"
        st.metric("上次运行", last_run)
    
    st.divider()
    
    # Configuration form
    with st.form("scheduler_form"):
        col_enable, col_time, col_freq = st.columns([1, 1, 1])
        
        with col_enable:
            enabled = st.checkbox(
                "启用定时检查",
                value=sched_config.enabled,
                help="开启后系统将在指定时间自动检查策略"
            )
        
        with col_time:
            try:
                default_time = datetime.strptime(sched_config.check_time, "%H:%M").time()
            except:
                default_time = datetime.strptime("09:30", "%H:%M").time()
            
            check_time = st.time_input(
                "检查时间",
                value=default_time,
                help="建议设置在美股收盘后"
            )
        
        with col_freq:
            freq_options = ["daily", "weekly"]
            freq_labels = {"daily": "每日", "weekly": "每周"}
            frequency = st.selectbox(
                "检查频率",
                options=freq_options,
                index=freq_options.index(sched_config.frequency) if sched_config.frequency in freq_options else 0,
                format_func=lambda x: freq_labels.get(x, x),
                help="选择检查的频率"
            )
        
        submitted = st.form_submit_button("💾 保存定时设置", type="primary", width="stretch")
        
        if submitted:
            sched_config.enabled = enabled
            sched_config.check_time = check_time.strftime("%H:%M")
            sched_config.frequency = frequency
            
            if scheduler.save_config(sched_config):
                # Also update the notification config
                config.check_frequency = frequency
                config.check_time = check_time.strftime("%H:%M")
                settings.save_notification_config(config)
                
                # Handle scheduler start/stop based on enabled state
                if enabled:
                    # Try to start the scheduler
                    if not scheduler.is_running():
                        if scheduler.start():
                            # Update session state
                            st.session_state.scheduler_instance = scheduler
                            st.session_state.scheduler_initialized = True
                            st.success("✅ 定时设置已保存，调度器已启动")
                        else:
                            st.success("✅ 定时设置已保存（调度器可能已在其他实例运行）")
                    else:
                        st.success("✅ 定时设置已保存")
                else:
                    # Stop the scheduler if it's running
                    if scheduler.is_running():
                        scheduler.stop()
                        st.session_state.scheduler_initialized = False
                        st.session_state.scheduler_instance = None
                    st.success("✅ 定时设置已保存，调度器已停止")
            else:
                st.error("保存失败")
    
    # Help section
    with st.expander("📖 定时检查说明"):
        st.markdown("""
### 工作原理

1. **策略检查**: 在设定时间，系统会自动运行您订阅的所有策略
2. **信号检测**: 比较策略输出的目标仓位与当前仓位
3. **通知发送**: 如果仓位变动超过阈值，通过配置的渠道发送通知

### 推荐设置

| 场景 | 推荐时间 | 说明 |
|------|----------|------|
| 美股投资 | 09:00 - 10:00 | 美股收盘后，有完整的交易数据 |
| 港股投资 | 17:00 - 18:00 | 港股收盘后 |
| 加密货币 | 任意时间 | 24小时交易 |

### 注意事项

- 检查时间基于服务器时区
- 确保应用保持运行状态（或部署到服务器）
- 建议先手动测试确保配置正确
""")


def render_channel_settings(settings, config: NotificationDefaults):
    """Render notification channel settings (email/WeChat)."""
    
    st.subheader("📤 推送渠道设置")
    st.info("💡 配置至少一种推送渠道，以便接收策略信号通知。")
    
    # Check current status
    has_email = bool(config.email_from and config.email_pwd and config.email_to)
    has_serverchan = bool(config.serverchan_key)
    has_pushplus = bool(config.pushplus_token)
    
    # Channel status overview
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if has_email:
            st.success("📧 邮件: 已配置")
        else:
            st.warning("📧 邮件: 未配置")
    
    with col2:
        if has_serverchan:
            st.success("💬 Server酱: 已配置")
        else:
            st.info("💬 Server酱: 未配置")
    
    with col3:
        if has_pushplus:
            st.success("💬 PushPlus: 已配置")
        else:
            st.info("💬 PushPlus: 未配置")
    
    st.divider()
    
    # Email settings
    with st.expander("📧 邮件设置", expanded=not has_email):
        render_email_form(settings, config)
    
    # WeChat settings
    with st.expander("💬 微信推送设置", expanded=not has_serverchan and not has_pushplus):
        render_wechat_form(settings, config)


def render_email_form(settings, config: NotificationDefaults):
    """Render email configuration form."""
    
    st.caption("推荐使用 Gmail，需要开启「应用专用密码」功能")
    
    with st.form("email_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            smtp_server = st.text_input(
                "SMTP 服务器",
                value=config.smtp_server,
                placeholder="smtp.gmail.com"
            )
            
            email_from = st.text_input(
                "发件邮箱",
                value=config.email_from,
                placeholder="your-email@gmail.com"
            )
        
        with col2:
            smtp_port = st.number_input(
                "SMTP 端口",
                value=config.smtp_port,
                min_value=1,
                max_value=65535
            )
            
            email_to = st.text_input(
                "收件邮箱",
                value=config.email_to,
                placeholder="recipient@gmail.com"
            )
        
        email_pwd = st.text_input(
            "邮箱密码 / 应用专用密码",
            value=config.email_pwd,
            type="password",
            help="Gmail 请使用应用专用密码"
        )
        
        col_save, col_test = st.columns(2)
        
        with col_save:
            save_btn = st.form_submit_button("💾 保存邮件设置", width="stretch")
        
        with col_test:
            test_btn = st.form_submit_button("🧪 发送测试邮件", type="primary", width="stretch")
        
        if save_btn:
            config.smtp_server = smtp_server
            config.smtp_port = smtp_port
            config.email_from = email_from
            config.email_to = email_to
            config.email_pwd = email_pwd
            
            if settings.save_notification_config(config):
                st.success("✅ 邮件设置已保存")
            else:
                st.error("保存失败")
        
        if test_btn:
            test_config = NotificationDefaults(
                smtp_server=smtp_server,
                smtp_port=smtp_port,
                email_from=email_from,
                email_to=email_to,
                email_pwd=email_pwd,
            )
            sender = EmailSender(test_config)
            
            if not sender.is_configured():
                st.error("请先填写完整的邮件配置")
            else:
                with st.spinner("正在发送测试邮件..."):
                    result = sender.send_test_email()
                
                if result.success:
                    st.success(f"✅ {result.message}")
                else:
                    st.error(f"❌ {result.message}")
    
    # Gmail guide
    with st.expander("📖 Gmail 设置指南"):
        st.markdown("""
### 如何获取 Gmail 应用专用密码

1. **开启两步验证**: 登录 Google 账户 → 安全性 → 两步验证 → 开启
2. **创建应用专用密码**: 安全性 → 两步验证 → 应用专用密码 → 生成
3. **填入配置**: SMTP 服务器 `smtp.gmail.com`，端口 `587`，密码使用生成的 16 位密码
""")


def render_wechat_form(settings, config: NotificationDefaults):
    """Render WeChat push configuration form."""
    
    st.caption("支持 Server酱 和 PushPlus 两种服务，配置任一即可")
    
    # Server酱
    st.write("**Server酱 (ServerChan)**")
    
    col_key, col_btn = st.columns([4, 1])
    
    with col_key:
        serverchan_key = st.text_input(
            "SendKey",
            value=config.serverchan_key,
            placeholder="SCT...",
            type="password",
            help="在 https://sct.ftqq.com 获取",
            key="serverchan_key_input"
        )
    
    with col_btn:
        st.write("")  # Spacing
        st.write("")
        if st.button("🧪 测试", key="test_serverchan", width="stretch"):
            if not serverchan_key:
                st.error("请先填写 SendKey")
            else:
                test_config = NotificationDefaults(serverchan_key=serverchan_key)
                push = WeChatPush(test_config)
                
                with st.spinner("发送测试消息..."):
                    result = push.send_serverchan("Quant Platform 测试", "这是一条测试消息，如果您收到说明配置成功！")
                
                if result.success:
                    st.success("✅ 发送成功")
                else:
                    st.error(f"❌ {result.message}")
    
    st.divider()
    
    # PushPlus
    st.write("**PushPlus**")
    
    col_token, col_btn2 = st.columns([4, 1])
    
    with col_token:
        pushplus_token = st.text_input(
            "Token",
            value=config.pushplus_token,
            placeholder="xxxxxxxxxxxxxx",
            type="password",
            help="在 https://www.pushplus.plus 获取",
            key="pushplus_token_input"
        )
    
    with col_btn2:
        st.write("")
        st.write("")
        if st.button("🧪 测试", key="test_pushplus", width="stretch"):
            if not pushplus_token:
                st.error("请先填写 Token")
            else:
                test_config = NotificationDefaults(pushplus_token=pushplus_token)
                push = WeChatPush(test_config)
                
                with st.spinner("发送测试消息..."):
                    result = push.send_pushplus("Quant Platform 测试", "这是一条测试消息，如果您收到说明配置成功！")
                
                if result.success:
                    st.success("✅ 发送成功")
                else:
                    st.error(f"❌ {result.message}")
    
    st.divider()
    
    # Save button
    if st.button("💾 保存微信推送设置", type="primary", width="stretch"):
        config.serverchan_key = serverchan_key
        config.pushplus_token = pushplus_token
        
        if settings.save_notification_config(config):
            st.success("✅ 微信推送设置已保存")
        else:
            st.error("保存失败")
    
    # Setup guides
    col_guide1, col_guide2 = st.columns(2)
    
    with col_guide1:
        with st.expander("📖 Server酱 配置指南"):
            st.markdown("""
1. 访问 [sct.ftqq.com](https://sct.ftqq.com)
2. 微信扫码登录
3. 进入「SendKey」页面复制 Key
4. 关注「方糖」公众号接收消息
""")
    
    with col_guide2:
        with st.expander("📖 PushPlus 配置指南"):
            st.markdown("""
1. 访问 [pushplus.plus](https://www.pushplus.plus)
2. 微信扫码登录
3. 在首页获取 Token
4. 自动关注公众号接收消息
""")


def render_test_and_run(settings, config: NotificationDefaults):
    """Render test and manual run section."""
    
    st.subheader("🧪 测试与运行")
    st.info("💡 在这里您可以测试通知渠道或手动运行策略检查。")
    
    # Check channel configuration
    has_email = bool(config.email_from and config.email_pwd and config.email_to)
    has_wechat = bool(config.serverchan_key or config.pushplus_token)
    
    # ========================================
    # Section 1: Quick Channel Test
    # ========================================
    st.write("### 📤 快速测试通知渠道")
    st.caption("测试各通知渠道是否配置正确，发送一条测试消息")
    
    if not has_email and not has_wechat:
        st.warning("⚠️ 请先在「推送渠道」中配置至少一种通知方式")
    else:
        col_test_email, col_test_wechat = st.columns(2)
        
        with col_test_email:
            email_disabled = not has_email
            if st.button(
                "📧 测试邮件通知", 
                width="stretch", 
                disabled=email_disabled,
                help="未配置邮件" if email_disabled else "发送测试邮件"
            ):
                sender = EmailSender(config)
                with st.spinner("正在发送测试邮件..."):
                    result = sender.send_test_email()
                if result.success:
                    st.success(f"✅ 邮件发送成功")
                else:
                    st.error(f"❌ {result.message}")
        
        with col_test_wechat:
            wechat_disabled = not has_wechat
            if st.button(
                "💬 测试微信通知", 
                width="stretch", 
                disabled=wechat_disabled,
                help="未配置微信推送" if wechat_disabled else "发送测试消息到微信"
            ):
                push = WeChatPush(config)
                with st.spinner("正在发送测试消息..."):
                    result = push.send_test()
                if result.success:
                    st.success(f"✅ 微信推送成功 ({result.service})")
                else:
                    st.error(f"❌ {result.message}")
    
    st.divider()
    
    # ========================================
    # Section 2: Strategy Check
    # ========================================
    st.write("### 📊 策略信号检查")
    
    if not config.subscriptions:
        st.warning("⚠️ 请先在「订阅管理」中添加策略订阅")
        return
    
    if not has_email and not has_wechat:
        st.warning("⚠️ 请先配置通知渠道，否则无法发送通知")
    
    # Subscription selection for testing
    st.caption("选择一个订阅，运行策略检查并可选发送通知")
    
    subscription_options = {
        f"{sub.strategy_name} + {sub.portfolio_name}": sub
        for sub in config.subscriptions
    }
    
    selected_sub_name = st.selectbox(
        "选择订阅",
        options=list(subscription_options.keys()),
        key="test_subscription_select",
        label_visibility="collapsed"
    )
    
    if selected_sub_name:
        selected_sub = subscription_options[selected_sub_name]
        
        # Show subscription details in a more compact way
        with st.container():
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("策略", selected_sub.strategy_name)
            with col2:
                st.metric("组合", selected_sub.portfolio_name)
            with col3:
                channels = []
                if selected_sub.notify_email:
                    channels.append("📧")
                if selected_sub.notify_wechat:
                    channels.append("💬")
                st.metric("渠道", " ".join(channels) if channels else "无")
            with col4:
                st.metric("阈值", f"{selected_sub.threshold_pct}%")
        
        # Action buttons
        col_check, col_notify, col_force = st.columns(3)
        
        with col_check:
            if st.button("🔍 仅检查信号", width="stretch", type="secondary", help="运行策略，查看信号但不发送通知"):
                run_strategy_check(config, selected_sub, send_notification=False)
        
        with col_notify:
            if st.button("🚀 检查并通知", width="stretch", type="primary", help="运行策略，如有调仓信号则发送通知"):
                run_strategy_check(config, selected_sub, send_notification=True)
        
        with col_force:
            if st.button("📨 强制发送通知", width="stretch", help="无论是否有调仓信号，都发送一条测试通知"):
                send_test_strategy_notification(config, selected_sub)
    
    st.divider()
    
    # ========================================
    # Section 3: Batch Run
    # ========================================
    st.write("### 🔄 批量运行")
    st.caption("运行所有启用的订阅检查，检测到信号时自动发送通知")
    
    # Show summary
    active_count = sum(1 for s in config.subscriptions if s.enabled)
    st.write(f"共 {len(config.subscriptions)} 个订阅，其中 {active_count} 个已启用")
    
    if st.button("🔄 运行所有订阅检查", width="stretch", type="primary"):
        run_all_subscription_checks(config)


def send_test_strategy_notification(config: NotificationDefaults, subscription: NotificationSubscription):
    """Send a test notification for the subscription regardless of strategy results."""
    
    st.write("**📤 发送测试通知**")
    
    # Create mock data for testing
    test_current_weights = {"TEST_A": 30.0, "TEST_B": 40.0, "TEST_C": 30.0}
    test_target_weights = {"TEST_A": 40.0, "TEST_B": 30.0, "TEST_C": 30.0}
    test_signals = [
        f"📊 这是一条测试通知",
        f"📈 TEST_A: 建议增仓 +10%",
        f"📉 TEST_B: 建议减仓 -10%",
    ]
    
    results = []
    
    # Send email if configured
    if subscription.notify_email and config.email_from and config.email_pwd:
        sender = EmailSender(config)
        with st.spinner("发送邮件..."):
            result = sender.send_strategy_alert(
                strategy_name=f"{subscription.strategy_name} (测试)",
                current_weights=test_current_weights,
                target_weights=test_target_weights,
                reason="这是一条测试通知，用于验证通知渠道是否正常工作",
            )
        results.append(("📧 邮件", result))
    else:
        if subscription.notify_email:
            st.caption("📧 邮件: 未配置或已禁用")
    
    # Send WeChat if configured  
    if subscription.notify_wechat and (config.serverchan_key or config.pushplus_token):
        push = WeChatPush(config)
        with st.spinner("发送微信推送..."):
            result = push.send_strategy_alert(
                strategy_name=f"{subscription.strategy_name} (测试)",
                current_weights=test_current_weights,
                target_weights=test_target_weights,
                reason="这是一条测试通知，用于验证通知渠道是否正常工作",
            )
        results.append(("💬 微信", result))
    else:
        if subscription.notify_wechat:
            st.caption("💬 微信: 未配置或已禁用")
    
    # Show results
    if results:
        for channel, result in results:
            if result.success:
                st.success(f"{channel}: 发送成功")
            else:
                st.error(f"{channel}: {result.message}")
    else:
        st.warning("没有可用的通知渠道，请检查订阅配置和渠道设置")


def run_strategy_check(config: NotificationDefaults, subscription: NotificationSubscription, send_notification: bool = False):
    """Run strategy check for a single subscription."""
    
    from strategy.engine import StrategyEngine
    from portfolio.manager import PortfolioManager
    
    strategy_engine = StrategyEngine()
    portfolio_manager = PortfolioManager()
    
    # Get strategy and portfolio
    strategy = strategy_engine.get(subscription.strategy_name)
    portfolio = portfolio_manager.get(subscription.portfolio_name)
    
    if not strategy:
        st.error(f"❌ 策略 '{subscription.strategy_name}' 不存在")
        return
    
    if not portfolio:
        st.error(f"❌ 组合 '{subscription.portfolio_name}' 不存在")
        return
    
    with st.spinner(f"正在运行策略 '{subscription.strategy_name}'..."):
        # Execute strategy
        result = strategy_engine.execute(
            code=strategy['code'],
            tickers=portfolio.tickers,
            current_weights=portfolio.weights,
        )
    
    if not result.success:
        st.error(f"❌ 策略执行失败: {result.message}")
        return
    
    # Display results
    st.success(f"✅ 策略执行成功 ({result.execution_time:.2f}s)")
    
    # Show signals
    if result.signals:
        with st.expander("📝 策略信号日志", expanded=True):
            for signal in result.signals:
                st.write(signal)
    
    # Compare weights
    current_weights = portfolio.weights
    target_weights = result.target_weights
    
    # Calculate changes
    changes = []
    for ticker in set(list(current_weights.keys()) + list(target_weights.keys())):
        current = current_weights.get(ticker, 0)
        target = target_weights.get(ticker, 0)
        change = target - current
        
        if abs(change) >= subscription.threshold_pct:
            changes.append({
                'ticker': ticker,
                'current': current,
                'target': target,
                'change': change,
            })
    
    if changes:
        st.write("**📊 建议调仓 (超过阈值的变动)**")
        
        # Create a nice table
        import pandas as pd
        df = pd.DataFrame(changes)
        df.columns = ['标的', '当前仓位 (%)', '目标仓位 (%)', '变动 (%)']
        
        # Format with colors
        def highlight_change(val):
            if val > 0:
                return 'color: green'
            elif val < 0:
                return 'color: red'
            return ''
        
        # Compatible with both old pandas (applymap) and new pandas 2.1+ (map)
        styler = df.style
        style_func = getattr(styler, 'map', None) or styler.applymap
        styled_df = style_func(highlight_change, subset=['变动 (%)'])
        st.dataframe(styled_df, width="stretch", hide_index=True)
        
        # Send notification if requested
        if send_notification and changes:
            send_strategy_notification(config, subscription, current_weights, target_weights, result.signals)
    else:
        st.info(f"ℹ️ 无需调仓 (所有变动均小于 {subscription.threshold_pct}% 阈值)")
        
        if send_notification:
            st.caption("由于无显著变动，未发送通知")


def send_strategy_notification(
    config: NotificationDefaults,
    subscription: NotificationSubscription,
    current_weights: dict,
    target_weights: dict,
    signals: list
):
    """Send notification for strategy signals."""
    
    results = []
    
    # Prepare reason text from signals
    reason = "\n".join(signals[:5]) if signals else "策略检测到调仓信号"
    
    # Send email
    if subscription.notify_email and config.email_from and config.email_pwd:
        sender = EmailSender(config)
        result = sender.send_strategy_alert(
            strategy_name=subscription.strategy_name,
            current_weights=current_weights,
            target_weights=target_weights,
            reason=reason,
        )
        results.append(("📧 邮件", result))
    
    # Send WeChat
    if subscription.notify_wechat and (config.serverchan_key or config.pushplus_token):
        push = WeChatPush(config)
        result = push.send_strategy_alert(
            strategy_name=subscription.strategy_name,
            current_weights=current_weights,
            target_weights=target_weights,
            reason=reason,
        )
        results.append(("💬 微信", result))
    
    # Show results
    st.write("**📤 通知发送结果**")
    for channel, result in results:
        if result.success:
            st.success(f"{channel}: 发送成功")
        else:
            st.error(f"{channel}: {result.message}")


def run_all_subscription_checks(config: NotificationDefaults):
    """Run checks for all active subscriptions."""
    
    from strategy.engine import StrategyEngine
    from portfolio.manager import PortfolioManager
    
    strategy_engine = StrategyEngine()
    portfolio_manager = PortfolioManager()
    
    active_subs = [s for s in config.subscriptions if s.enabled]
    
    if not active_subs:
        st.warning("没有启用的订阅")
        return
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    results_container = st.container()
    
    for i, sub in enumerate(active_subs):
        progress = (i + 1) / len(active_subs)
        progress_bar.progress(progress)
        status_text.text(f"正在检查: {sub.strategy_name}...")
        
        strategy = strategy_engine.get(sub.strategy_name)
        portfolio = portfolio_manager.get(sub.portfolio_name)
        
        if not strategy or not portfolio:
            with results_container:
                st.warning(f"⚠️ {sub.strategy_name}: 策略或组合不存在")
            continue
        
        # Execute strategy（透传订阅级归一化开关）
        result = strategy_engine.execute(
            code=strategy['code'],
            tickers=portfolio.tickers,
            current_weights=portfolio.weights,
            normalize_weights=sub.normalize_weights,
        )
        
        if not result.success:
            with results_container:
                st.error(f"❌ {sub.strategy_name}: {result.message}")
            continue
        
        # Check for significant changes
        changes = []
        for ticker in set(list(portfolio.weights.keys()) + list(result.target_weights.keys())):
            current = portfolio.weights.get(ticker, 0)
            target = result.target_weights.get(ticker, 0)
            change = abs(target - current)
            
            if change >= sub.threshold_pct:
                changes.append(ticker)
        
        with results_container:
            if changes:
                st.success(f"✅ {sub.strategy_name}: 检测到 {len(changes)} 个标的需要调仓")
                
                # Send notifications
                reason = "\n".join(result.signals[:3]) if result.signals else "策略信号触发"
                
                if sub.notify_email and config.email_from and config.email_pwd:
                    sender = EmailSender(config)
                    email_result = sender.send_strategy_alert(
                        strategy_name=sub.strategy_name,
                        current_weights=portfolio.weights,
                        target_weights=result.target_weights,
                        reason=reason,
                    )
                    if email_result.success:
                        st.caption("  📧 邮件已发送")
                
                if sub.notify_wechat and (config.serverchan_key or config.pushplus_token):
                    push = WeChatPush(config)
                    wechat_result = push.send_strategy_alert(
                        strategy_name=sub.strategy_name,
                        current_weights=portfolio.weights,
                        target_weights=result.target_weights,
                        reason=reason,
                    )
                    if wechat_result.success:
                        st.caption("  💬 微信已发送")
            else:
                st.info(f"ℹ️ {sub.strategy_name}: 无显著变动")
    
    progress_bar.progress(1.0)
    status_text.text("✅ 检查完成")
