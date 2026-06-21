# OKX 量化交易控制台

一个加密货币量化交易控制台（FastAPI 后端 + React 前端）：自由选择/组合策略、即时回测可视化、用 Python 写策略直接看效果、一键后台部署实盘（模拟/真实盘可切），并开放 REST API 供外部脚本/agent 监控控制。

核心是 **「信号生成 ⇄ 组合 ⇄ 执行」三层解耦**：策略只产出 `signal` 列（1 做多 / -1 做空 / 0 空仓），组合（Ensemble/Portfolio）与执行（回测/实盘）在下游统一消费。

## ✨ 功能

- **📊 数据与回测**：选品种/周期/天数 → 选策略调参 → 一键回测 → 全套 Plotly 可视化（K线+成交量+指标+买卖点、权益曲线、回撤、月度收益热力图、收益分布、交易明细、12 项指标卡片）。
- **🧩 策略组合**：
  - *Ensemble*：多策略信号按 投票/多数/AND/OR/加权 合成「一个组合策略」。
  - *Portfolio*：每策略独立运行、按资金比例切分，合成组合权益。
- **🛠️ 策略实验室**：浏览器内代码编辑器写 Python 策略，**保存即注册即用**；参数网格搜索找最优组合。
- **🚀 实盘部署**：选模拟/真实盘 + 策略 + 杠杆，一键启动**后台 daemon**（独立进程，关闭浏览器仍运行），真实/模拟盘可切。
- **📉 实盘监控**：实时持仓 / PnL / 余额 / 事件日志（自动刷新）。
- **🔌 REST API**：监控（行情/策略/任务/状态）+ 控制（回测/启停实盘），仅本地 + token。

## 🚀 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt          # 后端
cd web && npm install && cd ..            # 前端（首次）

# 2. 配置 API key（复制模板并填写）
cp .env.example .env
#   编辑 .env 填入 OKX_API_KEY / OKX_API_SECRET / OKX_API_PASSPHRASE

# 3. 一键启动（后端 API + 前端）
./run_dev.sh
#   前端：http://localhost:5173
#   API 文档：http://127.0.0.1:8787/docs
```

> 仓库自带 `.env` 含一组**模拟盘** key 便于开箱体验（已 gitignore）。**该 key 此前在原项目以明文进入过 git，用于真实盘前请务必到 OKX 后台重置。**

> 也可以单独启动后端：`python api_server.py`；前端单独：`cd web && npm run dev`。

## 🧠 写一个策略

策略继承 `Strategy`，声明参数（UI 自动生成控件），实现 `generate_signals` 输出 `signal` 列。可放在 `strategies/` 目录（自动发现），或在「策略实验室」页在线编辑保存。

```python
# strategies/my_strategy.py
from core.strategy.base import Strategy, Param
import pandas as pd

class MyStrategy(Strategy):
    name = "my_strategy"
    display_name = "我的策略"
    description = "示例：均线 + 成交量过滤"
    period = Param("period", 20, 5, 100, 1, label="均线周期")

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        ma = df["close"].rolling(int(self.period)).mean()
        sig = pd.Series(0, index=df.index)
        sig[(df["close"] > ma)] = 1
        sig[(df["close"] < ma)] = -1
        df["signal"] = sig.astype(int)
        df["trade"] = df["signal"].diff().fillna(0).astype(int)
        return df
```

内置策略：`ma_cross`（MA 双线交叉）、`rsi`（RSI 超买超卖）、`bollinger`（布林带）、`dual_thrust`（Dual Thrust 突破）。多币内置：动量轮动 / 等权持有 / 相对强弱 / 跨币回归。

> 「策略实验室」页内置 **AI 策略开发规范**（单币/多币），一键复制或下载 `.md` 喂给 AI（Claude / ChatGPT 等），让它按规范输出可直接保存使用的策略代码。

## 📁 架构

```
web/      React + Vite + Tailwind 前端（薄壳，调 /api）
api/      FastAPI REST 层（监控 GET 公开 / 控制 POST 需 token）
core/     纯 Python 业务逻辑（可独立测试、被 API 调用）
  strategy/   Strategy 基类、注册表、Ensemble、Portfolio、内置策略、多币
  data/       OKX K线拉取 + K线 parquet/交易对 JSON 缓存 + symbol/周期转换
  backtest/   逐K线 mark-to-market 引擎 + 指标 + 网格搜索
  live/       ccxt 交易所封装 + 单轮执行 + job/state 运行时
scripts/  trader_daemon.py（独立后台进程入口）
```

数据流：`拉数据 → 策略 generate_signals → [Ensemble/Portfolio] → 回测引擎 → 可视化`；实盘：`部署表单 → start_job 写 job 文件 → subprocess 起 daemon → 循环(拉数据/信号/对齐持仓/下单/写 state) → 监控页轮询`。

## 🔌 REST API 速查

```bash
TOKEN=你的_API_TOKEN   # 见 .env

# 监控（公开）
curl http://127.0.0.1:8787/api/health
curl http://127.0.0.1:8787/api/strategies
curl http://127.0.0.1:8787/api/market/BTC-USDT-SWAP?bar=1H&days=7
curl http://127.0.0.1:8787/api/jobs

# 控制（需 token）
curl -X POST http://127.0.0.1:8787/api/backtest \
  -H "X-API-Token: $TOKEN" -H "Content-Type: application/json" \
  -d '{"strategy":"ma_cross","params":{"ma_fast":20,"ma_slow":60},"symbol":"BTC-USDT-SWAP","days":120}'
curl "http://127.0.0.1:8787/api/balance?is_demo=true" -H "X-API-Token: $TOKEN"
curl -X POST http://127.0.0.1:8787/api/jobs \
  -H "X-API-Token: $TOKEN" -H "Content-Type: application/json" \
  -d '{"is_demo":true,"strategy":"ma_cross","symbol":"BTC-USDT-SWAP"}'
curl -X DELETE http://127.0.0.1:8787/api/jobs/<job_id> -H "X-API-Token: $TOKEN"
```

## ⚠️ 安全与风险

- **API key** 存本地 `.env`（已 gitignore），切勿提交；原项目遗留 key 请重置。
- **REST API** 仅监听 `127.0.0.1`，控制类接口需 `X-API-Token`。
- **策略代码**拥有完整 Python 权限（与本程序相同），仅运行可信代码。
- **实盘有风险**：回测不等于实盘；真实盘请从最小仓位、模拟盘验证开始。回测引擎默认未建模爆仓，高杠杆结果需谨慎。
