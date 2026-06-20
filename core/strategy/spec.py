"""对 AI 友好的策略开发规范（可直接复制粘贴给 AI，让其按规范输出策略代码）。

导出两份规范：STRATEGY_SPEC（单币）与 MULTI_STRATEGY_SPEC（多币）。"""

STRATEGY_SPEC = """# OKX 量化交易控制台 · 单币策略开发规范

你正在为「OKX 量化交易控制台」（FastAPI + React 控制台）编写一个交易策略。请严格遵循本规范。

## 你的任务
编写一个 Python 类，继承 `Strategy`，声明参数并实现 `generate_signals`，根据 K 线数据输出做多/做空/空仓信号。输出要能直接保存为 `strategies/<name>.py` 并被系统自动加载使用。

## 完整模板（照此结构写）

```python
from core.strategy.base import Strategy, Param
import pandas as pd


class XxxStrategy(Strategy):
    # —— 元数据（必填）——
    name = "xxx_strategy"          # 唯一标识，必须是合法 Python 标识符，建议与文件名一致
    display_name = "策略中文名"
    description = "一句话策略说明"
    side_mode = "long_short"       # "long_short"(多空) 或 "long_only"(仅做多)

    # —— 参数声明（可选；UI 会据此自动生成控件）——
    fast = Param("fast", 20, 2, 200, 1, label="快线周期")          # min/max/step → 滑块
    threshold = Param("threshold", 0.5, 0.0, 1.0, 0.05, label="阈值")  # 浮点滑块
    use_filter = Param("use_filter", True, options=[True, False], label="启用过滤")  # options → 下拉框
    note = Param("note", "默认", label="备注")                     # 仅 default → 文本/数字框

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        \"\"\"
        输入：OHLCV DataFrame，列 = [ts, open, high, low, close, vol]
              ts 为 pandas Timestamp；open/high/low/close/vol 为 float；按时间升序。
        输出：同一个 df（务必先 copy），新增 'signal' 列：
                1  = 做多（目标持多）
               -1  = 做空（目标持空）
                0  = 空仓
        约束：返回行数必须与输入一致；signal 必须是 int，不得有 NaN。
        \"\"\"
        df = df.copy()
        close = df["close"]

        # —— 你的指标与逻辑 ——
        ma_fast = close.rolling(int(self.fast)).mean()
        ma_slow = close.rolling(int(self.fast) * 3).mean()

        # —— 生成 signal ——
        raw = pd.Series(0, index=df.index)
        raw[ma_fast > ma_slow] = 1
        if self.side_mode != "long_only":
            raw[ma_fast < ma_slow] = -1
        # 状态保持：持有上一个信号直到反向信号（可选写法）
        df["signal"] = raw.where(raw != 0).ffill().fillna(0).astype(int)
        df["trade"] = df["signal"].diff().fillna(0).astype(int)  # 可选：换仓标记
        return df
```

## Param 参数声明（决定 UI 自动生成的控件）
`Param(name, default, min=None, max=None, step=None, options=None, label="", help="")`
- 给 `min/max/step` → 渲染**滑块**
- 给 `options`（列表）→ 渲染**下拉框**
- 只给 `default` → 渲染**数字/文本输入框**
- 在 `generate_signals` 中通过 `self.<name>` 读取当前值。

## signal 语义（关键）
`signal` 表示**目标持仓方向**，不是"即时触发"。回测/实盘引擎比较 signal 与当前持仓，方向不同才换仓。
- **持续持仓型**（如趋势跟随）：条件满足期间 signal 持续为 1 或 -1。
- **触发型**：用状态保持——触发后持有直到反向信号：
  `df["signal"] = raw.where(raw != 0).ffill().fillna(0).astype(int)`

## 可用环境
- 可直接 `import pandas as pd`、`import numpy as np`。
- 可读取 df 全部列：ts/open/high/low/close/vol。
- 可新增任意中间列（如 ma、rsi、bb_upper）；**数值列会被自动叠加到 K 线图作为指标**。

## 硬性要求（违反会导致报错或回测失真）
1. 必须先 `df = df.copy()`，不要就地修改输入。
2. 返回行数必须与输入一致（不要裁剪/重排）。
3. `signal` 必须是 int（1/-1/0），整列不得有 NaN（用 `.fillna(0)`）。
4. 处理好指标初期的 NaN（`rolling` 等会让前若干行为 NaN，填充为 0/空仓）。
5. `name` 必须是合法 Python 标识符且全局唯一；类名用驼峰，name 用下划线小写。
6. 代码拥有完整 Python 权限——只写策略逻辑，不要做文件/网络等副作用操作。

## 输出格式
直接输出**完整的、可保存为 `strategies/<name>.py` 的 Python 文件**（含 import、类定义、generate_signals 实现）。代码后可附不超过 3 行的简短说明（思路/参数含义）。不要输出多余解释或 markdown 标题包裹代码。
"""


MULTI_STRATEGY_SPEC = """# OKX 量化交易控制台 · 多币策略开发规范

你正在为「OKX 量化交易控制台」（FastAPI + React 控制台）编写一个**多币策略**。多币策略同时接收多个交易品种的对齐数据，按截面信息（排名/相对强弱/相关性等）分配持仓，适合轮动、配对、篮子交易等场景。请严格遵循本规范。

## 你的任务
编写一个 Python 类，继承 `MultiStrategy`（注意：**不是** `Strategy`），声明参数并实现 `generate_signals(ctx)`，根据多币 K 线数据为每个品种输出做多/做空/空仓信号。输出要能直接保存为 `strategies/<name>.py` 并被系统自动加载使用。

## 与单币策略的区别
- 基类是 `MultiStrategy`，不是 `Strategy`（二者平行，不继承）。
- `generate_signals(self, ctx)` 接收 `Context` 对象（多 symbol 对齐数据 + 特征注册表），而不是单个 DataFrame。
- 返回 `dict[str, pd.DataFrame]`（`{symbol: 含 signal 列的 df}`），**不是**单个 df。
- 参数声明、UI 控件渲染、注册发现机制与单币完全一致（复用同一套 `Param` 元类）。

## 完整模板（照此结构写）

```python
from core.strategy.multi_base import MultiStrategy
from core.strategy.base import Param
from core.strategy.context import Context, feature
import pandas as pd
import numpy as np


class XxxRotation(MultiStrategy):
    # —— 元数据（必填）——
    name = "xxx_rotation"          # 唯一标识，必须是合法 Python 标识符，建议与文件名一致
    display_name = "策略中文名"
    description = "一句话策略说明"
    universe = []                  # 可选：限定品种池（空列表 = 用户在 UI 选中的全部币种）

    # —— 参数声明（可选；UI 会据此自动生成控件）——
    period = Param("period", 24, 4, 120, 2, label="动量回看周期")          # 滑块
    top_k = Param("top_k", 1, 1, 10, 1, label="持有数量 Top-K")            # 整数滑块
    rebalance = Param("rebalance", 24, 1, 96, 1, label="再平衡间隔(根)")    # 滑块
    mode = Param("mode", "top", options=["top", "bottom"], label="选强/选弱")  # 下拉框

    def generate_signals(self, ctx: Context) -> dict[str, pd.DataFrame]:
        \"\"\"
        输入：ctx —— 多币上下文（见下方 Context API）。
        输出：{symbol: df}；每个 df 必须是 ctx.data[symbol].copy()，新增 'signal' 列：
                1  = 做多（目标持多）
               -1  = 做空（目标持空）
                0  = 空仓
        约束：返回的 dict 必须覆盖 ctx.symbols 的每一个；每个 df 行数与 ctx.data[symbol] 一致；
              signal 必须是 int，不得有 NaN。
        \"\"\"
        symbols = ctx.symbols
        period = int(self.period)
        reb = int(self.rebalance)
        k = int(self.top_k)

        # —— 截面特征：time×symbol 矩阵 ——
        mom = ctx.cross_section("momentum", period=period)
        rank = mom.rank(axis=1, method="min")   # 每行内排名：1=最弱, n=最强

        out: dict[str, pd.DataFrame] = {}
        sym_idx = {s: i for i, s in enumerate(symbols)}
        last_pick: set[str] = set()
        n = len(symbols)

        for s in symbols:
            df = ctx.data[s].copy()
            r = rank[s]
            sig = pd.Series(0, index=df.index)
            # 示例：每隔 reb 根，选截面最强的 k 个持有（再平衡）
            for i in range(n):
                if i % reb == 0:
                    row = mom.iloc[i].dropna()
                    picks = row.nlargest(min(k, len(row))).index if len(row) > 0 else []
                    last_pick = set(picks)
                if s in last_pick:
                    sig.iloc[i] = 1
            df["signal"] = sig.astype(int)
            df["trade"] = df["signal"].diff().fillna(0).astype(int)  # 可选：换仓标记
            out[s] = df
        return out
```

## Context API（核心，多币策略的全部输入）
```python
ctx.data           # dict[str, DataFrame]：各 symbol 的 OHLCV（列 ts/open/high/low/close/vol），已按 ts 对齐（同长度同时间轴）
ctx.symbols        # list[str]：品种列表，= list(ctx.data.keys())
ctx.bar            # str：周期，如 "1H"
ctx.ts()           # pd.Series：公共时间轴（各 symbol 共享）

ctx.feature(name, symbol, **kw)    # 单 symbol 的某个特征 → pd.Series（按位置对齐 data[symbol]）
ctx.cross_section(name, **kw)      # time×symbol 的截面 DataFrame → pd.DataFrame（轮动/排名用这个）
```

## 内置特征（直接用，name 传给 ctx.feature / ctx.cross_section）
| name | 关键参数 | 含义 |
|---|---|---|
| `"momentum"` | `period=20` | 过去 period 根收益率（动量） |
| `"returns"`  | `period=1`  | 单期收益率 |
| `"volatility"` | `period=20` | 收益率波动率 |
| `"rsi"` | `period=14` | RSI 指标 |

所有特征带缓存（同 symbol 同参数只算一次），跨 symbol 在 `cross_section` 中也已对齐长度。

## 自定义特征（按需扩展，开闭原则）
在策略文件里用 `@feature` 注册一个特征函数，框架会自动发现并可通过 `ctx.feature(name, ...)` 调用：
```python
from core.strategy.context import feature, Context
import pandas as pd

@feature("my_spread")
def _my_spread(ctx: Context, symbol: str, period: int = 20) -> pd.Series:
    \"\"\"签名固定：(ctx, symbol, **kwargs) -> pd.Series（长度与 ctx.data[symbol] 相同）。\"\"\"
    close = ctx.data[symbol]["close"]
    ma = close.rolling(period).mean()
    return (close - ma) / ma
```
之后 `ctx.cross_section("my_spread", period=20)` 即可拿到 time×symbol 的偏离度矩阵。

## Param 参数声明（与单币完全一致）
`Param(name, default, min=None, max=None, step=None, options=None, label="", help="")`
- 给 `min/max/step` → **滑块**
- 给 `options`（列表）→ **下拉框**
- 只给 `default` → **数字/文本输入框**
- 在 `generate_signals` 中通过 `self.<name>` 读取当前值。

## signal 语义（与单币一致）
`signal` 表示**目标持仓方向**。回测引擎比较 signal 与当前持仓，方向不同才换仓。
- 多币场景通常**只在 0 和 1 之间切换**（轮动/择优），做空需谨慎、品种数足够时再用。
- 截面排名后，把「被选中」的 symbol 在对应时刻 signal 置 1，其余置 0。
- 触发型/再平衡型：可用 `for i in range(n)` + `i % rebalance == 0` 控制再平衡节奏（见模板）。

## 资金分配与回测（了解即可，影响你对仓位大小的预期）
多币回测采用**资金槽模型**：总资金按权重切分给每个 symbol，各 symbol 在自己的资金槽内独立
跑单币引擎，再把权益曲线相加合成组合权益。默认等权 `1/N`。策略只决定 **方向（signal）**，
不决定具体仓位金额——权重由回测/实盘配置层处理。

## 可用环境
- 可直接 `import pandas as pd`、`import numpy as np`。
- 每个 symbol 的 df 列：ts/open/high/low/close/vol（ts 为 pandas Timestamp）。
- 可新增任意中间列；数值列会按 symbol 分别叠加到 K 线图。

## 硬性要求（违反会导致报错或回测失真）
1. 必须继承 `MultiStrategy`，**不要**继承 `Strategy`。
2. 每个 symbol 的 df 必须**先 copy**（`ctx.data[s].copy()`），不要就地修改输入。
3. 返回的 dict **必须覆盖 ctx.symbols 的每一个 symbol**（不能漏、不能多）。
4. 每个 df 的行数必须与 `ctx.data[symbol]` 一致（不要裁剪/重排）。
5. 每个 `signal` 列必须是 int（1/-1/0），整列不得有 NaN（用 `.fillna(0)`）。
6. 处理好指标初期的 NaN（`rolling`/`pct_change` 前若干行为 NaN，截面排名会传播 NaN，必要时 `dropna`）。
7. `name` 必须是合法 Python 标识符且全局唯一；类名用驼峰，name 用下划线小写。
8. 代码拥有完整 Python 权限——只写策略逻辑，不要做文件/网络等副作用操作。

## 典型模式速查
- **动量轮动（Top-K）**：`ctx.cross_section("momentum", period=...)` → 每行 `nlargest(k)` 选标的 → signal=1。
- **截面反转**：`rank = mom.rank(axis=1)` → 最弱（rank=1）做多、最强（rank=n）做空。
- **相对强弱**：固定基准 symbol（如 BTC），`mom[s] > mom[bench]` 时持有该 symbol。
- **等权持有**：全部 symbol signal 恒为 1（基准用）。

## 输出格式
直接输出**完整的、可保存为 `strategies/<name>.py` 的 Python 文件**（含 import、类定义、generate_signals 实现）。代码后可附不超过 3 行的简短说明（思路/参数含义）。不要输出多余解释或 markdown 标题包裹代码。
"""
