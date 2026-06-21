# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

OKX 加密货币量化交易控制台：**React + Vite 前端 + FastAPI REST API**，支持策略编写、回测可视化、策略组合、多币策略、实盘部署与监控。所有业务逻辑在 `core/`（纯 Python，可独立测试、被 API 调用），`web/` 与 `api/` 是薄壳。

## 常用命令

```bash
# 安装依赖
pip install -r requirements.txt                  # 后端
cd web && npm install && cd ..                    # 前端（首次）

# 一键启动（后端 API :8787 + 前端 :5173）
./run_dev.sh                                       # 前端 http://localhost:5173

# 单独启动
python api_server.py                               # API http://127.0.0.1:8787/docs
cd web && npm run dev                              # 前端 Vite dev server
cd web && npm run build                            # 前端生产构建到 web/dist

# 测试
pytest
pytest tests/test_xxx.py::test_name                # 跑单个测试

# 手动启动一个实盘 daemon（一般通过 UI/API，此处仅供调试）
python scripts/trader_daemon.py --job runtime/jobs/<job_id>.json
```

配置：`cp .env.example .env` 后填写 `OKX_API_KEY/SECRET/PASSPHRASE` 与 `API_TOKEN`。仓库自带一份模拟盘 `.env`（已 gitignore）。前端在侧边栏底部填 API Token 解锁写操作。

## 核心架构：三层解耦

贯穿全项目的契约是 **策略只产出 `signal` 列**（`1` 做多 / `-1` 做空 / `0` 空仓），下游组合与执行统一消费，互不感知。理解这一点就理解了大半代码。

**四种「信号来源」，都满足 `generate_signals(...)` 接口，下游可互换：**
- **单策略** `core/strategy/base.py::Strategy` — `generate_signals(df) -> df(含 signal)`。
- **Ensemble** `core/strategy/ensemble.py` — 多个单策略的 signal 按规则（vote/majority/and/or/weighted）在**信号层**合成，对外像一个策略。
- **Portfolio** `core/strategy/portfolio.py` — 多策略在**资金/权益层**合成（各策略独立持仓、按权重切分资金、权益相加），与 Ensemble 的区别在于合成维度。
- **多币策略** `core/strategy/multi_base.py::MultiStrategy` — `generate_signals(ctx) -> {symbol: df}`，接收 `Context`（多 symbol 对齐数据 + 特征注册表）。回测由 `core/backtest/multi.py` 按资金槽模型把资金分配到各 symbol，各跑单币引擎再合成组合权益。

**回测引擎** `core/backtest/engine.py`：逐 K 线 mark-to-market（每根 K 线按 close 估算未实现盈亏、记录连续权益曲线），含手续费/滑点。仓位模型为**复利**：每次用 `cash * position_ratio * leverage` 作名义价值开仓，盈亏计入 cash。注意：**默认不建模爆仓**，高杠杆回测结果偏乐观。

**实盘进程模型**（`core/live/runtime.py` + `scripts/trader_daemon.py`）：
- `start_job` 写 job 配置文件 → `subprocess.Popen(..., start_new_session=True)` 拉起独立 daemon 进程（脱离父进程组，关浏览器/重启控制台不死）。
- daemon 每个周期（默认 3600s）调一次 `core/live/trader.py::run_once`：拉最新 K 线 → 取信号 → 对齐当前持仓 → 平旧仓/开新仓市价单 → 写 state 文件 + 追加 JSONL 日志。
- 每轮 `try/except`：出错只写 state 的 error 字段、不崩溃。`stop_job` 先 SIGTERM 等待 5s，超时 SIGKILL。
- UI 监控页与 REST API 都是通过轮询 `runtime/` 下的 job/state/log 文件读取状态（无 IPC、无数据库）。
- 模拟盘/实盘切换由 job 配置的 `is_demo` 决定，传给 `ccxt.set_sandbox_mode`（`core/live/exchange.py`）。

## 关键约定（容易踩坑）

- **符号/周期格式**（`core/data/symbols.py`）：内部统一用 **OKX 格式**——合约 symbol `BTC-USDT-SWAP`、现货 `BTC-USDT`；bar 用大写后缀 `1H`/`4H`/`1D`（OKX REST 要求）。只有调 ccxt（实盘下单/查持仓）时才转成小写 `1h`/`4h`/`1d`，用 `okx_to_ccxt()` / `okx_to_ccxt_tf()`。
- **路径不依赖 cwd**：所有路径以 `core/utils/config.py` 推导出的项目根 `ROOT` 为基准（该文件位于 `core/utils/`，上溯两级）。入口脚本（`api_server.py`、`trader_daemon.py`）都先 `sys.path.insert(0, ROOT)`。
- **运行时目录**：`cache/`（K 线 parquet 缓存 + 交易对列表 JSON 缓存）、`runtime/jobs|state|logs/`（实盘作业）均已被 gitignore（保留 `.gitkeep`）。
- **Python 注解兼容性**：部署环境可能仍跑 `Python 3.9`。修改 `api/*.py`、入口脚本或其他导入时就会求值的模块时，不要假设 `X | None` / `A | B` 一定安全；优先保留 `from __future__ import annotations`，或改用 `Optional[...]` / `Union[...]`，避免启动阶段直接报 `TypeError`。

## 策略注册表与「保存即生效」

`core/strategy/registry.py::StrategyRegistry` 是单例式类注册表（类方法 + 类变量）：
- `discover_builtin()` 扫描 `core/strategy/builtin/` 包（含 `multi/` 子包）。
- `discover_dir(strategies/)` 扫描用户 `.py`，**每次重新 exec 文件**（`force_reload` 先卸载上次注册的策略），实现策略实验室页编辑后「保存即注册即用」。`_` 开头或 `.example` 结尾的文件被跳过。
- `discover_all()` 二者都跑。**注意**：注册表是进程内类变量状态，新文件需重新调用 `discover_all()` 才可见——API 路由与 UI 页每次都会调用它。

## 写策略的要点

继承 `Strategy`（或 `MultiStrategy`），用类属性 `Param(...)` 声明参数（元类 `_StrategyMeta` 自动收集到 `_param_list`，前端据此渲染控件：给 `min/max/step`→滑块、给 `options`→下拉、仅 `default`→输入框）。硬性约束：**先 `df.copy()`、返回行数与输入一致、`signal` 必须是无 NaN 的 int**。新增策略只需把 `.py` 放进 `strategies/`，无需改任何配置。

`core/strategy/spec.py` 导出两份可直接喂给 AI 的策略开发规范：`STRATEGY_SPEC`（单币）与 `MULTI_STRATEGY_SPEC`（多币），含模板 + signal 语义 + 硬性要求。前端「策略实验室」页可一键复制/下载，写策略或让 AI 写策略时以此为权威。

## API 层

`api/`（FastAPI，绑 `127.0.0.1`）：`routes_monitor.py`（GET，公开）与 `routes_control.py`（POST/DELETE，全部需 `X-API-Token` 头，由 `api/__init__.py::verify_token` 校验）。控制层是对 `core/` 能力的薄封装（触发回测、启停实盘、网格搜索、多币回测、策略文件 CRUD、.env 编辑、缓存清理）。回测结果落 `backtests` 表，由 `GET /api/backtests/{id}` 读取。

完整 REST API 规范见 `GET /api/api_spec`（源码 `api/spec.py`）。关键注意：`balance` 是可用余额（free），`equity` 才是总权益（对应 OKX App 显示的账户权益）。

## React 前端

`web/src/pages/*.tsx` 各自是一个导航页（`web/src/App.tsx` 用 `react-router` 聚合）。现有页面：`Dashboard`（仪表盘）、`Explore`（策略探索 · 模板调参 + 实时回测）、`Compose`（策略组合 · 拖拽编排）、`Multi`（多币策略 · 持仓热力图）、`Lab`（策略实验室 · 代码编辑器 + 网格搜索）、`Deploy`（实盘部署 + 监控）、`Settings`（设置）。页面都是 `core/` 经 `api/` 的薄壳——绘图/交互在 `web/`，逻辑放 `core/`。新增页面需在 `web/src/App.tsx` 的 `nav` 列表与 `<Routes>` 里登记。共用组件在 `web/src/components/`，API 客户端在 `web/src/api/client.ts`，类型契约在 `web/src/api/types.ts`（与 `api/schemas.py` + `core/strategy/node.py` 对齐）。
