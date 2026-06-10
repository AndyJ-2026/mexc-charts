# mexc-charts

MEXC Launchpad 认购监控自动化。GitHub Actions 每天 9:00 / 16:00 / 20:00 (北京时间) 跑一次 `monitor.py`，拉取认购数据，生成图表，提交回本仓库，并通过 Lark Webhook 推送卡片。

- 配置：`monitor.py` 顶部 `PROJECT_ID` / `PROJECT_NAME`
- Secret：`LARK_WEBHOOK`（仓库 Settings → Secrets and variables → Actions）
- 图表 URL：`https://raw.githubusercontent.com/AndyJ-2026/mexc-charts/main/chart.png`
- 历史数据：`data.json`
- 手动触发：Actions 页面 → MEXC Launchpad Monitor → Run workflow
