"""对 AI 友好的策略开发规范（可直接复制粘贴给 AI，让其按规范输出策略代码）。"""

STRATEGY_SPEC = """# OKX 量化交易控制台 · 策略开发规范

你正在为「OKX 量化交易控制台」（Python + Streamlit）编写一个交易策略。请严格遵循本规范。

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
