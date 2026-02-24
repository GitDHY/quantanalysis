# Quant Platform 📈

量化投资管理平台 - 支持投资组合管理、策略编写、历史回测和调仓提醒。

## 功能特性

- 📊 **投资组合管理** - 创建和管理多个投资组合
- 🧠 **策略编辑** - 使用 Python 编写动态调仓策略
- 📈 **回测分析** - 历史数据回测，支持交易成本和滑点
- 🔔 **通知提醒** - 邮件/微信调仓提醒

## 支持市场

- 🇺🇸 美股 (NYSE, NASDAQ)
- 🇸🇬 新加坡 (SGX)

## 本地运行

```bash
# 安装依赖
pip install -r requirements.txt

# 运行应用
streamlit run app.py
```

## 部署到 Streamlit Cloud

### 1. 准备 GitHub 仓库

```bash
# 初始化 Git 仓库（如果还没有）
git init
git add .
git commit -m "Initial commit"

# 推送到 GitHub
git remote add origin https://github.com/YOUR_USERNAME/quant_platform.git
git push -u origin main
```

### 2. 部署到 Streamlit Cloud

1. 访问 [share.streamlit.io](https://share.streamlit.io)
2. 使用 GitHub 账号登录
3. 点击 "New app"
4. 选择仓库、分支和主文件 (`app.py`)
5. 点击 "Deploy"

### 3. 配置 Secrets（可选）

如果需要使用邮件/微信通知功能，在 Streamlit Cloud 中：

1. 进入应用设置 (Settings)
2. 找到 "Secrets" 部分
3. 添加以下配置：

```toml
[email]
smtp_server = "smtp.gmail.com"
smtp_port = 587
email_from = "your_email@gmail.com"
email_to = "your_email@gmail.com"
email_pwd = "your_app_password"

[wechat]
serverchan_key = "your_serverchan_key"
```

## 数据说明

- 首次运行时，应用会自动创建示例数据
- 价格数据来自 Yahoo Finance，会自动缓存
- 所有数据存储在 `data/` 目录下

## 技术栈

- **前端**: Streamlit
- **数据**: yfinance, pandas
- **可视化**: Plotly
- **策略沙箱**: RestrictedPython

## License

MIT
